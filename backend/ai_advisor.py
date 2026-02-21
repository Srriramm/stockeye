"""
AI Advisor - OpenAI GPT-4 integration for stock market advice.
Provides personalized, data-driven stock recommendations for Indian markets.
"""

import os
import json
import logging
from datetime import datetime
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')

# Initialize OpenAI client
openai_client = None
try:
    from openai import OpenAI
    if OPENAI_API_KEY:
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
except ImportError:
    print("OpenAI package not installed")

# Initialize Anthropic client
anthropic_client = None
try:
    from anthropic import Anthropic
    if ANTHROPIC_API_KEY:
        anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
        print("Anthropic client initialized successfully")
except ImportError:
    print("Anthropic package not installed. Run: pip install anthropic")

# ─── System Prompt ──────────────────────────────────────────────

SYSTEM_PROMPT = """You are FinAI — a sophisticated, personalized AI Finance Consultant specializing in Indian equity markets (NSE/BSE). You combine the expertise of a SEBI-registered financial advisor with the analytical power of an AI to deliver deeply personalized, data-driven financial guidance.

YOUR CORE MISSION:
Help users build, manage, and grow wealth through intelligent, goal-aligned investment strategies tailored specifically to their unique financial situation.

PERSONALIZATION PROTOCOL:
When a user begins a conversation or asks for the first time, gently collect:
1. 🎯 Investment Goal (e.g., retirement, wealth creation, home purchase, child's education, emergency fund)
2. ⏱️ Investment Horizon (short: <3 years, medium: 3-7 years, long: >7 years)
3. 💰 Available Capital (approximate budget to invest)
4. ⚡ Risk Tolerance (conservative / balanced / aggressive / speculative)
5. 📋 Existing Holdings (if reviewing portfolio)

If any of these are missing, ask for them naturally in conversation — NOT all at once.

ADVISORY FRAMEWORK:
- **Conservative users** → Focus on large-cap NIFTY 50 stocks, dividend aristocrats, debt instruments, gold ETFs
- **Balanced users** → Mix of mid-cap growth + large-cap safety, sector diversification
- **Aggressive users** → Mid/small-cap growth stories, momentum plays, sectoral bets
- **Speculative** → High-risk opportunities with strict stop-losses

FORECASTING INTEGRATION:
When forecast data is available (price predictions, trend direction, signals):
- Reference the ML-generated price targets explicitly
- Explain the forecast signal (BUY/HOLD/SELL) and its basis
- Contextualize it with technical indicators
- Always mention confidence level and limitations of predictions

RESPONSE FORMAT:
For stock recommendations, use this format:
📊 **Stock: [Name] ([Ticker])**
💰 Current Price: ₹[price]
🎯 12-Month Target: ₹[target] ([X]% upside)
🔮 30-Day Forecast: ₹[forecast_target] ([forecast signal])
🛡️ Stop Loss: ₹[stop_loss]
⚡ Risk: [Low/Medium/High] | Horizon: [timeframe]
📋 Thesis: [2-3 sentences on WHY this stock]
✅ Suitability: [Which investor profile this fits]

IMPORTANT GUIDELINES:
- Always acknowledge market risks — never guarantee returns
- Suggest position sizing (e.g., "limit to 5-8% of portfolio")
- Recommend SIP for volatile stocks
- Mention tax implications (STCG 15%, LTCG 10% above ₹1L) when relevant
- Use Indian financial context: FII/DII flows, RBI policy, GST impact

DISCLAIMER (append to every recommendation):
"⚠️ AI-generated analysis for educational purposes. Past performance ≠ future results. Consult a SEBI-registered advisor before investing. Markets carry risk."

Your tone: Professional, warm, knowledgeable — like a trusted wealth manager who genuinely cares about your financial wellbeing.
"""

# ─── Conversation History ───────────────────────────────────────

conversation_history = []
MAX_HISTORY = 20


def clear_conversation():
    """Reset conversation history."""
    global conversation_history
    conversation_history = []


def get_conversation_history():
    """Get current conversation history."""
    return conversation_history


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

