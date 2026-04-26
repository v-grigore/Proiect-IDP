"""
Ticketing Service - Managementul evenimentelor și biletelor
Integrare cu Keycloak pentru SSO și RBAC
"""
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import os
import jwt
import requests
from datetime import datetime
from functools import wraps
import secrets
import pika
import json
import time
import redis

from rate_limiter import (
    InMemorySlidingWindowRateLimiter,
    RedisSlidingWindowRateLimiter,
    RateLimiterBackendUnavailable,
)
from cache import (
    RedisJsonCache,
    CacheBackendUnavailable,
    cache_enabled,
    cache_ttl_seconds,
    make_cache_key,
)

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
# URL public (issuer din token)
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


def _build_rate_limiter():
    backend = os.getenv('RATE_LIMIT_BACKEND', '').strip().lower()

    # If Redis is configured (as in Docker Swarm stack), default to Redis backend.
    if not backend:
        backend = 'redis' if REDIS_CLIENT is not None else 'memory'

    if backend == 'redis':
        if REDIS_CLIENT is None:
            # Misconfiguration: requested redis backend but no REDIS_URL.
            return None
        return RedisSlidingWindowRateLimiter(REDIS_CLIENT, prefix='rl:ticketing')

    # Fallback (not distributed)
    return InMemorySlidingWindowRateLimiter()


RATE_LIMITER = _build_rate_limiter()


def _build_cache():
    if not cache_enabled():
        return None
    if REDIS_CLIENT is None:
        return None
    return RedisJsonCache(REDIS_CLIENT, prefix='cache:ticketing')


CACHE = _build_cache()


# Models
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

    tickets = db.relationship('Ticket', backref='event', lazy=True, cascade='all, delete-orphan')

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


class BannedUser(db.Model):
    __tablename__ = 'banned_users'

    id = db.Column(db.Integer, primary_key=True)
    keycloak_sub = db.Column(db.String(255), unique=True, nullable=False)
    reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'keycloak_sub': self.keycloak_sub,
            'reason': self.reason,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class WaitlistEntry(db.Model):
    __tablename__ = 'waitlist_entries'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    keycloak_sub = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(32), nullable=False, default='pending')  # pending / promoted
    position = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    promoted_ticket_id = db.Column(db.Integer, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'event_id': self.event_id,
            'keycloak_sub': self.keycloak_sub,
            'status': self.status,
            'position': self.position,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'promoted_ticket_id': self.promoted_ticket_id,
        }


# Auth helpers (copiat și simplificat din User Profile Service)
def verify_token(f):
    """Decorator pentru verificarea JWT token-ului de la Keycloak"""

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


def is_banned(sub: str) -> bool:
    """Verifică dacă un utilizator este banat pentru ticketing."""
    if not sub:
        return False
    return db.session.query(BannedUser.id).filter_by(keycloak_sub=sub).first() is not None


