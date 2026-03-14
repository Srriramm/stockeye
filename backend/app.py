"""
Flask Main Server - API endpoints and WebSocket for the Stock Assistant.
Handles chatbot queries, stock data, portfolio management, and monitoring.
"""

import os
import sys
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify, session

import io
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# Configure logging — on Windows, wrap the raw stderr buffer with UTF-8 so
# the ₹ symbol and emoji in log messages don't crash with cp1252 errors.
# (sys.stderr.reconfigure alone doesn't survive eventlet's stream patching.)
os.makedirs('logs', exist_ok=True)
if sys.platform == 'win32' and hasattr(sys.stderr, 'buffer'):
    _console_stream = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
else:
    _console_stream = sys.stderr

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/backend.log', encoding='utf-8'),
        logging.StreamHandler(_console_stream)
    ]
)
logger = logging.getLogger(__name__)

# Import application modules
from portfolio_manager import (
    init_database, add_holding, get_all_holdings, get_holding_by_id,
    update_holding, delete_holding, calculate_portfolio_value, get_portfolio_stats,
    start_monitoring, stop_monitoring, get_monitored_stocks, sync_portfolio_to_monitors,
    create_alert, get_recent_alerts, get_alerts_for_ticker, mark_alert_read,
    add_price_alert, get_active_price_alerts,
    get_portfolio_history, save_chat_message, get_chat_history, clear_chat_history
)
from auth_manager import require_auth, optional_auth, verify_token, require_admin, decode_jwt_payload
from user_manager import (
    ensure_user_registered, get_user_record, get_cached_user_status,
    list_users, update_user_status, update_user_role, update_user_notes,
    get_system_stats, list_invited_emails, add_invited_email, remove_invited_email,
)
from conversation_manager import (
    create_conversation, get_conversations, get_conversation,
    rename_conversation, delete_conversation, delete_all_conversations,
    add_message, get_messages, get_or_create_conversation, get_all_user_messages
)
from stock_data import (
    get_stock_price, get_stock_info, get_historical_data,
    calculate_technical_indicators, get_market_indices, get_top_gainers_losers,
    search_stocks, get_stocks_by_sector, get_bulk_prices, get_stock_comparison,
    calculate_fibonacci_levels, find_support_resistance,
    POPULAR_INDIAN_STOCKS
)
from news_monitor import fetch_stock_news, fetch_market_news, get_news_summary, get_reddit_sentiment, clear_news_cache
from intelligence_engine import get_stock_profile, invalidate_profile
from ai_advisor import get_stock_advice, get_stock_advice_dual, analyze_stock, get_portfolio_review, compare_stocks
from market_monitor import monitor_service, set_socketio as set_monitor_socketio
from realtime_service import realtime_service, set_socketio as set_realtime_socketio
from watchlist_manager import (
    create_watchlist, get_all_watchlists, get_watchlist_by_id,
    update_watchlist, delete_watchlist, reorder_watchlists,
    add_stock_to_watchlist, remove_stock_from_watchlist,
    reorder_watchlist_items, move_stock_to_watchlist,
    get_stock_in_watchlists, search_watchlist_stocks
)
from trading_manager import (
    place_order, execute_order, cancel_order, get_order_by_id,
    get_orders, get_trades, get_trading_portfolio, get_trading_balance,
    reset_trading_account, add_funds, snapshot_portfolio, get_performance_history,
    OrderType, OrderSide
)
from stock_screener import screen_stocks, get_predefined_screens, get_sectors
from advanced_alerts import (
    create_price_alert, create_percent_change_alert, create_volume_surge_alert,
    create_rsi_alert, create_moving_average_cross_alert, create_week_52_alert,
    get_active_alerts, delete_alert as delete_advanced_alert, reset_alert
)
from forecasting_engine import forecast_stock_price, get_risk_profile
from brain_engine import run_brain_analysis
from proactive_agent import analyze_stock_for_user, set_agent_socketio
from recommendation_store import (
    get_recommendations, get_recommendation_by_id,
    mark_recommendation_read, dismiss_recommendation, get_unread_count,
    init_agent_recommendations_table,
)
from middleware import init_middleware
from rate_limiter import init_limiter, limiter, LIMIT_CHAT, LIMIT_FORECAST, LIMIT_TRADING, LIMIT_PORTFOLIO
from audit import log_event

# ─── App Configuration ─────────────────────────────────────────

app = Flask(__name__)
SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Security validation: Prevent weak secrets in production
WEAK_SECRETS = ['dev-secret-key-change-in-production', 'change-this-to-random-secret-in-production', 'secret', 'password', '123456']
if os.getenv('FLASK_ENV', 'production') == 'production' and (SECRET_KEY in WEAK_SECRETS or len(SECRET_KEY) < 32):
    raise ValueError(
        "SECURITY ERROR: Weak FLASK_SECRET_KEY detected in production!\n"
        "Generate a strong key with: python -c 'import secrets; print(secrets.token_hex(32))'\n"
        "Then update your .env file with the generated key."
    )

app.config['SECRET_KEY'] = SECRET_KEY

# CORS Configuration: Use specific allowed origins (not wildcard)
allowed_origins = os.getenv('FRONTEND_URL', 'http://localhost:3000').split(',')
CORS(app, resources={r"/api/*": {
    "origins": allowed_origins,
    "supports_credentials": True
}})

_REDIS_URL = os.getenv('REDIS_URL')
# SOCKETIO_MESSAGE_QUEUE: only set this when running multiple Flask workers
# (e.g. docker compose scale backend=3) so events emitted in one process
# reach clients connected to another.  On a single-process EC2 instance,
# leave it unset — Redis pub/sub is not needed and monkey-patching breaks
# Docker's internal DNS resolver, causing 20-second timeouts on every request.
_SOCKETIO_QUEUE = os.getenv('SOCKETIO_MESSAGE_QUEUE')
socketio = SocketIO(
    app,
    cors_allowed_origins=allowed_origins,
    async_mode='eventlet',
    message_queue=_SOCKETIO_QUEUE,
)

# Attach request-ID injection and structured logging middleware
init_middleware(app)

# Attach rate limiter (backed by Redis when REDIS_URL is set)
init_limiter(app)

# Connect monitoring service to socketio
set_monitor_socketio(socketio)

# Connect realtime price service to socketio
set_realtime_socketio(socketio)

# Connect proactive agent to socketio (for WebSocket recommendation pushes)
set_agent_socketio(socketio)

# Initialize database (no-op for Supabase; tables created by setup_db.py)
init_database()
init_agent_recommendations_table()

# Note: sync_portfolio_to_monitors is now per-user; skipping global sync


# ─── Beta Access Enforcement ────────────────────────────────────
# Paths that bypass the approval check (must be accessible before registration)
_OPEN_PATHS = {'/api/health', '/api/health/ready', '/api/auth/me'}

@app.before_request
def enforce_beta_access():
    """
    Block unapproved users from all API routes.
    - /api/auth/me is always open (used for registration + status check)
    - /api/admin/* is open here; @require_admin enforces its own auth+role check
    - /socket.io/* is handled by the WebSocket connect handler
    Everything else requires status='approved' in app_users.
    """
    path = request.path
    if (path in _OPEN_PATHS or
            path.startswith('/api/admin/') or
            path.startswith('/socket.io')):
        return None

    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None  # unauthenticated — @require_auth on the route returns 401

    try:
        user_id = verify_token(auth_header[7:].strip())  # Redis-cached, fast
    except Exception:
        return None  # invalid token — @require_auth handles the 401

    # Anonymous trial users — pass through without DB lookup
    try:
        token = auth_header[7:].strip()
        payload = decode_jwt_payload(token)
        if payload.get('is_anonymous'):
            return None
    except Exception:
        pass

    # Fast path: check Redis cache first
    cached = get_cached_user_status(user_id)
    if cached:
        status, _role = cached
    else:
        user = get_user_record(user_id)
        status = user['status'] if user else 'rejected'

    if status != 'approved':
        return jsonify({'error': 'Access denied', 'status': status}), 403
    return None


# ─── Input Validation Functions ────────────────────────────────

import re

def validate_ticker(ticker):
    """Validate Indian stock ticker format. Strips .NS/.BO exchange suffixes."""
    if not ticker or not isinstance(ticker, str):
        raise ValueError("Ticker is required")
    ticker = ticker.upper().strip()
    # Strip exchange suffixes (.NS, .BO) so both TCS and TCS.NS are accepted
    for suffix in ('.NS', '.BO'):
        if ticker.endswith(suffix):
            ticker = ticker[:-len(suffix)]
            break
    if not re.match(r'^[A-Z]{2,10}$', ticker):
        raise ValueError(f"Invalid ticker format: {ticker}")
    return ticker

def validate_price(price, field_name="price"):
    """Validate price is positive and reasonable."""
    try:
        price = float(price)
    except (ValueError, TypeError):
        raise ValueError(f"{field_name} must be a number")
    if price <= 0:
        raise ValueError(f"{field_name} must be positive")
    if price > 1_000_000:
        raise ValueError(f"{field_name} exceeds maximum allowed value")
    return price

def validate_quantity(quantity):
    """Validate quantity is positive."""
    try:
        quantity = float(quantity)
    except (ValueError, TypeError):
        raise ValueError("Quantity must be a number")
    if quantity <= 0:
        raise ValueError("Quantity must be positive")
    return quantity


# ─── Error Handlers ─────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Internal server error'}), 500


# ─── Health Check ───────────────────────────────────────────────

@app.route('/api/health', methods=['GET'])
def health_check():
    from db import DB_TYPE, get_db_connection

    # Check database
    db_ok = False
    try:
        with get_db_connection() as conn:
            conn.execute('SELECT 1').fetchone()
        db_ok = True
    except Exception as e:
        logger.warning(f"Health check DB error: {e}")

    # Check Redis
    redis_ok = False
    try:
        import redis as _redis
        r = _redis.from_url(os.getenv('REDIS_URL', 'redis://redis:6379/0'),
                            socket_connect_timeout=1, socket_timeout=1)
        r.ping()
        redis_ok = True
    except Exception:
        pass  # Redis unavailable is non-fatal (graceful degradation)

    status = 'ok' if db_ok else 'degraded'
    http_code = 200 if db_ok else 503

    return jsonify({
        'status': status,
        'timestamp': datetime.now().isoformat(),
        'db_type': DB_TYPE,
        'services': {
            'database': 'connected' if db_ok else 'error',
            'redis': 'connected' if redis_ok else 'unavailable',
            'monitoring': 'running' if monitor_service.is_running else 'stopped',
        }
    }), http_code


@app.route('/api/health/ready', methods=['GET'])
def readiness_check():
    """Lightweight readiness probe — confirms the app process is alive."""
    return jsonify({'ready': True}), 200


