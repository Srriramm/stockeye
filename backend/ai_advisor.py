"""
AI Advisor - OpenAI GPT-4 integration for stock market advice.
Provides personalized, data-driven stock recommendations for Indian markets.
"""

import os
import logging
from datetime import datetime
from dotenv import load_dotenv

import llm_client

logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# ─── System Prompt ──────────────────────────────────────────────

SYSTEM_PROMPT = """You are FinAI — a sophisticated AI Finance Consultant specializing in Indian equity markets (NSE/BSE). You combine the expertise of a SEBI-registered financial advisor with the analytical power of AI to deliver personalized, data-driven financial guidance.

YOUR CORE MISSION:
Help users build, manage, and grow wealth through intelligent, goal-aligned investment strategies tailored to their unique financial situation.

PERSONALIZATION PROTOCOL:
When a user begins a conversation, gently collect (one at a time, not all at once):
1. Investment Goal (retirement, wealth creation, home purchase, child's education, emergency fund)
2. Investment Horizon (short: <3 years, medium: 3-7 years, long: >7 years)
3. Available Capital (approximate budget)
4. Risk Tolerance (conservative / balanced / aggressive / speculative)
5. Existing Holdings (if reviewing portfolio)

ADVISORY FRAMEWORK:
- **Conservative** — Large-cap NIFTY 50 stocks, dividend aristocrats, debt instruments, gold ETFs
- **Balanced** — Mix of mid-cap growth and large-cap safety, sector diversification
- **Aggressive** — Mid/small-cap growth, momentum plays, sectoral bets
- **Speculative** — High-risk opportunities with strict stop-losses

FORECASTING INTEGRATION:
When forecast data is available, reference ML-generated price targets explicitly, explain the BUY/HOLD/SELL signal and its basis, and always mention confidence level and limitations.

RESPONSE FORMAT:
Use markdown. No emojis anywhere in your responses.

For a single stock recommendation, use a two-column table:

| Field | Details |
|---|---|
| Stock | Name (TICKER) |
| Current Price | Rs X,XXX |
| 12-Month Target | Rs X,XXX (X% upside) |
| 30-Day Forecast | Rs X,XXX — BUY / HOLD / SELL |
| Stop Loss | Rs X,XXX |
| Risk | Low / Medium / High |
| Horizon | Short / Medium / Long |
| Thesis | Why this stock in 2-3 sentences |
| Suitable for | Investor profile |

For comparing multiple stocks, use a comparison table:

| Stock | Price | Target | Upside | Signal | Risk |
|---|---|---|---|---|---|
| Name (TICKER) | Rs X | Rs X | X% | BUY | Medium |

Use **bold** for key terms, headings for sections, and bullet lists for guidelines. Keep prose concise.

IMPORTANT GUIDELINES:
- Never guarantee returns — always acknowledge market risks
- Suggest position sizing (e.g., limit to 5-8% of portfolio)
- Recommend SIP for volatile stocks
- Mention tax implications (STCG 15%, LTCG 10% above Rs 1L) when relevant
- Use Indian financial context: FII/DII flows, RBI policy, GST impact

DISCLAIMER (append to every recommendation):
"*AI-generated analysis for educational purposes only. Past performance does not guarantee future results. Consult a SEBI-registered advisor before investing. Markets carry risk.*"

Tone: Professional, clear, and direct — like a trusted wealth manager who respects the user's time.
"""

# ─── Conversation History ───────────────────────────────────────

MAX_HISTORY = 20


# ─── Query Classification ──────────────────────────────────────

def classify_query(user_message: str) -> str:
    """
    Classify query as 'quick' or 'deep' for AI provider routing.

    Quick queries: Simple price lookups, what is X, current data
    Deep queries: Analysis, recommendations, comparisons, portfolio reviews
    """
    message_lower = user_message.lower()
    word_count = len(user_message.split())

    # Keywords indicating deep analysis needed
    deep_keywords = ['analyze', 'review', 'recommend', 'should i', 'compare',
                     'portfolio', 'strategy', 'why', 'explain', 'risk', 'versus',
                     'which stock', 'best', 'diversif', 'outlook', 'future']

    # Keywords indicating simple query
    quick_keywords = ['price', 'what is', 'how much', 'current', 'latest',
                      'today', 'what sector', 'news', 'volume']

    has_deep = any(kw in message_lower for kw in deep_keywords)
    has_quick = any(kw in message_lower for kw in quick_keywords)

    # Decision logic
    if has_deep or word_count > 20:
        return 'deep'
    elif has_quick and word_count < 15:
        return 'quick'
    else:
        return 'quick'  # Default to quick for efficiency


