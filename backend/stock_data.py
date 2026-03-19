"""
Stock Data Module - Real-time stock data fetcher using yfinance.
Handles NSE/BSE stock prices, historical data, technical indicators,
and stock search functionality with caching.
"""

import yfinance as yf
import requests
import pandas as pd
import numpy as np
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from functools import lru_cache
import time
import json

try:
    from cache import (
        get_cached_price, cache_price,
        get_cached_technicals, cache_technicals,
        get_cached_indices, cache_indices,
        get_cached_bulk_prices, cache_bulk_prices,
    )
    _redis_cache_available = True
except ImportError:
    _redis_cache_available = False

logger = logging.getLogger(__name__)

# ─── Cache Layer ────────────────────────────────────────────────

_cache = {}
CACHE_DURATION = 60  # seconds


def _get_cached(key):
    """Get cached value if not expired."""
    if key in _cache:
        value, timestamp = _cache[key]
        if time.time() - timestamp < CACHE_DURATION:
            return value
    return None


def _set_cached(key, value):
    """Set cache value with timestamp."""
    _cache[key] = (value, time.time())


def clear_cache():
    """Clear all cached data."""
    _cache.clear()


# ─── NSE/BSE Ticker Formatting ─────────────────────────────────

# Top Indian stocks with NSE tickers
POPULAR_INDIAN_STOCKS = {
    'RELIANCE': {'name': 'Reliance Industries Ltd', 'sector': 'Energy', 'nse': 'RELIANCE.NS', 'bse': 'RELIANCE.BO'},
    'TCS': {'name': 'Tata Consultancy Services', 'sector': 'IT', 'nse': 'TCS.NS', 'bse': 'TCS.BO'},
    'HDFCBANK': {'name': 'HDFC Bank Ltd', 'sector': 'Banking', 'nse': 'HDFCBANK.NS', 'bse': 'HDFCBANK.BO'},
    'INFY': {'name': 'Infosys Ltd', 'sector': 'IT', 'nse': 'INFY.NS', 'bse': 'INFY.BO'},
    'ICICIBANK': {'name': 'ICICI Bank Ltd', 'sector': 'Banking', 'nse': 'ICICIBANK.NS', 'bse': 'ICICIBANK.BO'},
    'HINDUNILVR': {'name': 'Hindustan Unilever Ltd', 'sector': 'FMCG', 'nse': 'HINDUNILVR.NS', 'bse': 'HINDUNILVR.BO'},
    'SBIN': {'name': 'State Bank of India', 'sector': 'Banking', 'nse': 'SBIN.NS', 'bse': 'SBIN.BO'},
    'BHARTIARTL': {'name': 'Bharti Airtel Ltd', 'sector': 'Telecom', 'nse': 'BHARTIARTL.NS', 'bse': 'BHARTIARTL.BO'},
    'ITC': {'name': 'ITC Ltd', 'sector': 'FMCG', 'nse': 'ITC.NS', 'bse': 'ITC.BO'},
    'KOTAKBANK': {'name': 'Kotak Mahindra Bank', 'sector': 'Banking', 'nse': 'KOTAKBANK.NS', 'bse': 'KOTAKBANK.BO'},
    'LT': {'name': 'Larsen & Toubro Ltd', 'sector': 'Infrastructure', 'nse': 'LT.NS', 'bse': 'LT.BO'},
    'AXISBANK': {'name': 'Axis Bank Ltd', 'sector': 'Banking', 'nse': 'AXISBANK.NS', 'bse': 'AXISBANK.BO'},
    'WIPRO': {'name': 'Wipro Ltd', 'sector': 'IT', 'nse': 'WIPRO.NS', 'bse': 'WIPRO.BO'},
    'HCLTECH': {'name': 'HCL Technologies Ltd', 'sector': 'IT', 'nse': 'HCLTECH.NS', 'bse': 'HCLTECH.BO'},
    'ASIANPAINT': {'name': 'Asian Paints Ltd', 'sector': 'Consumer', 'nse': 'ASIANPAINT.NS', 'bse': 'ASIANPAINT.BO'},
    'MARUTI': {'name': 'Maruti Suzuki India Ltd', 'sector': 'Automobile', 'nse': 'MARUTI.NS', 'bse': 'MARUTI.BO'},
    'SUNPHARMA': {'name': 'Sun Pharmaceutical', 'sector': 'Pharma', 'nse': 'SUNPHARMA.NS', 'bse': 'SUNPHARMA.BO'},
    # 'TATAMOTORS': {'name': 'Tata Motors Ltd', 'sector': 'Automobile', 'nse': 'TATAMOTORS.NS', 'bse': 'TATAMOTORS.BO'},  # Temporarily unavailable
    'TATASTEEL': {'name': 'Tata Steel Ltd', 'sector': 'Metal', 'nse': 'TATASTEEL.NS', 'bse': 'TATASTEEL.BO'},
    'POWERGRID': {'name': 'Power Grid Corporation', 'sector': 'Power', 'nse': 'POWERGRID.NS', 'bse': 'POWERGRID.BO'},
    'NTPC': {'name': 'NTPC Ltd', 'sector': 'Power', 'nse': 'NTPC.NS', 'bse': 'NTPC.BO'},
    'ULTRACEMCO': {'name': 'UltraTech Cement Ltd', 'sector': 'Cement', 'nse': 'ULTRACEMCO.NS', 'bse': 'ULTRACEMCO.BO'},
    'TITAN': {'name': 'Titan Company Ltd', 'sector': 'Consumer', 'nse': 'TITAN.NS', 'bse': 'TITAN.BO'},
    'BAJFINANCE': {'name': 'Bajaj Finance Ltd', 'sector': 'Finance', 'nse': 'BAJFINANCE.NS', 'bse': 'BAJFINANCE.BO'},
    'BAJAJFINSV': {'name': 'Bajaj Finserv Ltd', 'sector': 'Finance', 'nse': 'BAJAJFINSV.NS', 'bse': 'BAJAJFINSV.BO'},
    'NESTLEIND': {'name': 'Nestle India Ltd', 'sector': 'FMCG', 'nse': 'NESTLEIND.NS', 'bse': 'NESTLEIND.BO'},
    'TECHM': {'name': 'Tech Mahindra Ltd', 'sector': 'IT', 'nse': 'TECHM.NS', 'bse': 'TECHM.BO'},
    'ADANIENT': {'name': 'Adani Enterprises Ltd', 'sector': 'Conglomerate', 'nse': 'ADANIENT.NS', 'bse': 'ADANIENT.BO'},
    'ADANIPORTS': {'name': 'Adani Ports & SEZ', 'sector': 'Infrastructure', 'nse': 'ADANIPORTS.NS', 'bse': 'ADANIPORTS.BO'},
    'COALINDIA': {'name': 'Coal India Ltd', 'sector': 'Mining', 'nse': 'COALINDIA.NS', 'bse': 'COALINDIA.BO'},
    'ONGC': {'name': 'Oil & Natural Gas Corp', 'sector': 'Energy', 'nse': 'ONGC.NS', 'bse': 'ONGC.BO'},
    'JSWSTEEL': {'name': 'JSW Steel Ltd', 'sector': 'Metal', 'nse': 'JSWSTEEL.NS', 'bse': 'JSWSTEEL.BO'},
    'M&M': {'name': 'Mahindra & Mahindra Ltd', 'sector': 'Automobile', 'nse': 'M&M.NS', 'bse': 'M&M.BO'},
    'DRREDDY': {'name': "Dr. Reddy's Laboratories", 'sector': 'Pharma', 'nse': 'DRREDDY.NS', 'bse': 'DRREDDY.BO'},
    'CIPLA': {'name': 'Cipla Ltd', 'sector': 'Pharma', 'nse': 'CIPLA.NS', 'bse': 'CIPLA.BO'},
    'DIVISLAB': {'name': "Divi's Laboratories", 'sector': 'Pharma', 'nse': 'DIVISLAB.NS', 'bse': 'DIVISLAB.BO'},
    'EICHERMOT': {'name': 'Eicher Motors Ltd', 'sector': 'Automobile', 'nse': 'EICHERMOT.NS', 'bse': 'EICHERMOT.BO'},
    'HEROMOTOCO': {'name': 'Hero MotoCorp Ltd', 'sector': 'Automobile', 'nse': 'HEROMOTOCO.NS', 'bse': 'HEROMOTOCO.BO'},
    'BPCL': {'name': 'Bharat Petroleum Corp', 'sector': 'Energy', 'nse': 'BPCL.NS', 'bse': 'BPCL.BO'},
    'BRITANNIA': {'name': 'Britannia Industries Ltd', 'sector': 'FMCG', 'nse': 'BRITANNIA.NS', 'bse': 'BRITANNIA.BO'},
}