# ═══════════════════════════════════════════════════════════════
# AUTH ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/auth/me', methods=['GET'])
@require_auth
def get_me(user_id):
    """
    Auto-register user on first login and return their profile + access status.
    Called by the frontend immediately after authentication to determine
    whether to show the app or the access-denied screen.
    """
    token = request.headers.get('Authorization', '')[7:]
    payload = decode_jwt_payload(token)

    # Anonymous trial users — approve immediately, no DB record created
    if payload.get('is_anonymous'):
        return jsonify({
            'user_id':   user_id,
            'email':     '',
            'full_name': 'Trial User',
            'avatar_url': None,
            'role':      'user',
            'status':    'approved',
            'is_trial':  True,
        })

    email = payload.get('email', '')
    meta = payload.get('user_metadata', {})
    full_name = meta.get('full_name')
    avatar_url = meta.get('avatar_url')

    user = ensure_user_registered(user_id, email=email,
                                  full_name=full_name, avatar_url=avatar_url)
    return jsonify({
        'user_id':    user_id,
        'email':      user.get('email', email),
        'full_name':  user.get('full_name'),
        'avatar_url': user.get('avatar_url'),
        'role':       user.get('role', 'user'),
        'status':     user.get('status', 'rejected'),
        'is_trial':   False,
    })


# ═══════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS  (all require @require_admin)
# ═══════════════════════════════════════════════════════════════

def _serialize_user(u: dict) -> dict:
    """Convert timestamps to ISO strings for JSON serialisation."""
    for k in ('created_at', 'approved_at', 'last_seen_at'):
        v = u.get(k)
        if v and not isinstance(v, str):
            u[k] = v.isoformat()
    return u


@app.route('/api/admin/stats', methods=['GET'])
@require_admin
def admin_stats(user_id):
    stats = get_system_stats()
    return jsonify(stats)


@app.route('/api/admin/users', methods=['GET'])
@require_admin
def admin_list_users(user_id):
    status_filter = request.args.get('status', 'all')
    limit  = min(int(request.args.get('limit', 100)), 200)
    offset = int(request.args.get('offset', 0))
    users = list_users(status=status_filter, limit=limit, offset=offset)
    return jsonify([_serialize_user(u) for u in users])


@app.route('/api/admin/users/<uid>/status', methods=['PATCH'])
@require_admin
def admin_update_status(user_id, uid):
    data = request.get_json() or {}
    new_status = data.get('status', '')
    if not update_user_status(uid, new_status, approved_by=user_id):
        return jsonify({'error': 'Invalid status value'}), 400
    log_event(user_id, f'admin.user.status.{new_status}', entity_type='user',
              details={'target_user_id': uid})
    return jsonify({'ok': True})


@app.route('/api/admin/users/<uid>/role', methods=['PATCH'])
@require_admin
def admin_update_role(user_id, uid):
    data = request.get_json() or {}
    new_role = data.get('role', '')
    if not update_user_role(uid, new_role):
        return jsonify({'error': 'Invalid role value'}), 400
    log_event(user_id, 'admin.user.role.change', entity_type='user',
              details={'target_user_id': uid, 'new_role': new_role})
    return jsonify({'ok': True})


@app.route('/api/admin/users/<uid>/notes', methods=['PATCH'])
@require_admin
def admin_update_notes(user_id, uid):
    data = request.get_json() or {}
    notes = data.get('notes', '')
    update_user_notes(uid, notes)
    return jsonify({'ok': True})


@app.route('/api/admin/audit', methods=['GET'])
@require_admin
def admin_audit_log(user_id):
    filter_uid = request.args.get('user_id')
    limit  = min(int(request.args.get('limit', 50)), 200)
    offset = int(request.args.get('offset', 0))
    from db import get_db_connection as _get_db
    with _get_db() as conn:
        if filter_uid:
            rows = conn.execute(
                'SELECT al.*, au.email AS user_email '
                'FROM audit_log al '
                'LEFT JOIN app_users au ON al.user_id = au.user_id '
                'WHERE al.user_id = ? '
                'ORDER BY al.created_at DESC LIMIT ? OFFSET ?',
                (filter_uid, limit, offset)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT al.*, au.email AS user_email '
                'FROM audit_log al '
                'LEFT JOIN app_users au ON al.user_id = au.user_id '
                'ORDER BY al.created_at DESC LIMIT ? OFFSET ?',
                (limit, offset)
            ).fetchall()
    result = []
    for r in rows:
        entry = dict(r)
        if entry.get('created_at') and not isinstance(entry['created_at'], str):
            entry['created_at'] = entry['created_at'].isoformat()
        # details may be a dict (psycopg2 JSONB) or string (SQLite)
        if isinstance(entry.get('details'), str):
            try:
                entry['details'] = json.loads(entry['details'])
            except Exception:
                pass
        result.append(entry)
    return jsonify(result)


@app.route('/api/admin/invites', methods=['GET'])
@require_admin
def admin_list_invites(user_id):
    invites = list_invited_emails()
    for inv in invites:
        if inv.get('created_at') and not isinstance(inv['created_at'], str):
            inv['created_at'] = inv['created_at'].isoformat()
    return jsonify(invites)


@app.route('/api/admin/invites', methods=['POST'])
@require_admin
def admin_add_invite(user_id):
    data = request.get_json() or {}
    email = (data.get('email') or '').strip()
    if not email or '@' not in email:
        return jsonify({'error': 'Valid email required'}), 400
    notes = data.get('notes', '')
    result = add_invited_email(email, added_by=user_id, notes=notes)
    log_event(user_id, 'admin.invite.add', details={'email': email})
    return jsonify(result), 201


@app.route('/api/admin/invites/<path:email>', methods=['DELETE'])
@require_admin
def admin_remove_invite(user_id, email):
    remove_invited_email(email)
    log_event(user_id, 'admin.invite.remove', details={'email': email})
    return jsonify({'ok': True})


# ─── Conversations ───────────────────────────────────────────────

@app.route('/api/conversations', methods=['GET'])
@require_auth
def list_conversations(user_id):
    return jsonify(get_conversations(user_id))


@app.route('/api/conversations', methods=['POST'])
@require_auth
def new_conversation(user_id):
    data  = request.json or {}
    title = data.get('title', 'New Chat')
    cid   = create_conversation(user_id, title)
    return jsonify({'id': cid, 'title': title}), 201


@app.route('/api/conversations/<int:cid>', methods=['GET'])
@require_auth
def get_conv(user_id, cid):
    conv = get_conversation(user_id, cid)
    if not conv:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(conv)


@app.route('/api/conversations/<int:cid>', methods=['PATCH'])
@require_auth
def rename_conv(user_id, cid):
    title = (request.json or {}).get('title', '')
    rename_conversation(user_id, cid, title)
    return jsonify({'ok': True})


@app.route('/api/conversations/<int:cid>', methods=['DELETE'])
@require_auth
def delete_conv(user_id, cid):
    delete_conversation(user_id, cid)
    return jsonify({'ok': True})


# ═══════════════════════════════════════════════════════════════
# CHATBOT ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/chat', methods=['POST'])
@require_auth
@limiter.limit(LIMIT_CHAT)
def chat(user_id):
    """Handle chatbot queries. Requires authentication for per-user conversation isolation."""
    data = request.json
    if not data or 'message' not in data:
        return jsonify({'error': 'Message is required'}), 400

    user_message = data['message']
    provider = data.get('provider', 'auto')
    conversation_id = data.get('conversation_id')

    # Always use conversation_manager for per-user isolated history
    cid = get_or_create_conversation(user_id, conversation_id)
    add_message(user_id, cid, 'user', user_message)

    # Load per-user conversation history to pass to AI (never use a global list)
    prior_messages = get_messages(user_id, cid, limit=20)

    # Detect query intent and fetch relevant data
    stock_data = None
    news_data = None
    portfolio_data = None
    technicals = None

    message_lower = user_message.lower()

    # Try to extract tickers from message
    mentioned_tickers = _extract_tickers(user_message)

    # Fetch data based on query type
    if mentioned_tickers:
        ticker = mentioned_tickers[0]
        stock_data = get_stock_info(ticker)
        technicals = calculate_technical_indicators(ticker)
        try:
            news_data = get_news_summary(ticker)
        except Exception as e:
            logger.error(f"Failed to fetch news for {ticker}: {e}")
            news_data = None

    # If asking about portfolio
    if any(word in message_lower for word in ['portfolio', 'holdings', 'my stocks', 'review']):
        try:
            holdings = get_all_holdings(user_id)
            if holdings:
                prices = get_bulk_prices([h['ticker'] for h in holdings])
                portfolio_data = calculate_portfolio_value(user_id, prices)
        except Exception as e:
            logger.error(f"Failed to fetch portfolio data: {e}")
            portfolio_data = None

    # If asking about market
    if any(word in message_lower for word in ['market', 'nifty', 'sensex', 'today', 'overview']):
        try:
            indices = get_market_indices()
            if not stock_data:
                stock_data = {'market_indices': indices}
            else:
                stock_data['market_indices'] = indices
        except Exception as e:
            logger.error(f"Failed to fetch market indices: {e}")
            # Continue without market indices

    # If asking about sector
    for sector in ['it', 'banking', 'pharma', 'fmcg', 'auto', 'metal', 'energy', 'infra']:
        if sector in message_lower:
            sector_stocks = get_stocks_by_sector(sector)
            if sector_stocks and not stock_data:
                stock_data = {'sector': sector, 'stocks': sector_stocks}
            break

    # If comparing two stocks
    if 'vs' in message_lower or 'compare' in message_lower:
        if len(mentioned_tickers) >= 2:
            comparison = get_stock_comparison(mentioned_tickers[0], mentioned_tickers[1])
            if comparison:
                stock_data = comparison

    # Get AI response — pass per-user conversation history, never a global list
    result = get_stock_advice_dual(
        user_message,
        provider=provider,
        conversation_history=prior_messages,
        stock_data=stock_data,
        news_data=news_data,
        portfolio_data=portfolio_data,
        technicals=technicals
    )

    add_message(user_id, cid, 'assistant', result['response'])

    return jsonify({
        'response': result['response'],
        'provider_used': result.get('provider_used', 'none'),
        'model_used': result.get('model_used', 'unknown'),
        'query_type': result.get('query_type', 'unknown'),
        'data_used': result.get('data_used', ''),
        'error': result.get('error'),
        'timestamp': datetime.now().isoformat(),
        'mentioned_stocks': mentioned_tickers,
        'conversation_id': cid,
    })


