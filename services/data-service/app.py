"""
Data Service - Agregare date cross-servicii din baza de date EventFlow
Oferă vederi agregate și statistici globale.

Endpoints:
  GET /health
  GET /data/stats        - statistici globale (ADMIN / ORGANIZER)
  GET /data/events       - toate evenimentele cu detalii extinse (public)
  GET /data/users        - utilizatori cu roluri (ADMIN)
  GET /data/payments     - sesiuni de plată agregate (ADMIN / ORGANIZER)
  GET /data/notifications - notificări recente (ADMIN / ORGANIZER)
"""

import os
from datetime import datetime
from functools import wraps

import jwt
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
CORS(app)

from prometheus_flask_exporter import PrometheusMetrics
PrometheusMetrics(app)

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL',
    'postgresql://eventflow:eventflow@postgres:5432/eventflow'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

KEYCLOAK_URL = os.getenv('KEYCLOAK_URL', 'http://keycloak:8080')
KEYCLOAK_REALM = os.getenv('KEYCLOAK_REALM', 'eventflow')
KEYCLOAK_PUBLIC_URL = os.getenv('KEYCLOAK_PUBLIC_URL', KEYCLOAK_URL)

db = SQLAlchemy(app)


# ---------------------------------------------------------------------------
# Models (read-only views, reflect existing tables)
# ---------------------------------------------------------------------------

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    keycloak_sub = db.Column(db.String(255), unique=True, nullable=False)
    email = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    roles = db.relationship('UserRole', backref='user', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'keycloak_sub': self.keycloak_sub,
            'email': self.email,
            'name': self.name,
            'roles': [r.role for r in self.roles],
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class UserRole(db.Model):
    __tablename__ = 'user_roles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    role = db.Column(db.String(50), nullable=False)


class Event(db.Model):
    __tablename__ = 'events'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    location = db.Column(db.String(255))
    starts_at = db.Column(db.DateTime, nullable=False)
    total_tickets = db.Column(db.Integer, nullable=False)
    tickets_sold = db.Column(db.Integer, nullable=False, default=0)
    created_by = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        remaining = max(self.total_tickets - self.tickets_sold, 0)
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'location': self.location,
            'starts_at': self.starts_at.isoformat() if self.starts_at else None,
            'total_tickets': self.total_tickets,
            'tickets_sold': self.tickets_sold,
            'remaining_tickets': remaining,
            'sold_out': remaining == 0,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Ticket(db.Model):
    __tablename__ = 'tickets'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    keycloak_sub = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(32), nullable=False)
    purchased_at = db.Column(db.DateTime, default=datetime.utcnow)
    used_at = db.Column(db.DateTime, nullable=True)


class PaymentSession(db.Model):
    __tablename__ = 'payment_sessions'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    keycloak_sub = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(32), nullable=False, default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    ticket_id = db.Column(db.Integer, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'event_id': self.event_id,
            'keycloak_sub': self.keycloak_sub,
            'status': self.status,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
            'expires_at': self.expires_at.isoformat() + 'Z' if self.expires_at else None,
            'ticket_id': self.ticket_id,
        }


class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, nullable=False)
    organizer_sub = db.Column(db.String(255), nullable=True)
    buyer_sub = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(32), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'event_id': self.event_id,
            'organizer_sub': self.organizer_sub,
            'buyer_sub': self.buyer_sub,
            'code': self.code,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def verify_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'No token provided'}), 401
        token = auth_header.split(' ', 1)[1]
        try:
            jwks_url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
            jwks_resp = requests.get(jwks_url, timeout=5)
            jwks = jwks_resp.json()

            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get('kid')
            key = None
            for jwk in jwks.get('keys', []):
                if jwk.get('kid') == kid:
                    key = jwt.algorithms.RSAAlgorithm.from_jwk(jwk)
                    break

            if not key:
                return jsonify({'error': 'Invalid token key'}), 401

            decoded = jwt.decode(
                token, key,
                algorithms=['RS256'],
                options={'verify_aud': False},
                issuer=f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}",
            )
            request.user = decoded
            request.user_sub = decoded.get('sub')
            request.user_roles = decoded.get('realm_access', {}).get('roles', [])
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError as e:
            return jsonify({'error': f'Invalid token: {e}'}), 401
        except Exception as e:
            return jsonify({'error': f'Token verification failed: {e}'}), 401
        return f(*args, **kwargs)
    return decorated


