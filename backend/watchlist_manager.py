"""
Watchlist Manager - per-user watchlist management.
All public functions require user_id as the first parameter.
"""

import logging
from db import get_db_connection

logger = logging.getLogger(__name__)


def init_watchlist_tables():
    from db import DB_TYPE
    if DB_TYPE == 'postgres':
        return
    with get_db_connection() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS watchlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
            name TEXT NOT NULL, description TEXT, color TEXT DEFAULT '#3b82f6',
            position INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS watchlist_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
            watchlist_id INTEGER NOT NULL, ticker TEXT NOT NULL, name TEXT, sector TEXT,
            position INTEGER DEFAULT 0, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (watchlist_id) REFERENCES watchlists(id) ON DELETE CASCADE,
            UNIQUE(watchlist_id, ticker))''')
        row = conn.execute('SELECT COUNT(*) FROM watchlists').fetchone()
        if row[0] == 0:
            conn.execute('''INSERT INTO watchlists (user_id, name, description, color, position)
                VALUES ('local', 'My Watchlist', 'Default watchlist', '#3b82f6', 0)''')


def create_watchlist(user_id, name, description='', color='#3b82f6'):
    with get_db_connection() as conn:
        row = conn.execute('SELECT MAX(position) FROM watchlists WHERE user_id = ?', (user_id,)).fetchone()
        position = (row[0] or 0) + 1
        cur = conn.execute('''
            INSERT INTO watchlists (user_id, name, description, color, position)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, name, description, color, position))
        return cur.lastrowid


def get_all_watchlists(user_id):
    with get_db_connection() as conn:
        rows = conn.execute('''
            SELECT w.id, w.name, w.description, w.color, w.position,
                   w.created_at, w.updated_at, COUNT(wi.id) as item_count
            FROM watchlists w
            LEFT JOIN watchlist_items wi ON w.id = wi.watchlist_id
            WHERE w.user_id = ?
            GROUP BY w.id ORDER BY w.position ASC
        ''', (user_id,)).fetchall()
        return [dict(r) for r in rows]


def get_watchlist_by_id(user_id, watchlist_id):
    with get_db_connection() as conn:
        row = conn.execute('SELECT * FROM watchlists WHERE id = ? AND user_id = ?',
                           (watchlist_id, user_id)).fetchone()
        if not row:
            return None
        wl = dict(row)
        items = conn.execute('''SELECT * FROM watchlist_items WHERE watchlist_id = ?
                                ORDER BY position ASC''', (watchlist_id,)).fetchall()
        wl['items'] = [dict(i) for i in items]
        return wl


def update_watchlist(user_id, watchlist_id, name=None, description=None, color=None):
    updates, params = [], []
    if name        is not None: updates.append('name = ?');        params.append(name)
    if description is not None: updates.append('description = ?'); params.append(description)
    if color       is not None: updates.append('color = ?');       params.append(color)
    if not updates: return False
    updates.append('updated_at = CURRENT_TIMESTAMP')
    params += [watchlist_id, user_id]
    with get_db_connection() as conn:
        cur = conn.execute(f"UPDATE watchlists SET {', '.join(updates)} WHERE id = ? AND user_id = ?", params)
        return cur.rowcount > 0


def delete_watchlist(user_id, watchlist_id):
    with get_db_connection() as conn:
        cur = conn.execute('DELETE FROM watchlists WHERE id = ? AND user_id = ?', (watchlist_id, user_id))
        return cur.rowcount > 0


def reorder_watchlists(user_id, watchlist_ids):
    with get_db_connection() as conn:
        for pos, wid in enumerate(watchlist_ids):
            conn.execute('UPDATE watchlists SET position = ? WHERE id = ? AND user_id = ?', (pos, wid, user_id))
    return True


