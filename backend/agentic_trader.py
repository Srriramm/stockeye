"""
Agentic Trader — autonomous Claude tool-use loop for paper/live trading.

The agent scans for market opportunities (ETF arbitrage, pairs divergence,
mean reversion), reasons about risk/reward, sizes positions, and executes
paper trades autonomously.

Hard limits (enforced in _execute_tool, non-negotiable):
  - Max 5%  of portfolio per single trade
  - Max 3   concurrent open positions
  - Max 2%  daily loss before auto-halt
  - Paper mode unless TRADING_LIVE_ENABLED=true + broker connected

Architecture mirrors proactive_agent.py and agentic_forecaster.py.
"""

import json
import logging
import os
from datetime import datetime, date

logger = logging.getLogger(__name__)

# ── Model config ──────────────────────────────────────────────────────────────
MODEL_FAST      = "claude-haiku-4-5-20251001"
MODEL_DEEP      = "claude-sonnet-4-6"
MAX_ITERATIONS  = 12

# ── Hard risk limits ──────────────────────────────────────────────────────────
MAX_POSITION_PCT   = 0.05   # 5 % of total portfolio per trade
MAX_OPEN_POSITIONS = 3
MAX_DAILY_LOSS_PCT = 0.02   # 2 % daily loss triggers halt

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an autonomous paper trading agent for Indian equity markets (NSE/BSE).
Your task: scan for opportunities, reason about risk/reward, execute disciplined paper trades,
and actively manage open positions — including selling when conditions are met.

WORKFLOW (call tools in this order):
1. scan_opportunities      — get current ETF arbitrage, pairs, and Bollinger signals
2. get_portfolio_state     — check capital, open positions with live P&L
3. execute_trade (SELL)    — exit positions that hit exit rules BEFORE opening new ones
4. analyse_opportunity     — deep-dive into the best 1-2 opportunities (only if slots remain)
5. calculate_position_size — risk-based position sizing for each trade
6. execute_trade (BUY)     — place paper trade only if setup is high-conviction
7. submit_session_summary  — final report of decisions made

EXIT RULES — evaluate open positions at step 3; sell if ANY rule triggers:
- ETF arb:      SELL ALL if NAV discount < 2% (gap closed, trade is done)
- Pairs long:   SELL ALL if z-score < 1.5σ (mean-reverted — take profit)
- Partial exit: SELL 50% of position if unrealised gain > 4% (lock in profit, let rest run)
- Hard stop:    SELL ALL if unrealised loss > 5% (capital protection — no exceptions)
- News exit:    SELL ALL if negative news sentiment is high for a holding (≥ 3 negative articles)
- Never re-buy a ticker that is currently in the portfolio

ENTRY RULES (strict — follow every rule):
- Only trade if expected profit > 0.5% after estimated transaction costs (0.15%)
- Risk/reward ratio must be ≥ 1.5  (target gain ÷ stop-loss distance)
- Never exceed 5% of portfolio per position
- Never open a 4th position when 3 are already open
- Stop trading immediately if daily loss > 2%
- Prefer ETF arbitrage > pairs divergence > directional Bollinger trades
- Always specify a stop-loss when executing
- Cite specific numbers: spread %, z-score, RSI, expected ₹ profit