def rate_limit(max_requests: int = 2, window_seconds: int = 60):
    """
    Rate limiting per utilizator (keycloak_sub), sliding window.
    In Docker Swarm (cu replicare), folosim Redis ca storage partajat.
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            user_sub = getattr(request, 'user_sub', None)
            if not user_sub:
                return jsonify({'error': 'Missing user context for rate limiting'}), 401

            if RATE_LIMITER is None:
                return jsonify({'error': 'Rate limiter not configured'}), 503

            # Scope limiter per endpoint as well (prevents cross-endpoint interference)
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


def publish_ticket_notification(ticket):
    """Trimite un mesaj în RabbitMQ când se cumpără un bilet."""
    try:
        rabbit_host = os.getenv('RABBITMQ_HOST', 'rabbitmq')
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=rabbit_host))
        channel = connection.channel()
        channel.queue_declare(queue='ticket_booked', durable=False)

        payload = {
            'event_id': ticket.event_id,
            'organizer_sub': ticket.event.created_by if ticket.event else None,
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
        # Pentru demo, doar logăm eroarea fără să stricăm flow-ul principal
        print(f"Error publishing RabbitMQ notification: {e}")


# Routes
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'service': 'ticketing-service', 'status': 'ok'}), 200


@app.route('/events', methods=['GET'])
def list_events():
    """Listă toate evenimentele (public)."""
    if CACHE is not None:
        key = make_cache_key('/events')
        try:
            cached = CACHE.get_json(key)
            if cached is not None:
                resp = make_response(jsonify(cached), 200)
                resp.headers['X-Cache'] = 'HIT'
                return resp
        except CacheBackendUnavailable:
            pass

    events = Event.query.order_by(Event.starts_at.asc()).all()
    payload = [e.to_dict() for e in events]

    if CACHE is not None:
        try:
            CACHE.set_json(key, payload, cache_ttl_seconds())
        except CacheBackendUnavailable:
            pass

    resp = make_response(jsonify(payload), 200)
    resp.headers['X-Cache'] = 'MISS'
    return resp


@app.route('/events', methods=['POST'])
@require_role('ADMIN', 'ORGANIZER')
def create_event():
    """Creează un nou eveniment (ADMIN / ORGANIZER)."""
    data = request.get_json() or {}

    try:
        name = data['name']
        starts_at_str = data['starts_at']
        total_tickets = int(data.get('total_tickets', 0))
    except (KeyError, ValueError):
        return jsonify({'error': 'name, starts_at, total_tickets sunt obligatorii'}), 400

    try:
        starts_at = datetime.fromisoformat(starts_at_str)
    except ValueError:
        return jsonify({'error': 'starts_at trebuie să fie ISO 8601 (ex: 2025-12-31T18:00:00)'}), 400

    event = Event(
        name=name,
        description=data.get('description'),
        location=data.get('location'),
        starts_at=starts_at,
        total_tickets=total_tickets,
        created_by=getattr(request, 'user_sub', None),
    )
    db.session.add(event)
    db.session.commit()

    return jsonify(event.to_dict()), 201


@app.route('/events/<int:event_id>', methods=['GET'])
def get_event(event_id):
    if CACHE is not None:
        key = make_cache_key(f'/events/{event_id}')
        try:
            cached = CACHE.get_json(key)
            if cached is not None:
                resp = make_response(jsonify(cached), 200)
                resp.headers['X-Cache'] = 'HIT'
                return resp
        except CacheBackendUnavailable:
            pass

    event = Event.query.get(event_id)
    if not event:
        return jsonify({'error': 'Event not found'}), 404

    payload = event.to_dict()
    if CACHE is not None:
        try:
            CACHE.set_json(key, payload, cache_ttl_seconds())
        except CacheBackendUnavailable:
            pass

    resp = make_response(jsonify(payload), 200)
    resp.headers['X-Cache'] = 'MISS'
    return resp


@app.route('/events/<int:event_id>', methods=['PATCH'])
@require_role('ADMIN', 'ORGANIZER')
def update_event(event_id):
    """Update simplu pentru eveniment (doar organizatorul sau ADMIN)."""
    event = Event.query.get(event_id)
    if not event:
        return jsonify({'error': 'Event not found'}), 404

    roles = getattr(request, 'user_roles', [])
    user_sub = getattr(request, 'user_sub', None)

    if 'ADMIN' not in roles and event.created_by != user_sub:
        return jsonify({'error': 'Not allowed to edit this event'}), 403

    data = request.get_json() or {}

    if 'name' in data:
        event.name = data['name']
    if 'description' in data:
        event.description = data['description']
    if 'location' in data:
        event.location = data['location']
    if 'starts_at' in data:
        try:
            event.starts_at = datetime.fromisoformat(data['starts_at'])
        except ValueError:
            return jsonify({'error': 'starts_at trebuie să fie ISO 8601'}), 400
    if 'total_tickets' in data:
        try:
            new_total = int(data['total_tickets'])
        except (TypeError, ValueError):
            return jsonify({'error': 'total_tickets trebuie să fie întreg'}), 400
        if new_total < event.tickets_sold:
            return jsonify({'error': 'total_tickets nu poate fi mai mic decât tickets_sold'}), 400
        event.total_tickets = new_total

    db.session.commit()
    return jsonify(event.to_dict()), 200


@app.route('/events/<int:event_id>/tickets', methods=['POST'])
@verify_token
@rate_limit(max_requests=2, window_seconds=60)
def buy_ticket(event_id):
    """Cumpără un bilet pentru utilizatorul curent."""
    if is_banned(request.user_sub):
        return jsonify({'error': 'User is banned from buying tickets'}), 403
    event = Event.query.get(event_id)
    if not event:
        return jsonify({'error': 'Event not found'}), 404

    if event.remaining_tickets() <= 0:
        return jsonify({'error': 'No tickets available'}), 400

    ticket_code = secrets.token_hex(4)  # ex: 8 hex chars, ușor de citit în demo

    ticket = Ticket(
        event_id=event.id,
        keycloak_sub=request.user_sub,
        code=ticket_code,
    )
    event.tickets_sold += 1

    db.session.add(ticket)
    db.session.commit()

    # publica notificare
    publish_ticket_notification(ticket)

    return jsonify(ticket.to_dict()), 201


@app.route('/events/<int:event_id>/waitlist', methods=['POST'])
@verify_token
def join_waitlist(event_id):
    """Adaugă utilizatorul curent pe lista de așteptare pentru un eveniment sold-out."""
    if is_banned(request.user_sub):
        return jsonify({'error': 'User is banned from buying tickets'}), 403

    event = Event.query.get(event_id)
    if not event:
        return jsonify({'error': 'Event not found'}), 404

    # dacă mai sunt bilete, nu are sens lista de așteptare
    if event.remaining_tickets() > 0:
        return jsonify({'error': 'Event is not sold out; you can still buy tickets'}), 400

    # dacă utilizatorul are deja bilet la acest eveniment, nu îl mai punem pe listă
    existing_ticket = Ticket.query.filter_by(
        event_id=event.id,
        keycloak_sub=request.user_sub,
    ).first()
    if existing_ticket:
        return jsonify({'error': 'You already have a ticket for this event'}), 400

    # verificăm dacă este deja pe lista de așteptare
    existing_entry = WaitlistEntry.query.filter_by(
        event_id=event.id,
        keycloak_sub=request.user_sub,
        status='pending',
    ).first()
    if existing_entry:
        return jsonify({
            'message': 'Already on waitlist',
            'entry': existing_entry.to_dict(),
        }), 200

    current_count = WaitlistEntry.query.filter_by(
        event_id=event.id,
        status='pending',
    ).count()

    entry = WaitlistEntry(
        event_id=event.id,
        keycloak_sub=request.user_sub,
        status='pending',
        position=current_count + 1,
    )
    db.session.add(entry)
    db.session.commit()

    return jsonify({
        'message': 'Added to waitlist',
        'entry': entry.to_dict(),
    }), 201


@app.route('/my-tickets', methods=['GET'])
@verify_token
def my_tickets():
    """Listează toate biletele utilizatorului curent."""
    if is_banned(request.user_sub):
        return jsonify({'error': 'User is banned'}), 403
    tickets = Ticket.query.filter_by(keycloak_sub=request.user_sub).all()
    return jsonify([t.to_dict() for t in tickets]), 200


@app.route('/admin/events/<int:event_id>/waitlist', methods=['GET'])
@require_role('ADMIN', 'ORGANIZER')
def admin_get_waitlist(event_id):
    """Listă de așteptare pentru un eveniment (ADMIN sau organizatorul evenimentului)."""
    event = Event.query.get(event_id)
    if not event:
        return jsonify({'error': 'Event not found'}), 404

    roles = getattr(request, 'user_roles', [])
    user_sub = getattr(request, 'user_sub', None)

    if 'ADMIN' not in roles and event.created_by != user_sub:
        return jsonify({'error': 'Not allowed for this event'}), 403

    entries = (
        WaitlistEntry.query.filter_by(event_id=event.id, status='pending')
        .order_by(WaitlistEntry.created_at.asc())
        .all()
    )
    return jsonify([e.to_dict() for e in entries]), 200


@app.route('/admin/events/<int:event_id>/waitlist/promote', methods=['POST'])
@require_role('ADMIN', 'ORGANIZER')
def admin_promote_waitlist(event_id):
    """
    Promovează primul utilizator din lista de așteptare în bilet real,
    dacă mai sunt locuri disponibile.
    """
    event = Event.query.get(event_id)
    if not event:
        return jsonify({'error': 'Event not found'}), 404

    roles = getattr(request, 'user_roles', [])
    user_sub = getattr(request, 'user_sub', None)

    if 'ADMIN' not in roles and event.created_by != user_sub:
        return jsonify({'error': 'Not allowed for this event'}), 403

    if event.remaining_tickets() <= 0:
        return jsonify({'error': 'No tickets available to promote waitlist'}), 400

    entry = (
        WaitlistEntry.query.filter_by(event_id=event.id, status='pending')
        .order_by(WaitlistEntry.created_at.asc())
        .first()
    )
    if not entry:
        return jsonify({'error': 'No pending entries on waitlist'}), 404

    if is_banned(entry.keycloak_sub):
        entry.status = 'promoted'
        db.session.commit()
        return jsonify({'error': 'Next user on waitlist is banned; marked as skipped'}), 400

    ticket_code = secrets.token_hex(4)
    ticket = Ticket(
        event_id=event.id,
        keycloak_sub=entry.keycloak_sub,
        code=ticket_code,
    )
    event.tickets_sold += 1

    entry.status = 'promoted'
    db.session.add(ticket)
    db.session.commit()

    entry.promoted_ticket_id = ticket.id
    db.session.commit()

    publish_ticket_notification(ticket)

    return jsonify({
        'message': 'User promoted from waitlist and ticket created',
        'entry': entry.to_dict(),
        'ticket': ticket.to_dict(),
    }), 201


@app.route('/admin/waitlist/<int:entry_id>/promote', methods=['POST'])
@require_role('ADMIN', 'ORGANIZER')
def admin_promote_waitlist_entry(entry_id):
    """
    Promovează un entry specific din waitlist (ales de organizator) în bilet real.
    """
    entry = WaitlistEntry.query.get(entry_id)
    if not entry or entry.status != 'pending':
        return jsonify({'error': 'Waitlist entry not found or not pending'}), 404

    event = Event.query.get(entry.event_id)
    if not event:
        return jsonify({'error': 'Event not found'}), 404

    roles = getattr(request, 'user_roles', [])
    user_sub = getattr(request, 'user_sub', None)

    if 'ADMIN' not in roles and event.created_by != user_sub:
        return jsonify({'error': 'Not allowed for this event'}), 403

    if event.remaining_tickets() <= 0:
        return jsonify({'error': 'No tickets available to promote waitlist'}), 400

    if is_banned(entry.keycloak_sub):
        entry.status = 'promoted'
        db.session.commit()
        return jsonify({'error': 'User on waitlist is banned; marked as skipped'}), 400

    ticket_code = secrets.token_hex(4)
    ticket = Ticket(
        event_id=event.id,
        keycloak_sub=entry.keycloak_sub,
        code=ticket_code,
    )
    event.tickets_sold += 1

    entry.status = 'promoted'
    db.session.add(ticket)
    db.session.commit()

    entry.promoted_ticket_id = ticket.id
    db.session.commit()

    publish_ticket_notification(ticket)

    return jsonify({
        'message': 'User promoted from waitlist and ticket created',
        'entry': entry.to_dict(),
        'ticket': ticket.to_dict(),
    }), 201


@app.route('/scan/<code>', methods=['POST'])
@require_role('ADMIN', 'ORGANIZER', 'STAFF')
def scan_ticket(code):
    """Validează un bilet după cod și îl marchează ca folosit."""
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

    return jsonify({'valid': True, 'ticket': ticket.to_dict()}), 200


@app.route('/admin/banned', methods=['GET'])
@require_role('ADMIN')
def list_banned():
    """Listă utilizatori banați (ADMIN)."""
    banned = BannedUser.query.order_by(BannedUser.created_at.desc()).all()
    return jsonify([b.to_dict() for b in banned]), 200


@app.route('/admin/banned', methods=['POST'])
@require_role('ADMIN')
def ban_user():
    """Ban/unban logic: creează sau actualizează un ban pentru un keycloak_sub."""
    data = request.get_json() or {}
    keycloak_sub = data.get('keycloak_sub')
    reason = data.get('reason', '')

    if not keycloak_sub:
        return jsonify({'error': 'keycloak_sub is required'}), 400

    banned = BannedUser.query.filter_by(keycloak_sub=keycloak_sub).first()
    if not banned:
        banned = BannedUser(keycloak_sub=keycloak_sub, reason=reason)
        db.session.add(banned)
    else:
        banned.reason = reason

    db.session.commit()
    return jsonify(banned.to_dict()), 201


@app.route('/admin/banned/<keycloak_sub>', methods=['DELETE'])
@require_role('ADMIN')
def unban_user(keycloak_sub):
    """Șterge ban-ul unui utilizator (ADMIN)."""
    banned = BannedUser.query.filter_by(keycloak_sub=keycloak_sub).first()
    if not banned:
        return jsonify({'error': 'Not banned'}), 404
    db.session.delete(banned)
    db.session.commit()
    return jsonify({'message': 'User unbanned'}), 200


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

    port = int(os.getenv('PORT', 3005))
    app.run(host='0.0.0.0', port=port, debug=False)