# Market indices
INDICES = {
    'NIFTY50': '^NSEI',
    'SENSEX': '^BSESN',
    'NIFTYBANK': '^NSEBANK',
    'NIFTYIT': '^CNXIT',
}


def format_ticker(ticker, exchange='NSE'):
    """Format ticker symbol for yfinance API."""
    ticker = ticker.upper().strip()
    if ticker.endswith('.NS') or ticker.endswith('.BO'):
        return ticker
    if exchange.upper() == 'BSE':
        return f"{ticker}.BO"
    return f"{ticker}.NS"


# ─── Stock Price Data ───────────────────────────────────────────

def get_stock_price(ticker):
    """Get real-time stock price and basic info."""
    cache_key = f"price_{ticker}"
    # L1: in-process dict (sub-millisecond, same process)
    cached = _get_cached(cache_key)
    if cached:
        return cached
    # L2: Redis (shared across worker processes, 30s TTL)
    if _redis_cache_available:
        redis_hit = get_cached_price(ticker)
        if redis_hit:
            _set_cached(cache_key, redis_hit)   # warm L1
            return redis_hit

    try:
        yf_ticker = format_ticker(ticker)

        # Retry up to 2 times with backoff on transient yfinance failures
        hist = None
        for attempt in range(3):
            try:
                stock = yf.Ticker(yf_ticker)
                hist = stock.history(period='5d')
                if hist is not None and not hist.empty and len(hist) >= 1:
                    break
            except Exception as retry_exc:
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
                    logger.debug(f"Retrying {ticker} (attempt {attempt + 2}/3): {retry_exc}")
                else:
                    raise

        if hist is None or hist.empty or len(hist) < 1:
            logger.warning(f"No price data available for {ticker}")
            return None

        current_price = float(hist['Close'].iloc[-1])
        # Use prev close safely — may not exist on brand-new listing days
        prev_close = float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_price
        change = current_price - prev_close
        change_pct = (change / prev_close * 100) if prev_close > 0 else 0

        # Get additional info (with fallback to avoid crashes)
        info = {}
        try:
            info = stock.info
        except Exception as e:
            logger.debug(f"Could not fetch detailed info for {ticker}: {e}")
            info = {}

        result = {
            'ticker': ticker.upper(),
            'name': info.get('longName', info.get('shortName', ticker)),
            'current_price': round(float(current_price), 2),
            'previous_close': round(float(prev_close), 2),
            'change': round(float(change), 2),
            'change_percent': round(float(change_pct), 2),
            'day_high': round(float(info.get('dayHigh', current_price)), 2) if info.get('dayHigh') else round(float(current_price), 2),
            'day_low': round(float(info.get('dayLow', current_price)), 2) if info.get('dayLow') else round(float(current_price), 2),
            'volume': int(hist['Volume'].iloc[-1]) if not hist['Volume'].empty else 0,
            'avg_volume': info.get('averageVolume', 0),
            'market_cap': info.get('marketCap', 0),
            'fifty_two_week_high': info.get('fiftyTwoWeekHigh', 0),
            'fifty_two_week_low': info.get('fiftyTwoWeekLow', 0),
            'sector': info.get('sector', ''),
            'industry': info.get('industry', ''),
            'timestamp': datetime.now().isoformat()
        }

        _set_cached(cache_key, result)
        if _redis_cache_available:
            cache_price(ticker, result, ttl=30)
        return result

    except Exception as e:
        logger.error(f"Error fetching price for {ticker}: {e}")
        return None


