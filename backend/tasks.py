"""
tasks.py — Celery worker tasks for background stock monitoring.

Run the worker:
  celery -A tasks worker --loglevel=info --concurrency=2

Run the beat scheduler:
  celery -A tasks beat --loglevel=info

The worker replaces the threading.Thread inside market_monitor.py so that:
  - Monitoring survives Flask process restarts
  - eventlet monkey-patching no longer interferes with psycopg2
  - Worker can be scaled independently from the API server

WebSocket emissions from Celery tasks reach connected clients via the
Redis pub/sub message_queue configured on the Flask-SocketIO server.
The SocketIO server subscribes to the same Redis channel and relays events
to connected clients automatically when message_queue is set in app.py.
"""

import os
import logging
from celery import Celery
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv('REDIS_URL', 'redis://redis:6379/0')
# Use a separate Redis DB for Celery broker/backend to avoid key collisions
CELERY_BROKER = REDIS_URL.rsplit('/', 1)[0] + '/2'
CELERY_BACKEND = REDIS_URL.rsplit('/', 1)[0] + '/2'

celery_app = Celery(
    'stockeye',
    broker=CELERY_BROKER,
    backend=CELERY_BACKEND,
)

celery_app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    timezone='Asia/Kolkata',
    enable_utc=True,
    worker_prefetch_multiplier=1,   # one task at a time per worker process
    task_acks_late=True,            # re-queue on worker crash
    beat_schedule={
        'monitor-all-stocks': {
            'task': 'tasks.run_monitor_cycle',
            'schedule': 300.0,      # every 5 minutes
        },
        'check-price-alerts': {
            'task': 'tasks.check_price_alerts',
            'schedule': 60.0,       # every 1 minute
        },
        'save-portfolio-snapshots': {
            'task': 'tasks.save_portfolio_snapshots',
            'schedule': 3600.0,     # every 1 hour
        },
        'run-proactive-morning': {
            'task': 'tasks.run_proactive_morning',
            'schedule': crontab(hour=9, minute=0),   # 9:00 AM IST — pre-market
        },
        'run-proactive-evening': {
            'task': 'tasks.run_proactive_evening',
            'schedule': crontab(hour=16, minute=0),  # 4:00 PM IST — post-market
        },
        'snapshot-trading-portfolios': {
            'task': 'tasks.snapshot_all_trading_portfolios',
            'schedule': crontab(hour=16, minute=30),  # 4:30 PM IST — after market close
        },
        'auto-session-morning': {
            'task': 'tasks.run_auto_session_all_users',
            'schedule': crontab(hour=9, minute=15),   # market open IST
        },
        'auto-session-evening': {
            'task': 'tasks.run_auto_session_all_users',
            'schedule': crontab(hour=15, minute=30),  # pre-close IST
        },
    },
)


@celery_app.task(name='tasks.run_monitor_cycle', bind=True, max_retries=3)
def run_monitor_cycle(self):
    """Check all actively monitored stocks for price/volume/technical alerts."""
    try:
        from market_monitor import monitor_service
        monitor_service._check_all_stocks()
    except Exception as exc:
        logger.error(f"Monitor cycle failed: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name='tasks.check_price_alerts', bind=True, max_retries=3)
def check_price_alerts(self):
    """Evaluate all active user-set price alerts."""
    try:
        from market_monitor import monitor_service
        monitor_service._check_price_alerts()
    except Exception as exc:
        logger.error(f"Price alert check failed: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=15)


@celery_app.task(name='tasks.save_portfolio_snapshots', bind=True, max_retries=2)
def save_portfolio_snapshots(self):
    """Persist portfolio value snapshots for all users (used for history charts)."""
    try:
        from market_monitor import monitor_service
        monitor_service._check_portfolio_snapshot()
    except Exception as exc:
        logger.error(f"Portfolio snapshot failed: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name='tasks.run_proactive_morning', bind=True, max_retries=2)
def run_proactive_morning(self):
    """Pre-market proactive analysis — 9:00 AM IST.
    Claude tool_use agentic loop analyzes all monitored stocks for all users
    and emits BUY/SELL/HOLD/WATCH recommendations via WebSocket.
    """
    try:
        from proactive_agent import run_analysis_for_all_users
        run_analysis_for_all_users(session='morning')
    except Exception as exc:
        logger.error(f"Proactive morning analysis failed: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name='tasks.run_proactive_evening', bind=True, max_retries=2)
def run_proactive_evening(self):
    """Post-market proactive analysis — 4:00 PM IST.
    Runs after market close to review the day and set next-day context.
    """
    try:
        from proactive_agent import run_analysis_for_all_users
        run_analysis_for_all_users(session='evening')
    except Exception as exc:
        logger.error(f"Proactive evening analysis failed: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name='tasks.run_auto_session_all_users', bind=True, max_retries=1)
def run_auto_session_all_users(self):
    """Autonomous trading session for all funded accounts — 9:15 AM and 3:30 PM IST."""
    try:
        from db import get_db_connection
        from agentic_trader import run_trading_session
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT user_id FROM trading_balance WHERE balance > 0"
            ).fetchall()
        logger.info(f"Auto-session starting for {len(rows)} user(s)")
        for row in rows:
            uid = row['user_id']
            try:
                from trading_manager import get_trading_balance
                bal = get_trading_balance(uid) or {}
                avail = float(bal.get('balance') or 0)
                # Use 60% of available balance as session budget so cash reserve stays
                budget = round(avail * 0.6, 2) if avail > 500 else None
                run_trading_session(uid, budget=budget)
            except Exception as e:
                logger.error(f"Auto-session failed for user {str(uid)[:8]}: {e}")
    except Exception as exc:
        logger.error(f"run_auto_session_all_users failed: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=120)


@celery_app.task(name='tasks.snapshot_all_trading_portfolios', bind=True, max_retries=2)
def snapshot_all_trading_portfolios(self):
    """Daily snapshot of all users' paper trading portfolios — 4:30 PM IST."""
    try:
        from trading_manager import snapshot_portfolio
        from db import get_db_connection
        with get_db_connection() as conn:
            rows = conn.execute("SELECT DISTINCT user_id FROM trading_balance").fetchall()
        for row in rows:
            try:
                snapshot_portfolio(row['user_id'])
            except Exception as e:
                logger.error(f"Snapshot failed for user {str(row['user_id'])[:8]}: {e}")
        logger.info(f"Trading snapshots saved for {len(rows)} user(s)")
    except Exception as exc:
        logger.error(f"snapshot_all_trading_portfolios failed: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60)
