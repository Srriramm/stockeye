"""
Trading Manager - Mock/Paper Trading System
Buy/Sell orders, order types, order history, P&L tracking
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / 'database' / 'stock_assistant.db'


class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"
    STOP_LOSS_MARKET = "STOP_LOSS_MARKET"


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


def init_trading_tables():
    """Initialize trading database tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Orders table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            name TEXT,
            side TEXT NOT NULL,
            order_type TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL,
            stop_price REAL,
            limit_price REAL,
            status TEXT DEFAULT 'PENDING',
            executed_price REAL,
            executed_quantity REAL,
            executed_at TIMESTAMP,
            brokerage REAL DEFAULT 0,
            taxes REAL DEFAULT 0,
            total_cost REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    ''')

    # Trades table (executed orders)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            ticker TEXT NOT NULL,
            side TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            brokerage REAL DEFAULT 0,
            taxes REAL DEFAULT 0,
            total_amount REAL NOT NULL,
            executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(id)
        )
    ''')

    # Trading portfolio (separate from main portfolio)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trading_portfolio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT UNIQUE NOT NULL,
            name TEXT,
            quantity REAL NOT NULL,
            avg_buy_price REAL NOT NULL,
            total_investment REAL NOT NULL,
            sector TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Trading balance
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trading_balance (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            balance REAL DEFAULT 100000.0,
            invested REAL DEFAULT 0,
            pnl REAL DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Initialize default balance if not exists
    cursor.execute('INSERT OR IGNORE INTO trading_balance (id, balance) VALUES (1, 100000.0)')

    conn.commit()
    conn.close()
    logger.info("Trading tables initialized")


# ═══════════════════════════════════════════════════════════════
# ORDER PLACEMENT
# ═══════════════════════════════════════════════════════════════

def calculate_charges(price, quantity, side):
    """
    Calculate brokerage and taxes for Indian markets.

    Typical charges:
    - Brokerage: 0.03% or ₹20 per order (whichever is lower)
    - STT: 0.025% on sell side
    - Exchange charges: 0.00325%
    - GST: 18% on brokerage
    - SEBI charges: ₹10 per crore
    - Stamp duty: 0.015% on buy side
    """
    trade_value = price * quantity

    # Brokerage
    brokerage = min(trade_value * 0.0003, 20)

    # STT (Securities Transaction Tax) - only on sell
    stt = (trade_value * 0.00025) if side == OrderSide.SELL.value else 0

    # Exchange charges
    exchange_charges = trade_value * 0.0000325

    # GST on brokerage
    gst = brokerage * 0.18

    # SEBI charges
    sebi_charges = (trade_value / 10000000) * 10  # ₹10 per crore

    # Stamp duty - only on buy
    stamp_duty = (trade_value * 0.00015) if side == OrderSide.BUY.value else 0

    total_charges = brokerage + stt + exchange_charges + gst + sebi_charges + stamp_duty

    return {
        'brokerage': round(brokerage, 2),
        'taxes': round(total_charges - brokerage, 2),
        'total': round(total_charges, 2)
    }


def place_order(ticker, name, side, order_type, quantity, price=None, stop_price=None, limit_price=None):
    """
    Place a trading order.

    Args:
        ticker: Stock symbol
        name: Stock name
        side: BUY or SELL
        order_type: MARKET, LIMIT, STOP_LOSS, STOP_LOSS_MARKET
        quantity: Number of shares
        price: Market price for MARKET orders
        stop_price: Trigger price for STOP_LOSS orders
        limit_price: Limit price for LIMIT/STOP_LOSS orders

    Returns:
        Order ID if successful, None otherwise
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Validate order
        if order_type == OrderType.LIMIT.value and not limit_price:
            raise ValueError("Limit price required for LIMIT orders")

        if order_type in [OrderType.STOP_LOSS.value, OrderType.STOP_LOSS_MARKET.value] and not stop_price:
            raise ValueError("Stop price required for STOP_LOSS orders")

        # Calculate charges
        execution_price = price or limit_price or stop_price
        charges = calculate_charges(execution_price, quantity, side)

        # Check balance for BUY orders
        if side == OrderSide.BUY.value:
            cursor.execute('SELECT balance FROM trading_balance WHERE id = 1')
            balance = cursor.fetchone()[0]

            total_cost = (execution_price * quantity) + charges['total']

            if balance < total_cost:
                raise ValueError(f"Insufficient balance. Required: ₹{total_cost:.2f}, Available: ₹{balance:.2f}")

        # Check holdings for SELL orders
        if side == OrderSide.SELL.value:
            cursor.execute('SELECT quantity FROM trading_portfolio WHERE ticker = ?', (ticker,))
            result = cursor.fetchone()

            if not result or result[0] < quantity:
                available = result[0] if result else 0
                raise ValueError(f"Insufficient holdings. Required: {quantity}, Available: {available}")

        # Insert order
        cursor.execute('''
            INSERT INTO orders (ticker, name, side, order_type, quantity, price, stop_price, limit_price,
                              brokerage, taxes, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING')
        ''', (ticker, name, side, order_type, quantity, price, stop_price, limit_price,
              charges['brokerage'], charges['taxes']))

        order_id = cursor.lastrowid

        # Auto-execute MARKET orders
        if order_type == OrderType.MARKET.value:
            execute_order(order_id, price, cursor)

        conn.commit()
        logger.info(f"Order placed: {side} {quantity} {ticker} at ₹{execution_price}")
        return order_id

    except Exception as e:
        conn.rollback()
        logger.error(f"Error placing order: {e}")
        raise
    finally:
        conn.close()


def execute_order(order_id, execution_price, cursor=None):
    """Execute a pending order."""
    should_close = cursor is None

    if cursor is None:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

    try:
        # Get order details
        cursor.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
        order = cursor.fetchone()

        if not order:
            raise ValueError(f"Order {order_id} not found")

        order_dict = dict(zip([d[0] for d in cursor.description], order))

        if order_dict['status'] != 'PENDING':
            raise ValueError(f"Order {order_id} is not pending")

        ticker = order_dict['ticker']
        side = order_dict['side']
        quantity = order_dict['quantity']

        # Calculate total amount
        charges = calculate_charges(execution_price, quantity, side)
        total_amount = (execution_price * quantity) + (charges['total'] if side == OrderSide.BUY.value else -charges['total'])

        # Update order
        cursor.execute('''
            UPDATE orders
            SET status = 'EXECUTED',
                executed_price = ?,
                executed_quantity = ?,
                total_cost = ?,
                executed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (execution_price, quantity, total_amount, order_id))

        # Create trade record
        cursor.execute('''
            INSERT INTO trades (order_id, ticker, side, quantity, price, brokerage, taxes, total_amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (order_id, ticker, side, quantity, execution_price, charges['brokerage'], charges['total'], total_amount))

        # Update balance
        if side == OrderSide.BUY.value:
            cursor.execute('UPDATE trading_balance SET balance = balance - ?, invested = invested + ? WHERE id = 1',
                         (total_amount, execution_price * quantity))

            # Add to portfolio
            cursor.execute('SELECT quantity, avg_buy_price FROM trading_portfolio WHERE ticker = ?', (ticker,))
            existing = cursor.fetchone()

            if existing:
                old_qty, old_avg = existing
                new_qty = old_qty + quantity
                new_avg = ((old_qty * old_avg) + (quantity * execution_price)) / new_qty

                cursor.execute('''
                    UPDATE trading_portfolio
                    SET quantity = ?, avg_buy_price = ?, total_investment = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE ticker = ?
                ''', (new_qty, new_avg, new_qty * new_avg, ticker))
            else:
                cursor.execute('''
                    INSERT INTO trading_portfolio (ticker, name, quantity, avg_buy_price, total_investment)
                    VALUES (?, ?, ?, ?, ?)
                ''', (ticker, order_dict['name'], quantity, execution_price, quantity * execution_price))

        elif side == OrderSide.SELL.value:
            cursor.execute('UPDATE trading_balance SET balance = balance + ? WHERE id = 1', (total_amount,))

            # Update portfolio
            cursor.execute('SELECT quantity FROM trading_portfolio WHERE ticker = ?', (ticker,))
            current_qty = cursor.fetchone()[0]

            new_qty = current_qty - quantity

            if new_qty <= 0:
                cursor.execute('DELETE FROM trading_portfolio WHERE ticker = ?', (ticker,))
            else:
                cursor.execute('''
                    UPDATE trading_portfolio
                    SET quantity = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE ticker = ?
                ''', (new_qty, ticker))

        if should_close:
            conn.commit()

        logger.info(f"Order {order_id} executed at ₹{execution_price}")

    finally:
        if should_close:
            conn.close()


def cancel_order(order_id):
    """Cancel a pending order."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE orders
        SET status = 'CANCELLED', updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND status = 'PENDING'
    ''', (order_id,))

    success = cursor.rowcount > 0
    conn.commit()
    conn.close()

    return success


# ═══════════════════════════════════════════════════════════════
# ORDER QUERIES
# ═══════════════════════════════════════════════════════════════

def get_order_by_id(order_id):
    """Get order details."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
    order = cursor.fetchone()

    conn.close()

    return dict(order) if order else None


def get_orders(status=None, limit=50):
    """Get orders with optional status filter."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if status:
        cursor.execute('SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC LIMIT ?', (status, limit))
    else:
        cursor.execute('SELECT * FROM orders ORDER BY created_at DESC LIMIT ?', (limit,))

    orders = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return orders


def get_trades(limit=50):
    """Get executed trades."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM trades ORDER BY executed_at DESC LIMIT ?', (limit,))
    trades = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return trades


# ═══════════════════════════════════════════════════════════════
# PORTFOLIO QUERIES
# ═══════════════════════════════════════════════════════════════

def get_trading_portfolio():
    """Get trading portfolio with current values."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM trading_portfolio')
    holdings = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return holdings


def get_trading_balance():
    """Get trading account balance and stats."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM trading_balance WHERE id = 1')
    balance = dict(cursor.fetchone())

    conn.close()
    return balance


def reset_trading_account():
    """Reset trading account to initial state."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('DELETE FROM orders')
    cursor.execute('DELETE FROM trades')
    cursor.execute('DELETE FROM trading_portfolio')
    cursor.execute('UPDATE trading_balance SET balance = 100000.0, invested = 0, pnl = 0 WHERE id = 1')

    conn.commit()
    conn.close()

    logger.info("Trading account reset")


# Initialize tables on import
init_trading_tables()
