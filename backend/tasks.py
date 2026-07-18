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
        'monitor-stop-losses': {
            'task': 'tasks.monitor_stop_losses',
            'schedule': 300.0,      # every 5 minutes during market hours
        },
        'auto-session-morning': {
            'task': 'tasks.run_auto_session_all_users',
            'schedule': crontab(hour=9, minute=15),   # market open IST
        },
        'auto-session-evening': {
            'task': 'tasks.run_auto_session_all_users',
            'schedule': crontab(hour=15, minute=30),  # pre-close IST
        },
        'expire-proposals': {
            'task': 'tasks.expire_proposals',
            'schedule': 300.0,      # every 5 min — lapse stale approval requests
        },
        'reconcile-live-orders': {
            'task': 'tasks.reconcile_live_orders',
            'schedule': 600.0,      # every 10 min — finalize async broker fills
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
        from datetime import datetime
        import pytz
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        if now.weekday() >= 5:  # Saturday / Sunday
            logger.info("Auto-session skipped — weekend")
            return
        market_open  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        if now < market_open or now > market_close:
            logger.info(f"Auto-session skipped — outside market hours ({now.strftime('%H:%M')} IST)")
            return

        # Require Redis for reliable per-user session locking.
        # Without it, concurrent Celery workers can double-run sessions for the
        # same user. Skip gracefully rather than trade with degraded safety.
        try:
            import redis as _redis
            import os as _os
            _r = _redis.from_url(_os.environ.get('REDIS_URL', REDIS_URL),
                                 socket_connect_timeout=2, socket_timeout=2)
            _r.ping()
        except Exception:
            logger.warning("Auto-session skipped — Redis unavailable (session lock requires Redis)")
            return

        from db import get_db_connection
        from agentic_trader import run_trading_session
        uids = []
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT user_id FROM trading_balance WHERE balance > 0"
            ).fetchall()
            uids = [r['user_id'] for r in rows]
            # Also include users with a linked live broker (they may hold real funds
            # with zero paper balance).
            try:
                broker_rows = conn.execute(
                    "SELECT DISTINCT user_id FROM broker_tokens WHERE status = 'connected'"
                ).fetchall()
                for br in broker_rows:
                    if br['user_id'] not in uids:
                        uids.append(br['user_id'])
            except Exception:
                pass   # broker_tokens table may not exist on older deployments
        logger.info(f"Auto-session starting for {len(uids)} user(s)")
        for uid in uids:
            try:
                # If a live broker is configured but the daily token expired, the
                # agent would silently fall back to paper. Ping to re-link and skip.
                from broker_manager import get_broker
                broker = get_broker(uid)
                if broker.broker_name != 'paper' and broker.needs_relink():
                    logger.info(f"Auto-session skipped for {str(uid)[:8]} — broker re-link needed")
                    try:
                        from telegram_notify import notify_relink
                        notify_relink(uid)
                    except Exception:
                        pass
                    continue

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


@celery_app.task(name='tasks.expire_proposals', bind=True, max_retries=1)
def expire_proposals(self):
    """Lapse PENDING live-order proposals that weren't acted on in time."""
    try:
        from proposal_store import expire_stale_proposals
        n = expire_stale_proposals()
        if n:
            logger.info(f"Expired {n} stale order proposal(s)")
    except Exception as exc:
        logger.error(f"expire_proposals failed: {exc}", exc_info=True)


@celery_app.task(name='tasks.reconcile_live_orders', bind=True, max_retries=1)
def reconcile_live_orders(self):
    """Finalize approved live orders whose broker fill was still pending."""
    try:
        from proposal_store import reconcile_open_orders
        n = reconcile_open_orders()
        if n:
            logger.info(f"Reconciled {n} live order(s)")
    except Exception as exc:
        logger.error(f"reconcile_live_orders failed: {exc}", exc_info=True)


@celery_app.task(name='tasks.monitor_stop_losses', bind=True, max_retries=2)
def monitor_stop_losses(self):
    """Check all open positions with stop-loss prices against live market data.
    Auto-sells when price breaches stop. Runs every 5 minutes during market hours."""
    try:
        from datetime import datetime
        import pytz
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        # Only run during market hours (9:15 AM - 3:30 PM IST, weekdays)
        if now.weekday() >= 5:  # Saturday/Sunday
            return
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        if now < market_open or now > market_close:
            return

        from trading_manager import get_open_stop_orders, place_order
        from stock_data import get_bulk_prices
        from telegram_notify import send_stop_loss_alert

        orders = get_open_stop_orders()
        if not orders:
            return

        # Deduplicate: one stop per (user_id, ticker) — use the highest stop_price
        stops = {}
        for o in orders:
            key = (o['user_id'], o['ticker'])
            if key not in stops or float(o['stop_price']) > float(stops[key]['stop_price']):
                stops[key] = o

        tickers = list({o['ticker'] for o in stops.values()})
        prices = get_bulk_prices(tickers) if tickers else {}

        triggered = 0
        for (user_id, ticker), order in stops.items():
            current_price = prices.get(ticker)
            if not current_price:
                continue

            stop_price = float(order['stop_price'])
            if current_price > stop_price:
                continue  # price above stop — safe

            # Stop-loss breached — auto-sell entire position
            held_qty = int(float(order.get('held_qty') or 0))
            if held_qty <= 0:
                continue

            avg_buy = float(order.get('avg_buy_price') or 0)
            try:
                place_order(
                    user_id=user_id,
                    ticker=ticker,
                    name=ticker,
                    side='SELL',
                    order_type='MARKET',
                    quantity=held_qty,
                    price=current_price,
                )
                pnl = (current_price - avg_buy) * held_qty
                send_stop_loss_alert(ticker, current_price, stop_price, held_qty, pnl)
                triggered += 1
                logger.info(
                    f"[StopLoss] {ticker} breached ₹{stop_price:.2f} "
                    f"(now ₹{current_price:.2f}) — sold {held_qty} for user {str(user_id)[:8]}"
                )
            except Exception as e:
                logger.error(f"[StopLoss] Failed to sell {ticker} for {str(user_id)[:8]}: {e}")

        if triggered:
            logger.info(f"[StopLoss] {triggered} stop-loss(es) triggered this cycle")
    except Exception as exc:
        logger.error(f"monitor_stop_losses failed: {exc}", exc_info=True)
        raise self.retry(exc=exc, countdown=60)


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
