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
