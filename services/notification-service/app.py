"""
Notification Service - primește mesaje din RabbitMQ când se cumpără bilete
și oferă organizatorilor/administratorilor un endpoint de vizualizare.
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import os
import jwt
import requests
from datetime import datetime
from functools import wraps
import threading
import pika
import json

app = Flask(__name__)
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL',
    'postgresql://eventflow:eventflow@postgres:5432/eventflow'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

KEYCLOAK_URL = os.getenv('KEYCLOAK_URL', 'http://keycloak:8080')
KEYCLOAK_REALM = os.getenv('KEYCLOAK_REALM', 'eventflow')
KEYCLOAK_PUBLIC_URL = os.getenv('KEYCLOAK_PUBLIC_URL', KEYCLOAK_URL)

db = SQLAlchemy(app)


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


def verify_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'No token provided'}), 401

        token = auth_header.split(' ')[1]
        try:
            jwks_url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
            jwks_response = requests.get(jwks_url)
            jwks = jwks_response.json()

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
                token,
                key,
                algorithms=['RS256'],
                options={'verify_aud': False},
                issuer=f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}",
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


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'service': 'notification-service', 'status': 'ok'}), 200


@app.route('/notifications', methods=['GET'])
@require_role('ADMIN', 'ORGANIZER')
def get_notifications():
    """Notificări pentru evenimentele organizatorului curent (sau toate pentru ADMIN)."""
    user_sub = getattr(request, 'user_sub', None)
    roles = getattr(request, 'user_roles', [])

    query = Notification.query
    if 'ADMIN' not in roles:
        query = query.filter_by(organizer_sub=user_sub)

    notes = query.order_by(Notification.created_at.desc()).limit(50).all()
    return jsonify([n.to_dict() for n in notes]), 200


@app.route('/my-notifications', methods=['GET'])
@verify_token
def my_notifications():
    """Notificări pentru utilizatorul curent (de ex. când i se emite/promovează un bilet)."""
    user_sub = getattr(request, 'user_sub', None)
    notes = (
        Notification.query.filter_by(buyer_sub=user_sub)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify([n.to_dict() for n in notes]), 200


def consume_from_rabbitmq():
    """Consumer simplu care ascultă queue-urile de tip ticket_* și salvează notificări."""
    rabbit_host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
    while True:
        try:
            params = pika.ConnectionParameters(host=rabbit_host)
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.queue_declare(queue='ticket_booked', durable=False)
            channel.queue_declare(queue='ticket_scanned', durable=False)

            def callback(ch, method, properties, body):
                try:
                    payload = json.loads(body.decode('utf-8'))
                    with app.app_context():
                        n = Notification(
                            event_id=payload.get('event_id'),
                            organizer_sub=payload.get('organizer_sub'),
                            buyer_sub=payload.get('buyer_sub') or payload.get('scanner_sub'),
                            code=payload.get('code'),
                        )
                        db.session.add(n)
                        db.session.commit()
                except Exception as e:
                    print(f"Error saving notification: {e}")
                finally:
                    ch.basic_ack(delivery_tag=method.delivery_tag)

            channel.basic_consume(queue='ticket_booked', on_message_callback=callback)
            channel.basic_consume(queue='ticket_scanned', on_message_callback=callback)
            print("Notification service: listening for ticket_booked and ticket_scanned messages...")
            channel.start_consuming()
        except Exception as e:
            print(f"Notification consumer error: {e}, retrying in 5s...")
            try:
                connection.close()
            except Exception:
                pass
            import time
            time.sleep(5)


def start_consumer_thread():
    t = threading.Thread(target=consume_from_rabbitmq, daemon=True)
    t.start()


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    start_consumer_thread()
    port = int(os.getenv('PORT', 3006))
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    with app.app_context():
        db.create_all()
    start_consumer_thread()