def get_stock_info(ticker):
    """Get comprehensive stock information including fundamentals."""
    cache_key = f"info_{ticker}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        yf_ticker = format_ticker(ticker)
        stock = yf.Ticker(yf_ticker)
        info = stock.info

        result = {
            'ticker': ticker.upper(),
            'name': info.get('longName', info.get('shortName', ticker)),
            'sector': info.get('sector', 'N/A'),
            'industry': info.get('industry', 'N/A'),
            'market_cap': info.get('marketCap', 0),
            'market_cap_formatted': _format_indian_number(info.get('marketCap', 0)),
            'pe_ratio': round(info.get('trailingPE', 0) or 0, 2),
            'forward_pe': round(info.get('forwardPE', 0) or 0, 2),
            'eps': round(info.get('trailingEps', 0) or 0, 2),
            'book_value': round(info.get('bookValue', 0) or 0, 2),
            'price_to_book': round(info.get('priceToBook', 0) or 0, 2),
            'dividend_yield': round((info.get('dividendYield', 0) or 0) * 100, 2),
            'debt_to_equity': round(info.get('debtToEquity', 0) or 0, 2),
            'roe': round((info.get('returnOnEquity', 0) or 0) * 100, 2),
            'revenue': info.get('totalRevenue', 0),
            'profit_margin': round((info.get('profitMargins', 0) or 0) * 100, 2),
            'operating_margin': round((info.get('operatingMargins', 0) or 0) * 100, 2),
            'beta': round(info.get('beta', 0) or 0, 2),
            'fifty_two_week_high': info.get('fiftyTwoWeekHigh', 0),
            'fifty_two_week_low': info.get('fiftyTwoWeekLow', 0),
            'avg_volume_10d': info.get('averageDailyVolume10Day', 0),
            'avg_volume_3m': info.get('averageVolume', 0),
            'description': info.get('longBusinessSummary', ''),
            'website': info.get('website', ''),
            'employees': info.get('fullTimeEmployees', 0),
        }

        _set_cached(cache_key, result)
        return result

    except Exception as e:
        logger.error(f"Error fetching info for {ticker}: {e}")
        return None