@app.route('/api/chat/history', methods=['GET'])
@require_auth
def chat_history(user_id):
    """Get chat history — all messages across all conversations, oldest first."""
    limit = request.args.get('limit', 200, type=int)
    msgs, latest_cid = get_all_user_messages(user_id, limit=limit)
    return jsonify({'messages': msgs, 'conversation_id': latest_cid})


@app.route('/api/chat/clear', methods=['POST'])
@require_auth
def clear_chat(user_id):
    """Clear chat history — delete all conversations for this user."""
    delete_all_conversations(user_id)
    return jsonify({'status': 'cleared'})


# ═══════════════════════════════════════════════════════════════
# STOCK DATA ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/stocks/search', methods=['GET'])
def stock_search():
    """Search stocks by name or ticker."""
    query = request.args.get('q', '')
    if not query or len(query) < 1:
        return jsonify({'results': []})

    results = search_stocks(query)
    return jsonify({'results': results})


@app.route('/api/stocks/<ticker>', methods=['GET'])
def stock_details(ticker):
    """Get comprehensive stock details."""
    price = get_stock_price(ticker)
    info = get_stock_info(ticker)
    technicals = calculate_technical_indicators(ticker)

    if not price:
        return jsonify({'error': f'Stock {ticker} not found'}), 404

    return jsonify({
        'price': price,
        'info': info,
        'technicals': technicals,
    })


@app.route('/api/stocks/<ticker>/history', methods=['GET'])
def stock_history(ticker):
    """Get historical price data for a stock."""
    period = request.args.get('period', '1y')
    interval = request.args.get('interval', '1d')

    data = get_historical_data(ticker, period=period, interval=interval)
    if not data:
        return jsonify({'error': f'No historical data for {ticker}'}), 404

    return jsonify({'ticker': ticker, 'data': data, 'period': period})


@app.route('/api/stocks/<ticker>/technicals', methods=['GET'])
def stock_technicals(ticker):
    """Get technical indicators for a stock."""
    data = calculate_technical_indicators(ticker)
    if not data:
        return jsonify({'error': f'Could not calculate indicators for {ticker}'}), 404
    return jsonify(data)


@app.route('/api/stocks/<ticker>/analyze', methods=['GET'])
def analyze_stock_endpoint(ticker):
    """Get AI analysis for a specific stock."""
    info = get_stock_info(ticker)
    technicals = calculate_technical_indicators(ticker)
    news = None
    try:
        news = get_news_summary(ticker)
    except Exception as e:
        logger.error(f"Failed to fetch news for {ticker} analysis: {e}")
        news = None

    result = analyze_stock(ticker, stock_info=info, technicals=technicals, news=news)
    return jsonify(result)


@app.route('/api/stocks/compare', methods=['GET'])
def compare_stocks_endpoint():
    """Compare two stocks."""
    ticker1 = request.args.get('t1', '')
    ticker2 = request.args.get('t2', '')

    if not ticker1 or not ticker2:
        return jsonify({'error': 'Two tickers (t1 and t2) are required'}), 400

    comparison = get_stock_comparison(ticker1, ticker2)
    ai_comparison = compare_stocks(ticker1, ticker2, comparison_data=comparison)

    return jsonify({
        'data': comparison,
        'analysis': ai_comparison,
    })


@app.route('/api/stocks/popular', methods=['GET'])
def popular_stocks():
    """Get list of popular Indian stocks."""
    stocks = []
    for ticker, info in POPULAR_INDIAN_STOCKS.items():
        stocks.append({
            'ticker': ticker,
            'name': info['name'],
            'sector': info['sector'],
        })
    return jsonify({'stocks': stocks})


@app.route('/api/stocks/<ticker>/fibonacci', methods=['GET'])
def get_fibonacci(ticker):
    """Get Fibonacci retracement levels for a stock."""
    period = request.args.get('period', '6mo')
    fib = calculate_fibonacci_levels(ticker.upper(), period=period)

    if 'error' in fib:
        return jsonify(fib), 404

    return jsonify(fib)


@app.route('/api/stocks/<ticker>/support-resistance', methods=['GET'])
def get_support_resistance_endpoint(ticker):
    """Get support and resistance levels for a stock."""
    period = request.args.get('period', '6mo')
    window = int(request.args.get('window', 20))

    levels = find_support_resistance(ticker.upper(), period=period, window=window)

    if 'error' in levels:
        return jsonify(levels), 404

    return jsonify(levels)


@app.route('/api/stocks/<ticker>/forecast', methods=['GET'])
@limiter.limit(LIMIT_FORECAST)
def stock_forecast(ticker):
    """Get AI Brain-powered analysis: technicals + ML forecast + news + backtest + narrative."""
    days = request.args.get('days', 30, type=int)
    days = max(7, min(days, 90))

    try:
        ticker_clean = validate_ticker(ticker)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    result = run_brain_analysis(ticker_clean, days=days)
    if 'error' in result:
        return jsonify(result), 404

    return jsonify(result)


@app.route('/api/stocks/<ticker>/agent-forecast', methods=['GET'])
@limiter.limit("10 per hour")
def agent_stock_forecast(ticker):
    """Agentic Claude forecast — Claude autonomously calls data tools and reasons
    across price, technicals, ML model, news, fundamentals, and risk to produce
    a structured forecast. Cached 6 hours per ticker+days."""
    days = request.args.get('days', 30, type=int)
    days = max(7, min(days, 60))

    try:
        ticker_clean = validate_ticker(ticker)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    from agentic_forecaster import run_agentic_forecast
    result = run_agentic_forecast(ticker_clean, days=days)
    if not result:
        return jsonify({'error': 'Agent forecast failed — check API key or try again'}), 500

    return jsonify(result)


@app.route('/api/stocks/<ticker>/risk-profile', methods=['GET'])
def stock_risk_profile(ticker):
    """Get comprehensive risk metrics for a stock."""
    historical = get_historical_data(ticker.upper(), period='1y', interval='1d')
    if not historical:
        return jsonify({'error': f'No historical data available for {ticker}'}), 404

    result = get_risk_profile(historical, ticker.upper())
    if 'error' in result:
        return jsonify(result), 500

    return jsonify(result)


# ═══════════════════════════════════════════════════════════════
# PORTFOLIO ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/portfolio', methods=['GET'])
@require_auth
def get_portfolio(user_id):
    """Get portfolio with live prices and P&L."""
    holdings = get_all_holdings(user_id)
    if not holdings:
        return jsonify({
            'holdings': [],
            'total_value': 0,
            'total_investment': 0,
            'total_pnl': 0,
            'total_pnl_percent': 0,
            'num_holdings': 0,
        })

    # Backfill: ensure all portfolio stocks appear in the default watchlist
    try:
        watchlists = get_all_watchlists(user_id)
        wl_id = watchlists[0]['id'] if watchlists else create_watchlist(user_id, 'My Watchlist', 'Default watchlist')
        for h in holdings:
            add_stock_to_watchlist(user_id, wl_id, h['ticker'], h.get('name', ''), h.get('sector', ''))
    except Exception:
        pass  # never block portfolio load for a sync failure

    tickers = [h['ticker'] for h in holdings]
    prices = get_bulk_prices(tickers)
    portfolio = calculate_portfolio_value(user_id, prices)

    # Enrich each holding's sector from POPULAR_INDIAN_STOCKS if not already set
    # (fast dict lookup — no extra API calls)
    for h in portfolio['holdings']:
        if not h.get('sector'):
            h['sector'] = POPULAR_INDIAN_STOCKS.get(h['ticker'], {}).get('sector', '')

    return jsonify(portfolio)


@app.route('/api/portfolio/stats', methods=['GET'])
@require_auth
def portfolio_stats(user_id):
    """Get comprehensive portfolio statistics."""
    holdings = get_all_holdings(user_id)
    if not holdings:
        return jsonify({'error': 'No holdings in portfolio'}), 404

    prices = get_bulk_prices([h['ticker'] for h in holdings])
    stats = get_portfolio_stats(user_id, prices)
    return jsonify(stats)


