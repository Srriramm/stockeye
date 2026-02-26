"""
Portfolio Manager - per-user database operations for portfolio management.
All public functions require user_id as the first parameter.
"""

import logging
from datetime import datetime, timedelta
from db import get_db_connection

logger = logging.getLogger(__name__)


def init_database():
    """Initialize local-SQLite tables (skipped when using Supabase — run setup_db.py instead)."""
    from db import DB_TYPE
    if DB_TYPE == 'postgres':
        logger.info("Supabase active — skipping local init_database(). Run setup_db.py to create tables.")
        return
    with get_db_connection() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
            ticker TEXT NOT NULL, name TEXT NOT NULL, quantity REAL NOT NULL,
            buy_price REAL NOT NULL, purchase_date TEXT NOT NULL,
            sector TEXT DEFAULT '', exchange TEXT DEFAULT 'NSE',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS monitored_stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
            ticker TEXT NOT NULL, name TEXT DEFAULT '', is_active BOOLEAN DEFAULT 1,
            price_baseline REAL DEFAULT 0, volume_avg_30d REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, ticker))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
            ticker TEXT NOT NULL, alert_type TEXT NOT NULL, message TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info', is_read BOOLEAN DEFAULT 0,
            data TEXT DEFAULT '{}', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS price_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
            ticker TEXT NOT NULL, target_price REAL NOT NULL,
            direction TEXT NOT NULL DEFAULT 'above', is_active BOOLEAN DEFAULT 1,
            triggered BOOLEAN DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS portfolio_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
            total_value REAL NOT NULL, total_investment REAL NOT NULL,
            pnl REAL NOT NULL, pnl_percent REAL NOT NULL, snapshot_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, snapshot_date))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL DEFAULT 'local',
            role TEXT NOT NULL, content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    logger.info("Local database initialized.")


# ─── Holdings ───────────────────────────────────────────────────

def add_holding(user_id, ticker, name, quantity, buy_price, purchase_date, sector='', exchange='NSE'):
    with get_db_connection() as conn:
        cur = conn.execute('''
            INSERT INTO holdings (user_id, ticker, name, quantity, buy_price, purchase_date, sector, exchange)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, ticker.upper(), name, quantity, buy_price, purchase_date, sector, exchange))
        return cur.lastrowid


def get_all_holdings(user_id):
    with get_db_connection() as conn:
        rows = conn.execute(
            'SELECT * FROM holdings WHERE user_id = ? ORDER BY created_at DESC', (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_holding_by_id(user_id, holding_id):
    with get_db_connection() as conn:
        row = conn.execute(
            'SELECT * FROM holdings WHERE id = ? AND user_id = ?', (holding_id, user_id)
        ).fetchone()
        return dict(row) if row else None


def update_holding(user_id, holding_id, data):
    ALLOWED = {'quantity', 'buy_price', 'purchase_date', 'sector', 'exchange', 'name'}
    updates = {k: v for k, v in data.items() if k in ALLOWED}
    if not updates:
        raise ValueError("No valid fields to update")
    set_clause = ', '.join(f'{k} = ?' for k in updates)
    values = list(updates.values()) + [holding_id, user_id]
    with get_db_connection() as conn:
        conn.execute(f'UPDATE holdings SET {set_clause} WHERE id = ? AND user_id = ?', values)
        return True


def delete_holding(user_id, holding_id):
    with get_db_connection() as conn:
        conn.execute('DELETE FROM holdings WHERE id = ? AND user_id = ?', (holding_id, user_id))
        return True


def calculate_portfolio_value(user_id, current_prices):
    holdings = get_all_holdings(user_id)
    total_value = total_investment = 0
    holdings_data = []
    for h in holdings:
        ticker = h['ticker']
        current_price = current_prices.get(ticker, h['buy_price'])
        investment = h['quantity'] * h['buy_price']
        current_val = h['quantity'] * current_price
        pnl = current_val - investment
        pnl_pct = (pnl / investment * 100) if investment > 0 else 0
        total_value += current_val
        total_investment += investment
        holdings_data.append({**h, 'current_price': current_price,
            'investment': round(investment, 2), 'current_value': round(current_val, 2),
            'pnl': round(pnl, 2), 'pnl_percent': round(pnl_pct, 2), 'portfolio_percent': 0})
    for h in holdings_data:
        h['portfolio_percent'] = round((h['current_value'] / total_value * 100) if total_value > 0 else 0, 2)
    total_pnl = total_value - total_investment
    return {'holdings': holdings_data, 'total_value': round(total_value, 2),
            'total_investment': round(total_investment, 2), 'total_pnl': round(total_pnl, 2),
            'total_pnl_percent': round((total_pnl / total_investment * 100) if total_investment > 0 else 0, 2),
            'num_holdings': len(holdings_data)}


def get_portfolio_stats(user_id, current_prices):
    portfolio = calculate_portfolio_value(user_id, current_prices)
    holdings = portfolio['holdings']
    if not holdings:
        return {**portfolio, 'best_performer': None, 'worst_performer': None, 'sectors': {}}
    best  = max(holdings, key=lambda x: x['pnl_percent'])
    worst = min(holdings, key=lambda x: x['pnl_percent'])
    sectors = {}
    for h in holdings:
        s = h.get('sector') or 'Unknown'
        sectors[s] = sectors.get(s, 0) + h['current_value']
    return {**portfolio,
            'best_performer':  {'ticker': best['ticker'],  'name': best['name'],  'pnl_percent': best['pnl_percent']},
            'worst_performer': {'ticker': worst['ticker'], 'name': worst['name'], 'pnl_percent': worst['pnl_percent']},
            'sectors': sectors}


# ─── Monitored Stocks ───────────────────────────────────────────

def start_monitoring(user_id, ticker, name='', price_baseline=0, volume_avg=0):
    with get_db_connection() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO monitored_stocks
            (user_id, ticker, name, is_active, price_baseline, volume_avg_30d)
            VALUES (?, ?, ?, TRUE, ?, ?)
        ''', (user_id, ticker.upper(), name, price_baseline, volume_avg))
        return True


