"""
Proactive Agent — Autonomous stock analysis using Claude tool_use.

Uses a real agentic loop where Claude calls Python tools to gather data,
then produces a structured BUY/SELL/HOLD/WATCH recommendation.

Cost control:
- Start with claude-haiku-4-5-20251001 (cheap triage)
- Escalate to claude-sonnet-4-6 only when brain score is high-signal (≥65 or ≤35)
- Redis cache per user + ticker + date + market session (4h TTL)
- Skip analysis entirely if cached result already exists

Scheduled via Celery Beat at 9:00 AM and 4:00 PM IST.
Also available on-demand via POST /api/agent/analyze.
"""

import os
import json
import logging
from datetime import date, datetime

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

# Model selection
MODEL_TRIAGE = "claude-haiku-4-5-20251001"   # Cheap — used for most analysis
MODEL_DEEP   = "claude-sonnet-4-6"            # Quality — used for high-signal stocks

MAX_TOOL_ITERATIONS = 6   # Hard cap on agentic loop steps
CACHE_TTL = 4 * 3600      # 4-hour Redis cache per session

# Brain score thresholds that trigger model escalation to Sonnet
ESCALATE_ABOVE = 65
ESCALATE_BELOW = 35

# Singleton Anthropic client
_client = None


def _get_client():
    global _client
    if _client is None:
        if not ANTHROPIC_API_KEY:
            logger.error("[ProactiveAgent] ANTHROPIC_API_KEY not set")
            return None
        from anthropic import Anthropic
        _client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client


# ─── WebSocket instance (injected from app.py) ───────────────────────────────

_socketio = None


def set_agent_socketio(sio):
    global _socketio
    _socketio = sio


# ─── Tool schema definitions ─────────────────────────────────────────────────

AGENT_TOOLS = [
    {
        "name": "get_stock_price",
        "description": (
            "Get current market price, day change %, volume, and 52-week range "
            "for an Indian stock (NSE/BSE)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "NSE ticker symbol, e.g. RELIANCE, TCS, INFY"
                }
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "get_technical_indicators",
        "description": (
            "Get technical analysis indicators: RSI, MACD, Bollinger Bands, "
            "SMA 20/50, EMA, and overall signal (BUY/SELL/NEUTRAL)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"}
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "get_news_sentiment",
        "description": (
            "Get recent news articles for a stock with overall sentiment score "
            "(positive/neutral/negative) and summary."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"}
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "get_brain_score",
        "description": (
            "Get the ML-powered Brain Engine composite score (0-100) and signal "
            "(BUY/HOLD/SELL) for a stock. Score ≥70 = strong buy, ≤30 = sell signal. "
            "Synthesizes technicals, ML forecast, news, and volume."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"}
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "get_portfolio_holdings",
        "description": (
            "Get the user's current portfolio holdings with quantity, buy price, "
            "current value, and P&L for each stock. Use this to understand position sizing "
            "context and whether the user already holds this stock."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "submit_recommendation",
        "description": (
            "Submit your final structured recommendation. Call this EXACTLY ONCE "
            "after gathering sufficient data. This completes the analysis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["BUY", "SELL", "HOLD", "WATCH"],
                    "description": (
                        "BUY: enter/add position now. "
                        "SELL: exit/reduce position now. "
                        "HOLD: keep current position, no new action. "
                        "WATCH: not yet a buy/sell, monitor closely."
                    )
                },
                "confidence": {
                    "type": "number",
                    "description": "Conviction level from 0.0 (uncertain) to 1.0 (very confident)."
                },
                "reasoning": {
                    "type": "string",
                    "description": (
                        "2-3 sentence explanation of why this action is recommended. "
                        "Cite specific data: RSI value, brain score, news sentiment, price level."
                    )
                },
                "entry_price": {
                    "type": "number",
                    "description": "Suggested entry price for BUY; null for SELL/HOLD/WATCH."
                },
                "target_price": {
                    "type": "number",
                    "description": "12-month price target."
                },
                "stop_loss": {
                    "type": "number",
                    "description": "Stop-loss price to limit downside."
                },
                "risk_reward": {
                    "type": "number",
                    "description": "(target - entry) / (entry - stop_loss). Aim for ≥2.0."
                },
                "timeframe": {
                    "type": "string",
                    "enum": ["short", "medium", "long"],
                    "description": "short = <3 months, medium = 3-12 months, long = >12 months."
                },
                "key_factors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Top 3 factors driving this recommendation (bullet points)."
                }
            },
            "required": ["action", "confidence", "reasoning", "timeframe", "key_factors"]
        }
    }
]