def get_stock_advice(user_query, market_context=None, stock_data=None, news_data=None, portfolio_data=None, technicals=None):
    """
    Get AI-powered stock advice based on user query and market data.

    Returns:
        dict with 'response' (AI message), 'data_used' (context info), and 'error' if any
    """
    global conversation_history

    if not openai_client:
        return {
            'response': _get_fallback_response(user_query),
            'data_used': 'No OpenAI API key configured. Using fallback response.',
            'error': 'OpenAI API key not configured. Add OPENAI_API_KEY to your .env file.'
        }

    # Prepare context
    context = _prepare_market_context(stock_data, news_data, portfolio_data, technicals)

    # Build user message with context
    user_message = user_query
    if context:
        user_message = f"""User Question: {user_query}

--- REAL-TIME MARKET DATA (use this to inform your advice) ---
{context}
--- END DATA ---

Please provide your analysis and advice based on the above real-time data."""

    # Build messages for API
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add conversation history for context
    for msg in conversation_history[-MAX_HISTORY:]:
        messages.append(msg)

    messages.append({"role": "user", "content": user_message})

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            max_tokens=2000,
            temperature=0.7,
            presence_penalty=0.1,
            frequency_penalty=0.1,
        )

        ai_response = response.choices[0].message.content

        # Update conversation history
        conversation_history.append({"role": "user", "content": user_query})
        conversation_history.append({"role": "assistant", "content": ai_response})

        # Trim history if too long
        if len(conversation_history) > MAX_HISTORY * 2:
            conversation_history = conversation_history[-MAX_HISTORY:]

        return {
            'response': ai_response,
            'data_used': context[:200] + '...' if context else 'No market data context',
            'tokens_used': response.usage.total_tokens if response.usage else 0,
            'error': None
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"OpenAI API error: {error_msg}", exc_info=True)

        # Return meaningful fallback
        return {
            'response': _get_fallback_response(user_query),
            'data_used': context[:200] if context else '',
            'error': f'AI service error: {error_msg}. Using fallback response.'
        }


def get_stock_advice_dual(user_query, provider='auto', **context):
    """
    Get AI-powered stock advice with dual provider support (OpenAI + Anthropic).

    Args:
        user_query: User's question
        provider: 'auto', 'openai', or 'anthropic'
        **context: stock_data, news_data, portfolio_data, technicals

    Returns:
        {
            'response': str,
            'provider_used': 'openai' | 'anthropic' | 'none',
            'model_used': str,
            'query_type': 'quick' | 'deep',
            'error': str | None
        }
    """
    global conversation_history

    # Determine provider
    query_type = classify_query(user_query)

    if provider == 'auto':
        # Smart routing: Claude for deep analysis, GPT-4 for quick queries
        if query_type == 'deep' and anthropic_client:
            provider = 'anthropic'
        elif openai_client:
            provider = 'openai'
        elif anthropic_client:
            provider = 'anthropic'
        else:
            provider = None

    # Route to appropriate provider
    if provider == 'anthropic' and anthropic_client:
        return _query_anthropic(user_query, query_type, **context)
    elif provider == 'openai' and openai_client:
        return _query_openai(user_query, query_type, **context)
    else:
        return {
            'response': _get_fallback_response(user_query),
            'provider_used': 'none',
            'model_used': 'fallback',
            'query_type': query_type,
            'error': 'No AI provider available. Please configure OPENAI_API_KEY or ANTHROPIC_API_KEY in .env file.'
        }


def _query_openai(user_query, query_type, **context):
    """Query OpenAI GPT-4."""
    global conversation_history  # Fix UnboundLocalError

    # Prepare context
    context_str = _prepare_market_context(
        context.get('stock_data'),
        context.get('news_data'),
        context.get('portfolio_data'),
        context.get('technicals')
    )

    # Build user message
    user_message = user_query
    if context_str:
        user_message = f"""User Question: {user_query}

--- REAL-TIME MARKET DATA (use this to inform your advice) ---
{context_str}
--- END DATA ---

Please provide your analysis and advice based on the above real-time data."""

    # Build messages for API
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add conversation history
    for msg in conversation_history[-MAX_HISTORY:]:
        messages.append(msg)

    messages.append({"role": "user", "content": user_message})

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            max_tokens=2000,
            temperature=0.7,
            presence_penalty=0.1,
            frequency_penalty=0.1,
        )

        ai_response = response.choices[0].message.content

        # Update conversation history
        conversation_history.append({"role": "user", "content": user_query})
        conversation_history.append({"role": "assistant", "content": ai_response})

        # Trim history if too long
        if len(conversation_history) > MAX_HISTORY * 2:
            conversation_history = conversation_history[-MAX_HISTORY:]

        return {
            'response': ai_response,
            'provider_used': 'openai',
            'model_used': 'gpt-4',
            'query_type': query_type,
            'tokens_used': response.usage.total_tokens if response.usage else 0,
            'error': None
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"OpenAI API error: {error_msg}", exc_info=True)
        return {
            'response': _get_fallback_response(user_query),
            'provider_used': 'openai',
            'model_used': 'gpt-4',
            'query_type': query_type,
            'error': f'OpenAI error: {error_msg}'
        }


