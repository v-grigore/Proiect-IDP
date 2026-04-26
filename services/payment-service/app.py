"""
Payment Service - rezervare și confirmare plata pentru bilete

Scop:
- când utilizatorul apasă "Cumpără bilet", creăm o sesiune de plată PENDING care rezervă locul
  pentru 2 minute.
- dacă utilizatorul CONFIRMĂ plata în < 2 minute, emitem biletul real.
- dacă încearcă după 2 minute, sesiunea este EXPIRATĂ și nu se mai poate emite bilet.

Nu există procesor de plăți real; confirmarea este simulată printr-un endpoint separat.
"""

import os
from datetime import datetime, timedelta
from functools import wraps
import json

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import jwt
import requests
import pika
import secrets
import redis

from rate_limiter import RedisSlidingWindowRateLimiter, RateLimiterBackendUnavailable

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


def _build_redis_client():
    redis_url = os.getenv('REDIS_URL', '').strip()
    if not redis_url:
        return None
    return redis.Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_timeout=1,
        socket_connect_timeout=1,
    )


REDIS_CLIENT = _build_redis_client()
RATE_LIMITER = RedisSlidingWindowRateLimiter(REDIS_CLIENT, prefix='rl:payment') if REDIS_CLIENT else None


def rate_limit(max_requests: int = 2, window_seconds: int = 60):
    """
    Rate limiting per utilizator (keycloak_sub), sliding window, stored in Redis (distributed).
    """

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            user_sub = getattr(request, 'user_sub', None)
            if not user_sub:
                return jsonify({'error': 'Missing user context for rate limiting'}), 401

            if RATE_LIMITER is None:
                return jsonify({'error': 'Rate limiter not configured'}), 503

            scope = request.path
            key = f"{user_sub}:{scope}"

            try:
                allowed = RATE_LIMITER.allow(key, max_requests, window_seconds)
            except RateLimiterBackendUnavailable:
                return jsonify({'error': 'Rate limiting backend unavailable'}), 503

            if not allowed:
                return jsonify({
                    'error': 'Too many requests',
                    'limit': max_requests,
                    'window_seconds': window_seconds,
                }), 429

            return f(*args, **kwargs)

        return wrapped

    return decorator


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


class Ticket(db.Model):
    __tablename__ = 'tickets'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    keycloak_sub = db.Column(db.String(255), nullable=False)
    code = db.Column(db.String(32), nullable=False)
    purchased_at = db.Column(db.DateTime, default=datetime.utcnow)
    used_at = db.Column(db.DateTime, nullable=True)
    used_by = db.Column(db.String(255), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'event_id': self.event_id,
            'keycloak_sub': self.keycloak_sub,
            'code': self.code,
            'purchased_at': self.purchased_at.isoformat() if self.purchased_at else None,
            'used_at': self.used_at.isoformat() if self.used_at else None,
            'used_by': self.used_by,
        }


class PaymentSession(db.Model):
    __tablename__ = 'payment_sessions'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    keycloak_sub = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(32), nullable=False, default='pending')  # pending / confirmed / canceled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    ticket_id = db.Column(db.Integer, nullable=True)

    def to_dict(self):
        def _iso_utc(dt):
            # We store naive UTC (datetime.utcnow). Emit explicit UTC ISO strings for clients.
            return (dt.isoformat() + 'Z') if dt else None
        return {
            'id': self.id,
            'event_id': self.event_id,
            'keycloak_sub': self.keycloak_sub,
            'status': self.status,
            'created_at': _iso_utc(self.created_at),
            'expires_at': _iso_utc(self.expires_at),
            'ticket_id': self.ticket_id,
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


def publish_ticket_notification(ticket: Ticket):
    """Trimite un mesaj în RabbitMQ când se finalizează plata și se emite biletul."""
    try:
        rabbit_host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbit_host))
        channel = connection.channel()
        channel.queue_declare(queue='ticket_booked', durable=False)

        # Important for organizer notifications:
        # notification-service filters /notifications by organizer_sub for ORGANIZER users.
        event = Event.query.get(ticket.event_id)
        organizer_sub = event.created_by if event else None

        payload = {
            'event_id': ticket.event_id,
            'organizer_sub': organizer_sub,
            'buyer_sub': ticket.keycloak_sub,
            'code': ticket.code,
            'created_at': datetime.utcnow().isoformat(),
        }
        channel.basic_publish(
            exchange='',
            routing_key='ticket_booked',
            body=json.dumps(payload).encode('utf-8'),
        )
        connection.close()
    except Exception as e:
        print(f"Error publishing RabbitMQ notification from payment-service: {e}")


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'service': 'payment-service', 'status': 'ok'}), 200