def get_historical_data(ticker, period='1y', interval='1d'):
    """
    Get historical price data.
    period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
    interval: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
    """
    cache_key = f"hist_{ticker}_{period}_{interval}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        yf_ticker = format_ticker(ticker)
        stock = yf.Ticker(yf_ticker)
        hist = stock.history(period=period, interval=interval)

        if hist.empty:
            return None

        INTRADAY_INTERVALS = {'1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h'}
        data = []
        for date, row in hist.iterrows():
            if interval in INTRADAY_INTERVALS:
                # Unix timestamp in seconds — lightweight-charts uses this for intraday
                date_val = int(date.timestamp())
            else:
                date_val = date.strftime('%Y-%m-%d')
            data.append({
                'date': date_val,
                'open': round(float(row['Open']), 2),
                'high': round(float(row['High']), 2),
                'low': round(float(row['Low']), 2),
                'close': round(float(row['Close']), 2),
                'volume': int(row['Volume']),
            })

        _set_cached(cache_key, data)
        return data

    except Exception as e:
        logger.error(f"Error fetching historical data for {ticker}: {e}")
        return None


# ─── Technical Indicators ──────────────────────────────────────

def calculate_technical_indicators(ticker, period='6mo'):
    """Calculate RSI, MACD, Bollinger Bands, Moving Averages."""
    # In-process L1 cache (keyed by period so 3mo and 6mo don't collide)
    cache_key = f"tech_{ticker}_{period}"
    cached = _get_cached(cache_key)
    if cached:
        return cached
    # Redis L2 cache (300s TTL — technicals don't change second-to-second)
    if _redis_cache_available:
        redis_hit = get_cached_technicals(ticker)
        if redis_hit:
            _set_cached(cache_key, redis_hit)
            return redis_hit

    try:
        yf_ticker = format_ticker(ticker)
        stock = yf.Ticker(yf_ticker)
        hist = stock.history(period=period)

        if hist.empty or len(hist) < 30:
            return None

        close = hist['Close']

        # Moving Averages
        sma_20 = close.rolling(window=20).mean().iloc[-1]
        sma_50 = close.rolling(window=50).mean().iloc[-1] if len(close) >= 50 else None
        sma_200 = close.rolling(window=200).mean().iloc[-1] if len(close) >= 200 else None
        ema_12 = close.ewm(span=12, adjust=False).mean().iloc[-1]
        ema_26 = close.ewm(span=26, adjust=False).mean().iloc[-1]

        # RSI (14-day)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()

        # Prevent division by zero in RSI calculation
        if loss.iloc[-1] == 0:
            rsi_value = 100.0  # All gains, no losses
        else:
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            rsi_value = rsi.iloc[-1]

        # MACD — compute full series for correct signal line
        ema_12_series = close.ewm(span=12, adjust=False).mean()
        ema_26_series = close.ewm(span=26, adjust=False).mean()
        macd_series    = ema_12_series - ema_26_series
        signal_series  = macd_series.ewm(span=9, adjust=False).mean()
        macd_line      = float(macd_series.iloc[-1])
        signal_line    = float(signal_series.iloc[-1])
        macd_histogram = macd_line - signal_line

        # Bollinger Bands (20-day, 2 std)
        bb_middle = sma_20
        bb_std = close.rolling(window=20).std().iloc[-1]
        bb_upper = bb_middle + (2 * bb_std)
        bb_lower = bb_middle - (2 * bb_std)

        # Volume analysis
        avg_volume_30 = hist['Volume'].tail(30).mean()
        current_volume = hist['Volume'].iloc[-1]
        volume_ratio = current_volume / avg_volume_30 if avg_volume_30 > 0 else 1

        current_price = close.iloc[-1]

        # Generate signal interpretation
        signals = []
        if rsi_value > 70:
            signals.append('RSI indicates OVERBOUGHT - potential reversal down')
        elif rsi_value < 30:
            signals.append('RSI indicates OVERSOLD - potential reversal up')
        else:
            signals.append(f'RSI is neutral at {rsi_value:.1f}')

        if macd_line > signal_line:
            signals.append('MACD is BULLISH (above signal line)')
        else:
            signals.append('MACD is BEARISH (below signal line)')

        if current_price > bb_upper:
            signals.append('Price is ABOVE upper Bollinger Band - potentially overbought')
        elif current_price < bb_lower:
            signals.append('Price is BELOW lower Bollinger Band - potentially oversold')

        if sma_50 and current_price > sma_50:
            signals.append('Price is above 50-day SMA - bullish trend')
        elif sma_50:
            signals.append('Price is below 50-day SMA - bearish trend')

        result = {
            'ticker': ticker.upper(),
            'current_price': round(float(current_price), 2),
            'sma_20': round(float(sma_20), 2),
            'sma_50': round(float(sma_50), 2) if sma_50 else None,
            'sma_200': round(float(sma_200), 2) if sma_200 else None,
            'ema_12': round(float(ema_12), 2),
            'ema_26': round(float(ema_26), 2),
            'rsi': round(float(rsi_value), 2),
            'macd': round(float(macd_line), 2),
            'macd_signal': round(float(signal_line), 2),
            'macd_histogram': round(float(macd_histogram), 2),
            'bb_upper': round(float(bb_upper), 2),
            'bb_middle': round(float(bb_middle), 2),
            'bb_lower': round(float(bb_lower), 2),
            'volume': int(current_volume),
            'avg_volume_30d': int(avg_volume_30),
            'volume_ratio': round(float(volume_ratio), 2),
            'signals': signals,
        }

        _set_cached(cache_key, result)
        if _redis_cache_available:
            cache_technicals(ticker, result, ttl=300)
        return result

    except Exception as e:
        logger.error(f"Error calculating indicators for {ticker}: {e}")
        return None


