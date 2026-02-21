"""
Enhanced AI Advisor - Uses REAL stock data to prevent hallucinations
Fetches live prices, historical data, technicals, and news before giving advice
"""

import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from stock_data import (
    get_stock_price, get_stock_info, get_historical_data,
    calculate_technical_indicators, POPULAR_INDIAN_STOCKS,
    get_bulk_prices
)
from news_monitor import fetch_stock_news, get_news_summary

logger = logging.getLogger(__name__)
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')

# Initialize clients
openai_client = None
anthropic_client = None

try:
    from openai import OpenAI
    if OPENAI_API_KEY:
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
except ImportError:
    pass

try:
    from anthropic import Anthropic
    if ANTHROPIC_API_KEY:
        anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
except ImportError:
    pass


SYSTEM_PROMPT = """You are an expert Indian stock market advisor. You ONLY recommend stocks based on REAL market data provided to you.

CRITICAL RULES:
1. NEVER make up or hallucinate stock prices
2. ONLY use the actual current prices provided in the data
3. ONLY recommend stocks from the data given to you
4. If no suitable stocks are found in the budget, say so clearly
5. Always verify prices match the user's budget before recommending

When recommending stocks:
📊 Stock: [Name] ([Ticker])
💰 Current Price: ₹[ACTUAL PRICE FROM DATA]
🎯 Target: ₹[based on analysis]
🛡️ Stop Loss: ₹[price]
📈 Expected Return: [X]% in [timeframe]
⚡ Risk Level: [Low/Medium/High]
📝 Reasoning: [Use historical data, technical indicators, news sentiment]

IMPORTANT:
- Base recommendations on provided technical indicators (RSI, MACD, moving averages)
- Consider recent news sentiment
- Account for sector diversification
- Explain WHY the stock is good (not just generic statements)

⚠️ Disclaimer: This is AI-generated advice for educational purposes only. Please consult a SEBI-registered financial advisor before making investment decisions. Past performance does not guarantee future returns.
"""


def find_stocks_in_budget(max_budget):
    """
    Find stocks within budget with complete real data.

    Args:
        max_budget: Maximum price per share in rupees

    Returns:
        List of stocks with full data (price, technicals, news, history)
    """
    logger.info(f"Finding stocks within budget: ₹{max_budget}")

    stocks_in_budget = []

    # Get all stock tickers
    all_tickers = list(POPULAR_INDIAN_STOCKS.keys())

    # Fetch prices for all stocks
    logger.info(f"Fetching prices for {len(all_tickers)} stocks...")
    prices = get_bulk_prices(all_tickers)

    # Filter stocks within budget
    for ticker, price in prices.items():
        if price and price <= max_budget:
            logger.info(f"Found {ticker} at ₹{price} (within budget)")

            # Get comprehensive data for this stock
            try:
                stock_info = get_stock_info(ticker)
                price_data = get_stock_price(ticker)
                historical = get_historical_data(ticker, period='6mo')
                technicals = calculate_technical_indicators(ticker, period='6mo')

                # Get news (optional, may fail)
                news_summary = None
                try:
                    news_summary = get_news_summary(ticker)
                except Exception as e:
                    logger.warning(f"Could not fetch news for {ticker}: {e}")

                stock_data = {
                    'ticker': ticker,
                    'name': POPULAR_INDIAN_STOCKS[ticker]['name'],
                    'sector': POPULAR_INDIAN_STOCKS[ticker]['sector'],
                    'current_price': price_data.get('current_price') if price_data else price,
                    'change_percent': price_data.get('change_percent', 0) if price_data else 0,
                    'fundamentals': stock_info,
                    'historical_data': historical[-30:] if historical else [],  # Last 30 days
                    'technical_indicators': technicals,
                    'news_summary': news_summary,
                    'volume': price_data.get('volume', 0) if price_data else 0,
                    'market_cap': stock_info.get('market_cap', 0) if stock_info else 0,
                    'pe_ratio': stock_info.get('pe_ratio', 0) if stock_info else 0,
                }

                stocks_in_budget.append(stock_data)

            except Exception as e:
                logger.error(f"Error fetching data for {ticker}: {e}")
                continue

    logger.info(f"Found {len(stocks_in_budget)} stocks within budget ₹{max_budget}")

    # Sort by market cap (prefer larger, more stable companies)
    stocks_in_budget.sort(key=lambda x: x.get('market_cap', 0), reverse=True)

    return stocks_in_budget