def _query_anthropic(user_query, query_type, **context):
    """Query Anthropic Claude."""
    global conversation_history  # Fix UnboundLocalError

    # Model selection based on query complexity
    model = "claude-opus-4-6" if query_type == 'deep' else "claude-sonnet-4-5-20250929"
    max_tokens = 4000 if query_type == 'deep' else 2000

    # Prepare context
    context_str = _prepare_market_context(
        context.get('stock_data'),
        context.get('news_data'),
        context.get('portfolio_data'),
        context.get('technicals')
    )

    # Build messages
    messages = []

    # Add conversation history (Claude format)
    for msg in conversation_history[-MAX_HISTORY:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Build user message with context
    user_message = user_query
    if context_str:
        user_message = f"""User Question: {user_query}

--- REAL-TIME MARKET DATA (use this to inform your advice) ---
{context_str}
--- END DATA ---

Please provide your analysis and advice based on the above real-time data."""

    messages.append({"role": "user", "content": user_message})

    try:
        response = anthropic_client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0.7,
            system=SYSTEM_PROMPT,
            messages=messages
        )

        ai_response = response.content[0].text

        # Update conversation history
        conversation_history.append({"role": "user", "content": user_query})
        conversation_history.append({"role": "assistant", "content": ai_response})

        # Trim history if too long
        if len(conversation_history) > MAX_HISTORY * 2:
            conversation_history = conversation_history[-MAX_HISTORY:]

        return {
            'response': ai_response,
            'provider_used': 'anthropic',
            'model_used': model,
            'query_type': query_type,
            'tokens_used': response.usage.input_tokens + response.usage.output_tokens if hasattr(response, 'usage') else 0,
            'error': None
        }

    except Exception as e:
        error_msg = str(e)
        print(f"Anthropic API error: {error_msg}")
        return {
            'response': _get_fallback_response(user_query),
            'provider_used': 'anthropic',
            'model_used': model,
            'query_type': query_type,
            'error': f'Anthropic error: {error_msg}'
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


# ─── Fallback Responses ────────────────────────────────────────

def _get_fallback_response(query):
    """Provide intelligent fallback when OpenAI is unavailable."""
    query_lower = query.lower()

    if any(word in query_lower for word in ['recommend', 'buy', 'invest', 'suggestion']):
        return """I'm currently unable to connect to the AI service, but here are some general tips for Indian stock investing:

📊 **General Recommendations for Beginners:**

1. **Large-cap stocks** (NIFTY 50) are generally safer for beginners
2. **Diversify** across at least 3-4 sectors (IT, Banking, FMCG, Pharma)
3. Start with **blue-chip stocks** like HDFC Bank, TCS, Reliance, Infosys
4. Use **SIP approach** - invest fixed amounts at regular intervals
5. Keep **20-30% in defensive stocks** (ITC, Hindustan Unilever)

📈 **Key Metrics to Check:**
- P/E Ratio < sector average (value stocks)
- Consistent revenue & profit growth
- Low debt-to-equity ratio
- Good ROE (>15%)

⚠️ **Please configure your OpenAI API key** in the .env file to get personalized, data-driven recommendations.

⚠️ This is general information only. Please consult a SEBI-registered financial advisor."""

    elif any(word in query_lower for word in ['market', 'nifty', 'sensex', 'today']):
        return """I'm unable to provide AI-powered market insights right now (OpenAI API not configured).

You can check the **Market Overview** section for real-time NIFTY and SENSEX data.

📊 **General Market Tips:**
- Check market indices (NIFTY 50, SENSEX) for overall direction
- Watch FII/DII data for institutional activity
- Monitor global markets (US futures, Asian markets) for cues

⚠️ Configure your OpenAI API key in .env for AI-powered market analysis."""

    elif any(word in query_lower for word in ['portfolio', 'review', 'holdings']):
        return """I can see your portfolio data but need the AI service to provide intelligent analysis.

📊 **General Portfolio Tips:**
- Aim for 10-15 stocks across 5-6 sectors
- No single stock > 15-20% of portfolio
- Rebalance quarterly
- Review underperformers every 6 months
- Keep some cash (10-15%) for opportunities

⚠️ Configure your OpenAI API key in .env for AI-powered portfolio review."""

    else:
        return """I'm your AI Stock Assistant! I can help with:

🤖 **Stock Recommendations** - "I have ₹10,000, what should I invest in?"
📊 **Stock Analysis** - "Should I buy Reliance?"
📈 **Market Insights** - "What's happening in the market today?"
💼 **Portfolio Review** - "Review my portfolio"
🔍 **Comparisons** - "Compare TCS vs Infosys"
🏢 **Sector Analysis** - "Tell me about IT sector stocks"

⚠️ Note: For AI-powered responses, please add your OpenAI API key to the .env file.
Currently providing rule-based responses."""
