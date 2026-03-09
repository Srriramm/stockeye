"""
Agentic Forecaster — autonomous Claude tool-use loop for stock price forecasting.

Instead of running a static ML pipeline, Claude actively decides which analytical
tools to call, reasons across multiple data sources, and produces a structured forecast.

Architecture:
  - Default model  : claude-haiku-4-5-20251001 (cheap, fast)
  - Escalation     : claude-sonnet-4-6 if RSI extreme or high volatility detected
  - Cache          : Redis 6 hours per ticker+days
  - Tools (7 data) : price, technicals, ml_forecast, news, fundamentals,
                     support_resistance, risk_metrics
  - Final tool     : submit_forecast (structured output — terminates loop)
"""

import json
import logging
import os
from datetime import datetime, date

logger = logging.getLogger(__name__)

# ── Model config ──────────────────────────────────────────────────
MODEL_FAST      = "claude-haiku-4-5-20251001"
MODEL_DEEP      = "claude-sonnet-4-6"
MAX_ITERATIONS  = 12
CACHE_TTL       = 6 * 3600   # 6 hours

# RSI thresholds that trigger model escalation
RSI_ESCALATE_LOW  = 25
RSI_ESCALATE_HIGH = 75

# ── System prompt ─────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a quantitative analyst specialising in Indian equity markets (NSE/BSE).
Your task: produce a rigorous, evidence-backed price forecast for a given stock.

WORKFLOW — follow this order, calling tools as needed:
1. get_price_data        — current price, 52w range, volume, market cap
2. get_technical_indicators — RSI, MACD, Bollinger, SMA trend
3. run_ml_forecast       — statistical baseline (Prophet model)
4. get_news_sentiment    — fundamental catalysts from recent news
5. get_fundamentals      — valuation (P/E, EPS, margins) for context
6. get_support_resistance — realistic price target anchors
7. get_risk_metrics      — calibrate confidence interval width
8. submit_forecast       — your final structured forecast

REASONING RULES:
- ML model gives DIRECTION only — do NOT copy its target price or confidence bands into submit_forecast
- Price targets must come from support/resistance levels and your own analysis, not ML confidence intervals
- Oversold RSI alone does NOT justify BUY if trend + MACD are bearish
- A strong negative news catalyst overrides mild bullish technicals
- Signal/target MUST be consistent — strictly enforce:
    BUY   → price_target MUST be above current price (use nearest resistance as target)
    SELL  → price_target MUST be below current price (use nearest support as target)
    HOLD  → price_target within ±5% of current (if mixed signals push a HOLD, target = current ±3%)
    WATCH → price_target within ±8% of current (monitoring zone)
  If your computed target would be >5% below current, the signal is SELL, not HOLD.
  If your computed target would be >5% above current, the signal is BUY, not HOLD.
- price_target_low / price_target_high = your bear-case and bull-case, derived from support/resistance zones, NOT from ML confidence bands
- Confidence 0.5–0.65 for mixed signals, 0.7–0.85 for clear signals
- Always cite specific numbers in reasoning (RSI value, MACD direction, P/E, news count)
- Stop loss should be at or just below nearest support level