def require_role(*allowed_roles):
    def decorator(f):
        @wraps(f)
        @verify_token
        def decorated(*args, **kwargs):
            if not any(r in getattr(request, 'user_roles', []) for r in allowed_roles):
                return jsonify({'error': 'Insufficient permissions'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'service': 'data-service', 'status': 'ok'}), 200


@app.route('/data/stats', methods=['GET'])
@require_role('ADMIN', 'ORGANIZER')
def stats():
    """Statistici globale pentru dashboard."""
    total_events = Event.query.count()
    total_tickets_sold = db.session.query(db.func.sum(Event.tickets_sold)).scalar() or 0
    total_tickets_capacity = db.session.query(db.func.sum(Event.total_tickets)).scalar() or 0
    total_users = User.query.count()
    total_notifications = Notification.query.count()

    pending_payments = PaymentSession.query.filter_by(status='pending').count()
    confirmed_payments = PaymentSession.query.filter_by(status='confirmed').count()

    tickets_used = Ticket.query.filter(Ticket.used_at.isnot(None)).count()
    tickets_unused = Ticket.query.filter(Ticket.used_at.is_(None)).count()

    return jsonify({
        'events': {
            'total': total_events,
        },
        'tickets': {
            'sold': int(total_tickets_sold),
            'capacity': int(total_tickets_capacity),
            'used': tickets_used,
            'unused': tickets_unused,
        },
        'users': {
            'total': total_users,
        },
        'payments': {
            'pending': pending_payments,
            'confirmed': confirmed_payments,
        },
        'notifications': {
            'total': total_notifications,
        },
    }), 200


@app.route('/data/events', methods=['GET'])
@verify_token
def data_events():
    """Toate evenimentele cu detalii extinse."""
    user_roles = getattr(request, 'user_roles', [])
    user_sub = getattr(request, 'user_sub', None)

    query = Event.query.order_by(Event.starts_at.asc())

    # ORGANIZER vede doar evenimentele lui, ADMIN vede toate
    if 'ADMIN' not in user_roles and 'ORGANIZER' in user_roles:
        query = query.filter_by(created_by=user_sub)

    events = query.all()
    result = []
    for ev in events:
        d = ev.to_dict()
        ticket_count = Ticket.query.filter_by(event_id=ev.id).count()
        used_count = Ticket.query.filter(
            Ticket.event_id == ev.id,
            Ticket.used_at.isnot(None)
        ).count()
        d['verified_tickets_sold'] = ticket_count
        d['tickets_used'] = used_count
        result.append(d)

    return jsonify(result), 200


@app.route('/data/users', methods=['GET'])
@require_role('ADMIN')
def data_users():
    """Lista completă de utilizatori cu roluri (ADMIN only)."""
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([u.to_dict() for u in users]), 200


@app.route('/data/payments', methods=['GET'])
@require_role('ADMIN', 'ORGANIZER')
def data_payments():
    """Sesiuni de plată agregate."""
    user_roles = getattr(request, 'user_roles', [])
    user_sub = getattr(request, 'user_sub', None)

    query = PaymentSession.query.order_by(PaymentSession.created_at.desc())

    # ORGANIZER vede doar sesiunile de plată pentru evenimentele lui
    if 'ADMIN' not in user_roles:
        organizer_event_ids = [
            ev.id for ev in Event.query.filter_by(created_by=user_sub).all()
        ]
        query = query.filter(PaymentSession.event_id.in_(organizer_event_ids))

    sessions = query.limit(100).all()
    return jsonify([s.to_dict() for s in sessions]), 200


@app.route('/data/notifications', methods=['GET'])
@require_role('ADMIN', 'ORGANIZER')
def data_notifications():
    """Notificări recente agregate."""
    user_roles = getattr(request, 'user_roles', [])
    user_sub = getattr(request, 'user_sub', None)

    query = Notification.query.order_by(Notification.created_at.desc())
    if 'ADMIN' not in user_roles:
        query = query.filter_by(organizer_sub=user_sub)

    notes = query.limit(100).all()
    return jsonify([n.to_dict() for n in notes]), 200


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    port = int(os.getenv('PORT', 3009))
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    with app.app_context():
        db.create_all()