# ─── Market Overview ────────────────────────────────────────────

def get_market_indices():
    """Get current values for major Indian market indices."""
    cache_key = "market_indices"
    cached = _get_cached(cache_key)
    if cached:
        return cached
    if _redis_cache_available:
        redis_hit = get_cached_indices()
        if redis_hit:
            _set_cached(cache_key, redis_hit)
            return redis_hit

    def _fetch_one(item):
        name, symbol = item
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='2d')
            if not hist.empty:
                current = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2] if len(hist) > 1 else current
                change = current - prev
                change_pct = (change / prev * 100) if prev > 0 else 0
                return name, {
                    'value': round(float(current), 2),
                    'change': round(float(change), 2),
                    'change_percent': round(float(change_pct), 2),
                }
        except Exception as e:
            print(f"Error fetching {name}: {e}")
        return name, {'value': 0, 'change': 0, 'change_percent': 0}

    results = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        for name, data in executor.map(_fetch_one, INDICES.items()):
            results[name] = data

    _set_cached(cache_key, results)
    if _redis_cache_available:
        cache_indices(results, ttl=300)
    return results


def get_top_gainers_losers():
    """Get top gainers and losers from NIFTY 50 stocks."""
    cache_key = "gainers_losers"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    stocks_data = []
    # Fetch in parallel for speed (30 stocks / 10 threads = fast)
    with ThreadPoolExecutor(max_workers=10) as executor:
        # Define helper for mapping
        def fetch_safe(sym):
            try:
                return get_stock_price(sym)
            except:
                return None

        # Submit tasks
        tickers = list(POPULAR_INDIAN_STOCKS.keys())[:40] 
        results = executor.map(fetch_safe, tickers)
        
        # Collect non-None results
        for r in results:
            if r:
                stocks_data.append(r)

    stocks_data.sort(key=lambda x: x['change_percent'], reverse=True)
    result = {
        'gainers': stocks_data[:5],
        'losers': stocks_data[-5:][::-1] if len(stocks_data) >= 5 else [],
    }

    _set_cached(cache_key, result)
    return result


