"""
Flask Main Server - API endpoints and WebSocket for the Stock Assistant.
Handles chatbot queries, stock data, portfolio management, and monitoring.
"""

import os
import sys
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify

# Windows console (cp1252) can't print ₹ or emoji — reconfigure to UTF-8
if sys.platform == 'win32' and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.platform == 'win32' and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Configure logging
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/backend.log'),
        logging.StreamHandler()
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
from stock_data import (
    get_stock_price, get_stock_info, get_historical_data,
    calculate_technical_indicators, get_market_indices, get_top_gainers_losers,
    search_stocks, get_stocks_by_sector, get_bulk_prices, get_stock_comparison,
    calculate_fibonacci_levels, find_support_resistance,
    POPULAR_INDIAN_STOCKS
)
from news_monitor import fetch_stock_news, fetch_market_news, get_news_summary, get_reddit_sentiment
from ai_advisor import get_stock_advice, get_stock_advice_dual, analyze_stock, get_portfolio_review, compare_stocks, clear_conversation
from ai_advisor_enhanced import get_budget_based_recommendation, extract_budget_from_message
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
    reset_trading_account, OrderType, OrderSide
)
from stock_screener import screen_stocks, get_predefined_screens, get_sectors
from advanced_alerts import (
    create_price_alert, create_percent_change_alert, create_volume_surge_alert,
    create_rsi_alert, create_moving_average_cross_alert, create_week_52_alert,
    get_active_alerts, delete_alert as delete_advanced_alert, reset_alert
)
from forecasting_engine import forecast_stock_price, get_risk_profile
from brain_engine import run_brain_analysis

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

socketio = SocketIO(app, cors_allowed_origins=allowed_origins, async_mode='eventlet')

# Connect monitoring service to socketio
set_monitor_socketio(socketio)

# Connect realtime price service to socketio
set_realtime_socketio(socketio)

# Initialize database
init_database()

# Auto-sync all existing portfolio holdings to monitoring on startup
sync_portfolio_to_monitors()


# ─── Input Validation Functions ────────────────────────────────

import re

def validate_ticker(ticker):
    """Validate Indian stock ticker format."""
    if not ticker or not isinstance(ticker, str):
        raise ValueError("Ticker is required")
    ticker = ticker.upper().strip()
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
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'services': {
            'database': 'connected',
            'monitoring': 'running' if monitor_service.is_running else 'stopped',
        }
    })


# ═══════════════════════════════════════════════════════════════
# CHATBOT ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chatbot queries with dual AI provider support."""
    data = request.json
    if not data or 'message' not in data:
        return jsonify({'error': 'Message is required'}), 400

    user_message = data['message']
    provider = data.get('provider', 'auto')  # NEW: provider selection ('auto', 'openai', 'anthropic')
    save_chat_message('user', user_message)

    # Check if this is a budget-based investment query
    budget = extract_budget_from_message(user_message)
    message_lower = user_message.lower()
    is_investment_query = any(word in message_lower for word in ['invest', 'buy', 'stock', 'recommend', 'which stock'])

    if budget and is_investment_query:
        # Use enhanced AI advisor with real stock data
        logger.info(f"Budget-based query detected: ₹{budget}")
        result = get_budget_based_recommendation(budget, user_message, provider)
        save_chat_message('assistant', result['response'])

        return jsonify({
            'response': result['response'],
            'provider_used': result.get('provider_used', 'none'),
            'query_type': 'budget_investment',
            'budget': budget,
            'stocks_analyzed': result.get('stocks_found', 0),
            'data_used': result.get('data_used', ''),
            'timestamp': datetime.now().isoformat(),
        })

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
            holdings = get_all_holdings()
            if holdings:
                prices = get_bulk_prices([h['ticker'] for h in holdings])
                portfolio_data = calculate_portfolio_value(prices)
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

    # Get AI response with dual provider support
    result = get_stock_advice_dual(
        user_message,
        provider=provider,  # NEW
        stock_data=stock_data,
        news_data=news_data,
        portfolio_data=portfolio_data,
        technicals=technicals
    )

    save_chat_message('assistant', result['response'])

    return jsonify({
        'response': result['response'],
        'provider_used': result.get('provider_used', 'none'),      # NEW
        'model_used': result.get('model_used', 'unknown'),         # NEW
        'query_type': result.get('query_type', 'unknown'),         # NEW
        'data_used': result.get('data_used', ''),
        'error': result.get('error'),
        'timestamp': datetime.now().isoformat(),
        'mentioned_stocks': mentioned_tickers,
    })


