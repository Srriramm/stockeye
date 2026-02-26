"""
Advanced Alert System - per-user price and technical alerts.
All public functions require user_id as the first parameter.
"""

import logging
from db import get_db_connection

logger = logging.getLogger(__name__)


def init_advanced_alerts_table():
    from db import DB_TYPE
    if DB_TYPE == 'postgres':
        return
    with get_db_connection() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS advanced_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
            ticker TEXT NOT NULL, alert_type TEXT NOT NULL, condition TEXT NOT NULL,
            threshold_value REAL, current_value REAL, is_active INTEGER DEFAULT 1,
            triggered INTEGER DEFAULT 0, triggered_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, notes TEXT)''')
    logger.info("Advanced alerts table initialized")


def _insert_alert(user_id, ticker, alert_type, condition, threshold=None, notes=None):
    with get_db_connection() as conn:
        cur = conn.execute('''
            INSERT INTO advanced_alerts (user_id, ticker, alert_type, condition, threshold_value, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, ticker.upper(), alert_type, condition, threshold, notes))
        return cur.lastrowid


def create_price_alert(user_id, ticker, target_price, condition='above'):
    aid = _insert_alert(user_id, ticker, 'PRICE_TARGET', condition, target_price)
    logger.info(f"Price alert: {ticker} {condition} ₹{target_price}")
    return aid


def create_percent_change_alert(user_id, ticker, percent_change, timeframe='1d'):
    aid = _insert_alert(user_id, ticker, 'PERCENT_CHANGE', timeframe, abs(percent_change), f"{timeframe} timeframe")
    logger.info(f"Pct alert: {ticker} {percent_change}% in {timeframe}")
    return aid


def create_volume_surge_alert(user_id, ticker, volume_multiplier=2.0):
    aid = _insert_alert(user_id, ticker, 'VOLUME_SURGE', 'multiplier', volume_multiplier)
    logger.info(f"Volume surge alert: {ticker} >{volume_multiplier}x avg")
    return aid


def create_rsi_alert(user_id, ticker, rsi_level, condition='below'):
    aid = _insert_alert(user_id, ticker, 'RSI_LEVEL', condition, rsi_level)
    logger.info(f"RSI alert: {ticker} RSI {condition} {rsi_level}")
    return aid


def create_moving_average_cross_alert(user_id, ticker, ma_type='sma_20'):
    aid = _insert_alert(user_id, ticker, 'MA_CROSS', 'crossover', notes=ma_type)
    return aid


def create_week_52_alert(user_id, ticker, alert_type='high'):
    aid = _insert_alert(user_id, ticker, 'WEEK_52_HIGH' if alert_type == 'high' else 'WEEK_52_LOW', alert_type)
    return aid


def check_price_alerts(user_id, ticker, current_price):
    from portfolio_manager import create_alert
    triggered = []
    with get_db_connection() as conn:
        rows = conn.execute('''SELECT * FROM advanced_alerts
            WHERE user_id=? AND ticker=? AND alert_type='PRICE_TARGET' AND is_active=TRUE AND triggered=FALSE''',
            (user_id, ticker.upper())).fetchall()
        for alert in rows:
            a = dict(alert)
            hit = (a['condition'] == 'above' and current_price >= a['threshold_value']) or \
                  (a['condition'] == 'below' and current_price <= a['threshold_value'])
            if hit:
                conn.execute('''UPDATE advanced_alerts SET triggered=TRUE, triggered_at=CURRENT_TIMESTAMP,
                    current_value=? WHERE id=?''', (current_price, a['id']))
                create_alert(user_id, ticker, 'PRICE_ALERT',
                    f"{ticker} reached ₹{current_price:.2f} ({a['condition']} ₹{a['threshold_value']:.2f})", 'high')
                triggered.append(a)
    return triggered


def check_volume_alerts(user_id, ticker, current_volume, avg_volume):
    from portfolio_manager import create_alert
    if avg_volume == 0:
        return []
    ratio = current_volume / avg_volume
    triggered = []
    with get_db_connection() as conn:
        rows = conn.execute('''SELECT * FROM advanced_alerts
            WHERE user_id=? AND ticker=? AND alert_type='VOLUME_SURGE' AND is_active=TRUE AND triggered=FALSE''',
            (user_id, ticker.upper())).fetchall()
        for alert in rows:
            a = dict(alert)
            if ratio >= a['threshold_value']:
                conn.execute('UPDATE advanced_alerts SET triggered=TRUE, triggered_at=CURRENT_TIMESTAMP, current_value=? WHERE id=?',
                             (ratio, a['id']))
                create_alert(user_id, ticker, 'VOLUME_SURGE',
                    f"{ticker} volume surge: {ratio:.2f}x avg", 'medium')
                triggered.append(a)
    return triggered


def check_rsi_alerts(user_id, ticker, current_rsi):
    from portfolio_manager import create_alert
    triggered = []
    with get_db_connection() as conn:
        rows = conn.execute('''SELECT * FROM advanced_alerts
            WHERE user_id=? AND ticker=? AND alert_type='RSI_LEVEL' AND is_active=TRUE AND triggered=FALSE''',
            (user_id, ticker.upper())).fetchall()
        for alert in rows:
            a = dict(alert)
            hit = (a['condition'] == 'above' and current_rsi >= a['threshold_value']) or \
                  (a['condition'] == 'below' and current_rsi <= a['threshold_value'])
            if hit:
                conn.execute('UPDATE advanced_alerts SET triggered=TRUE, triggered_at=CURRENT_TIMESTAMP, current_value=? WHERE id=?',
                             (current_rsi, a['id']))
                status = 'Overbought' if current_rsi > 70 else 'Oversold' if current_rsi < 30 else 'Alert'
                create_alert(user_id, ticker, 'RSI_ALERT',
                    f"{ticker} RSI {status}: {current_rsi:.2f} ({a['condition']} {a['threshold_value']})", 'medium')
                triggered.append(a)
    return triggered


def get_active_alerts(user_id, ticker=None):
    with get_db_connection() as conn:
        if ticker:
            rows = conn.execute('''SELECT * FROM advanced_alerts WHERE user_id=? AND ticker=? AND is_active=TRUE
                ORDER BY created_at DESC''', (user_id, ticker.upper())).fetchall()
        else:
            rows = conn.execute('SELECT * FROM advanced_alerts WHERE user_id=? AND is_active=TRUE ORDER BY created_at DESC',
                                (user_id,)).fetchall()
        return [dict(r) for r in rows]


def delete_alert(user_id, alert_id):
    with get_db_connection() as conn:
        cur = conn.execute('DELETE FROM advanced_alerts WHERE id=? AND user_id=?', (alert_id, user_id))
        return cur.rowcount > 0


def reset_alert(user_id, alert_id):
    with get_db_connection() as conn:
        cur = conn.execute('''UPDATE advanced_alerts SET triggered=FALSE, triggered_at=NULL, current_value=NULL
            WHERE id=? AND user_id=?''', (alert_id, user_id))
        return cur.rowcount > 0


init_advanced_alerts_table()