# ─── Stock Search ───────────────────────────────────────────────

def search_stocks(query):
    """Search for stocks (local + remote Yahoo)."""
    query_upper = query.upper().strip()
    results = []
    seen_tickers = set()

    # 1. Local Search (Fast)
    for ticker, info in POPULAR_INDIAN_STOCKS.items():
        if query_upper in ticker or query_upper in info['name'].upper():
            results.append({
                'ticker': ticker,
                'name': info['name'],
                'sector': info['sector'],
                'exchange': 'NSE',
            })
            seen_tickers.add(ticker)

    # 2. Remote Search (if local results are few)
    # Only search if query is meaningful (>2 chars) to avoid spam
    if len(results) < 5 and len(query) > 1:
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            # Yahoo Finance Autocomplete API
            url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=10&newsCount=0"
            resp = requests.get(url, headers=headers, timeout=1.5)
            data = resp.json()

            for q in data.get('quotes', []):
                sym = q.get('symbol', '')
                exch = q.get('exchDisp', '').upper()
                type_disp = q.get('typeDisp', '').upper()

                # Filter for Indian stocks (Equity only)
                if ('.NS' in sym or '.BO' in sym or exch in ['NSE', 'BSE', 'NSI']) and type_disp == 'EQUITY':
                    # Normalize ticker: strip .NS (default), keep .BO
                    clean_ticker = sym.replace('.NS', '')
                    
                    if clean_ticker not in seen_tickers:
                        results.append({
                            'ticker': clean_ticker,
                            'name': q.get('shortname') or q.get('longname') or sym,
                            'sector': q.get('sector', 'Unknown'),
                            'exchange': exch if exch != 'NSI' else 'NSE',
                        })
                        seen_tickers.add(clean_ticker)
        except Exception as e:
            logger.debug(f"Remote search failed for {query}: {e}")

    return results[:10]


