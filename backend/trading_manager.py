"""
Trading Manager - per-user paper trading system.
All public functions require user_id as the first parameter.
"""

import logging
from datetime import datetime
from enum import Enum
from db import get_db_connection

logger = logging.getLogger(__name__)


class OrderType(Enum):
    MARKET = "MARKET"; LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"; STOP_LOSS_MARKET = "STOP_LOSS_MARKET"

class OrderSide(Enum):
    BUY = "BUY"; SELL = "SELL"

class OrderStatus(Enum):
    PENDING = "PENDING"; EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"; REJECTED = "REJECTED"


def _ensure_snapshots_table(conn):
    """Create trading_daily_snapshots if missing (works for both SQLite and Postgres)."""
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS trading_daily_snapshots (
            id              SERIAL PRIMARY KEY,
            user_id         TEXT NOT NULL,
            date            TEXT NOT NULL,
            portfolio_value REAL,
            cash_balance    REAL,
            invested        REAL,
            pnl             REAL,
            pnl_pct         REAL,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date))''')
    except Exception:
        pass  # table may already exist with a different DDL — ignore


def init_trading_tables():
    from db import DB_TYPE
    if DB_TYPE == 'postgres':
        # Ensure the snapshots table exists (may be missing on older deployments)
        with get_db_connection() as conn:
            _ensure_snapshots_table(conn)
        return
    with get_db_connection() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY, user_id TEXT NOT NULL, ticker TEXT NOT NULL, name TEXT,
            side TEXT NOT NULL, order_type TEXT NOT NULL, quantity REAL NOT NULL,
            price REAL, stop_price REAL, limit_price REAL, status TEXT DEFAULT 'PENDING',
            executed_price REAL, executed_quantity REAL, executed_at TIMESTAMP,
            brokerage REAL DEFAULT 0, taxes REAL DEFAULT 0, total_cost REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, notes TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
            order_id INTEGER, ticker TEXT NOT NULL, side TEXT NOT NULL,
            quantity REAL NOT NULL, price REAL NOT NULL, brokerage REAL DEFAULT 0,
            taxes REAL DEFAULT 0, total_amount REAL NOT NULL,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS trading_portfolio (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
            ticker TEXT NOT NULL, name TEXT, quantity REAL NOT NULL,
            avg_buy_price REAL NOT NULL, total_investment REAL NOT NULL,
            sector TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, ticker))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS trading_balance (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL UNIQUE,
            balance REAL DEFAULT 100000.0, invested REAL DEFAULT 0, pnl REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS trading_daily_snapshots (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    TEXT NOT NULL,
            date       TEXT NOT NULL,
            portfolio_value REAL,
            cash_balance    REAL,
            invested        REAL,
            pnl             REAL,
            pnl_pct         REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, date))''')
    logger.info("Trading tables initialized")


def _ensure_balance(conn, user_id):
    """Insert default balance row for new users if not exists."""
    conn.execute('INSERT OR IGNORE INTO trading_balance (user_id, balance) VALUES (?, 100000.0)', (user_id,))


def calculate_charges(price, quantity, side):
    trade_value = price * quantity
    brokerage = min(trade_value * 0.0003, 20)
    stt = (trade_value * 0.00025) if side == OrderSide.SELL.value else 0
    exchange_charges = trade_value * 0.0000325
    gst = brokerage * 0.18
    sebi = (trade_value / 10000000) * 10
    stamp = (trade_value * 0.00015) if side == OrderSide.BUY.value else 0
    total = brokerage + stt + exchange_charges + gst + sebi + stamp
    return {'brokerage': round(brokerage, 2), 'taxes': round(total - brokerage, 2), 'total': round(total, 2)}


