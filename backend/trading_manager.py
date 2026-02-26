"""
Trading Manager - per-user paper trading system.
All public functions require user_id as the first parameter.
"""

import logging
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


def init_trading_tables():
    from db import DB_TYPE
    if DB_TYPE == 'postgres':
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
    with get_db_connection() as conn:
        conn.execute('DELETE FROM orders WHERE user_id=?', (user_id,))
        conn.execute('DELETE FROM trades WHERE user_id=?', (user_id,))
        conn.execute('DELETE FROM trading_portfolio WHERE user_id=?', (user_id,))
        conn.execute('UPDATE trading_balance SET balance=100000.0, invested=0, pnl=0 WHERE user_id=?', (user_id,))
    logger.info(f"Trading account reset for user {user_id[:8]}")


# Backward-compat shim: expose execute_order for any external callers
def execute_order(order_id, execution_price, cursor=None):
    logger.warning("execute_order() is deprecated — use place_order() which auto-executes MARKET orders.")


init_trading_tables()