def get_stocks_by_sector(sector):
    """Get all stocks in a specific sector."""
    sector = sector.upper().strip()
    results = []
    for ticker, info in POPULAR_INDIAN_STOCKS.items():
        if sector in info['sector'].upper():
            results.append({
                'ticker': ticker,
                'name': info['name'],
                'sector': info['sector'],
            })
    return results


# ─── Bulk Price Fetch ───────────────────────────────────────────

def get_bulk_prices(tickers):
    """Fetch current prices for multiple tickers at once."""
    if _redis_cache_available and tickers:
        redis_hit = get_cached_bulk_prices(tickers)
        if redis_hit:
            return redis_hit

    prices = {}
    for ticker in tickers:
        try:
            data = get_stock_price(ticker)
            if data:
                prices[ticker.upper()] = data['current_price']
        except Exception as e:
            logger.debug(f"Failed to fetch price for {ticker}: {e}")
            continue

    if _redis_cache_available and prices:
        cache_bulk_prices(tickers, prices, ttl=30)
    return prices


# ─── Helper Functions ───────────────────────────────────────────

def _format_indian_number(num):
    """Format number in Indian notation (Lakhs, Crores)."""
    if num is None or num == 0:
        return '0'
    if num >= 1e7:
        return f"₹{num / 1e7:.2f} Cr"
    elif num >= 1e5:
        return f"₹{num / 1e5:.2f} L"
    elif num >= 1e3:
        return f"₹{num / 1e3:.2f} K"
    else:
        return f"₹{num:.2f}"


def get_stock_comparison(ticker1, ticker2):
    """Compare two stocks side by side."""
    info1 = get_stock_info(ticker1)
    info2 = get_stock_info(ticker2)
    tech1 = calculate_technical_indicators(ticker1)
    tech2 = calculate_technical_indicators(ticker2)

    if not info1 or not info2:
        return None

    return {
        'stock1': {**info1, 'technicals': tech1},
        'stock2': {**info2, 'technicals': tech2},
    }


# ═══════════════════════════════════════════════════════════════
# ADVANCED TECHNICAL ANALYSIS
# ═══════════════════════════════════════════════════════════════

def calculate_fibonacci_levels(ticker, period='6mo'):
    """
    Calculate Fibonacci retracement levels from high/low swing points.

    Args:
        ticker: Stock ticker symbol
        period: Historical period to analyze (1mo, 3mo, 6mo, 1y, 2y)

    Returns:
        dict with swing high/low, Fibonacci levels, and current price
    """
    try:
        hist = get_historical_data(ticker, period=period)
        if not hist:
            return {'error': f'No historical data for {ticker}'}

        prices = [p['close'] for p in hist]
        high = max(prices)
        low = min(prices)
        diff = high - low

        current_price = prices[-1]

        # Calculate Fibonacci retracement levels
        levels = {
            '0.0%': round(high, 2),
            '23.6%': round(high - (0.236 * diff), 2),
            '38.2%': round(high - (0.382 * diff), 2),
            '50.0%': round(high - (0.5 * diff), 2),
            '61.8%': round(high - (0.618 * diff), 2),
            '78.6%': round(high - (0.786 * diff), 2),
            '100.0%': round(low, 2)
        }

        # Determine current level
        current_level = None
        for level_name, level_price in levels.items():
            if abs(current_price - level_price) / current_price < 0.02:  # Within 2%
                current_level = level_name
                break

        return {
            'ticker': ticker,
            'swing_high': round(high, 2),
            'swing_low': round(low, 2),
            'range': round(diff, 2),
            'levels': levels,
            'current_price': round(current_price, 2),
            'current_level': current_level,
            'period': period,
            'analysis': _fibonacci_analysis(current_price, levels)
        }

    except Exception as e:
        return {'error': str(e)}