@app.route('/api/chat/history', methods=['GET'])
def chat_history():
    """Get chat history."""
    limit = request.args.get('limit', 50, type=int)
    history = get_chat_history(limit)
    return jsonify({'messages': history})


@app.route('/api/chat/clear', methods=['POST'])
def clear_chat():
    """Clear chat history."""
    clear_chat_history()
    clear_conversation()
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
def get_portfolio():
    """Get portfolio with live prices and P&L."""
    holdings = get_all_holdings()
    if not holdings:
        return jsonify({
            'holdings': [],
            'total_value': 0,
            'total_investment': 0,
            'total_pnl': 0,
            'total_pnl_percent': 0,
            'num_holdings': 0,
        })

    tickers = [h['ticker'] for h in holdings]
    prices = get_bulk_prices(tickers)
    portfolio = calculate_portfolio_value(prices)

    return jsonify(portfolio)


@app.route('/api/portfolio/stats', methods=['GET'])
def portfolio_stats():
    """Get comprehensive portfolio statistics."""
    holdings = get_all_holdings()
    if not holdings:
        return jsonify({'error': 'No holdings in portfolio'}), 404

    prices = get_bulk_prices([h['ticker'] for h in holdings])
    stats = get_portfolio_stats(prices)
    return jsonify(stats)