def add_stock_to_watchlist(user_id, watchlist_id, ticker, name='', sector=''):
    with get_db_connection() as conn:
        exists = conn.execute('SELECT id FROM watchlist_items WHERE watchlist_id = ? AND ticker = ?',
                              (watchlist_id, ticker.upper())).fetchone()
        if exists:
            return None
        row = conn.execute('SELECT MAX(position) FROM watchlist_items WHERE watchlist_id = ?',
                           (watchlist_id,)).fetchone()
        position = (row[0] or 0) + 1
        cur = conn.execute('''
            INSERT INTO watchlist_items (user_id, watchlist_id, ticker, name, sector, position)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, watchlist_id, ticker.upper(), name, sector, position))
        conn.execute('UPDATE watchlists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?', (watchlist_id,))
        return cur.lastrowid


def remove_stock_from_watchlist(user_id, watchlist_id, ticker):
    with get_db_connection() as conn:
        cur = conn.execute('DELETE FROM watchlist_items WHERE watchlist_id = ? AND ticker = ?',
                           (watchlist_id, ticker.upper()))
        if cur.rowcount > 0:
            conn.execute('UPDATE watchlists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?', (watchlist_id,))
        return cur.rowcount > 0


def reorder_watchlist_items(user_id, watchlist_id, ticker_order):
    with get_db_connection() as conn:
        for pos, ticker in enumerate(ticker_order):
            conn.execute('UPDATE watchlist_items SET position = ? WHERE watchlist_id = ? AND ticker = ?',
                         (pos, watchlist_id, ticker.upper()))
        conn.execute('UPDATE watchlists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?', (watchlist_id,))
    return True


def move_stock_to_watchlist(user_id, ticker, from_id, to_id):
    with get_db_connection() as conn:
        # Verify the user owns both the source and destination watchlists
        from_wl = conn.execute(
            'SELECT id FROM watchlists WHERE id = ? AND user_id = ?',
            (from_id, user_id)
        ).fetchone()
        to_wl = conn.execute(
            'SELECT id FROM watchlists WHERE id = ? AND user_id = ?',
            (to_id, user_id)
        ).fetchone()
        if not from_wl or not to_wl:
            return False

        row = conn.execute('SELECT name, sector FROM watchlist_items WHERE watchlist_id = ? AND ticker = ?',
                           (from_id, ticker.upper())).fetchone()
        if not row:
            return False
        name, sector = row[0], row[1]
        conn.execute('DELETE FROM watchlist_items WHERE watchlist_id = ? AND ticker = ?', (from_id, ticker.upper()))
        if conn.execute('SELECT id FROM watchlist_items WHERE watchlist_id = ? AND ticker = ?',
                        (to_id, ticker.upper())).fetchone():
            return True
        max_pos = conn.execute('SELECT MAX(position) FROM watchlist_items WHERE watchlist_id = ?',
                               (to_id,)).fetchone()
        conn.execute('''INSERT INTO watchlist_items (user_id, watchlist_id, ticker, name, sector, position)
                        VALUES (?, ?, ?, ?, ?, ?)''',
                     (user_id, to_id, ticker.upper(), name, sector, (max_pos[0] or 0) + 1))
    return True


def get_stock_in_watchlists(user_id, ticker):
    with get_db_connection() as conn:
        rows = conn.execute('''
            SELECT w.id, w.name, w.color FROM watchlists w
            JOIN watchlist_items wi ON w.id = wi.watchlist_id
            WHERE wi.ticker = ? AND w.user_id = ? ORDER BY w.position ASC
        ''', (ticker.upper(), user_id)).fetchall()
        return [dict(r) for r in rows]


def search_watchlist_stocks(user_id, watchlist_id, query):
    with get_db_connection() as conn:
        rows = conn.execute('''
            SELECT * FROM watchlist_items WHERE watchlist_id = ?
            AND (ticker LIKE ? OR name LIKE ?) ORDER BY position ASC
        ''', (watchlist_id, f'%{query}%', f'%{query}%')).fetchall()
        return [dict(r) for r in rows]


init_watchlist_tables()