SYSTEM_PROMPT = """You are FinAI, an autonomous stock analysis agent for Indian equity markets (NSE/BSE).

Your task: Analyze the given stock by calling tools to gather live data, then submit one structured recommendation.

Analysis process:
1. Call get_stock_price to understand current price and momentum
2. Call get_technical_indicators for RSI, MACD, moving average signals
3. Call get_brain_score for the ML composite signal
4. Call get_news_sentiment to understand recent catalysts
5. Optionally call get_portfolio_holdings if you need position context
6. Call submit_recommendation with your verdict

Interpretation guidelines:
- RSI < 30 = oversold (potential BUY entry), RSI > 70 = overbought (potential SELL)
- Brain score ≥ 70 = strong BUY signal, ≤ 30 = SELL signal, 31-69 = mixed/HOLD
- Positive news + strong technicals + high brain score = high conviction BUY
- Negative news + weak technicals + low brain score = high conviction SELL
- Conflicting signals = lower confidence, HOLD or WATCH
- For SELL recommendations on held stocks: mention STCG (15%) if held < 1 year, LTCG (10%) if held > 1 year

Risk discipline:
- Only recommend BUY with confidence ≥ 0.6
- Set stop-loss at a meaningful support level (not arbitrary %)
- Risk-reward ratio should be ≥ 2.0 for actionable BUY/SELL calls
- Conservative bias: when signals conflict, default to HOLD or WATCH

Call submit_recommendation exactly once. Do not add commentary after submitting."""


# ─── Tool executors ───────────────────────────────────────────────────────────