def stop_monitoring(user_id, ticker):
    with get_db_connection() as conn:
        conn.execute('UPDATE monitored_stocks SET is_active = FALSE WHERE ticker = ? AND user_id = ?',
                     (ticker.upper(), user_id))
        return True


def sync_portfolio_to_monitors(user_id):
    holdings = get_all_holdings(user_id)
    for h in holdings:
        start_monitoring(user_id, h['ticker'], h.get('name', h['ticker']))
    return len(holdings)


def get_monitored_stocks(user_id, active_only=True):
    with get_db_connection() as conn:
        if active_only:
            rows = conn.execute(
                'SELECT * FROM monitored_stocks WHERE user_id = ? AND is_active = TRUE', (user_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM monitored_stocks WHERE user_id = ?', (user_id,)
            ).fetchall()
        return [dict(r) for r in rows]


def update_monitor_baseline(user_id, ticker, price, volume_avg):
    with get_db_connection() as conn:
        conn.execute('''
            UPDATE monitored_stocks SET price_baseline = ?, volume_avg_30d = ?
            WHERE ticker = ? AND user_id = ?
        ''', (price, volume_avg, ticker.upper(), user_id))


# ─── Alerts ─────────────────────────────────────────────────────

def create_alert(user_id, ticker, alert_type, message, severity='info', data='{}'):
    with get_db_connection() as conn:
        cur = conn.execute('''
            INSERT INTO alerts (user_id, ticker, alert_type, message, severity, data)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, ticker.upper(), alert_type, message, severity, data))
        return cur.lastrowid


def get_recent_alerts(user_id, hours=24, limit=50):
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    with get_db_connection() as conn:
        rows = conn.execute('''
            SELECT * FROM alerts WHERE user_id = ? AND created_at >= ?
            ORDER BY created_at DESC LIMIT ?
        ''', (user_id, cutoff, limit)).fetchall()
        return [dict(r) for r in rows]


def get_alerts_for_ticker(user_id, ticker, limit=20):
    with get_db_connection() as conn:
        rows = conn.execute('''
            SELECT * FROM alerts WHERE user_id = ? AND ticker = ?
            ORDER BY created_at DESC LIMIT ?
        ''', (user_id, ticker.upper(), limit)).fetchall()
        return [dict(r) for r in rows]


def mark_alert_read(user_id, alert_id):
    with get_db_connection() as conn:
        conn.execute('UPDATE alerts SET is_read = TRUE WHERE id = ? AND user_id = ?', (alert_id, user_id))


def clear_old_alerts(user_id, days=7):
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    with get_db_connection() as conn:
        conn.execute('DELETE FROM alerts WHERE user_id = ? AND created_at < ?', (user_id, cutoff))


# ─── Price Alerts ───────────────────────────────────────────────

def add_price_alert(user_id, ticker, target_price, direction='above'):
    with get_db_connection() as conn:
        cur = conn.execute('''
            INSERT INTO price_alerts (user_id, ticker, target_price, direction)
            VALUES (?, ?, ?, ?)
        ''', (user_id, ticker.upper(), target_price, direction))
        return cur.lastrowid


def get_active_price_alerts(user_id):
    with get_db_connection() as conn:
        rows = conn.execute('''
            SELECT * FROM price_alerts WHERE user_id = ? AND is_active = TRUE AND triggered = FALSE
        ''', (user_id,)).fetchall()
        return [dict(r) for r in rows]


def trigger_price_alert(user_id, alert_id):
    with get_db_connection() as conn:
        conn.execute('UPDATE price_alerts SET triggered = TRUE WHERE id = ? AND user_id = ?', (alert_id, user_id))


# ─── Portfolio Snapshots ────────────────────────────────────────

def save_portfolio_snapshot(user_id, total_value, total_investment, pnl, pnl_percent):
    today = datetime.now().strftime('%Y-%m-%d')
    with get_db_connection() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO portfolio_snapshots
            (user_id, total_value, total_investment, pnl, pnl_percent, snapshot_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, total_value, total_investment, pnl, pnl_percent, today))


def get_portfolio_history(user_id, days=30):
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    with get_db_connection() as conn:
        rows = conn.execute('''
            SELECT * FROM portfolio_snapshots WHERE user_id = ? AND snapshot_date >= ?
            ORDER BY snapshot_date ASC
        ''', (user_id, cutoff)).fetchall()
        return [dict(r) for r in rows]


# ─── Chat History (legacy — prefer conversation_manager) ────────

def save_chat_message(user_id, role, content):
    with get_db_connection() as conn:
        conn.execute('INSERT INTO chat_history (user_id, role, content) VALUES (?, ?, ?)',
                     (user_id, role, content))


def get_chat_history(user_id, limit=20):
    with get_db_connection() as conn:
        rows = conn.execute('''
            SELECT * FROM chat_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?
        ''', (user_id, limit)).fetchall()
        return [dict(r) for r in reversed(rows)]


def clear_chat_history(user_id):
    with get_db_connection() as conn:
        conn.execute('DELETE FROM chat_history WHERE user_id = ?', (user_id,))


# ─── Global (cross-user) helpers for background monitoring service ───

def get_all_monitored_stocks_global(active_only=True):
    """Get monitored stocks across ALL users (for background monitor service)."""
    with get_db_connection() as conn:
        if active_only:
            rows = conn.execute(
                'SELECT * FROM monitored_stocks WHERE is_active = TRUE'
            ).fetchall()
        else:
            rows = conn.execute('SELECT * FROM monitored_stocks').fetchall()
        return [dict(r) for r in rows]


def get_all_active_price_alerts_global():
    """Get active price alerts across ALL users (for background monitor service)."""
    with get_db_connection() as conn:
        rows = conn.execute(
            'SELECT * FROM price_alerts WHERE is_active = TRUE AND triggered = FALSE'
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_holdings_global():
    """Get holdings across ALL users (for portfolio snapshot service)."""
    with get_db_connection() as conn:
        rows = conn.execute('SELECT * FROM holdings ORDER BY user_id').fetchall()
        return [dict(r) for r in rows]


def update_monitor_baseline_global(ticker, price, volume_avg):
    """Update baseline for a ticker across ALL users who monitor it."""
    with get_db_connection() as conn:
        conn.execute('''
            UPDATE monitored_stocks SET price_baseline = ?, volume_avg_30d = ?
            WHERE ticker = ? AND is_active = TRUE
        ''', (price, volume_avg, ticker.upper()))


# Initialize local DB on import (no-op for Supabase)
init_database()

