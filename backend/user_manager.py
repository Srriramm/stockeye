"""
user_manager.py — User profile and beta access control.

Manages two tables:
  - app_users:      every user who has signed in, with role + access status
  - invited_emails: pre-approved email whitelist for invite-only beta

Admin bootstrap: set ADMIN_USER_IDS=<uuid1>,<uuid2> in .env.
Those users are auto-promoted to role='admin', status='approved' on first login.
"""

import os
import time
import logging
from db import get_db_connection

logger = logging.getLogger(__name__)

# Comma-separated UUIDs — these users get admin + approved on first login
ADMIN_USER_IDS = {x.strip() for x in os.getenv('ADMIN_USER_IDS', '').split(',') if x.strip()}


# ─── Redis cache for user status ───────────────────────────────
# Caches "status,role" string per user_id to speed up before_request checks.
_redis_client = None
_redis_unavailable_until = 0.0
_REDIS_RETRY_INTERVAL = 60

def _get_redis():
    global _redis_client, _redis_unavailable_until
    if _redis_client is not None:
        return _redis_client
    now = time.monotonic()
    if now < _redis_unavailable_until:
        return None
    redis_url = os.getenv('REDIS_URL')
    if not redis_url:
        return None
    try:
        import redis as _r
        client = _r.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        _redis_client = client
        _redis_unavailable_until = 0.0
        return _redis_client
    except Exception as e:
        logger.warning(f"Redis unavailable for user cache: {e}")
        _redis_unavailable_until = now + _REDIS_RETRY_INTERVAL
        return None


def _cache_user_status(user_id: str, status: str, role: str):
    r = _get_redis()
    if r:
        try:
            r.setex(f"stockeye:user:{user_id}", 300, f"{status},{role}")
        except Exception:
            pass


def _invalidate_user_cache(user_id: str):
    r = _get_redis()
    if r:
        try:
            r.delete(f"stockeye:user:{user_id}")
        except Exception:
            pass


def get_cached_user_status(user_id: str):
    """Returns (status, role) from Redis, or None if not cached."""
    r = _get_redis()
    if r:
        try:
            val = r.get(f"stockeye:user:{user_id}")
            if val:
                parts = val.decode().split(',', 1)
                if len(parts) == 2:
                    return parts[0], parts[1]
        except Exception:
            pass
    return None


# ─── Core user functions ────────────────────────────────────────

def ensure_user_registered(user_id: str, email: str,
                            full_name=None, avatar_url=None) -> dict:
    """
    Upsert user into app_users on every login.

    New users:
      - admin UUIDs (from ADMIN_USER_IDS) → role='admin', status='approved'
      - email in invited_emails → status='approved'
      - otherwise → status='rejected'

    Existing users: update last_seen_at and profile fields (name/avatar).
    Returns the full app_users row as a dict.
    """
    with get_db_connection() as conn:
        existing = conn.execute(
            'SELECT * FROM app_users WHERE user_id = ?', (user_id,)
        ).fetchone()

        if existing:
            # Re-check admin status on every login so adding ADMIN_USER_IDS
            # to .env promotes already-registered users without manual SQL.
            if user_id in ADMIN_USER_IDS and (
                existing['role'] != 'admin' or existing['status'] != 'approved'
            ):
                conn.execute(
                    "UPDATE app_users SET role = 'admin', status = 'approved', "
                    'last_seen_at = CURRENT_TIMESTAMP, '
                    'full_name = COALESCE(?, full_name), '
                    'avatar_url = COALESCE(?, avatar_url) '
                    'WHERE user_id = ?',
                    (full_name, avatar_url, user_id)
                )
                logger.info(f"Admin bootstrap: promoted existing user {email} to admin/approved")
            else:
                conn.execute(
                    'UPDATE app_users SET last_seen_at = CURRENT_TIMESTAMP, '
                    'full_name = COALESCE(?, full_name), '
                    'avatar_url = COALESCE(?, avatar_url) '
                    'WHERE user_id = ?',
                    (full_name, avatar_url, user_id)
                )
            row = conn.execute(
                'SELECT * FROM app_users WHERE user_id = ?', (user_id,)
            ).fetchone()
            result = dict(row)
            _cache_user_status(user_id, result['status'], result['role'])
            return result

        # New user — determine role and status
        if user_id in ADMIN_USER_IDS:
            role, status = 'admin', 'approved'
        else:
            invited = conn.execute(
                'SELECT id FROM invited_emails WHERE LOWER(email) = LOWER(?)', (email,)
            ).fetchone()
            role = 'user'
            status = 'approved' if invited else 'rejected'

        conn.execute(
            'INSERT INTO app_users '
            '(user_id, email, full_name, avatar_url, role, status, last_seen_at) '
            'VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)',
            (user_id, email, full_name, avatar_url, role, status)
        )
        row = conn.execute(
            'SELECT * FROM app_users WHERE user_id = ?', (user_id,)
        ).fetchone()
        result = dict(row)
        _cache_user_status(user_id, result['status'], result['role'])
        logger.info(f"New user registered: {email} → role={role}, status={status}")
        return result