Call submit_forecast once you have gathered sufficient evidence. Be direct and quantitative."""

# ── Tool definitions ──────────────────────────────────────────────
FORECAST_TOOLS = [
    {
        "name": "get_price_data",
        "description": (
            "Get current price snapshot: live price, previous close, day high/low, "
            "volume, 52-week high/low, market cap, sector. Call this first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "NSE/BSE ticker (e.g. TCS, RELIANCE)"}
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_technical_indicators",
        "description": (
            "Get RSI, MACD, Bollinger Bands, SMA 20/50/200, volume ratio, and "
            "pre-computed signals. Essential for momentum and trend analysis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "period": {
                    "type": "string",
                    "enum": ["3mo", "6mo", "1y"],
                    "description": "Lookback period for indicator calculation. Default 6mo.",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "run_ml_forecast",
        "description": (
            "Run the Prophet time-series model to get a statistical baseline price "
            "projection. Returns target price, trend %, direction, confidence, and "
            "signal_strength. Use as one data point — reason beyond it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
                "days": {
                    "type": "integer",
                    "description": "Forecast horizon in days (7–60)",
                },
            },
            "required": ["ticker", "days"],
        },
    },
    {
        "name": "get_news_sentiment",
        "description": (
            "Fetch recent news articles (last 7 days) with AI sentiment labels. "
            "Returns positive/negative/neutral counts and article titles. "
            "Use to identify fundamental catalysts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_fundamentals",
        "description": (
            "Get fundamental data: P/E, forward P/E, EPS, book value, dividend yield, "
            "debt/equity, ROE, profit margin, beta. Use for valuation context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_support_resistance",
        "description": (
            "Get key support and resistance price levels from recent price action, "
            "plus Fibonacci retracement levels. Use to set realistic price targets "
            "and stop-loss levels."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_risk_metrics",
        "description": (
            "Get risk profile: annual volatility, beta, Sharpe ratio, max drawdown, "
            "Value-at-Risk (95%). Use to calibrate confidence interval width and "
            "assess risk/reward."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "submit_forecast",
        "description": (
            "Submit your final forecast. Call this ONCE after gathering sufficient evidence. "
            "This terminates the analysis — make it comprehensive and evidence-backed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "price_target": {
                    "type": "number",
                    "description": (
                        "Your own price target (INR) derived from support/resistance analysis — "
                        "NOT copied from ML model output. For BUY: nearest resistance. "
                        "For SELL: nearest support. For HOLD: current price ±3%."
                    ),
                },
                "price_target_low": {
                    "type": "number",
                    "description": (
                        "Bear-case price (INR) — use nearest support level from get_support_resistance, "
                        "NOT the ML confidence band lower bound."
                    ),
                },
                "price_target_high": {
                    "type": "number",
                    "description": (
                        "Bull-case price (INR) — use nearest resistance level from get_support_resistance, "
                        "NOT the ML confidence band upper bound."
                    ),
                },
                "signal": {
                    "type": "string",
                    "enum": ["BUY", "SELL", "HOLD", "WATCH"],
                    "description": (
                        "Trading signal — MUST match your price_target direction. "
                        "BUY: target > current price (upside expected). "
                        "SELL: target < current price (downside expected, >3% decline). "
                        "HOLD: mixed/unclear signals; target stays within ±5% of current. "
                        "WATCH: insufficient data or high uncertainty. "
                        "If technicals/ML both point down >5%, choose SELL not HOLD."
                    ),
                },
                "confidence": {
                    "type": "number",
                    "description": "Forecast confidence 0.0–1.0. Be honest — use 0.5–0.65 for mixed signals.",
                },
                "entry_zone_low": {
                    "type": "number",
                    "description": "Lower bound of recommended entry price zone (INR). Null for SELL.",
                },
                "entry_zone_high": {
                    "type": "number",
                    "description": "Upper bound of recommended entry price zone (INR). Null for SELL.",
                },
                "stop_loss": {
                    "type": "number",
                    "description": "Stop-loss price — ideally just below nearest support (INR)",
                },
                "key_drivers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "3–5 factors driving this forecast. Cite specific numbers: "
                        "'RSI at 25 — deep oversold', 'MACD bearish', 'P/E 22x vs sector 28x'"
                    ),
                },
                "risks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "2–4 key risks to this forecast. Be specific.",
                },
                "reasoning": {
                    "type": "string",
                    "description": (
                        "2–4 sentence synthesis citing specific data. Example: "
                        "'RSI at 25 (oversold) with MACD still bearish and -3 negative articles "
                        "this week. Prophet model predicts -2.8% decline. P/E of 22x is below "
                        "sector average of 28x but earnings momentum is weak. HOLD until MACD "
                        "confirms reversal.'"
                    ),
                },
            },
            "required": [
                "price_target", "price_target_low", "price_target_high",
                "signal", "confidence", "stop_loss",
                "key_drivers", "risks", "reasoning",
            ],
        },
    },
]


# ── Redis cache helpers ───────────────────────────────────────────
def _cache_key(ticker: str, days: int) -> str:
    return f"stockeye:agentfcast:{ticker}:{days}:{date.today().isoformat()}"


def _get_cached(ticker: str, days: int):
    try:
        from cache import redis_client
        if not redis_client:
            return None
        raw = redis_client.get(_cache_key(ticker, days))
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _set_cache(ticker: str, days: int, result: dict):
    try:
        from cache import redis_client
        if not redis_client:
            return
        redis_client.setex(_cache_key(ticker, days), CACHE_TTL, json.dumps(result))
    except Exception:
        pass


# ── Anthropic client ─────────────────────────────────────────────
_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            logger.error("ANTHROPIC_API_KEY not set — agentic forecaster unavailable")
            return None
        _client = anthropic.Anthropic(api_key=key)
    return _client


# ── Tool executors ────────────────────────────────────────────────
def _execute_tool(name: str, inputs: dict, ticker: str, days: int) -> dict:
    """Execute a data-gathering tool and return a JSON-serialisable dict."""
    try:
        t = inputs.get("ticker", ticker).upper().replace(".NS", "").replace(".BO", "")

        if name == "get_price_data":
            from stock_data import get_stock_price
            result = get_stock_price(t)
            return result or {"error": "Price data unavailable"}

        elif name == "get_technical_indicators":
            from stock_data import calculate_technical_indicators
            period = inputs.get("period", "6mo")
            result = calculate_technical_indicators(t, period=period)
            return result or {"error": "Technical data unavailable"}

        elif name == "run_ml_forecast":
            from stock_data import get_historical_data
            from forecasting_engine import forecast_stock_price
            d = min(max(int(inputs.get("days", days)), 7), 60)
            historical = get_historical_data(t, period="1y", interval="1d")
            if not historical:
                return {"error": "No historical data"}
            result = forecast_stock_price(historical, t, days=d)
            # Drop the full forecast series — too many tokens
            return {k: v for k, v in result.items() if k != "forecast"}

        elif name == "get_news_sentiment":
            from news_monitor import fetch_stock_news
            articles = fetch_stock_news(t, days=7, max_articles=8)
            pos = sum(1 for a in articles if a.get("sentiment") == "positive")
            neg = sum(1 for a in articles if a.get("sentiment") == "negative")
            neu = sum(1 for a in articles if a.get("sentiment") == "neutral")
            return {
                "total_articles": len(articles),
                "positive": pos,
                "negative": neg,
                "neutral": neu,
                "sentiment_label": (
                    "Positive" if pos > neg else
                    ("Negative" if neg > pos else "Neutral")
                ),
                "articles": [
                    {
                        "title": a["title"],
                        "sentiment": a.get("sentiment"),
                        "source": a.get("source", ""),
                        "date": (a.get("published_at") or "")[:10],
                    }
                    for a in articles[:6]
                ],
            }

        elif name == "get_fundamentals":
            from stock_data import get_stock_info
            info = get_stock_info(t)
            if not info:
                return {"error": "Fundamentals unavailable"}
            keys = [
                "pe_ratio", "forward_pe", "eps", "book_value", "price_to_book",
                "dividend_yield", "debt_to_equity", "roe", "profit_margin",
                "operating_margin", "beta", "market_cap_formatted", "sector", "industry",
            ]
            return {k: info.get(k) for k in keys}

        elif name == "get_support_resistance":
            from stock_data import find_support_resistance, calculate_fibonacci_levels
            sr  = find_support_resistance(t, period="6mo")
            fib = calculate_fibonacci_levels(t, period="6mo")
            fib_levels = fib.get("levels", {})
            return {
                "support_levels":    (sr.get("support_levels") or [])[:3],
                "resistance_levels": (sr.get("resistance_levels") or [])[:3],
                "nearest_support":    sr.get("nearest_support"),
                "nearest_resistance": sr.get("nearest_resistance"),
                "fibonacci_38pct":   fib_levels.get("38.2%"),
                "fibonacci_50pct":   fib_levels.get("50.0%"),
                "fibonacci_61pct":   fib_levels.get("61.8%"),
                "swing_high":        fib.get("swing_high"),
                "swing_low":         fib.get("swing_low"),
            }

        elif name == "get_risk_metrics":
            from stock_data import get_historical_data
            from forecasting_engine import get_risk_profile
            historical = get_historical_data(t, period="1y", interval="1d")
            if not historical:
                return {"error": "No historical data for risk calculation"}
            return get_risk_profile(historical, t)

        else:
            return {"error": f"Unknown tool: {name}"}

    except Exception as exc:
        logger.error(f"Tool '{name}' failed for {ticker}: {exc}", exc_info=True)
        return {"error": str(exc)}


# ── Main agentic loop ─────────────────────────────────────────────
def run_agentic_forecast(ticker: str, days: int = 30) -> dict | None:
    """
    Run the autonomous Claude agentic forecasting loop.

    Claude calls data tools iteratively, reasons across them,
    and submits a structured forecast via submit_forecast.

    Returns a structured forecast dict or None on failure.
    Results are cached in Redis for 6 hours.
    """
    ticker = ticker.upper().replace(".NS", "").replace(".BO", "")

    cached = _get_cached(ticker, days)
    if cached:
        cached["from_cache"] = True
        return cached

    client = _get_client()
    if not client:
        return None

    messages = [
        {
            "role": "user",
            "content": (
                f"Analyse {ticker} and produce a {days}-day price forecast.\n"
                f"Today: {date.today().isoformat()}\n\n"
                f"Work systematically: start with get_price_data, then gather technical, "
                f"ML forecast, news, and fundamental evidence before submitting."
            ),
        }
    ]

    model          = MODEL_FAST
    data_sources   = []
    forecast_result = None

    for iteration in range(MAX_ITERATIONS):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=2200,
                temperature=0.2,
                system=SYSTEM_PROMPT,
                tools=FORECAST_TOOLS,
                messages=messages,
            )
        except Exception as exc:
            logger.error(f"Claude API error in agentic forecaster (iter {iteration}): {exc}")
            break

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            break
        if response.stop_reason != "tool_use":
            break

        tool_results = []
        loop_done    = False

        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_name  = block.name
            tool_input = block.input

            # ── Final answer ──────────────────────────────────────
            if tool_name == "submit_forecast":
                forecast_result = dict(tool_input)
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     json.dumps({"status": "accepted"}),
                })
                loop_done = True
                break

            # ── Execute data tool ─────────────────────────────────
            result = _execute_tool(tool_name, tool_input, ticker, days)
            data_sources.append(tool_name)

            # ── Model escalation on extreme signals ───────────────
            if tool_name == "get_technical_indicators" and model == MODEL_FAST:
                rsi = float(result.get("rsi") or 50)
                if rsi <= RSI_ESCALATE_LOW or rsi >= RSI_ESCALATE_HIGH:
                    model = MODEL_DEEP
                    logger.info(f"Escalated to {MODEL_DEEP} for {ticker} (RSI={rsi:.1f})")

            if tool_name == "get_risk_metrics" and model == MODEL_FAST:
                vol = float(result.get("annual_volatility_pct") or 0)
                if vol > 45:
                    model = MODEL_DEEP
                    logger.info(f"Escalated to {MODEL_DEEP} for {ticker} (vol={vol:.1f}%)")

            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": block.id,
                "content":     json.dumps(result, default=str),
            })

        messages.append({"role": "user", "content": tool_results})

        if loop_done:
            break

    if not forecast_result:
        logger.warning(f"Agentic forecaster produced no result for {ticker}")
        return None

    # ── Enrich with metadata ─────────────────────────────────────
    try:
        from stock_data import get_stock_price
        price_data    = get_stock_price(ticker) or {}
        current_price = float(price_data.get("current_price") or 0)
    except Exception:
        current_price = 0

    pt = float(forecast_result.get("price_target") or current_price)
    trend_pct = round((pt - current_price) / current_price * 100, 2) if current_price else 0

    result = {
        "ticker":            ticker,
        "forecast_days":     days,
        "current_price":     current_price,
        "price_target":      forecast_result.get("price_target"),
        "price_target_low":  forecast_result.get("price_target_low"),
        "price_target_high": forecast_result.get("price_target_high"),
        "trend_pct":         trend_pct,
        "signal":            forecast_result.get("signal", "HOLD"),
        "confidence":        forecast_result.get("confidence", 0.5),
        "entry_zone_low":    forecast_result.get("entry_zone_low"),
        "entry_zone_high":   forecast_result.get("entry_zone_high"),
        "stop_loss":         forecast_result.get("stop_loss"),
        "key_drivers":       forecast_result.get("key_drivers", []),
        "risks":             forecast_result.get("risks", []),
        "reasoning":         forecast_result.get("reasoning", ""),
        "data_sources":      list(dict.fromkeys(data_sources)),   # preserve order, dedupe
        "model_used":        model,
        "generated_at":      datetime.now().isoformat(),
        "from_cache":        False,
    }

    _set_cache(ticker, days, result)
    logger.info(
        f"Agentic forecast complete: {ticker} {days}d → {result['signal']} "
        f"target={result['price_target']} conf={result['confidence']:.0%} model={model}"
    )
    return result
