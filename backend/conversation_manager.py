"""
conversation_manager.py — Per-user conversation & message storage.
Each user has multiple named conversations; each has a list of messages.
"""

import logging
from datetime import datetime
from db import get_db_connection

logger = logging.getLogger(__name__)


# ─── Conversations ───────────────────────────────────────────────

def create_conversation(user_id: str, title: str = 'New Chat') -> int:
    """Create a new conversation for a user. Returns conversation id."""
    with get_db_connection() as conn:
        cur = conn.execute(
            'INSERT INTO conversations (user_id, title) VALUES (?, ?)',
            (user_id, title)
        )
        return cur.lastrowid


def get_conversations(user_id: str) -> list:
    """Get all conversations for a user, newest first."""
    with get_db_connection() as conn:
        rows = conn.execute('''
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   COUNT(m.id) AS message_count
            FROM conversations c
            LEFT JOIN conversation_messages m ON m.conversation_id = c.id
            WHERE c.user_id = ?
            GROUP BY c.id
            ORDER BY c.updated_at DESC
        ''', (user_id,)).fetchall()
        return [dict(r) for r in rows]


def get_conversation(user_id: str, conversation_id: int) -> dict | None:
    """Get a single conversation with its messages."""
    with get_db_connection() as conn:
        row = conn.execute(
            'SELECT * FROM conversations WHERE id = ? AND user_id = ?',
            (conversation_id, user_id)
        ).fetchone()
        if not row:
            return None
        conv = dict(row)
        messages = conn.execute('''
            SELECT id, role, content, created_at
            FROM conversation_messages
            WHERE conversation_id = ? AND user_id = ?
            ORDER BY created_at ASC
        ''', (conversation_id, user_id)).fetchall()
        conv['messages'] = [dict(m) for m in messages]
        return conv


def rename_conversation(user_id: str, conversation_id: int, title: str) -> bool:
    """Rename a conversation."""
    with get_db_connection() as conn:
        cur = conn.execute('''
            UPDATE conversations SET title = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
        ''', (title, conversation_id, user_id))
        return cur.rowcount > 0


def delete_conversation(user_id: str, conversation_id: int) -> bool:
    """Delete a conversation and all its messages."""
    with get_db_connection() as conn:
        cur = conn.execute(
            'DELETE FROM conversations WHERE id = ? AND user_id = ?',
            (conversation_id, user_id)
        )
        return cur.rowcount > 0


def delete_all_conversations(user_id: str) -> int:
    """Delete all conversations (and their messages) for a user. Returns rows deleted."""
    with get_db_connection() as conn:
        cur = conn.execute(
            'DELETE FROM conversations WHERE user_id = ?',
            (user_id,)
        )
        return cur.rowcount


# ─── Messages ────────────────────────────────────────────────────

def add_message(user_id: str, conversation_id: int, role: str, content: str) -> int:
    """Add a message to a conversation. Returns message id."""
    with get_db_connection() as conn:
        cur = conn.execute('''
            INSERT INTO conversation_messages (user_id, conversation_id, role, content)
            VALUES (?, ?, ?, ?)
        ''', (user_id, conversation_id, role, content))
        msg_id = cur.lastrowid
        # Bump conversations.updated_at
        conn.execute('''
            UPDATE conversations SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
        ''', (conversation_id, user_id))
        return msg_id


def get_messages(user_id: str, conversation_id: int, limit: int = 50) -> list:
    """Get recent messages for a conversation (for AI context)."""
    with get_db_connection() as conn:
        rows = conn.execute('''
            SELECT role, content FROM conversation_messages
            WHERE conversation_id = ? AND user_id = ?
            ORDER BY created_at DESC LIMIT ?
        ''', (conversation_id, user_id, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]


def get_all_user_messages(user_id: str, limit: int = 200) -> tuple[list, int | None]:
    """
    Fetch recent messages for a user across ALL conversations in a single query.
    Returns (messages, latest_conversation_id).
    Messages are in ascending time order (oldest first, newest last).
    """
    with get_db_connection() as conn:
        # Get the most-recent conversation_id in one shot
        latest = conn.execute(
            'SELECT id FROM conversations WHERE user_id = ? ORDER BY updated_at DESC LIMIT 1',
            (user_id,)
        ).fetchone()
        if not latest:
            return [], None
        latest_cid = latest['id'] if isinstance(latest, dict) else latest[0]

        # Fetch all messages in one query, oldest first, capped at limit
        rows = conn.execute('''
            SELECT role, content
            FROM conversation_messages
            WHERE user_id = ?
            ORDER BY created_at ASC
        ''', (user_id,)).fetchall()
        msgs = [dict(r) for r in rows]
        # Keep only the most recent `limit` messages
        return msgs[-limit:], latest_cid


def get_or_create_conversation(user_id: str, conversation_id: int | None = None) -> int:
    """
    Return existing conversation_id if valid for this user,
    otherwise create a fresh one and return its id.
    """
    if conversation_id:
        with get_db_connection() as conn:
            row = conn.execute(
                'SELECT id FROM conversations WHERE id = ? AND user_id = ?',
                (conversation_id, user_id)
            ).fetchone()
            if row:
                return conversation_id
    return create_conversation(user_id)