@app.route('/api/portfolio/add', methods=['POST'])
def add_stock():
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
            ticker=ticker,
            name=name,
            quantity=quantity,
            buy_price=buy_price,
            purchase_date=data.get('purchase_date', datetime.now().strftime('%Y-%m-%d')),
            sector=data.get('sector', ''),
            exchange=data.get('exchange', 'NSE'),
        )

        # Automatically start monitoring portfolio stocks
        start_monitoring(ticker, name)

        return jsonify({'id': holding_id, 'message': f'{ticker} added to portfolio'}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/portfolio/<int:holding_id>', methods=['PUT'])
def update_stock(holding_id):
    """Update a portfolio holding."""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    success = update_holding(holding_id, data)
    if success:
        return jsonify({'message': 'Holding updated successfully'})
    return jsonify({'error': 'Holding not found'}), 404


@app.route('/api/portfolio/<int:holding_id>', methods=['DELETE'])
def remove_stock(holding_id):
    """Remove a stock from the portfolio."""
    holding = get_holding_by_id(holding_id)
    if not holding:
        return jsonify({'error': 'Holding not found'}), 404

    delete_holding(holding_id)

    # Stop monitoring if not in any watchlist either
    try:
        from watchlist_manager import get_stock_in_watchlists
        in_watchlists = get_stock_in_watchlists(holding['ticker'])
        if not in_watchlists:
            stop_monitoring(holding['ticker'])
    except Exception:
        stop_monitoring(holding['ticker'])

    return jsonify({'message': f'{holding["ticker"]} removed from portfolio'})


@app.route('/api/portfolio/review', methods=['GET'])
def portfolio_review():
    """Get AI-powered portfolio review."""
    holdings = get_all_holdings()
    if not holdings:
        return jsonify({'error': 'No holdings in portfolio'}), 404

    prices = get_bulk_prices([h['ticker'] for h in holdings])
    portfolio_data = calculate_portfolio_value(prices)
    review = get_portfolio_review(portfolio_data)

    return jsonify(review)


@app.route('/api/portfolio/history', methods=['GET'])
def portfolio_history():
    """Get portfolio value history."""
    days = request.args.get('days', 30, type=int)
    history = get_portfolio_history(days)
    return jsonify({'history': history})


# ═══════════════════════════════════════════════════════════════
# MONITORING ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/monitor/start', methods=['POST'])
def start_stock_monitor():
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

    start_monitoring(
        ticker,
        name=price_data.get('name', ticker),
        price_baseline=price_data['current_price'],
        volume_avg=price_data.get('avg_volume', 0),
    )

    # Start monitoring service if not running
    if not monitor_service.is_running:
        monitor_service.start()

    return jsonify({
        'message': f'Started monitoring {ticker}',
        'baseline_price': price_data['current_price'],
    })


@app.route('/api/monitor/stop', methods=['POST'])
def stop_stock_monitor():
    """Stop monitoring a stock."""
    data = request.json
    if not data or 'ticker' not in data:
        return jsonify({'error': 'Ticker is required'}), 400

    stop_monitoring(data['ticker'].upper())
    return jsonify({'message': f'Stopped monitoring {data["ticker"].upper()}'})


@app.route('/api/monitor/stocks', methods=['GET'])
def monitored_stocks_list():
    """Get all monitored stocks with current status."""
    stocks = get_monitored_stocks(active_only=True)
    enriched = []

    for stock in stocks:
        ticker = stock['ticker']
        price_data = get_stock_price(ticker)
        enriched.append({
            **stock,
            'current_price': price_data['current_price'] if price_data else 0,
            'change_percent': price_data.get('change_percent', 0) if price_data else 0,
        })

    return jsonify({'stocks': enriched})


@app.route('/api/monitor/service', methods=['POST'])
def control_monitor_service():
    """Start or stop the monitoring service."""
    data = request.json
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
def alerts():
    """Get recent alerts."""
    hours = request.args.get('hours', 24, type=int)
    limit = request.args.get('limit', 50, type=int)
    alerts_list = get_recent_alerts(hours=hours, limit=limit)
    return jsonify({'alerts': alerts_list})


@app.route('/api/alerts/<ticker>', methods=['GET'])
def alerts_for_stock(ticker):
    """Get alerts for a specific stock."""
    limit = request.args.get('limit', 20, type=int)
    alerts_list = get_alerts_for_ticker(ticker.upper(), limit=limit)
    return jsonify({'alerts': alerts_list})


@app.route('/api/alerts/<int:alert_id>/read', methods=['POST'])
def read_alert(alert_id):
    """Mark an alert as read."""
    mark_alert_read(alert_id)
    return jsonify({'status': 'marked as read'})


@app.route('/api/alerts/price', methods=['POST'])
def set_price_alert():
    """Set a custom price alert."""
    try:
        data = request.json
        if not data or 'ticker' not in data or 'target_price' not in data:
            return jsonify({'error': 'ticker and target_price are required'}), 400

        # Validate inputs
        ticker = validate_ticker(data['ticker'])
        target_price = validate_price(data['target_price'], 'target_price')

        alert_id = create_price_alert(
            ticker,
            target_price,
            data.get('direction', 'above'),
        )

        return jsonify({'id': alert_id, 'message': 'Price alert set'}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/alerts/advanced', methods=['POST'])
def create_advanced_alert():
    """Create advanced alert (RSI, volume, MA cross, etc.)."""
    try:
        data = request.json
        if not data or 'ticker' not in data or 'alert_type' not in data:
            return jsonify({'error': 'ticker and alert_type are required'}), 400

        ticker = validate_ticker(data['ticker'])
        alert_type = data['alert_type']

        if alert_type == 'PERCENT_CHANGE':
            alert_id = create_percent_change_alert(
                ticker,
                data.get('percent_change', 5),
                data.get('timeframe', '1d')
            )
        elif alert_type == 'VOLUME_SURGE':
            alert_id = create_volume_surge_alert(
                ticker,
                data.get('volume_multiplier', 2.0)
            )
        elif alert_type == 'RSI_LEVEL':
            alert_id = create_rsi_alert(
                ticker,
                data.get('rsi_level', 30),
                data.get('condition', 'below')
            )
        elif alert_type == 'MA_CROSS':
            alert_id = create_moving_average_cross_alert(
                ticker,
                data.get('ma_type', 'sma_20')
            )
        elif alert_type == 'WEEK_52':
            alert_id = create_week_52_alert(
                ticker,
                data.get('level', 'high')
            )
        else:
            return jsonify({'error': 'Invalid alert type'}), 400

        return jsonify({'id': alert_id, 'message': f'{alert_type} alert created'}), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/alerts/advanced', methods=['GET'])
def get_advanced_alerts():
    """Get all active advanced alerts."""
    ticker = request.args.get('ticker')
    alerts = get_active_alerts(ticker=ticker)

    return jsonify({'alerts': alerts, 'count': len(alerts)})


@app.route('/api/alerts/advanced/<int:alert_id>', methods=['DELETE'])
def delete_advanced_alert_endpoint(alert_id):
    """Delete an advanced alert."""
    success = delete_advanced_alert(alert_id)

    if success:
        return jsonify({'message': 'Alert deleted'})

    return jsonify({'error': 'Alert not found'}), 404


@app.route('/api/alerts/advanced/<int:alert_id>/reset', methods=['POST'])
def reset_advanced_alert(alert_id):
    """Reset a triggered alert."""
    success = reset_alert(alert_id)

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
def get_watchlists():
    """Get all watchlists."""
    watchlists = get_all_watchlists()
    return jsonify({'watchlists': watchlists})


@app.route('/api/watchlists', methods=['POST'])
def create_new_watchlist():
    """Create a new watchlist."""
    data = request.json
    if not data or 'name' not in data:
        return jsonify({'error': 'Watchlist name is required'}), 400

    name = data['name']
    description = data.get('description', '')
    color = data.get('color', '#3b82f6')

    watchlist_id = create_watchlist(name, description, color)
    return jsonify({'id': watchlist_id, 'message': 'Watchlist created'}), 201


@app.route('/api/watchlists/<int:watchlist_id>', methods=['GET'])
def get_watchlist(watchlist_id):
    """Get a specific watchlist with all items."""
    watchlist = get_watchlist_by_id(watchlist_id)
    if not watchlist:
        return jsonify({'error': 'Watchlist not found'}), 404

    # Enrich with real-time prices
    for item in watchlist['items']:
        price_data = get_stock_price(item['ticker'])
        if price_data:
            item['price_data'] = price_data

    return jsonify(watchlist)


@app.route('/api/watchlists/<int:watchlist_id>', methods=['PUT'])
def update_watchlist_endpoint(watchlist_id):
    """Update watchlist properties."""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    success = update_watchlist(
        watchlist_id,
        name=data.get('name'),
        description=data.get('description'),
        color=data.get('color')
    )

    if success:
        return jsonify({'message': 'Watchlist updated'})
    return jsonify({'error': 'Watchlist not found'}), 404


@app.route('/api/watchlists/<int:watchlist_id>', methods=['DELETE'])
def delete_watchlist_endpoint(watchlist_id):
    """Delete a watchlist."""
    success = delete_watchlist(watchlist_id)
    if success:
        return jsonify({'message': 'Watchlist deleted'})
    return jsonify({'error': 'Watchlist not found'}), 404


@app.route('/api/watchlists/reorder', methods=['POST'])
def reorder_watchlists_endpoint():
    """Reorder watchlists."""
    data = request.json
    if not data or 'order' not in data:
        return jsonify({'error': 'Order array is required'}), 400

    reorder_watchlists(data['order'])
    return jsonify({'message': 'Watchlists reordered'})


@app.route('/api/watchlists/<int:watchlist_id>/items', methods=['POST'])
def add_to_watchlist(watchlist_id):
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

        item_id = add_stock_to_watchlist(watchlist_id, ticker, name, sector)

        if item_id is None:
            return jsonify({'error': 'Stock already in watchlist'}), 409

        # Start monitoring watchlist stocks so price alerts and signals fire
        start_monitoring(ticker, name)

        return jsonify({'id': item_id, 'message': f'{ticker} added to watchlist'}), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400


@app.route('/api/watchlists/<int:watchlist_id>/items/<ticker>', methods=['DELETE'])
def remove_from_watchlist(watchlist_id, ticker):
    """Remove a stock from a watchlist."""
    success = remove_stock_from_watchlist(watchlist_id, ticker.upper())
    if success:
        return jsonify({'message': f'{ticker} removed from watchlist'})
    return jsonify({'error': 'Stock not found in watchlist'}), 404


@app.route('/api/watchlists/<int:watchlist_id>/reorder', methods=['POST'])
def reorder_watchlist_items_endpoint(watchlist_id):
    """Reorder items in a watchlist."""
    data = request.json
    if not data or 'order' not in data:
        return jsonify({'error': 'Order array is required'}), 400

    reorder_watchlist_items(watchlist_id, data['order'])
    return jsonify({'message': 'Watchlist items reordered'})


@app.route('/api/watchlists/move', methods=['POST'])
def move_stock_between_watchlists():
    """Move a stock from one watchlist to another."""
    data = request.json
    required = ['ticker', 'from_watchlist_id', 'to_watchlist_id']

    for field in required:
        if field not in data:
            return jsonify({'error': f'{field} is required'}), 400

    success = move_stock_to_watchlist(
        data['ticker'].upper(),
        data['from_watchlist_id'],
        data['to_watchlist_id']
    )

    if success:
        return jsonify({'message': 'Stock moved successfully'})
    return jsonify({'error': 'Failed to move stock'}), 400


@app.route('/api/watchlists/stock/<ticker>', methods=['GET'])
def get_stock_watchlists(ticker):
    """Get all watchlists containing a specific stock."""
    watchlists = get_stock_in_watchlists(ticker.upper())
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
def place_trading_order():
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
            ticker=ticker,
            name=name,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=current_price if order_type == OrderType.MARKET.value else data.get('price'),
            stop_price=data.get('stop_price'),
            limit_price=data.get('limit_price')
        )

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
def get_trading_orders():
    """Get all orders."""
    status = request.args.get('status')
    limit = request.args.get('limit', 50, type=int)

    orders = get_orders(status=status, limit=limit)
    return jsonify({'orders': orders})


@app.route('/api/trading/orders/<int:order_id>', methods=['GET'])
def get_trading_order(order_id):
    """Get specific order details."""
    order = get_order_by_id(order_id)

    if not order:
        return jsonify({'error': 'Order not found'}), 404

    return jsonify(order)


@app.route('/api/trading/orders/<int:order_id>/cancel', methods=['POST'])
def cancel_trading_order(order_id):
    """Cancel a pending order."""
    success = cancel_order(order_id)

    if success:
        return jsonify({'message': 'Order cancelled'})

    return jsonify({'error': 'Order not found or already executed'}), 404


@app.route('/api/trading/trades', methods=['GET'])
def get_trading_trades():
    """Get trade history."""
    limit = request.args.get('limit', 50, type=int)
    trades = get_trades(limit=limit)

    return jsonify({'trades': trades})


@app.route('/api/trading/portfolio', methods=['GET'])
def get_trading_portfolio_endpoint():
    """Get trading portfolio with live P&L."""
    holdings = get_trading_portfolio()

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

    balance = get_trading_balance()

    return jsonify({
        'holdings': holdings,
        'balance': balance,
        'num_holdings': len(holdings)
    })


@app.route('/api/trading/balance', methods=['GET'])
def get_trading_balance_endpoint():
    """Get trading account balance."""
    balance = get_trading_balance()
    return jsonify(balance)


@app.route('/api/trading/reset', methods=['POST'])
def reset_trading_account_endpoint():
    """Reset trading account (for testing)."""
    reset_trading_account()
    return jsonify({'message': 'Trading account reset to ₹1,00,000'})


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


# ═══════════════════════════════════════════════════════════════
# NEWS ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.route('/api/news/<ticker>', methods=['GET'])
def stock_news(ticker):
    """Get news for a specific stock."""
    news = fetch_stock_news(ticker.upper())
    return jsonify({'ticker': ticker.upper(), 'news': news})


@app.route('/api/news/market', methods=['GET'])
def market_news():
    """Get general market news."""
    news = fetch_market_news()
    return jsonify({'news': news})


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
    print(f"Client connected: {request.sid}")
    emit('connected', {'status': 'connected', 'timestamp': datetime.now().isoformat()})


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
    """Send current portfolio data."""
    holdings = get_all_holdings()
    if holdings:
        prices = get_bulk_prices([h['ticker'] for h in holdings])
        portfolio = calculate_portfolio_value(prices)
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
    socketio.run(app, host='0.0.0.0', port=5000, debug=debug_mode, use_reloader=False)
