"""
Advanced Alert System - Enhanced price and technical alerts
Price targets, percentage changes, volume surges, RSI alerts, etc.
"""

import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from portfolio_manager import create_alert

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / 'database' / 'stock_assistant.db'


def init_advanced_alerts_table():
    """Initialize advanced alerts table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS advanced_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            condition TEXT NOT NULL,
            threshold_value REAL,
            current_value REAL,
            is_active INTEGER DEFAULT 1,
            triggered INTEGER DEFAULT 0,
            triggered_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    ''')

    conn.commit()
    conn.close()
    logger.info("Advanced alerts table initialized")


def create_price_alert(ticker, target_price, condition='above'):
    """
    Create price target alert.

    Args:
        ticker: Stock symbol
        target_price: Target price level
        condition: 'above' or 'below'
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO advanced_alerts (ticker, alert_type, condition, threshold_value)
        VALUES (?, 'PRICE_TARGET', ?, ?)
    ''', (ticker.upper(), condition, target_price))

    alert_id = cursor.lastrowid
    conn.commit()
    conn.close()

    logger.info(f"Price alert created: {ticker} {condition} ₹{target_price}")
    return alert_id


def create_percent_change_alert(ticker, percent_change, timeframe='1d'):
    """
    Create percentage change alert.

    Args:
        ticker: Stock symbol
        percent_change: Percentage threshold (e.g., 5 for 5%)
        timeframe: '1d', '1w', '1m'
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO advanced_alerts (ticker, alert_type, condition, threshold_value, notes)
        VALUES (?, 'PERCENT_CHANGE', ?, ?, ?)
    ''', (ticker.upper(), timeframe, abs(percent_change), f"{timeframe} timeframe"))

    alert_id = cursor.lastrowid
    conn.commit()
    conn.close()

    logger.info(f"Percent change alert created: {ticker} {percent_change}% in {timeframe}")
    return alert_id


def create_volume_surge_alert(ticker, volume_multiplier=2.0):
    """
    Create volume surge alert.

    Args:
        ticker: Stock symbol
        volume_multiplier: Alert when volume > X times average (default: 2x)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO advanced_alerts (ticker, alert_type, condition, threshold_value)
        VALUES (?, 'VOLUME_SURGE', 'multiplier', ?)
    ''', (ticker.upper(), volume_multiplier))

    alert_id = cursor.lastrowid
    conn.commit()
    conn.close()

    logger.info(f"Volume surge alert created: {ticker} > {volume_multiplier}x avg volume")
    return alert_id


def create_rsi_alert(ticker, rsi_level, condition='below'):
    """
    Create RSI alert.

    Args:
        ticker: Stock symbol
        rsi_level: RSI threshold (0-100)
        condition: 'above' or 'below'
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO advanced_alerts (ticker, alert_type, condition, threshold_value)
        VALUES (?, 'RSI_LEVEL', ?, ?)
    ''', (ticker.upper(), condition, rsi_level))

    alert_id = cursor.lastrowid
    conn.commit()
    conn.close()

    logger.info(f"RSI alert created: {ticker} RSI {condition} {rsi_level}")
    return alert_id


def create_moving_average_cross_alert(ticker, ma_type='sma_20'):
    """
    Create moving average crossover alert.

    Args:
        ticker: Stock symbol
        ma_type: 'sma_20', 'sma_50', 'sma_200', 'ema_12', 'ema_26'
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        INSERT INTO advanced_alerts (ticker, alert_type, condition, notes)
        VALUES (?, 'MA_CROSS', 'crossover', ?)
    ''', (ticker.upper(), ma_type))

    alert_id = cursor.lastrowid
    conn.commit()
    conn.close()

    logger.info(f"MA cross alert created: {ticker} price vs {ma_type}")
    return alert_id