def prepare_budget_recommendation_context(budget, stocks_data):
    """
    Prepare detailed context for budget-based stock recommendation.

    Args:
        budget: User's budget in rupees
        stocks_data: List of stocks with complete data

    Returns:
        Formatted context string for LLM
    """
    context_parts = [
        f"=== INVESTMENT QUERY ===",
        f"User Budget: ₹{budget}",
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M IST')}",
        f"",
        f"=== AVAILABLE STOCKS WITHIN BUDGET ===",
        f"Total stocks found: {len(stocks_data)}",
        f""
    ]

    for i, stock in enumerate(stocks_data[:10], 1):  # Top 10 stocks
        context_parts.append(f"\n--- Stock {i}: {stock['ticker']} ({stock['name']}) ---")
        context_parts.append(f"Sector: {stock['sector']}")
        context_parts.append(f"Current Price: ₹{stock['current_price']}")
        context_parts.append(f"Day Change: {stock['change_percent']:.2f}%")
        context_parts.append(f"Market Cap: ₹{stock['market_cap']:,.0f}")
        context_parts.append(f"P/E Ratio: {stock['pe_ratio']}")
        context_parts.append(f"Volume: {stock['volume']:,}")

        # Technical indicators
        if stock['technical_indicators']:
            tech = stock['technical_indicators']
            context_parts.append(f"\nTechnical Indicators:")
            context_parts.append(f"  RSI (14-day): {tech.get('rsi', 'N/A')}")
            context_parts.append(f"  MACD: {tech.get('macd', 'N/A')}")
            context_parts.append(f"  MACD Signal: {tech.get('macd_signal', 'N/A')}")
            context_parts.append(f"  SMA 20-day: ₹{tech.get('sma_20', 'N/A')}")
            context_parts.append(f"  SMA 50-day: ₹{tech.get('sma_50', 'N/A')}")

            if tech.get('signals'):
                context_parts.append(f"  Signals:")
                for signal in tech['signals']:
                    context_parts.append(f"    - {signal}")

        # Recent price movement
        if stock['historical_data'] and len(stock['historical_data']) >= 5:
            recent = stock['historical_data'][-5:]
            context_parts.append(f"\nRecent 5-day prices:")
            for day in recent:
                context_parts.append(f"  {day['date']}: ₹{day['close']} (Vol: {day['volume']:,})")

        # News sentiment
        if stock['news_summary']:
            news = stock['news_summary']
            context_parts.append(f"\nNews Sentiment:")
            context_parts.append(f"  Overall: {news.get('overall_sentiment', 'Neutral')}")
            if news.get('headlines'):
                context_parts.append(f"  Recent headlines:")
                for headline in news['headlines'][:3]:
                    context_parts.append(f"    - {headline}")

        # Fundamentals
        fund = stock.get('fundamentals', {})
        if fund:
            context_parts.append(f"\nFundamentals:")
            context_parts.append(f"  Dividend Yield: {fund.get('dividend_yield', 0):.2f}%")
            context_parts.append(f"  ROE: {fund.get('roe', 0):.2f}%")
            context_parts.append(f"  Debt to Equity: {fund.get('debt_to_equity', 0):.2f}")
            context_parts.append(f"  Profit Margin: {fund.get('profit_margin', 0):.2f}%")

        context_parts.append("")

    return "\n".join(context_parts)


def get_budget_based_recommendation(budget, user_message, provider='auto'):
    """
    Get AI recommendation for stocks within budget using REAL data.

    Args:
        budget: User's budget in rupees
        user_message: Original user query
        provider: 'auto', 'openai', or 'anthropic'

    Returns:
        AI recommendation with real stock data
    """
    try:
        # Step 1: Find stocks within budget with complete data
        stocks_in_budget = find_stocks_in_budget(budget)

        if not stocks_in_budget:
            return {
                'response': f"❌ Unfortunately, I couldn't find any stocks from our tracked list under ₹{budget}. "
                           f"Most quality stocks in Indian markets are priced higher. Consider:\n"
                           f"1. Increasing your budget to at least ₹1000-2000\n"
                           f"2. Starting with mutual funds or ETFs for small amounts\n"
                           f"3. Saving more before investing in individual stocks\n\n"
                           f"Remember: Quality stocks require reasonable capital, and diversification is key to reducing risk.",
                'provider_used': 'none',
                'stocks_found': 0
            }

        # Step 2: Prepare context with real data
        context = prepare_budget_recommendation_context(budget, stocks_in_budget)

        # Step 3: Create enhanced user message
        enhanced_message = f"{user_message}\n\nIMPORTANT: Only recommend stocks from the data provided below. Do not make up prices or stocks.\n\n{context}"

        # Step 4: Get AI recommendation
        if provider == 'anthropic' or (provider == 'auto' and anthropic_client):
            response = _get_anthropic_response(enhanced_message)
            provider_used = 'anthropic'
        elif provider == 'openai' or (provider == 'auto' and openai_client):
            response = _get_openai_response(enhanced_message)
            provider_used = 'openai'
        else:
            return {
                'response': "❌ No AI provider available. Please configure OPENAI_API_KEY or ANTHROPIC_API_KEY in your .env file.",
                'provider_used': 'none',
                'error': 'No API keys configured'
            }

        return {
            'response': response,
            'provider_used': provider_used,
            'stocks_found': len(stocks_in_budget),
            'budget': budget,
            'data_used': f"{len(stocks_in_budget)} real stocks analyzed"
        }

    except Exception as e:
        logger.error(f"Error in budget recommendation: {e}")
        return {
            'response': f"❌ Error generating recommendation: {str(e)}",
            'provider_used': 'none',
            'error': str(e)
        }


def _get_openai_response(message):
    """Get response from OpenAI GPT-4."""
    if not openai_client:
        raise ValueError("OpenAI client not initialized")

    response = openai_client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message}
        ],
        temperature=0.7,
        max_tokens=1500
    )

    return response.choices[0].message.content


def _get_anthropic_response(message):
    """Get response from Anthropic Claude."""
    if not anthropic_client:
        raise ValueError("Anthropic client not initialized")

    response = anthropic_client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=2000,
        temperature=0.7,
        system=SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": message}
        ]
    )

    return response.content[0].text


# Helper function to extract budget from user message
def extract_budget_from_message(message):
    """
    Extract budget amount from user message.

    Examples:
    - "I have 500 rupees" -> 500
    - "500 rs to invest" -> 500
    - "budget of ₹1000" -> 1000
    """
    import re

    # Patterns to match
    patterns = [
        r'(?:₹|rs\.?|rupees?)\s*(\d+)',  # ₹500, rs 500, rupees 500
        r'(\d+)\s*(?:₹|rs\.?|rupees?)',  # 500 rupees, 500 rs
        r'(?:budget|have|invest)\s+(?:of\s+)?(?:₹|rs\.?|rupees?)?\s*(\d+)',  # budget of 500
    ]

    message_lower = message.lower()

    for pattern in patterns:
        match = re.search(pattern, message_lower)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                continue

    return None
