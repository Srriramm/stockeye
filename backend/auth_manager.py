"""
auth_manager.py — JWT verification and Flask auth decorator.
Verifies Supabase user access tokens server-side via direct HTTP (requests),
avoiding supabase-py SDK conflicts with eventlet monkey-patching.

Token verification results are cached in Redis for 4 minutes to reduce
Supabase API calls (tokens refresh every 5 minutes on the client).
"""

import os
import base64
import hashlib
import json as _json
import logging
import time
import requests as _requests
from functools import wraps
from flask import request, jsonify, g

logger = logging.getLogger(__name__)

SUPABASE_URL        = os.getenv('SUPABASE_URL', '').rstrip('/')
SUPABASE_ANON_KEY   = os.getenv('SUPABASE_ANON_KEY', '')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY', '')

# Use service key for admin-level auth verification; fall back to anon key
_AUTH_KEY = SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY

# Redis client for token caching (lazily initialized)
_redis_client = None
_redis_unavailable_until = 0.0   # epoch seconds; 0 means "never failed yet"
_REDIS_RETRY_INTERVAL = 60       # seconds before retrying after a failure

def _get_redis():
    """Return a Redis client, or None if Redis is unavailable.

    Uses a 60-second circuit-breaker so a missing Redis server doesn't spam
    the logs or add latency to every auth check.
    """
    global _redis_client, _redis_unavailable_until
    if _redis_client is not None:
        return _redis_client
    now = time.monotonic()
    if now < _redis_unavailable_until:
        return None   # still in cooldown — skip silently
    redis_url = os.getenv('REDIS_URL')
    if not redis_url:
        return None
    try:
        import redis
        client = redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        _redis_client = client
        _redis_unavailable_until = 0.0
        return _redis_client
    except Exception as e:
        logger.warning(f"Redis unavailable for token cache: {e}")
        _redis_unavailable_until = now + _REDIS_RETRY_INTERVAL
        return None


def verify_token(access_token: str) -> str:
    """
    Verify a Supabase JWT by calling GET /auth/v1/user with the token.
    Results are cached in Redis for 4 minutes to avoid repeated Supabase calls.
    Uses the plain `requests` library to avoid eventlet/httpx conflicts.
    Returns the user_id (UUID string) on success, raises ValueError on failure.
    """
    if not SUPABASE_URL or not _AUTH_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY (or SERVICE_KEY) must be set in .env")

    # Check Redis cache first — never store raw token, only a SHA-256 hash
    token_hash = hashlib.sha256(access_token.encode()).hexdigest()
    cache_key = f"stockeye:auth:{token_hash}"
    r = _get_redis()
    if r:
        try:
            cached = r.get(cache_key)
            if cached:
                return cached.decode()
        except Exception:
            pass  # Redis unavailable — fall through to Supabase

    url = f"{SUPABASE_URL}/auth/v1/user"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "apikey": _AUTH_KEY,
    }

    try:
        resp = _requests.get(url, headers=headers, timeout=5)
    except _requests.RequestException as e:
        raise ValueError(f"Auth network error: {e}")

    if resp.status_code != 200:
        raise ValueError(f"Token rejected by Supabase ({resp.status_code})")

    data = resp.json()
    user_id = data.get("id")
    if not user_id:
        raise ValueError("No user id in Supabase auth response")

    user_id = str(user_id)

    # Cache the verified user_id for 4 minutes (tokens expire every 5 min on client)
    if r:
        try:
            r.setex(cache_key, 240, user_id)
        except Exception:
            pass  # Cache write failure is non-fatal

    return user_id


def require_auth(f):
    """
    Flask route decorator — extracts Bearer token, verifies it,
    and injects `user_id` as the first positional argument.

    Usage:
        @app.route('/api/portfolio/holdings')
        @require_auth
        def get_holdings(user_id):
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid Authorization header'}), 401
        token = auth_header[7:].strip()
        try:
            user_id = verify_token(token)
        except Exception as e:
            logger.warning(f"Auth failed: {e}")
            return jsonify({'error': 'Unauthorized — invalid or expired token'}), 401
        # Expose user_id for per-user rate limiting + structured logging.
        g.user_id = user_id
        return f(user_id, *args, **kwargs)
    return decorated


def optional_auth(f):
    """
    Like require_auth but doesn't block if no token is provided.
    Injects user_id=None when unauthenticated.
    Useful for public endpoints that optionally personalize results.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        user_id = None
        if auth_header.startswith('Bearer '):
            try:
                user_id = verify_token(auth_header[7:].strip())
            except Exception:
                pass
        if user_id:
            g.user_id = user_id
        return f(user_id, *args, **kwargs)
    return decorated


def decode_jwt_payload(token: str) -> dict:
    """
    Decode JWT payload without signature verification.
    Safe to call only AFTER verify_token() has confirmed the token is authentic.
    Returns the decoded payload dict, or {} on error.
    """
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return {}
        # Add padding to make length a multiple of 4
        padded = parts[1] + '=' * (-len(parts[1]) % 4)
        payload = base64.urlsafe_b64decode(padded)
        return _json.loads(payload)
    except Exception:
        return {}


def require_admin(f):
    """
    Flask route decorator — requires valid JWT AND role='admin' in app_users.
    Injects user_id as first positional argument (same as require_auth).

    Usage:
        @app.route('/api/admin/users')
        @require_admin
        def list_users(user_id):
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid Authorization header'}), 401
        token = auth_header[7:].strip()
        try:
            user_id = verify_token(token)
        except Exception as e:
            logger.warning(f"Admin auth failed: {e}")
            return jsonify({'error': 'Unauthorized — invalid or expired token'}), 401
        # Lazy import to avoid circular dependency at module load time
        from user_manager import get_user_record
        user = get_user_record(user_id)
        if not user or user.get('role') != 'admin':
            return jsonify({'error': 'Forbidden — admin access required'}), 403
        return f(user_id, *args, **kwargs)
    return decorated