@app.route('/api/portfolio/add', methods=['POST'])
@require_auth
def add_stock(user_id):
    """Add a stock to the portfolio."""
    try:
        data = request.json
        required = ['ticker', 'quantity', 'buy_price']

        for field in required:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400

        # Validate inputs
        ticker = validate_ticker(data['ticker'])
        quantity = validate_quantity(data['quantity'])
        buy_price = validate_price(data['buy_price'], 'buy_price')

        name = data.get('name', '')

        # Auto-fetch name if not provided
        if not name:
            stock_info = get_stock_info(ticker)
            if stock_info:
                name = stock_info.get('name', ticker)
                data['sector'] = stock_info.get('sector', '')
            else:
                name = ticker

        holding_id = add_holding(
            user_id,
            ticker=ticker,
            name=name,
            quantity=quantity,
            buy_price=buy_price,
            purchase_date=data.get('purchase_date', datetime.now().strftime('%Y-%m-%d')),
            sector=data.get('sector', ''),
            exchange=data.get('exchange', 'NSE'),
        )

        log_event(user_id, 'portfolio.add', 'holding', holding_id,
                  {'ticker': ticker, 'quantity': quantity, 'buy_price': buy_price})

        # Automatically start monitoring portfolio stocks
        start_monitoring(user_id, ticker, name)

        # Sync to default watchlist so it appears everywhere
        watchlists = get_all_watchlists(user_id)
        if not watchlists:
            wl_id = create_watchlist(user_id, 'My Watchlist', 'Default watchlist')
        else:
            wl_id = watchlists[0]['id']
        add_stock_to_watchlist(user_id, wl_id, ticker, name, data.get('sector', ''))

        return jsonify({'id': holding_id, 'message': f'{ticker} added to portfolio'}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/portfolio/<int:holding_id>', methods=['PUT'])
@require_auth
def update_stock(user_id, holding_id):
    """Update a portfolio holding."""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    success = update_holding(user_id, holding_id, data)
    if success:
        log_event(user_id, 'portfolio.update', 'holding', holding_id)
        return jsonify({'message': 'Holding updated successfully'})
    return jsonify({'error': 'Holding not found'}), 404


@app.route('/api/portfolio/<int:holding_id>', methods=['DELETE'])
@require_auth
def remove_stock(user_id, holding_id):
    """Remove a stock from the portfolio."""
    holding = get_holding_by_id(user_id, holding_id)
    if not holding:
        return jsonify({'error': 'Holding not found'}), 404

    delete_holding(user_id, holding_id)
    log_event(user_id, 'portfolio.delete', 'holding', holding_id,
              {'ticker': holding.get('ticker')})

    # Remove from all watchlists and stop monitoring
    try:
        ticker = holding['ticker']
        in_watchlists = get_stock_in_watchlists(user_id, ticker)
        for wl in in_watchlists:
            remove_stock_from_watchlist(user_id, wl['id'], ticker)
        stop_monitoring(user_id, ticker)
    except Exception:
        pass

    return jsonify({'message': f'{holding["ticker"]} removed from portfolio'})


@app.route('/api/portfolio/review', methods=['GET'])
@require_auth
def portfolio_review(user_id):
    """Get AI-powered portfolio review."""
    holdings = get_all_holdings(user_id)
    if not holdings:
        return jsonify({'error': 'No holdings in portfolio'}), 404

    prices = get_bulk_prices([h['ticker'] for h in holdings])
    portfolio_data = calculate_portfolio_value(user_id, prices)
    review = get_portfolio_review(portfolio_data)

    return jsonify(review)


@app.route('/api/portfolio/history', methods=['GET'])
@require_auth
def portfolio_history(user_id):
    """Get portfolio value history."""
    days = request.args.get('days', 30, type=int)
    history = get_portfolio_history(user_id, days)
    return jsonify({'history': history})


# ═══════════════════════════════════════════════════════════════
# MONITORING ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/monitor/start', methods=['POST'])
@require_auth
def start_stock_monitor(user_id):
    """Start monitoring a stock."""
    try:
        data = request.json
        if not data or 'ticker' not in data:
            return jsonify({'error': 'Ticker is required'}), 400

        # Validate ticker
        ticker = validate_ticker(data['ticker'])
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    # Get baseline data
    price_data = get_stock_price(ticker)
    if not price_data:
        return jsonify({'error': f'Could not fetch data for {ticker}'}), 404

    company_name = price_data.get('name', ticker)
    start_monitoring(
        user_id,
        ticker,
        name=company_name,
        price_baseline=price_data['current_price'],
        volume_avg=price_data.get('avg_volume', 0),
    )

    # Start monitoring service if not running
    if not monitor_service.is_running:
        monitor_service.start()

    # Pre-generate intelligence profile in background, then bust the news cache
    # so the next /api/news/<ticker> uses the fresh profile immediately.
    def _prime_intelligence(t, name):
        get_stock_profile(t, company_name=name)
        clear_news_cache(t)

    import threading
    threading.Thread(target=_prime_intelligence, args=(ticker, company_name), daemon=True).start()

    return jsonify({
        'message': f'Started monitoring {ticker}',
        'baseline_price': price_data['current_price'],
    })


@app.route('/api/monitor/stop', methods=['POST'])
@require_auth
def stop_stock_monitor(user_id):
    """Stop monitoring a stock."""
    data = request.json
    if not data or 'ticker' not in data:
        return jsonify({'error': 'Ticker is required'}), 400

    stop_monitoring(user_id, data['ticker'].upper())
    return jsonify({'message': f'Stopped monitoring {data["ticker"].upper()}'})


@app.route('/api/monitor/stocks', methods=['GET'])
@require_auth
def monitored_stocks_list(user_id):
    """Get all monitored stocks with current status."""
    stocks = get_monitored_stocks(user_id, active_only=True)
    enriched = []

    for stock in stocks:
        ticker = stock['ticker']
        price_data = get_stock_price(ticker)
        enriched.append({
            **stock,
            'current_price': price_data['current_price'] if price_data else None,
            'change_percent': price_data.get('change_percent', 0) if price_data else 0,
            'price_live': price_data is not None,
        })

    return jsonify({'stocks': enriched})


@app.route('/api/monitor/service', methods=['POST'])
@require_auth
def control_monitor_service(user_id):
    """Start or stop the monitoring service."""
    data = request.json or {}
    action = data.get('action', 'start')

    if action == 'start':
        monitor_service.start()
        return jsonify({'status': 'started'})
    elif action == 'stop':
        monitor_service.stop()
        return jsonify({'status': 'stopped'})
    else:
        return jsonify({'error': 'Invalid action. Use "start" or "stop"'}), 400


# ═══════════════════════════════════════════════════════════════
# ALERTS ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/alerts', methods=['GET'])
@require_auth
def alerts(user_id):
    """Get recent alerts."""
    hours = request.args.get('hours', 24, type=int)
    limit = request.args.get('limit', 50, type=int)
    alerts_list = get_recent_alerts(user_id, hours=hours, limit=limit)
    return jsonify({'alerts': alerts_list})


@app.route('/api/alerts/<ticker>', methods=['GET'])
@require_auth
def alerts_for_stock(user_id, ticker):
    """Get alerts for a specific stock."""
    limit = request.args.get('limit', 20, type=int)
    alerts_list = get_alerts_for_ticker(user_id, ticker.upper(), limit=limit)
    return jsonify({'alerts': alerts_list})


@app.route('/api/alerts/<int:alert_id>/read', methods=['POST'])
@require_auth
def read_alert(user_id, alert_id):
    """Mark an alert as read."""
    mark_alert_read(user_id, alert_id)
    return jsonify({'status': 'marked as read'})


@app.route('/api/alerts/price', methods=['POST'])
@require_auth
def set_price_alert(user_id):
    """Set a custom price alert."""
    try:
        data = request.json
        if not data or 'ticker' not in data or 'target_price' not in data:
            return jsonify({'error': 'ticker and target_price are required'}), 400

        # Validate inputs
        ticker = validate_ticker(data['ticker'])
        target_price = validate_price(data['target_price'], 'target_price')

        alert_id = create_price_alert(
            user_id,
            ticker,
            target_price,
            data.get('direction', 'above'),
        )

        return jsonify({'id': alert_id, 'message': 'Price alert set'}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/alerts/advanced', methods=['POST'])
@require_auth
def create_advanced_alert(user_id):
    """Create advanced alert (RSI, volume, MA cross, etc.)."""
    try:
        data = request.json
        if not data or 'ticker' not in data or 'alert_type' not in data:
            return jsonify({'error': 'ticker and alert_type are required'}), 400

        ticker = validate_ticker(data['ticker'])
        alert_type = data['alert_type']

        if alert_type == 'PERCENT_CHANGE':
            alert_id = create_percent_change_alert(
                user_id,
                ticker,
                data.get('percent_change', 5),
                data.get('timeframe', '1d')
            )
        elif alert_type == 'VOLUME_SURGE':
            alert_id = create_volume_surge_alert(
                user_id,
                ticker,
                data.get('volume_multiplier', 2.0)
            )
        elif alert_type == 'RSI_LEVEL':
            alert_id = create_rsi_alert(
                user_id,
                ticker,
                data.get('rsi_level', 30),
                data.get('condition', 'below')
            )
        elif alert_type == 'MA_CROSS':
            alert_id = create_moving_average_cross_alert(
                user_id,
                ticker,
                data.get('ma_type', 'sma_20')
            )
        elif alert_type == 'WEEK_52':
            alert_id = create_week_52_alert(
                user_id,
                ticker,
                data.get('level', 'high')
            )
        else:
            return jsonify({'error': 'Invalid alert type'}), 400

        log_event(user_id, 'alert.create', 'advanced_alert', alert_id,
                  {'ticker': ticker, 'alert_type': alert_type})

        return jsonify({'id': alert_id, 'message': f'{alert_type} alert created'}), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/alerts/advanced', methods=['GET'])
@require_auth
def get_advanced_alerts(user_id):
    """Get all active advanced alerts."""
    ticker = request.args.get('ticker')
    alerts = get_active_alerts(user_id, ticker=ticker)

    return jsonify({'alerts': alerts, 'count': len(alerts)})


@app.route('/api/alerts/advanced/<int:alert_id>', methods=['DELETE'])
@require_auth
def delete_advanced_alert_endpoint(user_id, alert_id):
    """Delete an advanced alert."""
    success = delete_advanced_alert(user_id, alert_id)

    if success:
        log_event(user_id, 'alert.delete', 'advanced_alert', alert_id)
        return jsonify({'message': 'Alert deleted'})

    return jsonify({'error': 'Alert not found'}), 404


@app.route('/api/alerts/advanced/<int:alert_id>/reset', methods=['POST'])
@require_auth
def reset_advanced_alert(user_id, alert_id):
    """Reset a triggered alert."""
    success = reset_alert(user_id, alert_id)

    if success:
        return jsonify({'message': 'Alert reset'})

    return jsonify({'error': 'Alert not found'}), 404


# ═══════════════════════════════════════════════════════════════
# MARKET OVERVIEW ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/market/overview', methods=['GET'])
def market_overview():
    """Get market indices and overview."""
    indices = get_market_indices()
    return jsonify({'indices': indices, 'timestamp': datetime.now().isoformat()})


@app.route('/api/market/movers', methods=['GET'])
def market_movers():
    """Get top gainers and losers."""
    movers = get_top_gainers_losers()
    return jsonify(movers)


# ═══════════════════════════════════════════════════════════════
# WATCHLIST ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/watchlists', methods=['GET'])
@require_auth
def get_watchlists(user_id):
    """Get all watchlists."""
    watchlists = get_all_watchlists(user_id)
    return jsonify({'watchlists': watchlists})


@app.route('/api/watchlists', methods=['POST'])
@require_auth
def create_new_watchlist(user_id):
    """Create a new watchlist."""
    data = request.json
    if not data or 'name' not in data:
        return jsonify({'error': 'Watchlist name is required'}), 400

    name = data['name']
    description = data.get('description', '')
    color = data.get('color', '#3b82f6')

    watchlist_id = create_watchlist(user_id, name, description, color)
    log_event(user_id, 'watchlist.create', 'watchlist', watchlist_id, {'name': name})
    return jsonify({'id': watchlist_id, 'message': 'Watchlist created'}), 201


@app.route('/api/watchlists/<int:watchlist_id>', methods=['GET'])
@require_auth
def get_watchlist(user_id, watchlist_id):
    """Get a specific watchlist with all items."""
    watchlist = get_watchlist_by_id(user_id, watchlist_id)
    if not watchlist:
        return jsonify({'error': 'Watchlist not found'}), 404

    # Enrich with real-time prices
    for item in watchlist['items']:
        price_data = get_stock_price(item['ticker'])
        if price_data:
            item['price_data'] = price_data

    return jsonify(watchlist)


@app.route('/api/watchlists/<int:watchlist_id>', methods=['PUT'])
@require_auth
def update_watchlist_endpoint(user_id, watchlist_id):
    """Update watchlist properties."""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    success = update_watchlist(
        user_id,
        watchlist_id,
        name=data.get('name'),
        description=data.get('description'),
        color=data.get('color')
    )

    if success:
        return jsonify({'message': 'Watchlist updated'})
    return jsonify({'error': 'Watchlist not found'}), 404


@app.route('/api/watchlists/<int:watchlist_id>', methods=['DELETE'])
@require_auth
def delete_watchlist_endpoint(user_id, watchlist_id):
    """Delete a watchlist."""
    success = delete_watchlist(user_id, watchlist_id)
    if success:
        log_event(user_id, 'watchlist.delete', 'watchlist', watchlist_id)
        return jsonify({'message': 'Watchlist deleted'})
    return jsonify({'error': 'Watchlist not found'}), 404


@app.route('/api/watchlists/reorder', methods=['POST'])
@require_auth
def reorder_watchlists_endpoint(user_id):
    """Reorder watchlists."""
    data = request.json
    if not data or 'order' not in data:
        return jsonify({'error': 'Order array is required'}), 400

    reorder_watchlists(user_id, data['order'])
    return jsonify({'message': 'Watchlists reordered'})


@app.route('/api/watchlists/<int:watchlist_id>/items', methods=['POST'])
@require_auth
def add_to_watchlist(user_id, watchlist_id):
    """Add a stock to a watchlist."""
    try:
        data = request.json
        if not data or 'ticker' not in data:
            return jsonify({'error': 'Ticker is required'}), 400

        ticker = validate_ticker(data['ticker'])
        name = data.get('name', '')
        sector = data.get('sector', '')

        # Auto-fetch name and sector if not provided
        if not name or not sector:
            stock_info = get_stock_info(ticker)
            if stock_info:
                name = name or stock_info.get('name', ticker)
                sector = sector or stock_info.get('sector', '')

        item_id = add_stock_to_watchlist(user_id, watchlist_id, ticker, name, sector)

        if item_id is None:
            return jsonify({'error': 'Stock already in watchlist'}), 409

        log_event(user_id, 'watchlist.stock_add', 'watchlist_item', item_id,
                  {'ticker': ticker, 'watchlist_id': watchlist_id})

        # Start monitoring watchlist stocks so price alerts and signals fire
        start_monitoring(user_id, ticker, name)

        return jsonify({'id': item_id, 'message': f'{ticker} added to watchlist'}), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/watchlists/<int:watchlist_id>/items/<ticker>', methods=['DELETE'])
@require_auth
def remove_from_watchlist(user_id, watchlist_id, ticker):
    """Remove a stock from a watchlist."""
    success = remove_stock_from_watchlist(user_id, watchlist_id, ticker.upper())
    if success:
        return jsonify({'message': f'{ticker} removed from watchlist'})
    return jsonify({'error': 'Stock not found in watchlist'}), 404


@app.route('/api/watchlists/<int:watchlist_id>/reorder', methods=['POST'])
@require_auth
def reorder_watchlist_items_endpoint(user_id, watchlist_id):
    """Reorder items in a watchlist."""
    data = request.json
    if not data or 'order' not in data:
        return jsonify({'error': 'Order array is required'}), 400

    reorder_watchlist_items(user_id, watchlist_id, data['order'])
    return jsonify({'message': 'Watchlist items reordered'})


@app.route('/api/watchlists/move', methods=['POST'])
@require_auth
def move_stock_between_watchlists(user_id):
    """Move a stock from one watchlist to another (user must own both watchlists)."""
    data = request.json
    required = ['ticker', 'from_watchlist_id', 'to_watchlist_id']

    for field in required:
        if field not in data:
            return jsonify({'error': f'{field} is required'}), 400

    success = move_stock_to_watchlist(
        user_id,
        data['ticker'].upper(),
        data['from_watchlist_id'],
        data['to_watchlist_id']
    )

    if success:
        return jsonify({'message': 'Stock moved successfully'})
    return jsonify({'error': 'Failed to move stock'}), 400


@app.route('/api/watchlists/stock/<ticker>', methods=['GET'])
@require_auth
def get_stock_watchlists(user_id, ticker):
    """Get all watchlists containing a specific stock."""
    watchlists = get_stock_in_watchlists(user_id, ticker.upper())
    return jsonify({'watchlists': watchlists})


@app.route('/api/watchlists/<int:watchlist_id>/search', methods=['GET'])
def search_watchlist(watchlist_id):
    """Search stocks within a watchlist."""
    query = request.args.get('q', '')
    if not query:
        return jsonify({'items': []})

    items = search_watchlist_stocks(watchlist_id, query)
    return jsonify({'items': items})


# ═══════════════════════════════════════════════════════════════
# TRADING ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/trading/orders', methods=['POST'])
@require_auth
def place_trading_order(user_id):
    """Place a buy/sell order."""
    try:
        data = request.json
        required = ['ticker', 'side', 'order_type', 'quantity']

        for field in required:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400

        ticker = validate_ticker(data['ticker'])
        quantity = validate_quantity(data['quantity'])
        side = data['side'].upper()
        order_type = data['order_type'].upper()

        # Validate order type and side
        if side not in [OrderSide.BUY.value, OrderSide.SELL.value]:
            return jsonify({'error': 'Invalid order side. Use BUY or SELL'}), 400

        if order_type not in [ot.value for ot in OrderType]:
            return jsonify({'error': 'Invalid order type'}), 400

        # Get stock name and price
        stock_info = get_stock_price(ticker)
        if not stock_info:
            return jsonify({'error': f'Could not fetch data for {ticker}'}), 404

        name = stock_info.get('name', ticker)
        current_price = stock_info['current_price']

        # Place order
        order_id = place_order(
            user_id=user_id,
            ticker=ticker,
            name=name,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=current_price if order_type == OrderType.MARKET.value else data.get('price'),
            stop_price=data.get('stop_price'),
            limit_price=data.get('limit_price')
        )

        log_event(user_id, 'trade.place', 'order', order_id,
                  {'ticker': ticker, 'side': side, 'order_type': order_type, 'quantity': quantity})

        return jsonify({
            'id': order_id,
            'message': f'{side} order placed for {quantity} {ticker}',
            'order_type': order_type
        }), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Error placing order: {e}")
        return jsonify({'error': 'Failed to place order'}), 500


@app.route('/api/trading/orders', methods=['GET'])
@require_auth
def get_trading_orders(user_id):
    """Get all orders for the authenticated user."""
    status = request.args.get('status')
    limit = request.args.get('limit', 50, type=int)

    orders = get_orders(user_id=user_id, status=status, limit=limit)
    return jsonify({'orders': orders})


@app.route('/api/trading/orders/<int:order_id>', methods=['GET'])
@require_auth
def get_trading_order(user_id, order_id):
    """Get specific order details, verifying ownership."""
    order = get_order_by_id(order_id)

    if not order:
        return jsonify({'error': 'Order not found'}), 404

    if order.get('user_id') != user_id:
        return jsonify({'error': 'Order not found'}), 404

    return jsonify(order)


@app.route('/api/trading/orders/<int:order_id>/cancel', methods=['POST'])
@require_auth
def cancel_trading_order(user_id, order_id):
    """Cancel a pending order, verifying ownership."""
    order = get_order_by_id(order_id)
    if not order or order.get('user_id') != user_id:
        return jsonify({'error': 'Order not found or already executed'}), 404

    success = cancel_order(order_id)

    if success:
        log_event(user_id, 'trade.cancel', 'order', order_id)
        return jsonify({'message': 'Order cancelled'})

    return jsonify({'error': 'Order not found or already executed'}), 404


@app.route('/api/trading/trades', methods=['GET'])
@require_auth
def get_trading_trades(user_id):
    """Get trade history for the authenticated user."""
    limit = request.args.get('limit', 50, type=int)
    trades = get_trades(user_id=user_id, limit=limit)

    return jsonify({'trades': trades})


@app.route('/api/trading/portfolio', methods=['GET'])
@require_auth
def get_trading_portfolio_endpoint(user_id):
    """Get trading portfolio with live P&L."""
    holdings = get_trading_portfolio(user_id=user_id)

    # Enrich with current prices
    tickers = [h['ticker'] for h in holdings]
    if tickers:
        prices = get_bulk_prices(tickers)

        for holding in holdings:
            current_price = prices.get(holding['ticker'])
            if current_price:
                current_value = holding['quantity'] * current_price
                pnl = current_value - holding['total_investment']
                pnl_percent = (pnl / holding['total_investment']) * 100

                holding['current_price'] = current_price
                holding['current_value'] = current_value
                holding['pnl'] = pnl
                holding['pnl_percent'] = pnl_percent

    balance = get_trading_balance(user_id=user_id)

    return jsonify({
        'holdings': holdings,
        'balance': balance,
        'num_holdings': len(holdings)
    })


@app.route('/api/trading/balance', methods=['GET'])
@require_auth
def get_trading_balance_endpoint(user_id):
    """Get trading account balance for the authenticated user."""
    balance = get_trading_balance(user_id=user_id)
    return jsonify(balance)


@app.route('/api/trading/reset', methods=['POST'])
@require_auth
def reset_trading_account_endpoint(user_id):
    """Reset trading account to starting balance."""
    reset_trading_account(user_id=user_id)
    log_event(user_id, 'account.reset', 'trading_balance')
    return jsonify({'message': 'Trading account reset. Add funds to start trading.'})


# ═══════════════════════════════════════════════════════════════
# PROACTIVE AGENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/agent/recommendations', methods=['GET'])
@require_auth
def agent_recommendations_list(user_id):
    """List proactive agent recommendations for the authenticated user.

    Query params:
      unread=true   — only unread recommendations
      ticker=RELIANCE — filter by ticker
      limit=20      — max results (default 20, max 50)
    """
    unread_only = request.args.get('unread', '').lower() == 'true'
    ticker = request.args.get('ticker', '').upper() or None
    limit = min(request.args.get('limit', 20, type=int), 50)

    recs = get_recommendations(user_id, limit=limit,
                               unread_only=unread_only, ticker=ticker)
    unread = get_unread_count(user_id)
    return jsonify({'recommendations': recs, 'unread_count': unread})


@app.route('/api/agent/analyze', methods=['POST'])
@require_auth
@limiter.limit("5 per hour")
def agent_analyze_on_demand(user_id):
    """Trigger an on-demand proactive analysis for a single stock.

    Body: { "ticker": "RELIANCE" }
    Returns the recommendation synchronously (may take 10-30s).
    """
    data = request.json or {}
    if 'ticker' not in data:
        return jsonify({'error': 'ticker is required'}), 400

    try:
        ticker = validate_ticker(data['ticker'])
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    result = analyze_stock_for_user(user_id, ticker, session='manual')
    if not result:
        return jsonify({'error': 'Analysis failed — check ticker or API key'}), 500

    return jsonify({'recommendation': result}), 200


@app.route('/api/agent/analyze-all', methods=['POST'])
@require_auth
@limiter.limit("2 per hour")
def agent_analyze_all(user_id):
    """Analyze every portfolio holding on-demand. Rate limited to 2/hour."""
    holdings = get_all_holdings(user_id)
    if not holdings:
        return jsonify({'results': [], 'message': 'No holdings to analyze'}), 200

    results = []
    for h in holdings:
        try:
            rec = analyze_stock_for_user(user_id, h['ticker'], session='manual')
            if rec:
                results.append({'ticker': h['ticker'], 'status': 'ok',
                                 'action': rec.get('action'), 'recommendation': rec})
            else:
                results.append({'ticker': h['ticker'], 'status': 'failed'})
        except Exception as exc:
            results.append({'ticker': h['ticker'], 'status': 'error', 'error': str(exc)})

    return jsonify({'results': results, 'analyzed': len(results)}), 200


@app.route('/api/agent/recommendations/<int:rec_id>/read', methods=['PATCH'])
@require_auth
def agent_mark_read(user_id, rec_id):
    """Mark a recommendation as read."""
    rec = get_recommendation_by_id(user_id, rec_id)
    if not rec:
        return jsonify({'error': 'Recommendation not found'}), 404
    mark_recommendation_read(user_id, rec_id)
    return jsonify({'ok': True})


@app.route('/api/agent/recommendations/<int:rec_id>/dismiss', methods=['PATCH'])
@require_auth
def agent_dismiss(user_id, rec_id):
    """Dismiss (soft-delete) a recommendation."""
    rec = get_recommendation_by_id(user_id, rec_id)
    if not rec:
        return jsonify({'error': 'Recommendation not found'}), 404
    dismiss_recommendation(user_id, rec_id)
    return jsonify({'ok': True})


# ═══════════════════════════════════════════════════════════════
# STOCK SCREENER ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/screener/screen', methods=['POST'])
def screen_stocks_endpoint():
    """Screen stocks based on custom filters."""
    data = request.json
    if not data or 'filters' not in data:
        return jsonify({'error': 'Filters are required'}), 400

    filters = data['filters']
    results = screen_stocks(filters)

    return jsonify({
        'results': results,
        'count': len(results),
        'filters_applied': filters
    })


@app.route('/api/screener/presets', methods=['GET'])
def get_screener_presets():
    """Get predefined screening strategies."""
    presets = get_predefined_screens()
    return jsonify({'presets': presets})


@app.route('/api/screener/presets/<preset_name>', methods=['GET'])
def run_preset_screen(preset_name):
    """Run a predefined screening strategy."""
    presets = get_predefined_screens()

    if preset_name not in presets:
        return jsonify({'error': 'Preset not found'}), 404

    preset = presets[preset_name]
    results = screen_stocks(preset['filters'])

    return jsonify({
        'preset_name': preset_name,
        'preset_description': preset['description'],
        'results': results,
        'count': len(results)
    })


@app.route('/api/screener/sectors', methods=['GET'])
def get_screener_sectors():
    """Get list of available sectors."""
    sectors = get_sectors()
    return jsonify({'sectors': sectors})


@app.route('/api/screener/natural', methods=['POST'])
def natural_language_screener():
    """
    Parse a natural language query into screener filters using GPT-4/Claude,
    then run the existing screen_stocks() function.

    Body: { "query": "profitable IT stocks under 2000 with RSI below 40" }
    """
    data = request.json
    if not data or 'query' not in data:
        return jsonify({'error': 'query is required'}), 400

    query = data['query'].strip()
    if not query:
        return jsonify({'error': 'query cannot be empty'}), 400

    filters, parsed_description = _parse_nl_query_to_filters(query)

    results = screen_stocks(filters)

    return jsonify({
        'query': query,
        'parsed_description': parsed_description,
        'filters_applied': filters,
        'results': results,
        'count': len(results),
    })


def _parse_nl_query_to_filters(query: str):
    """
    Use GPT-4 (or Claude fallback) to convert a natural-language stock
    screening query into a structured filter dict for screen_stocks().
    Returns (filters_dict, human_readable_description).
    """
    FILTER_SCHEMA = """{
  "price_min": <number | null>,
  "price_max": <number | null>,
  "pe_min": <number | null>,
  "pe_max": <number | null>,
  "rsi_min": <number | null>,
  "rsi_max": <number | null>,
  "dividend_yield_min": <number | null>,
  "market_cap_min": <number in INR | null>,
  "market_cap_max": <number in INR | null>,
  "volume_min": <number | null>,
  "change_percent_min": <number | null>,
  "change_percent_max": <number | null>,
  "sectors": <list of strings from ["IT","Banking","Finance","Pharma","Auto","FMCG","Metal","Energy","Infra","Telecom","Conglomerate","Consumer"] | null>,
  "week_52_high": <true | null>,
  "week_52_low": <true | null>,
  "description": "<plain English summary of what the user is looking for>"
}"""

    system_prompt = (
        "You are a financial screener query parser for Indian stocks (NSE/BSE). "
        "Convert the user's natural language query into a JSON filter object. "
        "Only include fields that are explicitly or clearly implied in the query — "
        "leave everything else null. "
        "For ₹ amounts, use plain numbers (e.g. ₹2000 → 2000, '1 lakh' → 100000, '1 crore' → 10000000). "
        "Respond with ONLY valid JSON, no explanation, no markdown fences.\n\n"
        f"JSON schema:\n{FILTER_SCHEMA}"
    )

    import openai as _oai
    import anthropic as _ant

    openai_key = os.getenv('OPENAI_API_KEY', '')
    anthropic_key = os.getenv('ANTHROPIC_API_KEY', '')

    raw = None

    # Try OpenAI first
    if openai_key and not openai_key.startswith('sk-proj-...'):
        try:
            client = _oai.OpenAI(api_key=openai_key)
            resp = client.chat.completions.create(
                model='gpt-4o-mini',
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': query},
                ],
                max_tokens=400,
                temperature=0,
                response_format={'type': 'json_object'},
            )
            raw = resp.choices[0].message.content
        except Exception as e:
            logger.warning(f"NL screener OpenAI parse failed: {e}")

    # Fallback to Anthropic
    if raw is None and anthropic_key and not anthropic_key.startswith('sk-ant-...'):
        try:
            client = _ant.Anthropic(api_key=anthropic_key)
            resp = client.messages.create(
                model='claude-haiku-20240307',
                max_tokens=400,
                system=system_prompt,
                messages=[{'role': 'user', 'content': query}],
            )
            raw = resp.content[0].text
        except Exception as e:
            logger.warning(f"NL screener Anthropic parse failed: {e}")

    # Parse the JSON
    if raw:
        try:
            parsed = json.loads(raw)
            description = parsed.pop('description', f'Filters from: "{query}"')
            # Strip null values
            filters = {k: v for k, v in parsed.items() if v is not None}
            return filters, description
        except Exception as e:
            logger.warning(f"NL screener JSON parse failed: {e}")

    # Rule-based fallback when AI is unavailable
    filters, description = _rule_based_parse(query)
    return filters, description


def _rule_based_parse(query: str):
    """Lightweight rule-based fallback for NL screener parsing."""
    import re as _re
    q = query.lower()
    filters = {}

    # Price
    m = _re.search(r'under\s+(?:rs\.?|₹)?\s*(\d[\d,]*)', q)
    if m: filters['price_max'] = float(m.group(1).replace(',', ''))
    m = _re.search(r'above\s+(?:rs\.?|₹)?\s*(\d[\d,]*)', q)
    if m: filters['price_min'] = float(m.group(1).replace(',', ''))

    # RSI
    m = _re.search(r'rsi\s+(?:below|under|<)\s*(\d+)', q)
    if m: filters['rsi_max'] = float(m.group(1))
    m = _re.search(r'rsi\s+(?:above|over|>)\s*(\d+)', q)
    if m: filters['rsi_min'] = float(m.group(1))

    # P/E
    m = _re.search(r'p/?e\s+(?:below|under|<)\s*(\d+)', q)
    if m: filters['pe_max'] = float(m.group(1))

    # Sectors
    sector_map = {
        'it': 'IT', 'tech': 'IT', 'technology': 'IT',
        'bank': 'Banking', 'banking': 'Banking',
        'pharma': 'Pharma', 'pharmaceutical': 'Pharma',
        'auto': 'Auto', 'automobile': 'Auto',
        'fmcg': 'FMCG', 'consumer': 'Consumer',
        'metal': 'Metal', 'steel': 'Metal',
        'energy': 'Energy', 'oil': 'Energy',
    }
    found_sectors = [v for k, v in sector_map.items() if k in q]
    if found_sectors: filters['sectors'] = list(set(found_sectors))

    # 52-week
    if '52' in q and 'high' in q: filters['week_52_high'] = True
    if '52' in q and 'low' in q: filters['week_52_low'] = True

    # Dividend
    if 'dividend' in q:
        m = _re.search(r'dividend.*?(\d+(?:\.\d+)?)\s*%', q)
        filters['dividend_yield_min'] = float(m.group(1)) if m else 2.0

    desc_parts = []
    if 'price_max' in filters: desc_parts.append(f"Price under ₹{filters['price_max']:,.0f}")
    if 'rsi_max' in filters: desc_parts.append(f"RSI below {filters['rsi_max']}")
    if 'sectors' in filters: desc_parts.append(f"Sectors: {', '.join(filters['sectors'])}")
    description = ' | '.join(desc_parts) if desc_parts else f'Query: "{query}"'

    return filters, description


# ═══════════════════════════════════════════════════════════════
# CHART ZONES ENDPOINT (Support/Resistance + Fibonacci)
# ═══════════════════════════════════════════════════════════════

@app.route('/api/stocks/<ticker>/zones', methods=['GET'])
def get_chart_zones(ticker):
    """
    Return support/resistance levels and Fibonacci retracement bands
    for overlay on the price chart.
    """
    try:
        ticker = ticker.upper()
        period = request.args.get('period', '6mo')

        sr   = find_support_resistance(ticker, period=period) or {}
        fib  = calculate_fibonacci_levels(ticker, period=period) or {}

        # Normalise support/resistance lists
        supports    = sr.get('support_levels', [])
        resistances = sr.get('resistance_levels', [])
        current     = sr.get('current_price') or fib.get('current_price')

        # Determine actionable entry / exit suggestion
        entry_zone = exit_zone = None
        if supports and current:
            nearest_supp = min(supports, key=lambda x: abs(x - current))
            entry_zone = {
                'price': round(nearest_supp, 2),
                'label': 'Entry Zone',
                'note': 'Strong support level — good area to accumulate',
            }
        if resistances and current:
            nearest_res = min(resistances, key=lambda x: abs(x - current))
            exit_zone = {
                'price': round(nearest_res, 2),
                'label': 'Exit / Target Zone',
                'note': 'Key resistance — consider booking partial profits here',
            }

        return jsonify({
            'ticker': ticker,
            'current_price': current,
            'support_levels':    [round(v, 2) for v in supports],
            'resistance_levels': [round(v, 2) for v in resistances],
            'fibonacci_levels':  fib.get('levels', {}),
            'swing_high':        fib.get('swing_high'),
            'swing_low':         fib.get('swing_low'),
            'entry_zone':        entry_zone,
            'exit_zone':         exit_zone,
            'analysis':          fib.get('analysis', ''),
            'position':          sr.get('position', ''),
        })
    except Exception as e:
        logger.error(f"Zones endpoint error for {ticker}: {e}")
        return jsonify({'error': str(e)}), 500


# ═══════════════════════════════════════════════════════════════
# QUICK SIGNAL ENDPOINT
# ═══════════════════════════════════════════════════════════════

@app.route('/api/stocks/<ticker>/quick-signal', methods=['GET'])
def quick_signal(ticker):
    """Get a lightweight BUY/SELL/HOLD signal using technicals + news sentiment."""
    try:
        ticker = ticker.upper()

        # Technical indicators (calculate_technical_indicators takes a ticker string)
        technicals = calculate_technical_indicators(ticker) or {}

        rsi = technicals.get('rsi', 50) or 50
        macd = technicals.get('macd', 0) or 0
        macd_signal_val = technicals.get('macd_signal', 0) or 0
        sma_20 = technicals.get('sma_20', 0) or 0
        sma_50 = technicals.get('sma_50', 0) or 0

        # Technical score (0–100)
        tech_score = 50
        if rsi <= 30:
            tech_score += 25
        elif rsi >= 70:
            tech_score -= 25
        elif rsi < 45:
            tech_score += 10
        elif rsi > 55:
            tech_score -= 10

        if macd > macd_signal_val:
            tech_score += 10
        elif macd < macd_signal_val:
            tech_score -= 10

        if sma_20 and sma_50:
            if sma_20 > sma_50:
                tech_score += 10
            else:
                tech_score -= 10

        tech_score = max(0, min(100, tech_score))

        # News sentiment score (0–100)
        news = fetch_stock_news(ticker, max_articles=8)
        pos = sum(1 for a in news if a.get('sentiment') == 'positive')
        neg = sum(1 for a in news if a.get('sentiment') == 'negative')
        total = len(news) if news else 1
        news_score = 50 + (pos - neg) / total * 25
        news_score = max(0, min(100, news_score))

        # Weighted composite score
        score = round(0.65 * tech_score + 0.35 * news_score, 1)

        if score >= 62:
            signal = 'BUY'
        elif score <= 38:
            signal = 'SELL'
        else:
            signal = 'HOLD'

        return jsonify({
            'ticker': ticker,
            'signal': signal,
            'score': score,
            'rsi': round(rsi, 1),
            'macd_bullish': macd > macd_signal_val,
            'sma_bullish': bool(sma_20 and sma_50 and sma_20 > sma_50),
            'positive_news': pos,
            'negative_news': neg,
            'neutral_news': total - pos - neg,
        })
    except Exception as e:
        logger.error(f'quick-signal error for {ticker}: {e}')
        return jsonify({'ticker': ticker, 'signal': 'HOLD', 'score': 50, 'error': str(e)})


# ═══════════════════════════════════════════════════════════════
# NEWS ENDPOINTS
# NOTE: static routes (/api/news/market) MUST be registered before
# the variable route (/api/news/<ticker>) so Flask doesn't capture
# the literal string "market" as a ticker symbol.
# ═══════════════════════════════════════════════════════════════

@app.route('/api/news/market', methods=['GET'])
def market_news():
    """Get general market news."""
    news = fetch_market_news()
    return jsonify({'news': news})


@app.route('/api/news/<ticker>', methods=['GET'])
def stock_news(ticker):
    """Get intelligence-driven news for a stock."""
    clean = ticker.upper()
    profile = get_stock_profile(clean)
    news = fetch_stock_news(clean, intelligence_profile=profile)
    return jsonify({'ticker': clean, 'news': news, 'profile': profile})


@app.route('/api/stocks/<ticker>/intelligence', methods=['GET'])
def stock_intelligence(ticker):
    """Return (or generate) the AI intelligence profile for a ticker."""
    clean = validate_ticker(ticker)
    # Accept optional company_name hint from query string
    company_name = request.args.get('name')
    refresh = request.args.get('refresh', 'false').lower() == 'true'
    if refresh:
        invalidate_profile(clean)
    profile = get_stock_profile(clean, company_name=company_name)
    return jsonify(profile)


@app.route('/api/news/<ticker>/sentiment', methods=['GET'])
def stock_sentiment(ticker):
    """Get comprehensive sentiment analysis."""
    summary = get_news_summary(ticker.upper())
    return jsonify(summary)


# ═══════════════════════════════════════════════════════════════
# WEBSOCKET EVENTS
# ═══════════════════════════════════════════════════════════════

@socketio.on('connect')
def handle_connect():
    """Authenticate WebSocket connection via token query param."""
    token = request.args.get('token')
    if not token:
        logger.warning(f"WebSocket rejected (no token): {request.sid}")
        return False  # reject unauthenticated connection
    try:
        ws_user_id = verify_token(token)
        session['ws_user_id'] = ws_user_id
        print(f"Client connected: {request.sid} (user: {ws_user_id})")
        emit('connected', {'status': 'connected', 'timestamp': datetime.now().isoformat()})
    except Exception:
        logger.warning(f"WebSocket rejected (invalid token): {request.sid}")
        return False


@socketio.on('disconnect')
def handle_disconnect():
    print(f"Client disconnected: {request.sid}")
    # Cleanup subscriptions for this client
    realtime_service.unsubscribe(request.sid)


@socketio.on('subscribe_stock')
def handle_subscribe(data):
    """Subscribe to real-time updates for a stock."""
    ticker = data.get('ticker', '').upper()
    if ticker:
        # Subscribe to real-time updates
        realtime_service.subscribe(request.sid, ticker)

        # Send immediate price update
        price = get_stock_price(ticker)
        emit('price_update', {'ticker': ticker, 'data': price, 'timestamp': datetime.now().isoformat()})


@socketio.on('unsubscribe_stock')
def handle_unsubscribe(data):
    """Unsubscribe from real-time updates for a stock."""
    ticker = data.get('ticker', '').upper()
    if ticker:
        realtime_service.unsubscribe(request.sid, ticker)
        emit('unsubscribed', {'ticker': ticker, 'status': 'success'})


@socketio.on('request_portfolio_update')
def handle_portfolio_update():
    """Send current portfolio data for the authenticated WebSocket user."""
    ws_user_id = session.get('ws_user_id')
    if not ws_user_id:
        return
    holdings = get_all_holdings(ws_user_id)
    if holdings:
        prices = get_bulk_prices([h['ticker'] for h in holdings])
        portfolio = calculate_portfolio_value(ws_user_id, prices)
        emit('portfolio_update', portfolio)


# ─── Helper Functions ───────────────────────────────────────────

def _extract_tickers(text):
    """Extract stock ticker symbols from user message."""
    text_upper = text.upper()
    found_tickers = []

    for ticker in POPULAR_INDIAN_STOCKS.keys():
        if ticker in text_upper:
            found_tickers.append(ticker)

    # Also check common aliases
    aliases = {
        'RELIANCE': ['RELIANCE', 'RIL'],
        'TCS': ['TCS', 'TATA CONSULTANCY'],
        'INFY': ['INFY', 'INFOSYS'],
        'HDFCBANK': ['HDFC BANK', 'HDFCBANK'],
        'ICICIBANK': ['ICICI BANK', 'ICICIBANK'],
        'SBIN': ['SBIN', 'SBI', 'STATE BANK'],
        # 'TATAMOTORS': ['TATA MOTORS', 'TATAMOTORS'],  # Temporarily unavailable
        'TATASTEEL': ['TATA STEEL', 'TATASTEEL'],
        'BAJFINANCE': ['BAJAJ FINANCE', 'BAJFINANCE'],
        'WIPRO': ['WIPRO'],
        'MARUTI': ['MARUTI', 'MARUTI SUZUKI'],
    }

    for ticker, names in aliases.items():
        for name in names:
            if name in text_upper and ticker not in found_tickers:
                found_tickers.append(ticker)
                break

    return found_tickers


# ═══════════════════════════════════════════════════════════════
# SECTOR HEATMAP & PEER COMPARISON ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/market/heatmap', methods=['GET'])
def get_market_heatmap():
    """Return per-sector aggregates and individual stock tiles for the sector heatmap."""
    from concurrent.futures import ThreadPoolExecutor
    from collections import defaultdict

    def _fetch(ticker):
        try:
            p = get_stock_price(ticker)
            if not p:
                return None
            meta = POPULAR_INDIAN_STOCKS.get(ticker, {})
            return {
                'ticker': ticker,
                'name': meta.get('name', ticker),
                'sector': meta.get('sector', 'Other'),
                'change_percent': round(p.get('change_percent', 0), 2),
                'current_price': p.get('current_price', 0),
                'market_cap': p.get('market_cap', 0),
            }
        except Exception:
            return None

    tickers = list(POPULAR_INDIAN_STOCKS.keys())
    stocks = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        for result in ex.map(_fetch, tickers):
            if result:
                stocks.append(result)

    sector_map = defaultdict(list)
    for s in stocks:
        sector_map[s['sector']].append(s['change_percent'])

    sectors = {
        sec: round(sum(vals) / len(vals), 2)
        for sec, vals in sector_map.items()
    }

    return jsonify({
        'stocks': stocks,
        'sectors': sectors,
        'updated_at': datetime.now().isoformat(),
    })


@app.route('/api/stocks/<ticker>/peers', methods=['GET'])
def get_peer_comparison(ticker):
    """Return 4 closest sector peers with price, change%, RSI for peer comparison."""
    ticker = ticker.upper()
    meta = POPULAR_INDIAN_STOCKS.get(ticker)
    if not meta:
        return jsonify({'error': f'Unknown ticker: {ticker}'}), 404

    sector = meta['sector']
    peers = [t for t, m in POPULAR_INDIAN_STOCKS.items()
             if m['sector'] == sector and t != ticker][:6]

    def _build_row(t):
        try:
            p = get_stock_price(t)
            tech = calculate_technical_indicators(t)
            if not p:
                return None
            return {
                'ticker': t,
                'name': POPULAR_INDIAN_STOCKS.get(t, {}).get('name', t),
                'sector': sector,
                'current_price': p.get('current_price', 0),
                'change_percent': round(p.get('change_percent', 0), 2),
                'market_cap': p.get('market_cap', 0),
                'rsi': round(tech['rsi'], 1) if tech else None,
            }
        except Exception:
            return None

    from concurrent.futures import ThreadPoolExecutor
    rows = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(_build_row, peers):
            if r:
                rows.append(r)

    self_row = _build_row(ticker)

    return jsonify({
        'ticker': ticker,
        'sector': sector,
        'self': self_row,
        'peers': sorted(rows, key=lambda x: abs(x['change_percent']), reverse=True)[:4],
    })


# ═══════════════════════════════════════════════════════════════
# AUTO TRADING
# ═══════════════════════════════════════════════════════════════

@app.route('/api/auto-trading/opportunities', methods=['GET'])
@require_auth
def get_auto_trading_opportunities(user_id):
    """Scan market for current arbitrage / statistical opportunities.

    Query params:
      tickers=TCS,INFY,RELIANCE  (comma-separated; overrides watchlist if provided)
    """
    try:
        # User-chosen tickers from query param take priority
        tickers_param = request.args.get('tickers', '').strip()
        if tickers_param:
            tickers = [t.strip().upper() for t in tickers_param.split(',') if t.strip()]
        else:
            # Fallback: use watchlist
            from db import get_db_connection
            with get_db_connection() as conn:
                rows = conn.execute(
                    "SELECT ws.ticker FROM watchlist_items ws "
                    "JOIN watchlists w ON ws.watchlist_id = w.id "
                    "WHERE w.user_id = ?",
                    (user_id,)
                ).fetchall()
            tickers = [r['ticker'] for r in rows][:30]

        from arbitrage_detector import scan_opportunities
        opps = scan_opportunities(tickers)
        return jsonify({'opportunities': opps, 'count': len(opps), 'tickers_scanned': tickers})
    except Exception as exc:
        logger.error(f"get_auto_trading_opportunities error: {exc}")
        return jsonify({'error': str(exc)}), 500


@app.route('/api/auto-trading/run', methods=['POST'])
@require_auth
@limiter.limit("10 per hour")
def run_auto_trading_session(user_id):
    """Trigger one autonomous paper-trading session."""
    try:
        from agentic_trader import run_trading_session
        body    = request.get_json(silent=True) or {}
        tickers = [t.strip().upper() for t in body.get('tickers', []) if t.strip()] or None
        budget  = float(body['budget']) if body.get('budget') else None
        result  = run_trading_session(user_id, tickers=tickers, budget=budget)
        if not result:
            return jsonify({'error': 'Trading session failed — check API key or logs'}), 500
        return jsonify(result)
    except Exception as exc:
        logger.error(f"run_auto_trading_session error: {exc}", exc_info=True)
        return jsonify({'error': str(exc)}), 500


@app.route('/api/auto-trading/wallet/add', methods=['POST'])
@require_auth
@limiter.limit("20 per hour")
def add_wallet_funds(user_id):
    """Add paper money to user's trading wallet."""
    try:
        body   = request.get_json(silent=True) or {}
        amount = float(body.get('amount', 0))
        result = add_funds(user_id, amount)
        return jsonify(result)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as exc:
        logger.error(f"add_wallet_funds error: {exc}", exc_info=True)
        return jsonify({'error': str(exc)}), 500


@app.route('/api/auto-trading/performance', methods=['GET'])
@require_auth
def get_trading_performance(user_id):
    """Daily return history for the paper trading portfolio."""
    days    = min(int(request.args.get('days', 30)), 365)
    history = get_performance_history(user_id, days)
    return jsonify({'history': history, 'count': len(history)})


@app.route('/api/auto-trading/session/active', methods=['GET'])
@require_auth
def get_active_trading_session(user_id):
    """Return the current or last session state for this user."""
    from agentic_trader import get_active_session
    session = get_active_session(user_id)
    return jsonify(session if session else {'status': 'idle'})


@app.route('/api/auto-trading/broker/status', methods=['GET'])
@require_auth
def get_broker_status(user_id):
    """Return current broker connection status."""
    from broker_manager import get_broker
    return jsonify(get_broker().get_status())


@app.route('/api/auto-trading/broker/login-url', methods=['GET'])
@require_auth
def get_broker_login_url(user_id):
    """Get Zerodha Kite OAuth login URL (only when ZERODHA_API_KEY is set)."""
    from broker_manager import get_broker
    broker = get_broker()
    url = broker.get_login_url()
    if not url:
        return jsonify({'error': 'No live broker configured. Set ZERODHA_API_KEY to enable.'}), 400
    return jsonify({'login_url': url, 'broker': broker.broker_name})


@app.route('/api/auto-trading/broker/callback', methods=['GET'])
def broker_oauth_callback():
    """OAuth callback from Zerodha Kite after user login."""
    request_token = request.args.get('request_token')
    if not request_token:
        return jsonify({'error': 'Missing request_token in callback'}), 400
    from broker_manager import get_broker
    success = get_broker().complete_login(request_token)
    if success:
        return redirect('/?broker=connected')
    return jsonify({'error': 'Broker authentication failed'}), 500


# ═══════════════════════════════════════════════════════════════
# ADVISOR — unified intelligent broker brief
# ═══════════════════════════════════════════════════════════════

@app.route('/api/advisor/brief', methods=['GET'])
@require_auth
def get_advisor_brief(user_id):
    """Return a single payload powering the Advisor page:
    - Latest AI recommendations (entry, target, stop) from recommendation_store
    - Live arbitrage/statistical opportunities scanned from user's watchlist
    - Paper-trading portfolio snapshot (balance, holdings, P&L)
    - Market indices
    """
    try:
        from db import get_db_connection
        from trading_manager import get_trading_portfolio, get_trading_balance
        from arbitrage_detector import ETF_MAPPINGS

        from portfolio_manager import get_monitored_stocks

        # 1. User's personal tickers: watchlist + monitored + portfolio holdings
        with get_db_connection() as conn:
            wl_rows = conn.execute(
                'SELECT DISTINCT ticker FROM watchlist_items WHERE user_id = ?',
                (user_id,)
            ).fetchall()
            alert_rows = conn.execute(
                'SELECT DISTINCT ticker FROM price_alerts WHERE user_id = ? AND triggered = FALSE',
                (user_id,)
            ).fetchall()
        watchlist_tickers = [r['ticker'] for r in wl_rows]
        alert_tickers     = [r['ticker'] for r in alert_rows]
        monitored         = [s['ticker'] for s in (get_monitored_stocks(user_id) or [])]

        # 2. Live market movers — dynamically fetched, no hardcoding
        try:
            movers      = get_top_gainers_losers()
            mover_tickers = [s['ticker'] for s in movers.get('gainers', [])] + \
                            [s['ticker'] for s in movers.get('losers', [])]
        except Exception:
            mover_tickers = []

        # Merge all sources, deduplicated, personal tickers first
        scan_tickers = list(dict.fromkeys(
            watchlist_tickers + monitored + alert_tickers + mover_tickers
        ))

        # 2. Latest AI recommendations from recommendation_store (already have prices)
        recommendations = get_recommendations(user_id, limit=15)

        # 3. Portfolio snapshot
        holdings = get_trading_portfolio(user_id) or []
        balance_info = get_trading_balance(user_id) or {'balance': 100000.0, 'invested': 0, 'pnl': 0}

        # Compute live P&L for holdings
        tickers_held    = [h['ticker'] for h in holdings]
        live_prices     = get_bulk_prices(tickers_held) if tickers_held else {}
        portfolio_value = balance_info.get('balance', 0)
        total_invested  = 0
        for h in holdings:
            qty  = h.get('quantity', 0)
            cost = h.get('total_investment', 0)
            # get_bulk_prices returns {ticker: float}
            lp   = live_prices.get(h['ticker']) or live_prices.get(h['ticker'].upper()) or h.get('avg_buy_price', 0)
            h['current_price']  = lp
            h['current_value']  = round(qty * lp, 2)
            h['unrealised_pnl'] = round(qty * lp - cost, 2)
            h['pnl_pct']        = round((qty * lp - cost) / cost * 100, 2) if cost else 0
            portfolio_value    += qty * lp
            total_invested     += cost

        unrealised_pnl = round(portfolio_value - balance_info.get('balance', 0) - total_invested, 2)

        # 4. Market indices
        try:
            indices = get_market_indices()
        except Exception:
            indices = {}

        return jsonify({
            'recommendations': recommendations,
            'watchlist_tickers': watchlist_tickers,
            'scan_tickers': scan_tickers,   # watchlist + popular defaults when watchlist is small
            'portfolio': {
                'balance':       round(balance_info.get('balance', 0), 2),
                'invested':      round(total_invested, 2),
                'portfolio_value': round(portfolio_value, 2),
                'unrealised_pnl': unrealised_pnl,
                'holdings':      holdings,
                'holdings_count': len(holdings),
            },
            'indices': indices,
        })

    except Exception as exc:
        logger.error(f"get_advisor_brief error: {exc}", exc_info=True)
        return jsonify({'error': str(exc)}), 500


@app.route('/api/advisor/scan', methods=['POST'])
@require_auth
@limiter.limit("20 per hour")
def advisor_scan(user_id):
    """Scan for live market opportunities using user's watchlist (or provided tickers)."""
    try:
        from db import get_db_connection
        from arbitrage_detector import scan_opportunities, ETF_MAPPINGS

        from portfolio_manager import get_monitored_stocks

        body    = request.get_json(silent=True) or {}
        tickers = body.get('tickers', [])

        if not tickers:
            # Build scan universe purely from user data + live market signals
            with get_db_connection() as conn:
                wl_rows = conn.execute(
                    'SELECT DISTINCT ticker FROM watchlist_items WHERE user_id = ?',
                    (user_id,)
                ).fetchall()
            watchlist = [r['ticker'] for r in wl_rows]
            monitored = [s['ticker'] for s in (get_monitored_stocks(user_id) or [])]

            # Live market movers — dynamic, changes every day
            try:
                movers = get_top_gainers_losers()
                mover_tickers = [s['ticker'] for s in movers.get('gainers', [])] + \
                                [s['ticker'] for s in movers.get('losers', [])]
            except Exception:
                mover_tickers = []

            tickers = list(dict.fromkeys(watchlist + monitored + mover_tickers))

        opps = scan_opportunities(tickers) if tickers else []
        return jsonify({'opportunities': opps, 'count': len(opps)})

    except Exception as exc:
        logger.error(f"advisor_scan error: {exc}", exc_info=True)
        return jsonify({'error': str(exc)}), 500


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 60)
    print("  AI Stock Assistant - Backend Server")
    print("  Starting on http://localhost:5000")
    print("=" * 60)

    # Start monitoring service
    monitor_service.start()

    # Start realtime price service
    realtime_service.start()

    # Debug mode only in development (not in production for security)
    debug_mode = os.getenv('FLASK_ENV', 'production') == 'development'
    port = int(os.getenv('PORT', 5000))   # Render/Railway/Fly inject PORT at runtime
    socketio.run(app, host='0.0.0.0', port=port, debug=debug_mode, use_reloader=False)