def place_order(user_id, ticker, name, side, order_type, quantity, price=None, stop_price=None, limit_price=None):
    if order_type == OrderType.LIMIT.value and not limit_price:
        raise ValueError("Limit price required for LIMIT orders")
    if order_type in [OrderType.STOP_LOSS.value, OrderType.STOP_LOSS_MARKET.value] and not stop_price:
        raise ValueError("Stop price required for STOP_LOSS orders")

    exec_price = price or limit_price or stop_price
    charges = calculate_charges(exec_price, quantity, side)

    with get_db_connection() as conn:
        _ensure_balance(conn, user_id)

        if side == OrderSide.BUY.value:
            balance = conn.execute('SELECT balance FROM trading_balance WHERE user_id = ?', (user_id,)).fetchone()[0]
            total_cost = (exec_price * quantity) + charges['total']
            if balance < total_cost:
                raise ValueError(f"Insufficient balance. Required: ₹{total_cost:.2f}, Available: ₹{balance:.2f}")

        if side == OrderSide.SELL.value:
            result = conn.execute('SELECT quantity FROM trading_portfolio WHERE user_id = ? AND ticker = ?',
                                  (user_id, ticker)).fetchone()
            if not result or result[0] < quantity:
                raise ValueError(f"Insufficient holdings. Available: {result[0] if result else 0}")

        cur = conn.execute('''
            INSERT INTO orders (user_id, ticker, name, side, order_type, quantity, price,
                stop_price, limit_price, brokerage, taxes, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
        ''', (user_id, ticker, name, side, order_type, quantity, price, stop_price, limit_price,
              charges['brokerage'], charges['taxes']))
        order_id = cur.lastrowid

        if order_type == OrderType.MARKET.value:
            _execute_in_conn(conn, user_id, order_id, price, ticker, name, side, quantity, charges)

    logger.info(f"Order placed: {side} {quantity} {ticker} at ₹{exec_price} for user {user_id[:8]}")
    return order_id


