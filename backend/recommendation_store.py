"""
Recommendation Store — DB layer for agent_recommendations table.
All functions require user_id as the first parameter for per-user isolation.
"""

import json
import logging
from datetime import datetime
from db import get_db_connection

logger = logging.getLogger(__name__)


def init_agent_recommendations_table():
    """Create the agent_recommendations table for local SQLite (dev mode).
    Supabase/PostgreSQL: apply schema.sql manually via setup_db.py instead.
    """
    from db import DB_TYPE
    if DB_TYPE == 'postgres':
        return
    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS agent_recommendations (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      TEXT NOT NULL,
                ticker       TEXT NOT NULL,
                action       TEXT NOT NULL,
                confidence   REAL NOT NULL DEFAULT 0,
                reasoning    TEXT NOT NULL DEFAULT '',
                entry_price  REAL,
                target_price REAL,
                stop_loss    REAL,
                risk_reward  REAL,
                timeframe    TEXT DEFAULT 'short',
                key_factors  TEXT DEFAULT '[]',
                model_used   TEXT,
                data_sources TEXT DEFAULT '[]',
                session      TEXT,
                is_read      BOOLEAN DEFAULT 0,
                is_dismissed BOOLEAN DEFAULT 0,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_agent_recs_user
            ON agent_recommendations(user_id, created_at)
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_agent_recs_unread
            ON agent_recommendations(user_id, is_read, is_dismissed)
        ''')
    logger.info("agent_recommendations table ready (SQLite).")


def create_recommendation(user_id: str, ticker: str, data: dict) -> int:
    """Persist an agent recommendation to DB. Returns the new row id."""
    key_factors = data.get('key_factors', [])
    data_sources = data.get('data_sources', [])

    with get_db_connection() as conn:
        cur = conn.execute('''
            INSERT INTO agent_recommendations
                (user_id, ticker, action, confidence, reasoning,
                 entry_price, target_price, stop_loss, risk_reward,
                 timeframe, key_factors, model_used, data_sources, session)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            ticker.upper(),
            data.get('action', 'HOLD'),
            data.get('confidence', 0.0),
            data.get('reasoning', ''),
            data.get('entry_price'),
            data.get('target_price'),
            data.get('stop_loss'),
            data.get('risk_reward'),
            data.get('timeframe', 'short'),
            json.dumps(key_factors) if isinstance(key_factors, list) else key_factors,
            data.get('model_used'),
            json.dumps(data_sources) if isinstance(data_sources, list) else data_sources,
            data.get('session', 'manual'),
        ))
        return cur.lastrowid


def get_recommendations(user_id: str, limit: int = 20,
                        unread_only: bool = False, ticker: str = None) -> list:
    """Fetch recommendations for a user, newest first. Excludes dismissed."""
    conditions = ['user_id = ?', 'is_dismissed = FALSE']
    params = [user_id]

    if unread_only:
        conditions.append('is_read = FALSE')
    if ticker:
        conditions.append('ticker = ?')
        params.append(ticker.upper())

    where = ' AND '.join(conditions)
    params.append(limit)

    with get_db_connection() as conn:
        rows = conn.execute(
            f'SELECT * FROM agent_recommendations WHERE {where} '
            f'ORDER BY created_at DESC LIMIT ?',
            params
        ).fetchall()

    result = []
    for row in rows:
        rec = dict(row)
        # Deserialize JSON fields
        for field in ('key_factors', 'data_sources'):
            raw = rec.get(field)
            if raw and isinstance(raw, str):
                try:
                    rec[field] = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    rec[field] = []
        result.append(rec)
    return result


def get_recommendation_by_id(user_id: str, rec_id: int) -> dict | None:
    """Fetch a single recommendation, verified to belong to user."""
    with get_db_connection() as conn:
        row = conn.execute(
            'SELECT * FROM agent_recommendations WHERE id = ? AND user_id = ?',
            (rec_id, user_id)
        ).fetchone()

    if not row:
        return None

    rec = dict(row)
    for field in ('key_factors', 'data_sources'):
        raw = rec.get(field)
        if raw and isinstance(raw, str):
            try:
                rec[field] = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                rec[field] = []
    return rec


def mark_recommendation_read(user_id: str, rec_id: int) -> bool:
    """Mark a recommendation as read."""
    with get_db_connection() as conn:
        conn.execute(
            'UPDATE agent_recommendations SET is_read = TRUE WHERE id = ? AND user_id = ?',
            (rec_id, user_id)
        )
    return True


def dismiss_recommendation(user_id: str, rec_id: int) -> bool:
    """Dismiss (soft-delete) a recommendation."""
    with get_db_connection() as conn:
        conn.execute(
            'UPDATE agent_recommendations SET is_dismissed = TRUE WHERE id = ? AND user_id = ?',
            (rec_id, user_id)
        )
    return True


def get_unread_count(user_id: str) -> int:
    """Return count of unread, non-dismissed recommendations."""
    with get_db_connection() as conn:
        row = conn.execute(
            'SELECT COUNT(*) as cnt FROM agent_recommendations '
            'WHERE user_id = ? AND is_read = FALSE AND is_dismissed = FALSE',
            (user_id,)
        ).fetchone()
    return row['cnt'] if row else 0