def get_user_record(user_id: str) -> dict | None:
    """Return the app_users row for user_id, or None if not registered."""
    with get_db_connection() as conn:
        row = conn.execute(
            'SELECT * FROM app_users WHERE user_id = ?', (user_id,)
        ).fetchone()
        return dict(row) if row else None


# ─── Admin CRUD ─────────────────────────────────────────────────

def list_users(status=None, limit=100, offset=0) -> list:
    """Admin: list all users, optionally filtered by status."""
    with get_db_connection() as conn:
        if status and status != 'all':
            rows = conn.execute(
                'SELECT * FROM app_users WHERE status = ? '
                'ORDER BY created_at DESC LIMIT ? OFFSET ?',
                (status, limit, offset)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM app_users '
                'ORDER BY created_at DESC LIMIT ? OFFSET ?',
                (limit, offset)
            ).fetchall()
        return [dict(r) for r in rows]


def update_user_status(user_id: str, status: str, approved_by: str = None) -> bool:
    """Admin: change a user's access status. Returns True on success."""
    if status not in {'approved', 'rejected', 'suspended'}:
        return False
    with get_db_connection() as conn:
        if status == 'approved':
            conn.execute(
                'UPDATE app_users SET status = ?, approved_by = ?, '
                'approved_at = CURRENT_TIMESTAMP WHERE user_id = ?',
                (status, approved_by, user_id)
            )
        else:
            conn.execute(
                'UPDATE app_users SET status = ? WHERE user_id = ?',
                (status, user_id)
            )
    _invalidate_user_cache(user_id)
    return True


def update_user_role(user_id: str, role: str) -> bool:
    """Admin: promote or demote a user. Returns True on success."""
    if role not in {'admin', 'user'}:
        return False
    with get_db_connection() as conn:
        conn.execute(
            'UPDATE app_users SET role = ? WHERE user_id = ?', (role, user_id)
        )
    _invalidate_user_cache(user_id)
    return True


def update_user_notes(user_id: str, notes: str) -> bool:
    """Admin: save internal notes on a user."""
    with get_db_connection() as conn:
        conn.execute(
            'UPDATE app_users SET notes = ? WHERE user_id = ?', (notes, user_id)
        )
    return True


def get_system_stats() -> dict:
    """Admin: user counts grouped by status."""
    with get_db_connection() as conn:
        rows = conn.execute(
            'SELECT status, COUNT(*) AS cnt FROM app_users GROUP BY status'
        ).fetchall()
        total_row = conn.execute(
            'SELECT COUNT(*) AS cnt FROM app_users'
        ).fetchone()
    counts = {r['status']: r['cnt'] for r in rows}
    return {
        'total':     total_row['cnt'] if total_row else 0,
        'approved':  counts.get('approved', 0),
        'rejected':  counts.get('rejected', 0),
        'suspended': counts.get('suspended', 0),
    }


# ─── Invite list ────────────────────────────────────────────────

def list_invited_emails(limit=200, offset=0) -> list:
    """Admin: all entries in the invited_emails whitelist."""
    with get_db_connection() as conn:
        rows = conn.execute(
            'SELECT ie.*, au.email AS added_by_email '
            'FROM invited_emails ie '
            'LEFT JOIN app_users au ON ie.added_by = au.user_id '
            'ORDER BY ie.created_at DESC LIMIT ? OFFSET ?',
            (limit, offset)
        ).fetchall()
        return [dict(r) for r in rows]


def add_invited_email(email: str, added_by: str = None, notes: str = None) -> dict:
    """
    Admin: add an email to the invite whitelist.
    Auto-approves any existing rejected user with that email.
    Returns {'email': ..., 'auto_approved': <count>}.
    """
    email = email.lower().strip()
    affected_ids = []

    with get_db_connection() as conn:
        conn.execute(
            'INSERT OR IGNORE INTO invited_emails (email, added_by, notes) '
            'VALUES (?, ?, ?)',
            (email, added_by, notes)
        )
        conn.execute(
            "UPDATE app_users SET status = 'approved', approved_by = ?, "
            "approved_at = CURRENT_TIMESTAMP "
            "WHERE LOWER(email) = ? AND status = 'rejected'",
            (added_by, email)
        )
        rows = conn.execute(
            'SELECT user_id FROM app_users WHERE LOWER(email) = ?', (email,)
        ).fetchall()
        affected_ids = [r['user_id'] for r in rows]

    for uid in affected_ids:
        _invalidate_user_cache(uid)

    logger.info(f"Invite added: {email} (auto_approved={len(affected_ids)})")
    return {'email': email, 'auto_approved': len(affected_ids)}


def remove_invited_email(email: str) -> bool:
    """
    Admin: remove an email from the whitelist.
    Already-approved users are NOT reverted — only future sign-ups are affected.
    """
    email = email.lower().strip()
    with get_db_connection() as conn:
        conn.execute(
            'DELETE FROM invited_emails WHERE LOWER(email) = ?', (email,)
        )
    return True