def _cleanup_expired_sessions():
    now = datetime.utcnow()
    PaymentSession.query.filter(
        PaymentSession.status == 'pending',
        PaymentSession.expires_at < now,
    ).update({'status': 'canceled'})
    db.session.commit()


@app.route('/payments/start', methods=['POST'])
@verify_token
@rate_limit(max_requests=2, window_seconds=60)
def start_payment():
    """
    Creează o sesiune de plată PENDING pentru 2 minute.
    Nu creează biletul încă, doar rezervă un loc.
    """
    data = request.get_json() or {}
    event_id = data.get('event_id')
    if not event_id:
        return jsonify({'error': 'event_id is required'}), 400

    event = Event.query.get(event_id)
    if not event:
        return jsonify({'error': 'Event not found'}), 404

    now = datetime.utcnow()
    _cleanup_expired_sessions()

    tickets_sold = Ticket.query.filter_by(event_id=event.id).count()
    pending_sessions = PaymentSession.query.filter(
        PaymentSession.event_id == event.id,
        PaymentSession.status == 'pending',
        PaymentSession.expires_at > now,
    ).count()

    if tickets_sold + pending_sessions >= event.total_tickets:
        return jsonify({'error': 'No tickets available (including reserved ones)'}), 400

    existing = PaymentSession.query.filter_by(
        event_id=event.id,
        keycloak_sub=request.user_sub,
        status='pending',
    ).filter(PaymentSession.expires_at > now).first()
    if existing:
        return jsonify({
            'message': 'Existing pending payment session',
            'session': existing.to_dict(),
        }), 200

    expires_at = now + timedelta(minutes=2)
    session = PaymentSession(
        event_id=event.id,
        keycloak_sub=request.user_sub,
        status='pending',
        created_at=now,
        expires_at=expires_at,
    )
    db.session.add(session)
    db.session.commit()

    return jsonify({
        'message': 'Payment session started',
        'session': session.to_dict(),
    }), 201


@app.route('/payments/confirm/<int:session_id>', methods=['POST'])
@verify_token
def confirm_payment(session_id):
    """
    Confirmă o sesiune de plată:
    - verifică să nu fie expirată (>2 min)
    - emite biletul real
    """
    now = datetime.utcnow()
    session = PaymentSession.query.get(session_id)
    if not session:
        return jsonify({'error': 'Payment session not found'}), 404

    if session.keycloak_sub != request.user_sub:
        return jsonify({'error': 'This payment session does not belong to you'}), 403

    if session.status != 'pending':
        return jsonify({'error': f'Payment session is {session.status}, not pending'}), 400

    if session.expires_at < now:
        session.status = 'canceled'
        db.session.commit()
        return jsonify({'error': 'Payment session expired (more than 2 minutes)'}), 400

    event = Event.query.get(session.event_id)
    if not event:
        session.status = 'canceled'
        db.session.commit()
        return jsonify({'error': 'Event not found; session canceled'}), 404

    tickets_sold = Ticket.query.filter_by(event_id=event.id).count()
    if tickets_sold >= event.total_tickets:
        session.status = 'canceled'
        db.session.commit()
        return jsonify({'error': 'No tickets available at confirmation time'}), 400

    ticket_code = secrets.token_hex(4)
    ticket = Ticket(
        event_id=event.id,
        keycloak_sub=session.keycloak_sub,
        code=ticket_code,
    )
    event.tickets_sold += 1
    db.session.add(ticket)
    db.session.commit()

    session.status = 'confirmed'
    session.ticket_id = ticket.id
    db.session.commit()

    publish_ticket_notification(ticket)

    return jsonify({
        'message': 'Payment confirmed and ticket issued',
        'ticket': ticket.to_dict(),
        'session': session.to_dict(),
    }), 201


@app.route('/payments/cancel/<int:session_id>', methods=['POST'])
@verify_token
def cancel_payment(session_id):
    """Anulează explicit o sesiune de plată PENDING."""
    session = PaymentSession.query.get(session_id)
    if not session:
        return jsonify({'error': 'Payment session not found'}), 404

    if session.keycloak_sub != request.user_sub:
        return jsonify({'error': 'This payment session does not belong to you'}), 403

    if session.status != 'pending':
        return jsonify({'error': f'Payment session is {session.status}, not pending'}), 400

    session.status = 'canceled'
    db.session.commit()
    return jsonify({'message': 'Payment session canceled', 'session': session.to_dict()}), 200


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    port = int(os.getenv('PORT', 3008))
    app.run(host='0.0.0.0', port=port, debug=False)



