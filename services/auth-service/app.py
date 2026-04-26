"""
Auth Service - Verificare JWT și proxy token Keycloak
Serviciu centralizat de autentificare pentru arhitectura EventFlow.

Endpoints:
  GET  /health          - health check
  POST /auth/verify     - verifică un JWT Bearer și returnează user info + roluri
  POST /auth/token      - proxy la Keycloak (grant_type=password) pentru obținere token
  GET  /auth/userinfo   - returnează info utilizator din token Bearer curent
"""

import os
from functools import wraps

import jwt
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

from prometheus_flask_exporter import PrometheusMetrics
PrometheusMetrics(app)

KEYCLOAK_URL = os.getenv('KEYCLOAK_URL', 'http://keycloak:8080')
KEYCLOAK_REALM = os.getenv('KEYCLOAK_REALM', 'eventflow')
KEYCLOAK_CLIENT_ID = os.getenv('KEYCLOAK_CLIENT_ID', 'eventflow-api')
KEYCLOAK_CLIENT_SECRET = os.getenv('KEYCLOAK_CLIENT_SECRET', '')
KEYCLOAK_PUBLIC_URL = os.getenv('KEYCLOAK_PUBLIC_URL', KEYCLOAK_URL)


def _jwks_url():
    return f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"


def _token_url():
    return f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"


def _decode_bearer(token: str):
    """Verifică și decodează un JWT emis de Keycloak. Aruncă excepție dacă e invalid."""
    jwks_resp = requests.get(_jwks_url(), timeout=5)
    jwks_resp.raise_for_status()
    jwks = jwks_resp.json()

    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get('kid')

    key = None
    for jwk in jwks.get('keys', []):
        if jwk.get('kid') == kid:
            key = jwt.algorithms.RSAAlgorithm.from_jwk(jwk)
            break

    if not key:
        raise jwt.InvalidTokenError('Key not found in JWKS')

    return jwt.decode(
        token,
        key,
        algorithms=['RS256'],
        options={'verify_aud': False},
        issuer=f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}",
    )


def _extract_user_info(decoded: dict) -> dict:
    roles = decoded.get('realm_access', {}).get('roles', [])
    return {
        'sub': decoded.get('sub'),
        'username': decoded.get('preferred_username'),
        'email': decoded.get('email'),
        'name': decoded.get('name'),
        'roles': roles,
    }


def verify_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'No token provided'}), 401
        token = auth_header.split(' ', 1)[1]
        try:
            decoded = _decode_bearer(token)
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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'service': 'auth-service', 'status': 'ok'}), 200


@app.route('/auth/verify', methods=['POST'])
def verify():
    """
    Body JSON: { "token": "<jwt>" }
    Returnează user info + roluri dacă token-ul e valid, altfel 401.
    """
    data = request.get_json() or {}
    token = data.get('token', '')

    # Acceptăm și Bearer din Authorization header
    if not token:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ', 1)[1]

    if not token:
        return jsonify({'error': 'Token required (body.token sau Authorization: Bearer)'}), 400

    try:
        decoded = _decode_bearer(token)
        return jsonify({
            'valid': True,
            'user': _extract_user_info(decoded),
        }), 200
    except jwt.ExpiredSignatureError:
        return jsonify({'valid': False, 'error': 'Token expired'}), 401
    except jwt.InvalidTokenError as e:
        return jsonify({'valid': False, 'error': f'Invalid token: {e}'}), 401
    except Exception as e:
        return jsonify({'valid': False, 'error': str(e)}), 401


@app.route('/auth/token', methods=['POST'])
def get_token():
    """
    Proxy la Keycloak token endpoint.
    Body JSON: { "username": "...", "password": "...", "client_id": "..." (opțional) }
    Returnează access_token, refresh_token, expires_in.
    """
    data = request.get_json() or {}
    username = data.get('username', '')
    password = data.get('password', '')
    client_id = data.get('client_id', KEYCLOAK_CLIENT_ID)
    client_secret = data.get('client_secret', KEYCLOAK_CLIENT_SECRET)

    if not username or not password:
        return jsonify({'error': 'username și password sunt obligatorii'}), 400

    form = {
        'grant_type': 'password',
        'client_id': client_id,
        'username': username,
        'password': password,
    }
    if client_secret:
        form['client_secret'] = client_secret

    try:
        resp = requests.post(_token_url(), data=form, timeout=10)
        kc_data = resp.json()
        if resp.status_code != 200:
            return jsonify({
                'error': kc_data.get('error_description', kc_data.get('error', 'Authentication failed')),
            }), resp.status_code

        return jsonify({
            'access_token': kc_data.get('access_token'),
            'refresh_token': kc_data.get('refresh_token'),
            'expires_in': kc_data.get('expires_in'),
            'token_type': kc_data.get('token_type', 'Bearer'),
        }), 200
    except Exception as e:
        return jsonify({'error': f'Keycloak unreachable: {e}'}), 503


@app.route('/auth/userinfo', methods=['GET'])
@verify_token
def userinfo():
    """Returnează informațiile utilizatorului autentificat din token-ul Bearer."""
    return jsonify(_extract_user_info(request.user)), 200


if __name__ == '__main__':
    port = int(os.getenv('PORT', 3003))
    app.run(host='0.0.0.0', port=port, debug=False)
