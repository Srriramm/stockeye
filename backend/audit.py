"""
audit.py — Non-blocking audit event logging.

Call log_event() at mutation points (portfolio add/delete, trade place/cancel,
watchlist operations, auth failures) to build a tamper-evident audit trail.

The audit_log table must exist in the database (see schema.sql).
Write failures are logged but never propagate to the caller.
"""

import json
import logging
from flask import g, request

logger = logging.getLogger(__name__)


def log_event(user_id, event_type, entity_type=None, entity_id=None, details=None):
    """
    Write an audit log entry.

    Args:
        user_id:      UUID of the acting user (or None for unauthenticated/system events)
        event_type:   Dot-namespaced event string, e.g. 'portfolio.add', 'trade.place',
                      'auth.unauthorized', 'alert.create'
        entity_type:  Type of the affected record, e.g. 'holding', 'order', 'watchlist'
        entity_id:    Integer PK of the affected record (optional)
        details:      Dict of additional context (ticker, amount, reason, etc.)

    Common event_type values:
        auth.unauthorized       auth.token_expired
        portfolio.add           portfolio.update        portfolio.delete
        trade.place             trade.cancel            account.reset
        watchlist.create        watchlist.delete        watchlist.stock_add
        alert.create            alert.delete
        chat.request
    """
    try:
        from db import get_db_connection
        with get_db_connection() as conn:
            conn.execute('''
                INSERT INTO audit_log
                    (user_id, event_type, entity_type, entity_id,
                     ip_address, user_agent, request_id, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                str(user_id) if user_id else None,
                event_type,
                entity_type,
                entity_id,
                _safe_ip(),
                _safe_ua(),
                getattr(g, 'request_id', None),
                json.dumps(details or {}),
            ))
    except Exception as e:
        # Audit log failures must never break the main request flow
        logger.error(f"audit_log write failed [{event_type}]: {e}")


def _safe_ip():
    try:
        return request.remote_addr
    except RuntimeError:
        return None


def _safe_ua():
    try:
        ua = request.headers.get('User-Agent', '')
        return ua[:500] if ua else None
    except RuntimeError:
        return None