def _execute_in_conn(conn, user_id, order_id, execution_price, ticker, name, side, quantity, charges):
    total_amount = (execution_price * quantity) + (charges['total'] if side == OrderSide.BUY.value else -charges['total'])
    conn.execute('''UPDATE orders SET status='EXECUTED', executed_price=?, executed_quantity=?,
        total_cost=?, executed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE id=?''',
        (execution_price, quantity, total_amount, order_id))
    conn.execute('''INSERT INTO trades (user_id, order_id, ticker, side, quantity, price, brokerage, taxes, total_amount)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (user_id, order_id, ticker, side, quantity, execution_price, charges['brokerage'], charges['total'], total_amount))

    if side == OrderSide.BUY.value:
        conn.execute('UPDATE trading_balance SET balance=balance-?, invested=invested+? WHERE user_id=?',
                     (total_amount, execution_price * quantity, user_id))
        existing = conn.execute('SELECT quantity, avg_buy_price FROM trading_portfolio WHERE user_id=? AND ticker=?',
                                (user_id, ticker)).fetchone()
        if existing:
            old_qty, old_avg = existing[0], existing[1]
            new_qty = old_qty + quantity
            new_avg = ((old_qty * old_avg) + (quantity * execution_price)) / new_qty
            conn.execute('UPDATE trading_portfolio SET quantity=?, avg_buy_price=?, total_investment=? WHERE user_id=? AND ticker=?',
                         (new_qty, new_avg, new_qty * new_avg, user_id, ticker))
        else:
            conn.execute('INSERT INTO trading_portfolio (user_id, ticker, name, quantity, avg_buy_price, total_investment) VALUES (?,?,?,?,?,?)',
                         (user_id, ticker, name, quantity, execution_price, quantity * execution_price))

    elif side == OrderSide.SELL.value:
        conn.execute('UPDATE trading_balance SET balance=balance+? WHERE user_id=?', (total_amount, user_id))
        current_qty = conn.execute('SELECT quantity FROM trading_portfolio WHERE user_id=? AND ticker=?',
                                   (user_id, ticker)).fetchone()[0]
        new_qty = current_qty - quantity
        if new_qty <= 0:
            conn.execute('DELETE FROM trading_portfolio WHERE user_id=? AND ticker=?', (user_id, ticker))
        else:
            conn.execute('UPDATE trading_portfolio SET quantity=? WHERE user_id=? AND ticker=?', (new_qty, user_id, ticker))


def cancel_order(user_id, order_id):
    with get_db_connection() as conn:
        cur = conn.execute("UPDATE orders SET status='CANCELLED', updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=? AND status='PENDING'",
                           (order_id, user_id))
        return cur.rowcount > 0


def get_order_by_id(user_id, order_id):
    with get_db_connection() as conn:
        row = conn.execute('SELECT * FROM orders WHERE id=? AND user_id=?', (order_id, user_id)).fetchone()
        return dict(row) if row else None


def get_orders(user_id, status=None, limit=50):
    with get_db_connection() as conn:
        if status:
            rows = conn.execute('SELECT * FROM orders WHERE user_id=? AND status=? ORDER BY created_at DESC LIMIT ?',
                                (user_id, status, limit)).fetchall()
        else:
            rows = conn.execute('SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT ?',
                                (user_id, limit)).fetchall()
        return [dict(r) for r in rows]


def get_trades(user_id, limit=50):
    with get_db_connection() as conn:
        rows = conn.execute('SELECT * FROM trades WHERE user_id=? ORDER BY executed_at DESC LIMIT ?',
                            (user_id, limit)).fetchall()
        return [dict(r) for r in rows]


def get_trading_portfolio(user_id):
    with get_db_connection() as conn:
        rows = conn.execute('SELECT * FROM trading_portfolio WHERE user_id=?', (user_id,)).fetchall()
        return [dict(r) for r in rows]


def get_trading_balance(user_id):
    with get_db_connection() as conn:
        _ensure_balance(conn, user_id)
        row = conn.execute('SELECT * FROM trading_balance WHERE user_id=?', (user_id,)).fetchone()
        return dict(row) if row else {'balance': 100000.0, 'invested': 0, 'pnl': 0}


def reset_trading_account(user_id):
    from db import DB_TYPE
    with get_db_connection() as conn:
        conn.execute('DELETE FROM orders WHERE user_id=?', (user_id,))
        conn.execute('DELETE FROM trades WHERE user_id=?', (user_id,))
        conn.execute('DELETE FROM trading_portfolio WHERE user_id=?', (user_id,))
        conn.execute('UPDATE trading_balance SET balance=100000.0, invested=0, pnl=0 WHERE user_id=?', (user_id,))
        # Delete snapshots — table may not exist on older deployments.
        # Use SAVEPOINT on Postgres so a missing-table error can't abort the outer tx.
        if DB_TYPE == 'postgres':
            conn.execute('SAVEPOINT sp_snap')
            try:
                conn.execute('DELETE FROM trading_daily_snapshots WHERE user_id=?', (user_id,))
                conn.execute('RELEASE SAVEPOINT sp_snap')
            except Exception:
                conn.execute('ROLLBACK TO SAVEPOINT sp_snap')
        else:
            try:
                conn.execute('DELETE FROM trading_daily_snapshots WHERE user_id=?', (user_id,))
            except Exception:
                pass
    logger.info(f"Trading account reset for user {user_id[:8]}")


def add_funds(user_id: str, amount: float) -> dict:
    """Add paper money to user's trading wallet."""
    if amount <= 0 or amount > 10_000_000:
        raise ValueError("Amount must be between ₹1 and ₹1,00,00,000")
    with get_db_connection() as conn:
        _ensure_balance(conn, user_id)
        conn.execute(
            'UPDATE trading_balance SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?',
            (amount, user_id)
        )
        row = conn.execute('SELECT * FROM trading_balance WHERE user_id = ?', (user_id,)).fetchone()
    return dict(row)


def snapshot_portfolio(user_id: str) -> None:
    """Save today's portfolio value snapshot for daily return tracking."""
    from stock_data import get_bulk_prices
    holdings    = get_trading_portfolio(user_id)
    balance_row = get_trading_balance(user_id)
    prices      = get_bulk_prices([h['ticker'] for h in holdings]) if holdings else {}
    invested    = sum(h['quantity'] * (prices.get(h['ticker']) or h['avg_buy_price']) for h in holdings)
    total       = balance_row['balance'] + invested
    today       = datetime.utcnow().strftime('%Y-%m-%d')
    with get_db_connection() as conn:
        prev = conn.execute(
            "SELECT portfolio_value FROM trading_daily_snapshots WHERE user_id = ? ORDER BY date DESC LIMIT 1",
            (user_id,)
        ).fetchone()
        prev_val = prev['portfolio_value'] if prev else total
        pnl      = round(total - prev_val, 2)
        pnl_pct  = round(pnl / prev_val * 100, 2) if prev_val else 0
        conn.execute(
            "INSERT OR REPLACE INTO trading_daily_snapshots "
            "(user_id, date, portfolio_value, cash_balance, invested, pnl, pnl_pct) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, today, round(total, 2), round(balance_row['balance'], 2),
             round(invested, 2), pnl, pnl_pct)
        )


def get_performance_history(user_id: str, days: int = 30) -> list:
    """Return day-wise portfolio snapshots, newest first."""
    try:
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM trading_daily_snapshots WHERE user_id = ? ORDER BY date DESC LIMIT ?",
                (user_id, days)
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"get_performance_history: table may not exist yet — {e}")
        return []


# Backward-compat shim: expose execute_order for any external callers
def execute_order(order_id, execution_price, cursor=None):
    logger.warning("execute_order() is deprecated — use place_order() which auto-executes MARKET orders.")


init_trading_tables()
