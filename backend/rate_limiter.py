"""
rate_limiter.py — Flask-Limiter setup with Redis backend.

Initialize by calling init_limiter(app) after creating the Flask app.
Apply per-endpoint limits with @limiter.limit("N per period") decorators.

Default global limit: 200 requests per minute per user (or IP if unauthenticated).
"""

import os
import logging
from flask import g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

logger = logging.getLogger(__name__)


def _rate_limit_key():
    """Rate limit key: user_id when authenticated, IP when not."""
    return getattr(g, 'user_id', None) or get_remote_address()


REDIS_URL = os.getenv('REDIS_URL')

limiter = Limiter(
    key_func=_rate_limit_key,
    storage_uri=REDIS_URL or "memory://",   # fall back to in-memory if no Redis
    default_limits=["200 per minute"],
    headers_enabled=True,                   # expose X-RateLimit-* headers
)


def init_limiter(app):
    """Attach the limiter to the Flask app."""
    limiter.init_app(app)
    if not REDIS_URL:
        logger.warning("REDIS_URL not set — rate limiter using in-memory storage (not suitable for multi-process)")


# ─── Per-Endpoint Limit Strings ───────────────────────────────
# Use these as: @limiter.limit(LIMIT_CHAT)

LIMIT_CHAT = "10 per minute"          # AI calls are expensive
LIMIT_FORECAST = "5 per minute"       # Prophet is slow
LIMIT_TRADING = "30 per minute"       # Paper trading writes
LIMIT_PORTFOLIO = "60 per minute"     # Portfolio reads/writes
LIMIT_PUBLIC = "120 per minute"       # Public stock data reads