def _execute_tool(tool_name: str, tool_input: dict, user_id: str) -> dict:
    """Dispatch a Claude tool call to the corresponding Python function."""
    try:
        if tool_name == "get_stock_price":
            ticker = tool_input.get("ticker", "").upper()
            from stock_data import get_stock_price
            result = get_stock_price(ticker)
            return result or {"error": f"No price data available for {ticker}"}

        elif tool_name == "get_technical_indicators":
            ticker = tool_input.get("ticker", "").upper()
            from stock_data import calculate_technical_indicators
            result = calculate_technical_indicators(ticker)
            return result or {"error": f"No technical data available for {ticker}"}

        elif tool_name == "get_news_sentiment":
            ticker = tool_input.get("ticker", "").upper()
            from news_monitor import get_news_summary
            result = get_news_summary(ticker)
            return result or {"sentiment": "neutral", "articles": [], "ticker": ticker}

        elif tool_name == "get_brain_score":
            ticker = tool_input.get("ticker", "").upper()
            try:
                from brain_engine import run_brain_analysis
                result = run_brain_analysis(ticker, days=7)
                if "error" in result:
                    return {"score": 50, "signal": "HOLD",
                            "note": f"Brain engine error: {result['error']}"}
                return {
                    "score": result.get("weighted_score", 50),
                    "signal": result.get("signal", "HOLD"),
                    "technical_score": result.get("score_breakdown", {})
                                            .get("technical", {}).get("score", 50),
                    "forecast_score": result.get("score_breakdown", {})
                                          .get("forecast", {}).get("score", 50),
                    "news_score": result.get("score_breakdown", {})
                                       .get("news", {}).get("score", 50),
                    "trend_pct": result.get("trend_pct", 0),
                }
            except ImportError:
                return {"score": 50, "signal": "HOLD", "note": "Brain engine unavailable"}

        elif tool_name == "get_portfolio_holdings":
            # Prefer the user's REAL broker holdings when a live broker is linked,
            # so recommendations reference actual positions (e.g. "trim your INFY").
            try:
                from broker_manager import get_portfolio_state
                pstate = get_portfolio_state(user_id)
                if pstate["mode"] == "live":
                    slim = [
                        {
                            "ticker":        h.get("ticker"),
                            "name":          h.get("name", ""),
                            "quantity":      h.get("quantity"),
                            "buy_price":     h.get("avg_buy_price"),
                            "current_price": h.get("current_price"),
                            "pnl_percent":   round((float(h.get("current_price") or 0) /
                                                    float(h.get("avg_buy_price") or 1) - 1) * 100, 2),
                        }
                        for h in pstate["holdings"]
                    ]
                    return {
                        "source":             "broker",
                        "holdings":           slim,
                        "total_value":        pstate["total_value"],
                        "total_pnl_percent":  None,
                    }
            except Exception as exc:
                logger.debug(f"[ProactiveAgent] live holdings unavailable, using manual portfolio: {exc}")

            from portfolio_manager import get_all_holdings, get_bulk_prices, calculate_portfolio_value
            holdings = get_all_holdings(user_id)
            if not holdings:
                return {"holdings": [], "total_value": 0, "total_pnl": 0}
            tickers = [h["ticker"] for h in holdings]
            prices = get_bulk_prices(tickers)
            portfolio = calculate_portfolio_value(user_id, prices)
            # Trim to avoid token bloat — keep only essential fields
            slim_holdings = [
                {
                    "ticker": h["ticker"],
                    "name": h.get("name", ""),
                    "quantity": h["quantity"],
                    "buy_price": h["buy_price"],
                    "current_price": h.get("current_price"),
                    "pnl_percent": h.get("pnl_percent", 0),
                }
                for h in portfolio.get("holdings", [])
            ]
            return {
                "holdings": slim_holdings,
                "total_value": portfolio.get("total_value", 0),
                "total_pnl_percent": portfolio.get("total_pnl_percent", 0),
            }

        elif tool_name == "submit_recommendation":
            # Final answer tool — pass through as-is
            return {"status": "accepted"}

        else:
            return {"error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        logger.error(f"[ProactiveAgent] Tool error ({tool_name}): {e}", exc_info=True)
        return {"error": str(e)}


# ─── Redis cache helpers ──────────────────────────────────────────────────────

def _cache_key(user_id: str, ticker: str, session: str) -> str:
    today = date.today().isoformat()
    return f"stockeye:agent:{user_id}:{ticker.upper()}:{today}:{session}"


def _get_cached(user_id: str, ticker: str, session: str) -> dict | None:
    try:
        from cache import _get
        return _get(_cache_key(user_id, ticker, session))
    except Exception:
        return None


def _set_cache(user_id: str, ticker: str, session: str, data: dict):
    try:
        from cache import _set
        _set(_cache_key(user_id, ticker, session), data, CACHE_TTL)
    except Exception:
        pass


# ─── Core agentic loop ───────────────────────────────────────────────────────

def analyze_stock_for_user(user_id: str, ticker: str,
                           session: str = "manual") -> dict | None:
    """
    Run the Claude tool_use agentic loop for one stock + user.

    Returns the recommendation dict on success, None if skipped or failed.
    session: 'morning' | 'evening' | 'manual'
    """
    ticker = ticker.upper()

    # Cache check — skip if we already ran this session
    cached = _get_cached(user_id, ticker, session)
    if cached:
        logger.info(f"[ProactiveAgent] Cache hit: {ticker} ({user_id}, {session})")
        return cached

    import llm_client
    if not llm_client.is_available():
        logger.error("[ProactiveAgent] No LLM provider configured")
        return None

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M IST")
    session_label = {
        "morning": "Pre-market strategic review",
        "evening": "Post-market review",
        "manual":  "On-demand analysis",
    }.get(session, "Analysis")

    # Include shared platform intelligence (autonomous trades, monitor alerts, advisor chats)
    intel_block = ""
    try:
        from shared_context import get_context_summary
        intel_block = get_context_summary(user_id, max_age_hours=12)
    except Exception:
        pass

    user_message = (
        f"Analyze {ticker} (NSE/BSE India) — {session_label} as of {now_str}.\n"
        f"{intel_block}"
        f"Gather the necessary data using tools, then submit your recommendation."
    )

    # Escalate to the deep model tier when the brain score is extreme.
    def _escalate(name, inp, result, deep):
        if name == "get_brain_score":
            score = (result or {}).get("score", 50)
            if score >= ESCALATE_ABOVE or score <= ESCALATE_BELOW:
                logger.info(f"[ProactiveAgent] Escalating to deep model (brain score={score} for {ticker})")
                return True
        return False

    loop = llm_client.run_agent_loop(
        system=SYSTEM_PROMPT,
        user_prompt=user_message,
        tools=AGENT_TOOLS,
        dispatch=lambda name, inp: _execute_tool(name, inp, user_id),
        terminal_tools={"submit_recommendation"},
        max_iterations=MAX_TOOL_ITERATIONS,
        temperature=0.3,
        max_tokens=1800,
        escalate=_escalate,
    )

    recommendation = loop.get("terminal_result")
    if not recommendation:
        logger.warning(
            f"[ProactiveAgent] No recommendation produced for {ticker} ({user_id})"
        )
        return None

    model = loop.get("model")
    # Enrich with metadata
    recommendation.update({
        "ticker": ticker,
        "user_id": user_id,
        "session": session,
        "model_used": model,
        "data_sources": loop.get("tools_called", []),
        "generated_at": datetime.now().isoformat(),
    })

    # Cache to avoid redundant API calls within the same session
    _set_cache(user_id, ticker, session, recommendation)

    # Publish to shared intelligence bus so other modules can see this signal
    try:
        from shared_context import signal_from_recommendation
        signal_from_recommendation(user_id, ticker, recommendation)
    except Exception:
        pass

    # Persist to DB
    try:
        from recommendation_store import create_recommendation
        rec_id = create_recommendation(user_id, ticker, recommendation)
        recommendation["id"] = rec_id
        logger.info(
            f"[ProactiveAgent] Saved recommendation #{rec_id}: "
            f"{ticker} → {recommendation.get('action')} "
            f"(confidence={recommendation.get('confidence', 0):.2f}, model={model})"
        )
    except Exception as e:
        logger.error(f"[ProactiveAgent] DB save failed for {ticker}: {e}")

    # Emit WebSocket notification to the user
    _emit_recommendation(recommendation)

    return recommendation


def _emit_recommendation(rec: dict):
    """Push a lightweight recommendation summary to the connected frontend."""
    if not _socketio:
        return
    try:
        _socketio.emit(
            "agent_recommendation",
            {
                "id": rec.get("id"),
                "ticker": rec.get("ticker"),
                "action": rec.get("action"),
                "confidence": rec.get("confidence"),
                "reasoning": rec.get("reasoning", "")[:200],  # truncate for wire
                "session": rec.get("session"),
                "generated_at": rec.get("generated_at"),
            },
            namespace="/",
        )
    except Exception as e:
        logger.warning(f"[ProactiveAgent] WebSocket emit failed: {e}")


# ─── Batch runner (called by Celery tasks) ───────────────────────────────────

def run_analysis_for_all_users(session: str = "morning"):
    """
    Analyze all monitored stocks across all active users.
    Called by Celery Beat at 9:00 AM (morning) and 4:00 PM (evening) IST.
    """
    from portfolio_manager import get_all_monitored_stocks_global

    monitored = get_all_monitored_stocks_global(active_only=True)
    if not monitored:
        logger.info("[ProactiveAgent] No monitored stocks found — skipping batch.")
        return

    # Group by user_id to log per-user stats
    user_stocks: dict[str, list[str]] = {}
    for stock in monitored:
        uid = stock.get("user_id")
        if not uid:
            continue
        user_stocks.setdefault(uid, []).append(stock["ticker"])

    total_users = len(user_stocks)
    total_tickers = sum(len(t) for t in user_stocks.values())
    logger.info(
        f"[ProactiveAgent] Starting {session} batch: "
        f"{total_users} users, {total_tickers} stocks"
    )

    analyzed = 0
    skipped = 0

    for user_id, tickers in user_stocks.items():
        for ticker in tickers:
            try:
                result = analyze_stock_for_user(user_id, ticker, session=session)
                if result:
                    analyzed += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error(
                    f"[ProactiveAgent] Error analyzing {ticker} for {user_id}: {e}"
                )
                skipped += 1

    logger.info(
        f"[ProactiveAgent] {session} batch complete — "
        f"{analyzed} analyzed, {skipped} skipped/cached"
    )
