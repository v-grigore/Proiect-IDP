"""
User Profile Service - Managementul profilurilor și rolurilor utilizatorilor
Integrare cu Keycloak pentru SSO
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint
import os
import jwt
import requests
from datetime import datetime
from functools import wraps

app = Flask(__name__)
CORS(app)

from prometheus_flask_exporter import PrometheusMetrics
PrometheusMetrics(app)

# Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL',
    'postgresql://eventflow:eventflow@postgres:5432/eventflow'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Keycloak configuration
KEYCLOAK_URL = os.getenv('KEYCLOAK_URL', 'http://keycloak:8080')
KEYCLOAK_REALM = os.getenv('KEYCLOAK_REALM', 'eventflow')
KEYCLOAK_CLIENT_ID = os.getenv('KEYCLOAK_CLIENT_ID', 'eventflow-api')
KEYCLOAK_CLIENT_SECRET = os.getenv('KEYCLOAK_CLIENT_SECRET', '')
# URL-ul public folosit în token-uri (issuer). Implicit folosim KEYCLOAK_URL.
# În producție poate fi un hostname extern (ex: https://auth.example.com),
# în timp ce KEYCLOAK_URL rămâne URL-ul intern din cluster.
KEYCLOAK_PUBLIC_URL = os.getenv('KEYCLOAK_PUBLIC_URL', KEYCLOAK_URL)

db = SQLAlchemy(app)


# Database Models
class User(db.Model):
    """Model pentru utilizatori"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    keycloak_sub = db.Column(db.String(255), unique=True, nullable=False, index=True)
    email = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    roles = db.relationship('UserRole', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'keycloak_sub': self.keycloak_sub,
            'email': self.email,
            'name': self.name,
            'roles': [role.role for role in self.roles],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class UserRole(db.Model):
    """Model pentru rolurile utilizatorilor"""
    __tablename__ = 'user_roles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    role = db.Column(db.String(50), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (UniqueConstraint('user_id', 'role', name='unique_user_role'),)
    
    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'role': self.role,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# JWT Verification Middleware
def verify_token(f):
    """Decorator pentru verificarea JWT token-ului de la Keycloak"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'No token provided'}), 401
        
        token = auth_header.split(' ')[1]
        
        try:
            # Get Keycloak public key
            jwks_url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
            jwks_response = requests.get(jwks_url)
            jwks = jwks_response.json()
            
            # Decode token header to get kid
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get('kid')
            
            # Find the key
            key = None
            for jwk in jwks.get('keys', []):
                if jwk.get('kid') == kid:
                    key = jwt.algorithms.RSAAlgorithm.from_jwk(jwk)
                    break
            
            if not key:
                return jsonify({'error': 'Invalid token key'}), 401
            
            # Verify and decode token
            # Unele versiuni Keycloak nu includ explicit 'aud' pentru token-urile password grant,
            # dar includ 'azp' (authorized party). Ca să nu stricăm compatibilitatea,
            # dezactivăm verificarea automată a 'aud' și verificăm doar semnătura + issuer.
            decoded = jwt.decode(
                token,
                key,
                algorithms=['RS256'],
                options={'verify_aud': False},
                issuer=f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}"
            )
            
            request.user = decoded
            request.user_roles = decoded.get('realm_access', {}).get('roles', [])
            request.user_sub = decoded.get('sub')
            
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError as e:
            return jsonify({'error': f'Invalid token: {str(e)}'}), 401
        except Exception as e:
            return jsonify({'error': f'Token verification failed: {str(e)}'}), 401
        
        return f(*args, **kwargs)
    return decorated


def require_role(*allowed_roles):
    """Decorator pentru verificarea rolurilor"""
    def decorator(f):
        @wraps(f)
        @verify_token
        def decorated(*args, **kwargs):
            user_roles = getattr(request, 'user_roles', [])
            
            if not any(role in user_roles for role in allowed_roles):
                return jsonify({'error': 'Insufficient permissions'}), 403
            
            return f(*args, **kwargs)
        return decorated
    return decorator


# Routes
@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'service': 'user-profile-service'}), 200


@app.route('/profile/<keycloak_sub>', methods=['GET'])
@verify_token
def get_profile(keycloak_sub):
    """
    Obține sau creează profilul utilizatorului
    Sincronizează cu Keycloak și actualizează rolurile
    """
    # Verify that the token belongs to this user (or admin)
    user_roles = getattr(request, 'user_roles', [])
    if request.user_sub != keycloak_sub and 'ADMIN' not in user_roles:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Get or create user
    user = User.query.filter_by(keycloak_sub=keycloak_sub).first()
    
    if not user:
        # Fetch user info from Keycloak
        try:
            # Get admin token for Keycloak API
            admin_token = get_keycloak_admin_token()
            
            # Get user info from Keycloak
            headers = {'Authorization': f'Bearer {admin_token}'}
            user_info_url = f"{KEYCLOAK_URL}/admin/realms/{KEYCLOAK_REALM}/users"
            params = {'username': keycloak_sub.split(':')[-1] if ':' in keycloak_sub else keycloak_sub}
            
            response = requests.get(user_info_url, headers=headers, params=params)
            
            if response.status_code == 200 and response.json():
                kc_user = response.json()[0]
                email = kc_user.get('email', f'{keycloak_sub}@example.com')
                name = f"{kc_user.get('firstName', '')} {kc_user.get('lastName', '')}".strip() or 'User'
            else:
                email = f'{keycloak_sub}@example.com'
                name = 'User'
        except Exception as e:
            print(f"Error fetching from Keycloak: {e}")
            email = f'{keycloak_sub}@example.com'
            name = 'User'
        
        # Create user
        user = User(
            keycloak_sub=keycloak_sub,
            email=email,
            name=name
        )
        db.session.add(user)
        db.session.commit()
    
    # Sync roles from token
    sync_user_roles(user, request.user_roles)
    
    db.session.refresh(user)
    return jsonify(user.to_dict()), 200


@app.route('/profile/<keycloak_sub>', methods=['PUT'])
@verify_token
def update_profile(keycloak_sub):
    """Actualizează profilul utilizatorului"""
    # Verify authorization
    user_roles = getattr(request, 'user_roles', [])
    if request.user_sub != keycloak_sub and 'ADMIN' not in user_roles:
        return jsonify({'error': 'Unauthorized'}), 403
    
    user = User.query.filter_by(keycloak_sub=keycloak_sub).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json() or {}
    
    if 'name' in data:
        user.name = data['name']
    if 'email' in data:
        user.email = data['email']
    
    user.updated_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify(user.to_dict()), 200


@app.route('/profile/<keycloak_sub>/roles', methods=['GET'])
@verify_token
def get_user_roles(keycloak_sub):
    """Obține rolurile unui utilizator"""
    user_roles_list = getattr(request, 'user_roles', [])
    if request.user_sub != keycloak_sub and 'ADMIN' not in user_roles_list:
        return jsonify({'error': 'Unauthorized'}), 403
    
    user = User.query.filter_by(keycloak_sub=keycloak_sub).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({
        'user_id': user.id,
        'keycloak_sub': user.keycloak_sub,
        'roles': [role.role for role in user.roles]
    }), 200


@app.route('/profile/<keycloak_sub>/roles', methods=['POST'])
@require_role('ADMIN')
def add_user_role(keycloak_sub):
    """Adaugă un rol unui utilizator (doar ADMIN)"""
    user = User.query.filter_by(keycloak_sub=keycloak_sub).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    data = request.get_json()
    if not data or 'role' not in data:
        return jsonify({'error': 'Role is required'}), 400
    
    role_name = data['role']
    
    # Check if role already exists
    existing_role = UserRole.query.filter_by(user_id=user.id, role=role_name).first()
    if existing_role:
        return jsonify({'error': 'Role already assigned'}), 400
    
    # Add role
    user_role = UserRole(user_id=user.id, role=role_name)
    db.session.add(user_role)
    db.session.commit()
    
    return jsonify(user_role.to_dict()), 201


@app.route('/profile/<keycloak_sub>/roles/<role>', methods=['DELETE'])
@require_role('ADMIN')
def remove_user_role(keycloak_sub, role):
    """Șterge un rol de la un utilizator (doar ADMIN)"""
    user = User.query.filter_by(keycloak_sub=keycloak_sub).first()
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    user_role = UserRole.query.filter_by(user_id=user.id, role=role).first()
    if not user_role:
        return jsonify({'error': 'Role not found'}), 404
    
    db.session.delete(user_role)
    db.session.commit()
    
    return jsonify({'message': 'Role removed'}), 200


def sync_user_roles(user, keycloak_roles):
    """Sincronizează rolurile din Keycloak cu baza de date locală"""
    # Get current roles
    current_roles = {role.role for role in user.roles}
    keycloak_roles_set = set(keycloak_roles)
    
    # Add new roles
    for role in keycloak_roles_set:
        if role not in current_roles:
            user_role = UserRole(user_id=user.id, role=role)
            db.session.add(user_role)
    
    # Remove roles that are no longer in Keycloak (optional - usually we keep them)
    # Uncomment if you want to sync deletions:
    # for role in current_roles:
    #     if role not in keycloak_roles_set:
    #         UserRole.query.filter_by(user_id=user.id, role=role).delete()
    
    db.session.commit()


def get_keycloak_admin_token():
    """Obține token-ul admin pentru Keycloak API"""
    try:
        token_url = f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"
        data = {
            'grant_type': 'password',
            'client_id': 'admin-cli',
            'username': os.getenv('KEYCLOAK_ADMIN', 'admin'),
            'password': os.getenv('KEYCLOAK_ADMIN_PASSWORD', 'admin')
        }
        response = requests.post(token_url, data=data)
        if response.status_code == 200:
            return response.json().get('access_token')
    except Exception as e:
        print(f"Error getting admin token: {e}")
    return None


if __name__ == '__main__':
    # Create tables on startup
    with app.app_context():
        db.create_all()
    
    port = int(os.getenv('PORT', 3004))
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    # For production (gunicorn, etc.)
    with app.app_context():
        db.create_all()