def _fibonacci_analysis(current_price, levels):
    """Generate analysis based on current price vs Fibonacci levels."""
    level_prices = list(levels.values())

    # Find nearest support (below current price)
    supports = [p for p in level_prices if p < current_price]
    nearest_support = max(supports) if supports else None

    # Find nearest resistance (above current price)
    resistances = [p for p in level_prices if p > current_price]
    nearest_resistance = min(resistances) if resistances else None

    analysis = []

    if nearest_support:
        support_distance = ((current_price - nearest_support) / current_price) * 100
        analysis.append(f"Nearest Fibonacci support at ₹{nearest_support:.2f} ({support_distance:.1f}% below)")

    if nearest_resistance:
        resistance_distance = ((nearest_resistance - current_price) / current_price) * 100
        analysis.append(f"Nearest Fibonacci resistance at ₹{nearest_resistance:.2f} ({resistance_distance:.1f}% above)")

    return analysis


def find_support_resistance(ticker, period='6mo', window=20):
    """
    Identify support and resistance levels using local minima/maxima.

    Args:
        ticker: Stock ticker symbol
        period: Historical period (1mo, 3mo, 6mo, 1y)
        window: Rolling window size for detecting local extrema (default: 20 days)

    Returns:
        dict with support/resistance levels and current price position
    """
    try:
        hist = get_historical_data(ticker, period=period)
        if not hist or len(hist) < window * 2:
            return {'error': f'Insufficient data for {ticker}'}

        df = pd.DataFrame(hist)

        # Find local maxima (resistance levels) using rolling window
        df['local_max'] = df['high'].rolling(window=window, center=True).max()
        resistance_candidates = df[df['high'] == df['local_max']]['high'].values

        # Find local minima (support levels)
        df['local_min'] = df['low'].rolling(window=window, center=True).min()
        support_candidates = df[df['low'] == df['local_min']]['low'].values

        # Remove duplicates and cluster nearby levels
        resistances = _cluster_levels(resistance_candidates, tolerance=0.02)
        supports = _cluster_levels(support_candidates, tolerance=0.02)

        current_price = df['close'].iloc[-1]

        # Find nearest levels
        supports_below = [s for s in supports if s < current_price]
        resistances_above = [r for r in resistances if r > current_price]

        nearest_support = max(supports_below) if supports_below else None
        nearest_resistance = min(resistances_above) if resistances_above else None

        return {
            'ticker': ticker,
            'current_price': round(current_price, 2),
            'support_levels': sorted([round(s, 2) for s in supports], reverse=True)[:5],
            'resistance_levels': sorted([round(r, 2) for r in resistances])[:5],
            'nearest_support': round(nearest_support, 2) if nearest_support else None,
            'nearest_resistance': round(nearest_resistance, 2) if nearest_resistance else None,
            'window_days': window,
            'period': period,
            'analysis': _support_resistance_analysis(current_price, nearest_support, nearest_resistance)
        }

    except Exception as e:
        return {'error': str(e)}


def _cluster_levels(levels, tolerance=0.02):
    """
    Cluster nearby price levels to avoid duplicates.

    Args:
        levels: Array of price levels
        tolerance: Percentage tolerance for clustering (default: 2%)

    Returns:
        List of clustered levels
    """
    if len(levels) == 0:
        return []

    levels = sorted(set(levels))
    clustered = [levels[0]]

    for level in levels[1:]:
        # Check if this level is close to the last clustered level
        if abs(level - clustered[-1]) / clustered[-1] > tolerance:
            clustered.append(level)

    return clustered


def _support_resistance_analysis(current_price, support, resistance):
    """Generate analysis for support/resistance levels."""
    analysis = []

    if support:
        support_distance = ((current_price - support) / current_price) * 100
        analysis.append(f"Nearest support at ₹{support:.2f} ({support_distance:.1f}% below)")
        if support_distance < 3:
            analysis.append("⚠️ Price is very close to support - potential bounce zone")
    else:
        analysis.append("⚠️ No strong support level found below current price")

    if resistance:
        resistance_distance = ((resistance - current_price) / current_price) * 100
        analysis.append(f"Nearest resistance at ₹{resistance:.2f} ({resistance_distance:.1f}% above)")
        if resistance_distance < 3:
            analysis.append("⚠️ Price is approaching resistance - potential pullback zone")
    else:
        analysis.append("✅ No immediate resistance above - potential for upward movement")

    return analysis