# ─── Data Preparation ──────────────────────────────────────────

def _prepare_market_context(stock_data=None, news_data=None, portfolio_data=None, technicals=None):
    """Prepare market data context for the AI."""
    context_parts = []
    context_parts.append(f"Current Date/Time: {datetime.now().strftime('%Y-%m-%d %H:%M IST')}")

    if stock_data:
        if isinstance(stock_data, dict):
            context_parts.append(f"\n--- Stock Data ---")
            for key, value in stock_data.items():
                if isinstance(value, dict):
                    context_parts.append(f"\n{key}:")
                    for k, v in value.items():
                        context_parts.append(f"  {k}: {v}")
                else:
                    context_parts.append(f"{key}: {value}")

    if technicals:
        context_parts.append(f"\n--- Technical Indicators ---")
        if isinstance(technicals, dict):
            for key, value in technicals.items():
                if key == 'signals':
                    context_parts.append("Technical Signals:")
                    for signal in value:
                        context_parts.append(f"  - {signal}")
                else:
                    context_parts.append(f"{key}: {value}")

    if news_data:
        context_parts.append(f"\n--- Recent News & Sentiment ---")
        if isinstance(news_data, dict):
            context_parts.append(f"Overall Sentiment: {news_data.get('combined_sentiment_label', 'N/A')}")
            context_parts.append(f"Sentiment Score: {news_data.get('combined_sentiment_score', 'N/A')}")
            for article in news_data.get('news_articles', [])[:3]:
                context_parts.append(f"  - [{article.get('sentiment', 'neutral')}] {article.get('title', '')}")

    if portfolio_data:
        context_parts.append(f"\n--- User's Portfolio ---")
        context_parts.append(f"Total Value: ₹{portfolio_data.get('total_value', 0):,.2f}")
        context_parts.append(f"Total P&L: ₹{portfolio_data.get('total_pnl', 0):,.2f} ({portfolio_data.get('total_pnl_percent', 0):.2f}%)")
        context_parts.append(f"Holdings: {portfolio_data.get('num_holdings', 0)}")
        for h in portfolio_data.get('holdings', [])[:10]:
            context_parts.append(f"  - {h['name']} ({h['ticker']}): {h['quantity']} shares @ ₹{h['buy_price']} | P&L: ₹{h.get('pnl', 0):,.2f}")

    return '\n'.join(context_parts)


# ─── Main AI Chat Function ─────────────────────────────────────

def _build_user_message(user_query, context_str):
    """Wrap the user query with the real-time market-data block when present."""
    if not context_str:
        return user_query
    return f"""User Question: {user_query}

--- REAL-TIME MARKET DATA (use this to inform your advice) ---
{context_str}
--- END DATA ---

Please provide your analysis and advice based on the above real-time data."""


def get_stock_advice(user_query, market_context=None, stock_data=None, news_data=None,
                     portfolio_data=None, technicals=None, conversation_history=None):
    """
    Get AI-powered stock advice based on user query and market data.
    Thin compatibility wrapper over the model-agnostic path.

    Returns:
        dict with 'response' (AI message), 'data_used' (context info), and 'error' if any
    """
    context = _prepare_market_context(stock_data, news_data, portfolio_data, technicals)
    result = get_stock_advice_dual(
        user_query, provider='auto', conversation_history=conversation_history,
        stock_data=stock_data, news_data=news_data,
        portfolio_data=portfolio_data, technicals=technicals,
    )
    return {
        'response': result.get('response', ''),
        'data_used': (context[:200] + '...') if context else 'No market data context',
        'tokens_used': result.get('tokens_used', 0),
        'error': result.get('error'),
    }


def get_ai_response(user_query, conversation_history=None, user_id=None, **context):
    """Thin wrapper — called by telegram_bot and other modules."""
    result = get_stock_advice_dual(user_query, provider='auto',
                                   conversation_history=conversation_history,
                                   user_id=user_id, **context)
    return result.get('response', '')


