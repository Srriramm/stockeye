"""
Watchlist Manager - Manage multiple watchlists with stocks
Allows users to create, organize, and track stocks in custom watchlists.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / 'database' / 'stock_assistant.db'


def init_watchlist_tables():
    """Initialize watchlist database tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Watchlists table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watchlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            color TEXT DEFAULT '#3b82f6',
            position INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Watchlist items table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watchlist_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watchlist_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            name TEXT,
            sector TEXT,
            position INTEGER DEFAULT 0,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (watchlist_id) REFERENCES watchlists(id) ON DELETE CASCADE,
            UNIQUE(watchlist_id, ticker)
        )
    ''')

    # Create default watchlist if none exists
    cursor.execute('SELECT COUNT(*) FROM watchlists')
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO watchlists (name, description, color, position)
            VALUES ('My Watchlist', 'Default watchlist', '#3b82f6', 0)
        ''')

    conn.commit()
    conn.close()
    logger.info("Watchlist tables initialized")


# ═══════════════════════════════════════════════════════════════
# WATCHLIST OPERATIONS
# ═══════════════════════════════════════════════════════════════

def create_watchlist(name, description='', color='#3b82f6'):
    """Create a new watchlist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get max position
    cursor.execute('SELECT MAX(position) FROM watchlists')
    max_pos = cursor.fetchone()[0]
    position = (max_pos or 0) + 1

    cursor.execute('''
        INSERT INTO watchlists (name, description, color, position)
        VALUES (?, ?, ?, ?)
    ''', (name, description, color, position))

    watchlist_id = cursor.lastrowid
    conn.commit()
    conn.close()

    logger.info(f"Created watchlist: {name} (ID: {watchlist_id})")
    return watchlist_id


def get_all_watchlists():
    """Get all watchlists with item counts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT
            w.id,
            w.name,
            w.description,
            w.color,
            w.position,
            w.created_at,
            w.updated_at,
            COUNT(wi.id) as item_count
        FROM watchlists w
        LEFT JOIN watchlist_items wi ON w.id = wi.watchlist_id
        GROUP BY w.id
        ORDER BY w.position ASC
    ''')

    watchlists = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return watchlists


def get_watchlist_by_id(watchlist_id):
    """Get a specific watchlist with all its items."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get watchlist info
    cursor.execute('SELECT * FROM watchlists WHERE id = ?', (watchlist_id,))
    watchlist = cursor.fetchone()

    if not watchlist:
        conn.close()
        return None

    watchlist = dict(watchlist)

    # Get watchlist items
    cursor.execute('''
        SELECT * FROM watchlist_items
        WHERE watchlist_id = ?
        ORDER BY position ASC
    ''', (watchlist_id,))

    watchlist['items'] = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return watchlist


def update_watchlist(watchlist_id, name=None, description=None, color=None):
    """Update watchlist properties."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    updates = []
    params = []

    if name is not None:
        updates.append('name = ?')
        params.append(name)
    if description is not None:
        updates.append('description = ?')
        params.append(description)
    if color is not None:
        updates.append('color = ?')
        params.append(color)

    if not updates:
        conn.close()
        return False

    updates.append('updated_at = CURRENT_TIMESTAMP')
    params.append(watchlist_id)

    query = f"UPDATE watchlists SET {', '.join(updates)} WHERE id = ?"
    cursor.execute(query, params)

    success = cursor.rowcount > 0
    conn.commit()
    conn.close()

    return success


def delete_watchlist(watchlist_id):
    """Delete a watchlist and all its items."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('DELETE FROM watchlists WHERE id = ?', (watchlist_id,))
    success = cursor.rowcount > 0

    conn.commit()
    conn.close()

    logger.info(f"Deleted watchlist ID: {watchlist_id}")
    return success


def reorder_watchlists(watchlist_ids):
    """Reorder watchlists by providing ordered list of IDs."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for position, watchlist_id in enumerate(watchlist_ids):
        cursor.execute(
            'UPDATE watchlists SET position = ? WHERE id = ?',
            (position, watchlist_id)
        )

    conn.commit()
    conn.close()
    return True


# ═══════════════════════════════════════════════════════════════
# WATCHLIST ITEM OPERATIONS
# ═══════════════════════════════════════════════════════════════

def add_stock_to_watchlist(watchlist_id, ticker, name='', sector=''):
    """Add a stock to a watchlist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if stock already exists in this watchlist
    cursor.execute(
        'SELECT id FROM watchlist_items WHERE watchlist_id = ? AND ticker = ?',
        (watchlist_id, ticker.upper())
    )

    if cursor.fetchone():
        conn.close()
        logger.warning(f"{ticker} already in watchlist {watchlist_id}")
        return None

    # Get max position in this watchlist
    cursor.execute(
        'SELECT MAX(position) FROM watchlist_items WHERE watchlist_id = ?',
        (watchlist_id,)
    )
    max_pos = cursor.fetchone()[0]
    position = (max_pos or 0) + 1

    cursor.execute('''
        INSERT INTO watchlist_items (watchlist_id, ticker, name, sector, position)
        VALUES (?, ?, ?, ?, ?)
    ''', (watchlist_id, ticker.upper(), name, sector, position))

    item_id = cursor.lastrowid

    # Update watchlist timestamp
    cursor.execute(
        'UPDATE watchlists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (watchlist_id,)
    )

    conn.commit()
    conn.close()

    logger.info(f"Added {ticker} to watchlist {watchlist_id}")
    return item_id


def remove_stock_from_watchlist(watchlist_id, ticker):
    """Remove a stock from a watchlist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        'DELETE FROM watchlist_items WHERE watchlist_id = ? AND ticker = ?',
        (watchlist_id, ticker.upper())
    )

    success = cursor.rowcount > 0

    if success:
        # Update watchlist timestamp
        cursor.execute(
            'UPDATE watchlists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            (watchlist_id,)
        )

    conn.commit()
    conn.close()

    logger.info(f"Removed {ticker} from watchlist {watchlist_id}")
    return success


def reorder_watchlist_items(watchlist_id, ticker_order):
    """Reorder items in a watchlist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for position, ticker in enumerate(ticker_order):
        cursor.execute('''
            UPDATE watchlist_items
            SET position = ?
            WHERE watchlist_id = ? AND ticker = ?
        ''', (position, watchlist_id, ticker.upper()))

    # Update watchlist timestamp
    cursor.execute(
        'UPDATE watchlists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?',
        (watchlist_id,)
    )

    conn.commit()
    conn.close()
    return True


def move_stock_to_watchlist(ticker, from_watchlist_id, to_watchlist_id):
    """Move a stock from one watchlist to another."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get stock info
    cursor.execute(
        'SELECT name, sector FROM watchlist_items WHERE watchlist_id = ? AND ticker = ?',
        (from_watchlist_id, ticker.upper())
    )

    result = cursor.fetchone()
    if not result:
        conn.close()
        return False

    name, sector = result

    # Remove from old watchlist
    cursor.execute(
        'DELETE FROM watchlist_items WHERE watchlist_id = ? AND ticker = ?',
        (from_watchlist_id, ticker.upper())
    )

    # Add to new watchlist (if not already there)
    cursor.execute(
        'SELECT id FROM watchlist_items WHERE watchlist_id = ? AND ticker = ?',
        (to_watchlist_id, ticker.upper())
    )

    if cursor.fetchone():
        conn.commit()
        conn.close()
        return True  # Already in target watchlist

    # Get max position in target watchlist
    cursor.execute(
        'SELECT MAX(position) FROM watchlist_items WHERE watchlist_id = ?',
        (to_watchlist_id,)
    )
    max_pos = cursor.fetchone()[0]
    position = (max_pos or 0) + 1

    cursor.execute('''
        INSERT INTO watchlist_items (watchlist_id, ticker, name, sector, position)
        VALUES (?, ?, ?, ?, ?)
    ''', (to_watchlist_id, ticker.upper(), name, sector, position))

    conn.commit()
    conn.close()

    logger.info(f"Moved {ticker} from watchlist {from_watchlist_id} to {to_watchlist_id}")
    return True


def get_stock_in_watchlists(ticker):
    """Get all watchlists containing a specific stock."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT w.id, w.name, w.color
        FROM watchlists w
        JOIN watchlist_items wi ON w.id = wi.watchlist_id
        WHERE wi.ticker = ?
        ORDER BY w.position ASC
    ''', (ticker.upper(),))

    watchlists = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return watchlists


# ═══════════════════════════════════════════════════════════════
# SEARCH & FILTER
# ═══════════════════════════════════════════════════════════════

def search_watchlist_stocks(watchlist_id, query):
    """Search stocks within a watchlist."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM watchlist_items
        WHERE watchlist_id = ?
        AND (ticker LIKE ? OR name LIKE ?)
        ORDER BY position ASC
    ''', (watchlist_id, f'%{query}%', f'%{query}%'))

    items = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return items


# Initialize tables on import
init_watchlist_tables()
