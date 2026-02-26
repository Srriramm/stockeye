"""
cache.py — Redis-backed cache helpers for stock market data.

Key namespaces and TTLs:
  stockeye:price:<TICKER>    30 seconds   (current price, high-frequency)
  stockeye:tech:<TICKER>     300 seconds  (technical indicators, 5 min)
  stockeye:news:<TICKER>     900 seconds  (news articles, 15 min)
  stockeye:indices:nse       60 seconds   (market indices, 1 min)
  stockeye:bulk:<hash>       30 seconds   (bulk price results)

Falls back gracefully if Redis is unavailable — all get functions return None
and callers fetch fresh data from yfinance/APIs as before.
"""

import os
import json
import hashlib
import logging

logger = logging.getLogger(__name__)

_redis_client = None


def _get_redis():
    """Return a shared Redis client, or None if unavailable."""
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv('REDIS_URL')
        if redis_url:
            try:
                import redis
                _redis_client = redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
                _redis_client.ping()
            except Exception as e:
                logger.warning(f"Redis unavailable for data cache: {e}")
                _redis_client = None
    return _redis_client


def _get(key: str):
    r = _get_redis()
    if not r:
        return None
    try:
        raw = r.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _set(key: str, value, ttl: int):
    r = _get_redis()
    if not r:
        return
    try:
        r.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        pass


# ─── Stock Price ──────────────────────────────────────────────

def get_cached_price(ticker: str):
    return _get(f"stockeye:price:{ticker.upper()}")


def cache_price(ticker: str, data, ttl: int = 30):
    _set(f"stockeye:price:{ticker.upper()}", data, ttl)


# ─── Technical Indicators ─────────────────────────────────────

def get_cached_technicals(ticker: str):
    return _get(f"stockeye:tech:{ticker.upper()}")


def cache_technicals(ticker: str, data, ttl: int = 300):
    _set(f"stockeye:tech:{ticker.upper()}", data, ttl)


# ─── News ─────────────────────────────────────────────────────

def get_cached_news(ticker: str):
    return _get(f"stockeye:news:{ticker.upper()}")


def cache_news(ticker: str, data, ttl: int = 900):
    _set(f"stockeye:news:{ticker.upper()}", data, ttl)


# ─── Market Indices ───────────────────────────────────────────

def get_cached_indices():
    return _get("stockeye:indices:nse")


def cache_indices(data, ttl: int = 60):
    _set("stockeye:indices:nse", data, ttl)


# ─── Bulk Prices ─────────────────────────────────────────────

def get_cached_bulk_prices(tickers: list):
    key = "stockeye:bulk:" + hashlib.md5(",".join(sorted(tickers)).encode()).hexdigest()
    return _get(key)


def cache_bulk_prices(tickers: list, data, ttl: int = 30):
    key = "stockeye:bulk:" + hashlib.md5(",".join(sorted(tickers)).encode()).hexdigest()
    _set(key, data, ttl)