def get_stock_advice_dual(user_query, provider='auto', conversation_history=None, user_id=None, **context):
    """
    Get AI-powered stock advice via the model-agnostic LLM layer.

    Args:
        user_query: User's question
        provider: 'auto' (default provider — Gemini unless reconfigured), or an
                  explicit 'gemini' | 'anthropic' | 'openai'
        user_id: Supabase user_id — used to load shared platform intelligence
        conversation_history: List of prior {role, content} messages for this user's session.
                              Never pass a global list — always load per-user history from DB.
        **context: stock_data, news_data, portfolio_data, technicals

    Returns:
        {
            'response': str,
            'provider_used': str,
            'model_used': str,
            'query_type': 'quick' | 'deep',
            'error': str | None
        }
    """
    if conversation_history is None:
        conversation_history = []

    query_type = classify_query(user_query)
    deep = query_type == 'deep'

    # 'auto' means "let llm_client pick the default provider"
    llm_provider = None if provider in ('auto', None) else provider

    # Load shared platform intelligence for this user
    intel_block = ""
    if user_id:
        try:
            from shared_context import get_context_summary
            intel_block = get_context_summary(user_id, max_age_hours=12)
        except Exception:
            pass

    # Build system prompt + context
    system = SYSTEM_PROMPT + ("\n\n" + intel_block if intel_block else "")
    context_str = _prepare_market_context(
        context.get('stock_data'), context.get('news_data'),
        context.get('portfolio_data'), context.get('technicals'),
    )

    # Build neutral message history (per-user, no global state)
    messages = []
    for msg in conversation_history[-MAX_HISTORY:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": _build_user_message(user_query, context_str)})

    result = llm_client.generate(
        system=system, messages=messages, provider=llm_provider,
        deep=deep, temperature=0.7, max_tokens=4000 if deep else 2000,
    )

    if result.get('error'):
        logger.error(f"LLM error ({result.get('provider')}): {result['error']}")
        return {
            'response': f"AI service error: {result['error']}",
            'provider_used': result.get('provider', 'none'),
            'model_used': result.get('model', 'none'),
            'query_type': query_type,
            'error': result['error'],
        }

    return {
        'response': result['text'],
        'provider_used': result['provider'],
        'model_used': result['model'],
        'query_type': query_type,
        'error': None,
    }


def analyze_stock(ticker, stock_info=None, technicals=None, news=None):
    """Generate comprehensive AI analysis for a specific stock - uses dual provider."""
    context_parts = []

    if stock_info:
        context_parts.append(f"Stock: {stock_info.get('name', ticker)} ({ticker})")
        context_parts.append(f"Sector: {stock_info.get('sector', 'N/A')}")
        context_parts.append(f"Market Cap: {stock_info.get('market_cap_formatted', 'N/A')}")
        context_parts.append(f"P/E Ratio: {stock_info.get('pe_ratio', 'N/A')}")
        context_parts.append(f"EPS: ₹{stock_info.get('eps', 'N/A')}")
        context_parts.append(f"Debt/Equity: {stock_info.get('debt_to_equity', 'N/A')}")
        context_parts.append(f"ROE: {stock_info.get('roe', 'N/A')}%")
        context_parts.append(f"Dividend Yield: {stock_info.get('dividend_yield', 'N/A')}%")
        context_parts.append(f"52W High: ₹{stock_info.get('fifty_two_week_high', 'N/A')}")
        context_parts.append(f"52W Low: ₹{stock_info.get('fifty_two_week_low', 'N/A')}")
        context_parts.append(f"Beta: {stock_info.get('beta', 'N/A')}")

    if technicals:
        context_parts.append(f"\nTechnical Indicators:")
        context_parts.append(f"RSI: {technicals.get('rsi', 'N/A')}")
        context_parts.append(f"MACD: {technicals.get('macd', 'N/A')}")
        context_parts.append(f"SMA 20: ₹{technicals.get('sma_20', 'N/A')}")
        context_parts.append(f"SMA 50: ₹{technicals.get('sma_50', 'N/A')}")
        for signal in technicals.get('signals', []):
            context_parts.append(f"  Signal: {signal}")

    if news:
        context_parts.append(f"\nNews Sentiment: {news.get('combined_sentiment_label', 'N/A')}")
        for article in news.get('news_articles', [])[:3]:
            context_parts.append(f"  - {article.get('title', '')}")

    query = f"Provide a comprehensive analysis of {ticker} stock with a buy/sell/hold recommendation."
    context = '\n'.join(context_parts)

    # Use dual provider (will automatically route to Claude for deep analysis)
    return get_stock_advice_dual(query, provider='auto', stock_data={'analysis_context': context},
                                   technicals=technicals, news_data=news)


def get_portfolio_review(portfolio_data):
    """Generate AI review of user's portfolio - uses dual provider."""
    query = "Review my portfolio and suggest changes for better diversification and returns."
    # Portfolio review is deep analysis - will route to Claude
    return get_stock_advice_dual(query, provider='auto', portfolio_data=portfolio_data)


def compare_stocks(ticker1, ticker2, comparison_data=None):
    """Generate AI comparison of two stocks - uses dual provider."""
    query = f"Compare {ticker1} vs {ticker2}. Which is a better investment right now and why?"
    # Stock comparison is deep analysis - will route to Claude
    return get_stock_advice_dual(query, provider='auto', stock_data=comparison_data)