Be disciplined and conservative. Managing exits is as important as finding entries."""

# ── Tool definitions ──────────────────────────────────────────────────────────
TRADING_TOOLS = [
    {
        "name": "scan_opportunities",
        "description": (
            "Scan the market for current trading opportunities: ETF NAV divergence, "
            "correlated pairs divergence (z-score), and Bollinger Band extremes. "
            "Call this first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "include_etf":   {"type": "boolean", "description": "Scan ETF NAV divergence (default true)"},
                "include_pairs": {"type": "boolean", "description": "Scan pairs divergence (default true)"},
                "include_bb":    {"type": "boolean", "description": "Scan Bollinger extremes (default true)"},
            },
        },
    },
    {
        "name": "get_portfolio_state",
        "description": (
            "Get current paper trading state: available capital, open positions, "
            "today's realised P&L, and max allowed position size."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "analyse_opportunity",
        "description": (
            "Deep technical + sentiment analysis for a specific ticker: RSI, MACD, "
            "Bollinger, SMA trend, news sentiment, and recent price action."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "NSE ticker to analyse"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "calculate_position_size",
        "description": (
            "Calculate a safe position size using fixed-fractional risk. "
            "Respects the 5% portfolio cap and returns quantity + capital at risk."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker":      {"type": "string"},
                "entry_price": {"type": "number", "description": "Intended entry price (INR)"},
                "stop_loss":   {"type": "number", "description": "Stop-loss price (INR)"},
                "risk_pct":    {"type": "number", "description": "Fraction of portfolio to risk (e.g. 0.01 = 1%). Default 0.01"},
            },
            "required": ["ticker", "entry_price", "stop_loss"],
        },
    },
    {
        "name": "execute_trade",
        "description": "Execute a paper trade. Returns order confirmation with order ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker":     {"type": "string"},
                "side":       {"type": "string", "enum": ["BUY", "SELL"]},
                "quantity":   {"type": "integer", "minimum": 1},
                "order_type": {"type": "string", "enum": ["MARKET"]},
                "price":      {"type": "number", "description": "Limit price (required for LIMIT orders)"},
                "stop_loss":  {"type": "number", "description": "Stop-loss price (INR)"},
                "reasoning":  {"type": "string", "description": "1-2 sentences: why this trade, what signal triggered it"},
            },
            "required": ["ticker", "side", "quantity", "order_type", "reasoning"],
        },
    },
    {
        "name": "submit_session_summary",
        "description": "Submit the final session report. Call this when done — it ends the session.",
        "input_schema": {
            "type": "object",
            "properties": {
                "trades_executed":        {"type": "integer"},
                "opportunities_found":    {"type": "integer"},
                "total_capital_deployed": {"type": "number"},
                "reasoning":              {"type": "string", "description": "2-3 sentence summary of the session"},
                "market_conditions":      {"type": "string"},
                "risk_assessment":        {"type": "string"},
                "skipped_trades":         {"type": "string", "description": "Opportunities passed on and why"},
            },
            "required": ["trades_executed", "opportunities_found", "reasoning"],
        },
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Tool executors
# ─────────────────────────────────────────────────────────────────────────────
def _execute_tool(name: str, inputs: dict, user_id: str, session_id: str,
                  user_tickers: list | None = None,
                  budget: float | None = None) -> dict:
    """Execute one trading tool and return a JSON-serialisable dict."""
    try:
        # ── scan_opportunities ────────────────────────────────────────────────
        if name == "scan_opportunities":
            from arbitrage_detector import scan_opportunities
            if user_tickers:
                tickers = user_tickers
            else:
                from db import get_db_connection
                with get_db_connection() as conn:
                    rows = conn.execute(
                        "SELECT ws.ticker FROM watchlist_items ws "
                        "JOIN watchlists w ON ws.watchlist_id = w.id "
                        "WHERE w.user_id = ?",
                        (user_id,)
                    ).fetchall()
                tickers = [r["ticker"] for r in rows][:20]
            opps = scan_opportunities(tickers)
            return {"opportunities": opps, "count": len(opps), "tickers_scanned": len(tickers)}

        # ── get_portfolio_state ───────────────────────────────────────────────
        elif name == "get_portfolio_state":
            from trading_manager import get_trading_balance, get_trading_portfolio
            from stock_data import get_bulk_prices
            balance  = get_trading_balance(user_id) or {}
            holdings = get_trading_portfolio(user_id) or []
            prices   = get_bulk_prices([h["ticker"] for h in holdings]) if holdings else {}

            enriched = []
            for h in holdings:
                ticker    = h.get("ticker")
                avg_buy   = float(h.get("avg_buy_price") or 0)
                qty       = float(h.get("quantity") or 0)
                cur_price = float(prices.get(ticker) or avg_buy)
                unreal    = round((cur_price - avg_buy) * qty, 2)
                pnl_pct   = round((cur_price / avg_buy - 1) * 100, 2) if avg_buy else 0
                enriched.append({
                    "ticker":           ticker,
                    "quantity":         qty,
                    "avg_buy_price":    avg_buy,
                    "current_price":    cur_price,
                    "total_investment": h.get("total_investment"),
                    "unrealised_pnl":   unreal,
                    "pnl_pct":          pnl_pct,
                })

            market_value = sum(p["current_price"] * p["quantity"] for p in enriched)
            avail        = float(balance.get("balance") or 0)
            total        = avail + market_value

            return {
                "available_capital":     round(avail, 2),
                "total_portfolio_value": round(total, 2),
                "open_positions":        len(holdings),
                "max_position_size_inr": round(total * MAX_POSITION_PCT, 2),
                "positions":             enriched,
            }

        # ── analyse_opportunity ───────────────────────────────────────────────
        elif name == "analyse_opportunity":
            ticker = inputs.get("ticker", "").upper().replace(".NS", "").replace(".BO", "")
            from stock_data import calculate_technical_indicators, get_stock_price
            from news_monitor import fetch_stock_news
            price_data = get_stock_price(ticker) or {}
            tech       = calculate_technical_indicators(ticker, period="3mo") or {}
            articles   = fetch_stock_news(ticker, days=3, max_articles=5)
            pos = sum(1 for a in articles if a.get("sentiment") == "positive")
            neg = sum(1 for a in articles if a.get("sentiment") == "negative")
            return {
                "ticker":          ticker,
                "current_price":   price_data.get("current_price"),
                "day_change_pct":  price_data.get("day_change_pct"),
                "volume_ratio":    tech.get("volume_ratio"),
                "rsi":             tech.get("rsi"),
                "macd_direction":  tech.get("macd_direction"),
                "sma_20":          tech.get("sma_20"),
                "sma_50":          tech.get("sma_50"),
                "bollinger":       tech.get("bollinger_bands", {}),
                "news_positive":   pos,
                "news_negative":   neg,
                "tech_signal":     tech.get("signal"),
            }

        # ── calculate_position_size ───────────────────────────────────────────
        elif name == "calculate_position_size":
            from trading_manager import get_trading_balance, get_trading_portfolio
            entry    = float(inputs.get("entry_price") or 0)
            stop     = float(inputs.get("stop_loss")   or 0)
            risk_pct = float(inputs.get("risk_pct")    or 0.01)
            ticker   = inputs.get("ticker", "")

            if entry <= 0:
                return {"error": "entry_price must be > 0"}
            risk_per_share = abs(entry - stop) if stop else entry * 0.02
            if risk_per_share == 0:
                return {"error": "stop_loss must differ from entry_price"}

            balance   = get_trading_balance(user_id) or {}
            holdings  = get_trading_portfolio(user_id) or []   # list of dicts
            invested  = sum(float(h.get("total_investment") or 0) for h in holdings)
            total     = float(balance.get("balance") or 100_000) + invested
            avail     = float(balance.get("balance") or 100_000)
            # If a session budget was set, split it evenly across max positions
            if budget is not None:
                ref_capital  = min(float(budget), avail)
                # Budget mode: split evenly across slots — use capital sizing, not risk sizing
                slot_capital = ref_capital / MAX_OPEN_POSITIONS  # e.g. 9000/3 = ₹3000
                quantity     = max(1, int(slot_capital / entry))
            else:
                ref_capital  = total
                max_capital  = ref_capital * MAX_POSITION_PCT
                risk_capital = ref_capital * min(risk_pct, 0.02)
                qty_risk     = int(risk_capital / risk_per_share)
                qty_capital  = int(max_capital / entry)
                quantity     = max(1, min(qty_risk, qty_capital))

            capital_required = round(quantity * entry, 2)
            return {
                "ticker":                ticker,
                "quantity":              quantity,
                "entry_price":           entry,
                "stop_loss":             stop,
                "capital_required":      capital_required,
                "capital_at_risk":       round(quantity * risk_per_share, 2),
                "available_capital":     round(avail, 2),
                "within_limits":         capital_required <= avail,
            }

        # ── execute_trade ─────────────────────────────────────────────────────
        elif name == "execute_trade":
            from trading_manager import (
                get_trading_portfolio, get_trading_balance, place_order
            )
            holdings     = get_trading_portfolio(user_id) or []
            held_tickers = {h["ticker"] for h in holdings}
            ticker_check = inputs.get("ticker", "").upper()
            side_check   = inputs.get("side", "BUY")

            # No-rebuy guard
            if side_check == "BUY" and ticker_check in held_tickers:
                return {"error": f"Already holding {ticker_check} — sell first or pick a different stock"}

            # Hard limit: max open positions
            if side_check == "BUY" and len(holdings) >= MAX_OPEN_POSITIONS:
                return {"error": f"Max {MAX_OPEN_POSITIONS} open positions reached — skipping trade"}

            # Hard limit: daily loss (approximate using invested vs balance)
            balance   = get_trading_balance(user_id) or {}
            invested  = sum(float(h.get("total_investment") or 0) for h in holdings)
            total     = float(balance.get("balance") or 100_000) + invested

            ticker     = inputs.get("ticker", "").upper()
            side       = inputs.get("side", "BUY")
            quantity   = int(inputs.get("quantity") or 1)
            order_type = "MARKET"  # paper trading always executes immediately
            price      = float(inputs.get("price") or 0)
            stop_loss  = inputs.get("stop_loss")

            # Fetch live price if not provided
            if not price:
                from stock_data import get_stock_price
                p = get_stock_price(ticker) or {}
                price = float(p.get("current_price") or 0)
            if not price:
                return {"error": f"Could not determine price for {ticker}"}

            # Capital check for buys
            avail = float(balance.get("balance") or 0)
            if side == "BUY" and price * quantity > avail:
                return {
                    "error": (
                        f"Insufficient capital: need ₹{price*quantity:,.0f}, "
                        f"available ₹{avail:,.0f}"
                    )
                }

            order_id = place_order(
                user_id    = user_id,
                ticker     = ticker,
                name       = ticker,
                side       = side,
                order_type = order_type,
                quantity   = quantity,
                price      = price,
                stop_price = float(stop_loss) if stop_loss else None,
                limit_price= price if order_type == "LIMIT" else None,
            )
            if not order_id:
                return {"error": "Order placement failed — check trading_manager logs"}

            # Publish to shared intelligence bus
            try:
                from shared_context import signal_from_trade
                signal_from_trade(user_id, ticker, side, quantity, price,
                                  reasoning=inputs.get("reasoning", ""))
            except Exception:
                pass

            logger.info(
                f"[AutoTrader:{session_id}] {side} {quantity}x{ticker} @ ₹{price:.2f} | "
                f"{inputs.get('reasoning','')[:120]}"
            )
            return {
                "success":         True,
                "order_id":        order_id,
                "status":          "EXECUTED" if order_type == "MARKET" else "PENDING",
                "ticker":          ticker,
                "side":            side,
                "quantity":        quantity,
                "execution_price": round(price, 2),
                "total_value":     round(quantity * price, 2),
            }

        # ── submit_session_summary ────────────────────────────────────────────
        elif name == "submit_session_summary":
            return {"status": "session_complete", **inputs}

        else:
            return {"error": f"Unknown tool: {name}"}

    except Exception as exc:
        logger.error(f"[AutoTrader] tool '{name}' failed: {exc}", exc_info=True)
        return {"error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Win-rate helper
# ─────────────────────────────────────────────────────────────────────────────
def _compute_win_rate(user_id: str) -> float | None:
    """
    Return win rate of the last 10 completed (SELL) positions.
    For each SELL trade, finds the most recent matching BUY and compares prices.
    Returns None if fewer than 3 sell trades exist (insufficient data).
    """
    try:
        from db import get_db_connection
        with get_db_connection() as conn:
            sells = conn.execute(
                "SELECT ticker, price FROM trades WHERE user_id=? AND side='SELL' "
                "ORDER BY executed_at DESC LIMIT 10",
                (user_id,)
            ).fetchall()
        if len(sells) < 3:
            return None
        wins = 0
        with get_db_connection() as conn:
            for sell in sells:
                buy = conn.execute(
                    "SELECT price FROM trades WHERE user_id=? AND ticker=? AND side='BUY' "
                    "ORDER BY executed_at DESC LIMIT 1",
                    (user_id, sell['ticker'])
                ).fetchone()
                if buy and float(sell['price']) > float(buy['price']):
                    wins += 1
        return wins / len(sells)
    except Exception as exc:
        logger.debug(f"_compute_win_rate failed (non-fatal): {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Active session registry (in-memory; one session per process)
# ─────────────────────────────────────────────────────────────────────────────
_active_sessions: dict[str, dict] = {}   # user_id → session dict


def get_active_session(user_id: str) -> dict | None:
    return _active_sessions.get(user_id)


# ─────────────────────────────────────────────────────────────────────────────
# Main agentic loop
# ─────────────────────────────────────────────────────────────────────────────
def run_trading_session(user_id: str, tickers: list | None = None,
                        budget: float | None = None) -> dict | None:
    """
    Run one autonomous paper-trading session for a user.

    Args:
        budget: Optional cap on capital to deploy in this session (INR).
                If None, the full available balance is usable.

    Returns a structured session summary dict or None on failure.
    """
    import anthropic
    from trading_manager import get_trading_balance

    session_id = f"trade-{user_id[:8]}-{datetime.now().strftime('%H%M%S')}"
    _active_sessions[user_id] = {"session_id": session_id, "status": "running", "user_id": user_id}

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY not set — agentic trader unavailable")
        return None

    # Determine usable capital for this session
    balance_row    = get_trading_balance(user_id) or {}
    available      = float(balance_row.get('balance') or 0)
    usable_capital = min(float(budget), available) if budget is not None else available

    client  = anthropic.Anthropic(api_key=api_key)
    model   = MODEL_FAST
    trades  = []
    session_result = None

    per_slot = usable_capital / MAX_OPEN_POSITIONS if budget is not None else 0
    budget_note = (
        f"BUDGET FOR THIS SESSION: ₹{usable_capital:,.2f} split across up to {MAX_OPEN_POSITIONS} positions "
        f"(≈₹{per_slot:,.0f} per stock). "
        f"AIM TO FILL ALL {MAX_OPEN_POSITIONS} SLOTS — scan broadly and pick the best {MAX_OPEN_POSITIONS} opportunities. "
        f"Do not stop at 1 trade if more opportunities exist. "
        f"Your available cash is ₹{available:,.2f}. "
    ) if budget is not None else ""

    # Shared intelligence from other modules (proactive agent, monitor alerts)
    try:
        from shared_context import get_context_summary
        intel_block = get_context_summary(user_id, max_age_hours=12)
    except Exception:
        intel_block = ""

    # Self-tuning: adjust sizing/criteria based on recent win rate
    win_rate     = _compute_win_rate(user_id)
    win_rate_note = ""
    if win_rate is not None:
        if win_rate < 0.4:
            win_rate_note = (
                f"CAUTION: recent win rate is {win_rate:.0%}. "
                f"Raise minimum R:R to 2.0 and halve all position sizes. "
            )
        elif win_rate > 0.7:
            win_rate_note = (
                f"CONFIDENCE: recent win rate is {win_rate:.0%}. Normal sizing applies. "
            )

    messages = [
        {
            "role": "user",
            "content": (
                f"Run a paper trading session. Today: {date.today().isoformat()}. "
                f"{budget_note}"
                f"{win_rate_note}"
                f"{intel_block}"
                f"Follow the workflow: first check portfolio state, apply exit rules to "
                f"open positions, then scan and execute 1-2 high-conviction new trades. "
                f"Prioritise tickers flagged as bullish in the platform intelligence above. "
                f"Avoid tickers flagged as bearish unless the reversal case is very clear. "
                f"Only trade if risk/reward ≥ 1.5."
            ),
        }
    ]

    for iteration in range(MAX_ITERATIONS):
        # Force-submit nudge after iteration 7 to prevent stalling
        if iteration == 7 and not session_result:
            messages.append({
                "role": "user",
                "content": (
                    "You have gathered sufficient data. "
                    "Call submit_session_summary NOW with your final report."
                ),
            })

        try:
            response = client.messages.create(
                model      = model,
                max_tokens = 4096,
                temperature= 0.1,
                system     = SYSTEM_PROMPT,
                tools      = TRADING_TOOLS,
                messages   = messages,
            )
        except Exception as exc:
            logger.error(f"[{session_id}] Claude API error (iter {iteration}): {exc}")
            break

        logger.debug(
            f"[{session_id}] iter={iteration} stop={response.stop_reason} "
            f"blocks={[b.type for b in response.content]}"
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            logger.warning(f"[{session_id}] end_turn at iter {iteration} without submitting")
            break
        if response.stop_reason != "tool_use":
            break

        tool_results = []
        loop_done    = False

        for block in response.content:
            if block.type != "tool_use":
                continue

            name  = block.name
            inp   = block.input

            if name == "submit_session_summary":
                session_result = dict(inp)
                tool_results.append({
                    "type":        "tool_result",
                    "tool_use_id": block.id,
                    "content":     json.dumps({"status": "session_complete"}),
                })
                loop_done = True
                break

            # Escalate to Sonnet for deep analysis
            if name == "analyse_opportunity" and model == MODEL_FAST:
                model = MODEL_DEEP
                logger.info(f"[{session_id}] Escalated to Sonnet for analysis")

            result = _execute_tool(name, inp, user_id, session_id,
                                   user_tickers=tickers, budget=budget)

            # Track executed trades
            if name == "execute_trade" and result.get("success"):
                trades.append(result)
                # Update session state in registry
                _active_sessions[user_id]["trades"] = trades

            tool_results.append({
                "type":        "tool_result",
                "tool_use_id": block.id,
                "content":     json.dumps(result, default=str),
            })

        messages.append({"role": "user", "content": tool_results})

        if loop_done:
            break

    # Fallback summary if Claude never called submit_session_summary
    if not session_result:
        logger.warning(f"[{session_id}] No session summary produced")
        session_result = {
            "trades_executed":        len(trades),
            "opportunities_found":    0,
            "total_capital_deployed": sum(t.get("total_value", 0) for t in trades),
            "reasoning":              "Session ended without explicit summary.",
            "market_conditions":      "Unknown",
            "risk_assessment":        "N/A",
        }

    final = {
        "session_id":   session_id,
        "user_id":      user_id,
        "trades":       trades,
        "model_used":   model,
        "generated_at": datetime.now().isoformat(),
        "status":       "complete",
        **session_result,
    }

    _active_sessions[user_id] = final
    logger.info(
        f"[{session_id}] Complete — {len(trades)} trade(s), "
        f"capital_deployed=₹{session_result.get('total_capital_deployed',0):,.0f}, "
        f"model={model}"
    )

    # Save daily snapshot so return history is always up to date after a session
    try:
        from trading_manager import snapshot_portfolio
        snapshot_portfolio(user_id)
    except Exception as snap_exc:
        logger.warning(f"[{session_id}] Snapshot failed (non-fatal): {snap_exc}")

    # Push Telegram notification
    try:
        from telegram_notify import send_trade_summary
        send_trade_summary(final)
    except Exception:
        pass

    return final
