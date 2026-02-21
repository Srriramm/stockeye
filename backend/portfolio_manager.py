"""
Portfolio Manager - SQLite database operations for portfolio management.
Handles CRUD operations for holdings, monitored stocks, and alerts.
"""

import sqlite3
import os
import logging
from datetime import datetime, timedelta
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DATABASE_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'portfolio.db')


def get_db_path():
    """Get the absolute path to the database file."""
    return os.path.abspath(DATABASE_PATH)


@contextmanager
def get_db_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception as e:
        logger.error(f"Database transaction failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database():
    """Initialize the database with required tables."""
    os.makedirs(os.path.dirname(get_db_path()), exist_ok=True)

    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                name TEXT NOT NULL,
                quantity REAL NOT NULL,
                buy_price REAL NOT NULL,
                purchase_date TEXT NOT NULL,
                sector TEXT DEFAULT '',
                exchange TEXT DEFAULT 'NSE',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS monitored_stocks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL UNIQUE,
                name TEXT DEFAULT '',
                is_active BOOLEAN DEFAULT 1,
                price_baseline REAL DEFAULT 0,
                volume_avg_30d REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                message TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'info',
                is_read BOOLEAN DEFAULT 0,
                data TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS price_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                target_price REAL NOT NULL,
                direction TEXT NOT NULL DEFAULT 'above',
                is_active BOOLEAN DEFAULT 1,
                triggered BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                total_value REAL NOT NULL,
                total_investment REAL NOT NULL,
                pnl REAL NOT NULL,
                pnl_percent REAL NOT NULL,
                snapshot_date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    print("Database initialized successfully.")


# ─── Holdings CRUD ──────────────────────────────────────────────

def add_holding(ticker, name, quantity, buy_price, purchase_date, sector='', exchange='NSE'):
    """Add a new stock holding to the portfolio."""
    with get_db_connection() as conn:
        cursor = conn.execute('''
            INSERT INTO holdings (ticker, name, quantity, buy_price, purchase_date, sector, exchange)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (ticker.upper(), name, quantity, buy_price, purchase_date, sector, exchange))
        return cursor.lastrowid


def get_all_holdings():
    """Fetch all holdings from the portfolio."""
    with get_db_connection() as conn:
        rows = conn.execute('SELECT * FROM holdings ORDER BY created_at DESC').fetchall()
        return [dict(row) for row in rows]


def get_holding_by_id(holding_id):
    """Fetch a single holding by ID."""
    with get_db_connection() as conn:
        row = conn.execute('SELECT * FROM holdings WHERE id = ?', (holding_id,)).fetchone()
        return dict(row) if row else None


def update_holding(holding_id, data):
    """Update a holding's information with strict field validation."""
    # Strict whitelist of allowed fields - prevents SQL injection
    ALLOWED_UPDATE_FIELDS = {'quantity', 'buy_price', 'purchase_date', 'sector', 'exchange', 'name'}

    # Filter to only allowed fields
    updates = {k: v for k, v in data.items() if k in ALLOWED_UPDATE_FIELDS}

    if not updates:
        raise ValueError("No valid fields to update")

    # Build safe SQL (field names are validated, values use parameters)
    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    values = list(updates.values()) + [holding_id]

    with get_db_connection() as conn:
        try:
            conn.execute(f'UPDATE holdings SET {set_clause} WHERE id = ?', values)
            return True
        except Exception as e:
            raise Exception(f"Failed to update holding: {str(e)}")


def delete_holding(holding_id):
    """Remove a stock from the portfolio."""
    with get_db_connection() as conn:
        conn.execute('DELETE FROM holdings WHERE id = ?', (holding_id,))
        return True


def calculate_portfolio_value(current_prices):
    """
    Calculate total portfolio value using current prices.
    current_prices: dict of {ticker: current_price}
    """
    holdings = get_all_holdings()
    total_value = 0
    total_investment = 0
    holdings_data = []

    for h in holdings:
        ticker = h['ticker']
        current_price = current_prices.get(ticker, h['buy_price'])
        investment = h['quantity'] * h['buy_price']
        current_val = h['quantity'] * current_price
        pnl = current_val - investment
        pnl_percent = (pnl / investment * 100) if investment > 0 else 0

        total_value += current_val
        total_investment += investment

        holdings_data.append({
            **h,
            'current_price': current_price,
            'investment': round(investment, 2),
            'current_value': round(current_val, 2),
            'pnl': round(pnl, 2),
            'pnl_percent': round(pnl_percent, 2),
            'portfolio_percent': 0  # calculated below
        })

    # Calculate portfolio percentage for each holding
    for h in holdings_data:
        h['portfolio_percent'] = round((h['current_value'] / total_value * 100) if total_value > 0 else 0, 2)

    total_pnl = total_value - total_investment
    total_pnl_percent = (total_pnl / total_investment * 100) if total_investment > 0 else 0

    return {
        'holdings': holdings_data,
        'total_value': round(total_value, 2),
        'total_investment': round(total_investment, 2),
        'total_pnl': round(total_pnl, 2),
        'total_pnl_percent': round(total_pnl_percent, 2),
        'num_holdings': len(holdings_data)
    }


def get_portfolio_stats(current_prices):
    """Calculate comprehensive portfolio statistics."""
    portfolio = calculate_portfolio_value(current_prices)
    holdings = portfolio['holdings']

    if not holdings:
        return {**portfolio, 'best_performer': None, 'worst_performer': None, 'sectors': {}}

    best = max(holdings, key=lambda x: x['pnl_percent'])
    worst = min(holdings, key=lambda x: x['pnl_percent'])

    # Sector allocation
    sectors = {}
    for h in holdings:
        sector = h.get('sector', 'Unknown') or 'Unknown'
        sectors[sector] = sectors.get(sector, 0) + h['current_value']

    return {
        **portfolio,
        'best_performer': {'ticker': best['ticker'], 'name': best['name'], 'pnl_percent': best['pnl_percent']},
        'worst_performer': {'ticker': worst['ticker'], 'name': worst['name'], 'pnl_percent': worst['pnl_percent']},
        'sectors': sectors
    }


# ─── Monitored Stocks ──────────────────────────────────────────

def start_monitoring(ticker, name='', price_baseline=0, volume_avg=0):
    """Add a stock to the monitoring list."""
    with get_db_connection() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO monitored_stocks (ticker, name, is_active, price_baseline, volume_avg_30d)
            VALUES (?, ?, 1, ?, ?)
        ''', (ticker.upper(), name, price_baseline, volume_avg))
        return True


def stop_monitoring(ticker):
    """Deactivate monitoring for a stock."""
    with get_db_connection() as conn:
        conn.execute('UPDATE monitored_stocks SET is_active = 0 WHERE ticker = ?', (ticker.upper(),))
        return True


def sync_portfolio_to_monitors():
    """Sync all portfolio holdings to monitored_stocks. Called at startup."""
    holdings = get_all_holdings()
    synced = 0
    for h in holdings:
        start_monitoring(h['ticker'], h.get('name', h['ticker']))
        synced += 1
    if synced:
        logger.info(f"Auto-synced {synced} portfolio holdings to monitoring")
    return synced


def get_monitored_stocks(active_only=True):
    """Fetch all monitored stocks."""
    with get_db_connection() as conn:
        if active_only:
            rows = conn.execute('SELECT * FROM monitored_stocks WHERE is_active = 1').fetchall()
        else:
            rows = conn.execute('SELECT * FROM monitored_stocks').fetchall()
        return [dict(row) for row in rows]


def update_monitor_baseline(ticker, price, volume_avg):
    """Update baseline values for a monitored stock."""
    with get_db_connection() as conn:
        conn.execute('''
            UPDATE monitored_stocks SET price_baseline = ?, volume_avg_30d = ? WHERE ticker = ?
        ''', (price, volume_avg, ticker.upper()))


# ─── Alerts ─────────────────────────────────────────────────────

def create_alert(ticker, alert_type, message, severity='info', data='{}'):
    """Create a new alert."""
    with get_db_connection() as conn:
        cursor = conn.execute('''
            INSERT INTO alerts (ticker, alert_type, message, severity, data)
            VALUES (?, ?, ?, ?, ?)
        ''', (ticker.upper(), alert_type, message, severity, data))
        return cursor.lastrowid


def get_recent_alerts(hours=24, limit=50):
    """Fetch recent alerts."""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    with get_db_connection() as conn:
        rows = conn.execute('''
            SELECT * FROM alerts WHERE created_at >= ? ORDER BY created_at DESC LIMIT ?
        ''', (cutoff, limit)).fetchall()
        return [dict(row) for row in rows]


def get_alerts_for_ticker(ticker, limit=20):
    """Fetch alerts for a specific stock."""
    with get_db_connection() as conn:
        rows = conn.execute('''
            SELECT * FROM alerts WHERE ticker = ? ORDER BY created_at DESC LIMIT ?
        ''', (ticker.upper(), limit)).fetchall()
        return [dict(row) for row in rows]


def mark_alert_read(alert_id):
    """Mark an alert as read."""
    with get_db_connection() as conn:
        conn.execute('UPDATE alerts SET is_read = 1 WHERE id = ?', (alert_id,))


def clear_old_alerts(days=7):
    """Clear alerts older than specified days."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    with get_db_connection() as conn:
        conn.execute('DELETE FROM alerts WHERE created_at < ?', (cutoff,))


# ─── Price Alerts ───────────────────────────────────────────────

def add_price_alert(ticker, target_price, direction='above'):
    """Set a custom price alert."""
    with get_db_connection() as conn:
        cursor = conn.execute('''
            INSERT INTO price_alerts (ticker, target_price, direction)
            VALUES (?, ?, ?)
        ''', (ticker.upper(), target_price, direction))
        return cursor.lastrowid


def get_active_price_alerts():
    """Fetch all active price alerts."""
    with get_db_connection() as conn:
        rows = conn.execute('''
            SELECT * FROM price_alerts WHERE is_active = 1 AND triggered = 0
        ''').fetchall()
        return [dict(row) for row in rows]


def trigger_price_alert(alert_id):
    """Mark a price alert as triggered."""
    with get_db_connection() as conn:
        conn.execute('UPDATE price_alerts SET triggered = 1 WHERE id = ?', (alert_id,))


# ─── Portfolio Snapshots ────────────────────────────────────────

def save_portfolio_snapshot(total_value, total_investment, pnl, pnl_percent):
    """Save a daily portfolio snapshot."""
    today = datetime.now().strftime('%Y-%m-%d')
    with get_db_connection() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO portfolio_snapshots (total_value, total_investment, pnl, pnl_percent, snapshot_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (total_value, total_investment, pnl, pnl_percent, today))


def get_portfolio_history(days=30):
    """Get portfolio value history."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    with get_db_connection() as conn:
        rows = conn.execute('''
            SELECT * FROM portfolio_snapshots WHERE snapshot_date >= ? ORDER BY snapshot_date ASC
        ''', (cutoff,)).fetchall()
        return [dict(row) for row in rows]


# ─── Chat History ───────────────────────────────────────────────

def save_chat_message(role, content):
    """Save a chat message."""
    with get_db_connection() as conn:
        conn.execute('INSERT INTO chat_history (role, content) VALUES (?, ?)', (role, content))


def get_chat_history(limit=20):
    """Get recent chat history."""
    with get_db_connection() as conn:
        rows = conn.execute('''
            SELECT * FROM chat_history ORDER BY created_at DESC LIMIT ?
        ''', (limit,)).fetchall()
        return [dict(row) for row in reversed(rows)]


def clear_chat_history():
    """Clear all chat history."""
    with get_db_connection() as conn:
        conn.execute('DELETE FROM chat_history')


# Initialize database on import
init_database()