def create_week_52_alert(ticker, alert_type='high'):
    """
    Create 52-week high/low alert.

    Args:
        ticker: Stock symbol
        alert_type: 'high' or 'low'
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    alert_name = 'WEEK_52_HIGH' if alert_type == 'high' else 'WEEK_52_LOW'

    cursor.execute('''
        INSERT INTO advanced_alerts (ticker, alert_type, condition)
        VALUES (?, ?, ?)
    ''', (ticker.upper(), alert_name, alert_type))

    alert_id = cursor.lastrowid
    conn.commit()
    conn.close()

    logger.info(f"52-week {alert_type} alert created: {ticker}")
    return alert_id


def check_price_alerts(ticker, current_price):
    """Check if price alerts should trigger."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM advanced_alerts
        WHERE ticker = ? AND alert_type = 'PRICE_TARGET' AND is_active = 1 AND triggered = 0
    ''', (ticker.upper(),))

    alerts = cursor.fetchall()
    triggered = []

    for alert in alerts:
        alert_dict = dict(alert)
        target = alert_dict['threshold_value']
        condition = alert_dict['condition']

        should_trigger = False

        if condition == 'above' and current_price >= target:
            should_trigger = True
        elif condition == 'below' and current_price <= target:
            should_trigger = True

        if should_trigger:
            # Mark as triggered
            cursor.execute('''
                UPDATE advanced_alerts
                SET triggered = 1, triggered_at = CURRENT_TIMESTAMP, current_value = ?
                WHERE id = ?
            ''', (current_price, alert_dict['id']))

            # Create notification alert
            create_alert(
                ticker,
                'PRICE_ALERT',
                f"{ticker} reached ₹{current_price:.2f} ({condition} ₹{target:.2f})",
                'high'
            )

            triggered.append(alert_dict)

    conn.commit()
    conn.close()

    return triggered


def check_volume_alerts(ticker, current_volume, avg_volume):
    """Check if volume surge alerts should trigger."""
    if avg_volume == 0:
        return []

    volume_ratio = current_volume / avg_volume

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM advanced_alerts
        WHERE ticker = ? AND alert_type = 'VOLUME_SURGE' AND is_active = 1 AND triggered = 0
    ''', (ticker.upper(),))

    alerts = cursor.fetchall()
    triggered = []

    for alert in alerts:
        alert_dict = dict(alert)
        threshold = alert_dict['threshold_value']

        if volume_ratio >= threshold:
            # Mark as triggered
            cursor.execute('''
                UPDATE advanced_alerts
                SET triggered = 1, triggered_at = CURRENT_TIMESTAMP, current_value = ?
                WHERE id = ?
            ''', (volume_ratio, alert_dict['id']))

            # Create notification
            create_alert(
                ticker,
                'VOLUME_SURGE',
                f"{ticker} volume surge: {volume_ratio:.2f}x average ({current_volume:,} vs {avg_volume:,})",
                'medium'
            )

            triggered.append(alert_dict)

    conn.commit()
    conn.close()

    return triggered


def check_rsi_alerts(ticker, current_rsi):
    """Check if RSI alerts should trigger."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT * FROM advanced_alerts
        WHERE ticker = ? AND alert_type = 'RSI_LEVEL' AND is_active = 1 AND triggered = 0
    ''', (ticker.upper(),))

    alerts = cursor.fetchall()
    triggered = []

    for alert in alerts:
        alert_dict = dict(alert)
        threshold = alert_dict['threshold_value']
        condition = alert_dict['condition']

        should_trigger = False

        if condition == 'above' and current_rsi >= threshold:
            should_trigger = True
        elif condition == 'below' and current_rsi <= threshold:
            should_trigger = True

        if should_trigger:
            # Mark as triggered
            cursor.execute('''
                UPDATE advanced_alerts
                SET triggered = 1, triggered_at = CURRENT_TIMESTAMP, current_value = ?
                WHERE id = ?
            ''', (current_rsi, alert_dict['id']))

            # Create notification
            status = 'Overbought' if current_rsi > 70 else 'Oversold' if current_rsi < 30 else 'Alert'
            create_alert(
                ticker,
                'RSI_ALERT',
                f"{ticker} RSI {status}: {current_rsi:.2f} ({condition} {threshold})",
                'medium'
            )

            triggered.append(alert_dict)

    conn.commit()
    conn.close()

    return triggered


def get_active_alerts(ticker=None):
    """Get all active alerts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if ticker:
        cursor.execute('''
            SELECT * FROM advanced_alerts
            WHERE ticker = ? AND is_active = 1
            ORDER BY created_at DESC
        ''', (ticker.upper(),))
    else:
        cursor.execute('''
            SELECT * FROM advanced_alerts
            WHERE is_active = 1
            ORDER BY created_at DESC
        ''')

    alerts = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return alerts


def delete_alert(alert_id):
    """Delete an alert."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('DELETE FROM advanced_alerts WHERE id = ?', (alert_id,))
    success = cursor.rowcount > 0

    conn.commit()
    conn.close()

    return success


def reset_alert(alert_id):
    """Reset a triggered alert to active again."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE advanced_alerts
        SET triggered = 0, triggered_at = NULL, current_value = NULL
        WHERE id = ?
    ''', (alert_id,))

    success = cursor.rowcount > 0
    conn.commit()
    conn.close()

    return success


# Initialize on import
init_advanced_alerts_table()
