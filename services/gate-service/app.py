"""
Gate Service - Validare bilete la intrare
Folosește aceleași tabele ca ticketing-service dar expune doar endpointuri de scanare.
Publică evenimente de tip `ticket_scanned` în RabbitMQ pentru analytics / notificări.
"""

import os
from datetime import datetime
from functools import wraps
import json

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import jwt
import requests
import pika

app = Flask(__name__)
CORS(app)

# Config DB
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL',
    'postgresql://eventflow:eventflow@postgres:5432/eventflow'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Keycloak
KEYCLOAK_URL = os.getenv('KEYCLOAK_URL', 'http://keycloak:8080')
KEYCLOAK_REALM = os.getenv('KEYCLOAK_REALM', 'eventflow')
KEYCLOAK_PUBLIC_URL = os.getenv('KEYCLOAK_PUBLIC_URL', KEYCLOAK_URL)

db = SQLAlchemy(app)


# Models (copiate din ticketing-service, doar câmpurile relevante)
class Event(db.Model):
    __tablename__ = 'events'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    location = db.Column(db.String(255))
    starts_at = db.Column(db.DateTime, nullable=False)
    total_tickets = db.Column(db.Integer, nullable=False)
    tickets_sold = db.Column(db.Integer, nullable=False, default=0)
    created_by = db.Column(db.String(255))  # keycloak_sub
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tickets = db.relationship('Ticket', backref='event', lazy=True)

    def remaining_tickets(self) -> int:
        return max(self.total_tickets - self.tickets_sold, 0)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'location': self.location,
            'starts_at': self.starts_at.isoformat() if self.starts_at else None,
            'total_tickets': self.total_tickets,
            'tickets_sold': self.tickets_sold,
            'remaining_tickets': self.remaining_tickets(),
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
    used_by = db.Column(db.String(255), nullable=True)  # keycloak_sub al staff-ului care a validat

    def to_dict(self):
        return {
            'id': self.id,
            'event_id': self.event_id,
            'keycloak_sub': self.keycloak_sub,
            'code': self.code,
            'purchased_at': self.purchased_at.isoformat() if self.purchased_at else None,
            'used_at': self.used_at.isoformat() if self.used_at else None,
            'used_by': self.used_by,
            'event': self.event.to_dict() if self.event else None,
        }


# Auth helpers (similar cu cele din ticketing / notification service)
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


def publish_ticket_scanned(ticket, validator_sub: str | None):
    """Trimite un mesaj în RabbitMQ când se scanează/validează un bilet."""
    try:
        rabbit_host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbit_host))
        channel = connection.channel()
        channel.queue_declare(queue='ticket_scanned', durable=False)

        payload = {
            'event_id': ticket.event_id,
            'organizer_sub': ticket.event.created_by if ticket.event else None,
            'scanner_sub': validator_sub,
            'code': ticket.code,
            'created_at': datetime.utcnow().isoformat(),
        }
        channel.basic_publish(
            exchange='',
            routing_key='ticket_scanned',
            body=json.dumps(payload).encode('utf-8'),
        )
        connection.close()
    except Exception as e:
        print(f"Error publishing ticket_scanned notification: {e}")


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'service': 'gate-service', 'status': 'ok'}), 200


@app.route('/scan/<code>', methods=['POST'])
@require_role('ADMIN', 'ORGANIZER', 'STAFF')
def scan_ticket(code):
    """
    Validează un bilet după cod și îl marchează ca folosit.
    Acest serviciu este gândit ca „poarta” de acces la eveniment.
    """
    ticket = Ticket.query.filter_by(code=code).first()
    if not ticket:
        return jsonify({'valid': False, 'error': 'Ticket not found'}), 404

    if ticket.used_at is not None:
        return jsonify({
            'valid': False,
            'error': 'Ticket already used',
            'ticket': ticket.to_dict(),
        }), 400

    ticket.used_at = datetime.utcnow()
    ticket.used_by = getattr(request, 'user_sub', None)
    db.session.commit()

    publish_ticket_scanned(ticket, ticket.used_by)

    return jsonify({'valid': True, 'ticket': ticket.to_dict()}), 200


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    port = int(os.getenv('PORT', 3007))
    app.run(host='0.0.0.0', port=port, debug=False)



