"""
Agentic Trader — autonomous Claude tool-use loop for paper/live trading.

The agent scans for market opportunities (ETF arbitrage, pairs divergence,
mean reversion), reasons about risk/reward, sizes positions, and executes
paper trades autonomously.

Hard limits (enforced by RiskGate.check_all on every BUY, non-negotiable):
  - Max 20% of portfolio in any single stock
  - Max 5   concurrent open positions
  - Max 5%  daily loss before HOLD-only auto-halt
  - Paper mode unless live trading is enabled + broker connected

The model is provider-agnostic (see llm_client): Gemini by default, with
Anthropic/OpenAI as configurable alternatives.

Architecture mirrors proactive_agent.py and agentic_forecaster.py.
"""

import logging
from datetime import datetime, date

logger = logging.getLogger(__name__)

# ── Loop config ───────────────────────────────────────────────────────────────
MAX_ITERATIONS  = 12

# ── Hard risk limits (the authoritative values live in RiskGate; these mirror
#    them for prompt display + sizing). max_position_size_inr shown to the model
#    reflects RiskGate's single-stock cap so the two never disagree. ───────────
MAX_POSITION_PCT   = 0.20   # 20% single-stock cap — matches RiskGate.max_single_stock_pct
MAX_OPEN_POSITIONS = 5
MAX_DAILY_LOSS_PCT = 0.05   # 5% daily loss triggers HOLD-only mode

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are Arjun, a senior proprietary trader with 12 years of experience on NSE/BSE.
You have traded through multiple market cycles — the 2008 crash, 2020 COVID collapse, and the 2021 bull run.
You manage a paper portfolio for a client and your job is to grow it consistently, not just avoid losses.

YOUR TRADING PHILOSOPHY:
- The market is always right. Your opinion means nothing — price action and data are everything.
- Cut losses fast, let winners run. A bad trade held too long kills more portfolios than bad entries.
- Cash is a position. Sitting out is sometimes the best trade.
- Never fall in love with a thesis. If the trade isn't working after a reasonable time, exit — the market
  is telling you something your model missed.
- ETF discounts in India can persist for months when liquidity is low — don't hold an arb that isn't closing.
- Oversold doesn't mean buy. A stock in a downtrend can stay oversold. Wait for a reversal signal.
- Size up when conviction is high, size down when uncertain. Don't treat every trade equally.

WORKFLOW (execute in this order every session):
1. scan_opportunities      — see what the market is offering right now
2. get_portfolio_state     — know your book: capital, open positions, live P&L, days held
3. execute_trade (SELL)    — manage exits FIRST before looking at new trades
4. analyse_opportunity     — deep-dive on the 1-3 best setups if you have open slots
5. calculate_position_size — size based on conviction and available capital
6. execute_trade (BUY)     — only pull the trigger on high-conviction setups
7. submit_session_summary  — honest debrief: what you did, why, what you're watching

HOW TO MANAGE EXITS (use your judgement, not rigid rules):
- If a trade thesis is broken (ETF discount widening instead of closing, pairs diverging further),
  EXIT — don't wait for a hard stop. Thesis failure IS the exit signal.
- If a position has been held more than 5 trading days with no meaningful move toward the target, EXIT.
  The opportunity cost of dead capital is real.
- If a stock gets hit by genuine bad news (not noise), EXIT before sentiment worsens.
- Take partial profits (50%) when a position is up meaningfully — let the rest run with a trailing stop.
- Hard floor: never let any single position lose more than 5% of its entry value. This is non-negotiable.

HOW TO ENTER (think like a professional):
- Ask yourself: "Would I put my own money in this right now?" If the answer is hesitant, skip it.
- Confirm with at least 2 independent signals (e.g., RSI + volume + news + z-score).
- Every entry needs a clear exit plan — target price, stop-loss, and time limit — before you buy.
- In a weak market, prefer mean-reversion (ETF arb, pairs) over directional bets.
- In a strong market, ride momentum — don't fight the tape.
- Always cite your numbers: price, spread %, z-score, RSI, expected ₹ P&L.

SIGNAL ENGINE (new — use analyse_opportunity to see these):
- Composite signal score 0-100 combining: FII/DII flows (25%), F&O PCR (20%), Technicals (20%), Delivery % (15%), News (20%)
- Score > 65 = bullish setup, Score < 35 = avoid, Score 45-65 = neutral/watch
- FII/DII flow is the single most important signal for Indian equities
- Data quality "low" = fewer than 3 signals available = reduce conviction

RISK GATE (enforced automatically on every BUY — no exceptions):
- Max 1.5% portfolio at risk per trade (ATR-based stop sizing)
- Max 20% portfolio in any single stock
- Max 60% total portfolio deployed simultaneously
- Max 5 open positions
- No new longs if daily loss > 5% or drawdown > 15%
- No entry if India VIX > 25 or FII selling > ₹2000cr
- 3 consecutive losses → HOLD-only mode
- Minimum confidence 0.70 required — set it honestly

Be honest in your session summary. If you didn't trade, explain exactly why. If you made a mistake, say so.
A good trader learns from every session — profitable or not."""

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
            "Get current paper trading state: available capital, open positions with "
            "live prices, unrealised P&L per position, days held, and max allowed "
            "position size. Positions with should_review=true have been held 5+ days."
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
        "description": "Execute a paper trade. All BUY orders pass through RiskGate — hard rules enforced automatically. Returns order confirmation or rejection reason.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker":     {"type": "string"},
                "side":       {"type": "string", "enum": ["BUY", "SELL"]},
                "quantity":   {"type": "integer", "minimum": 1},
                "order_type": {"type": "string", "enum": ["MARKET"]},
                "price":      {"type": "number", "description": "Entry price (INR)"},
                "stop_loss":  {"type": "number", "description": "Stop-loss price — must be at a meaningful technical level, not arbitrary"},
                "confidence": {"type": "number", "description": "Your confidence 0.0-1.0. Below 0.70 will be blocked by RiskGate."},
                "reasoning":  {"type": "string", "description": "2-3 sentences: what signals aligned, why now, what is the exit plan"},
            },
            "required": ["ticker", "side", "quantity", "order_type", "reasoning", "confidence"],
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
            from broker_manager import get_portfolio_state as bm_portfolio_state
            pstate = bm_portfolio_state(user_id)

            # Live broker: holdings already carry real avg/ltp/pnl from the broker.
            if pstate["mode"] == "live":
                enriched = []
                for h in pstate["holdings"]:
                    avg_buy   = float(h.get("avg_buy_price") or 0)
                    qty       = float(h.get("quantity") or 0)
                    cur_price = float(h.get("current_price") or avg_buy)
                    enriched.append({
                        "ticker":           h.get("ticker"),
                        "quantity":         qty,
                        "avg_buy_price":    avg_buy,
                        "current_price":    cur_price,
                        "total_investment": h.get("total_investment"),
                        "unrealised_pnl":   round((cur_price - avg_buy) * qty, 2),
                        "pnl_pct":          round((cur_price / avg_buy - 1) * 100, 2) if avg_buy > 0 else 0,
                        "days_held":        None,          # not tracked by broker holdings
                        "should_review":    False,
                    })
                avail = float(pstate["balance"])
                total = float(pstate["total_value"])
                return {
                    "mode":                  "live",
                    "broker":                pstate["broker"],
                    "available_capital":     round(avail, 2),
                    "total_portfolio_value": round(total, 2),
                    "open_positions":        len(enriched),
                    "max_position_size_inr": round(total * MAX_POSITION_PCT, 2),
                    "positions":             enriched,
                }

            # Paper mode: enrich with live prices + position ages as before.
            from trading_manager import get_trading_balance, get_trading_portfolio, get_position_ages
            from stock_data import get_bulk_prices
            balance  = get_trading_balance(user_id) or {}
            holdings = get_trading_portfolio(user_id) or []
            try:
                prices = get_bulk_prices([h["ticker"] for h in holdings]) if holdings else {}
            except Exception:
                prices = {}
            try:
                ages = get_position_ages(user_id) if holdings else {}
            except Exception:
                ages = {}

            enriched = []
            for h in holdings:
                ticker    = h.get("ticker")
                avg_buy   = float(h.get("avg_buy_price") or 0)
                qty       = float(h.get("quantity") or 0)
                cur_price = float(prices.get(ticker) or avg_buy)
                unreal    = round((cur_price - avg_buy) * qty, 2)
                pnl_pct   = round((cur_price / avg_buy - 1) * 100, 2) if avg_buy > 0 else 0
                days_held = ages.get(ticker, 0)
                enriched.append({
                    "ticker":           ticker,
                    "quantity":         qty,
                    "avg_buy_price":    avg_buy,
                    "current_price":    cur_price,
                    "total_investment": h.get("total_investment"),
                    "unrealised_pnl":   unreal,
                    "pnl_pct":          pnl_pct,
                    "days_held":        days_held,
                    "should_review":    days_held >= 5,
                })

            market_value = sum(p["current_price"] * p["quantity"] for p in enriched)
            avail        = float(balance.get("balance") or 0)
            total        = avail + market_value

            return {
                "mode":                  "paper",
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
            from signal_engine import score_stock, format_scores_for_prompt

            # 15-minute cache — avoid re-fetching the same ticker multiple times
            # per session and across concurrent user sessions
            import hashlib, json as _json
            _cache_key = f"stockeye:analysis:{ticker}"
            _cached_raw = None
            try:
                from cache import _get_redis
                _r = _get_redis()
                if _r:
                    _cached_raw = _r.get(_cache_key)
            except Exception:
                pass
            if _cached_raw:
                return _json.loads(_cached_raw)

            price_data = get_stock_price(ticker) or {}
            tech       = calculate_technical_indicators(ticker, period="3mo") or {}
            articles   = fetch_stock_news(ticker, days=3, max_articles=5)
            pos = sum(1 for a in articles if a.get("sentiment") == "positive")
            neg = sum(1 for a in articles if a.get("sentiment") == "negative")

            # India-specific signal scoring
            signal_result = score_stock(ticker)
            signal_block  = format_scores_for_prompt(signal_result)

            # Deep analysis: use the deep model tier via the model-agnostic layer.
            deep_reasoning = ""
            try:
                analysis_prompt = f"""You are a senior NSE/BSE trader doing a deep analysis before committing capital.

{signal_block}

Price: ₹{price_data.get('current_price', 'N/A')}
Day change: {price_data.get('day_change_pct', 'N/A')}%
RSI: {tech.get('rsi', 'N/A')} | MACD: {tech.get('macd', 'N/A')} (signal {tech.get('macd_signal', 'N/A')})
SMA-20: {tech.get('sma_20', 'N/A')} | SMA-50: {tech.get('sma_50', 'N/A')}
Bollinger: upper {tech.get('bb_upper', 'N/A')} / mid {tech.get('bb_middle', 'N/A')} / lower {tech.get('bb_lower', 'N/A')}
News: {pos} positive, {neg} negative articles (last 3 days)

Answer these 4 questions:
1. Are the signals genuinely aligned or is this noise?
2. What could go wrong? What's the asymmetric downside?
3. What is the ideal entry, stop-loss (below technical support), and target (min 2:1 R:R)?
4. Final verdict: BUY / WATCH / AVOID — and confidence 0-100.

Be skeptical. A great setup missed is better than a bad trade taken."""

                import llm_client
                deep_reasoning = llm_client.generate_text(
                    prompt=analysis_prompt, deep=True, temperature=0.2, max_tokens=1500,
                ) or "(Deep analysis unavailable)"
            except Exception as _e:
                logger.warning(f"[AutoTrader] Deep analysis failed for {ticker}: {_e}")
                deep_reasoning = "(Deep analysis unavailable)"

            _result = {
                "ticker":            ticker,
                "current_price":     price_data.get("current_price"),
                "day_change_pct":    price_data.get("day_change_pct"),
                "volume_ratio":      tech.get("volume_ratio"),
                "rsi":               tech.get("rsi"),
                "macd":              tech.get("macd"),
                "macd_signal":       tech.get("macd_signal"),
                "sma_20":            tech.get("sma_20"),
                "sma_50":            tech.get("sma_50"),
                "bollinger":         {"upper": tech.get("bb_upper"),
                                      "middle": tech.get("bb_middle"),
                                      "lower": tech.get("bb_lower")},
                "news_positive":     pos,
                "news_negative":     neg,
                "tech_signals":      tech.get("signals"),
                "composite_score":   signal_result["composite_score"],
                "signal_scores":     signal_result["scores"],
                "market_data":       signal_result["market_data"],
                "data_quality":      signal_result["data_quality"],
                "deep_analysis":     deep_reasoning,
            }
            # Cache for 15 minutes so repeated calls (same ticker, same session)
            # and concurrent user sessions don't re-hit the API
            try:
                from cache import _get_redis
                _r = _get_redis()
                if _r:
                    _r.setex(_cache_key, 900, _json.dumps(_result, default=str))
            except Exception:
                pass
            return _result

        # ── calculate_position_size ───────────────────────────────────────────
        elif name == "calculate_position_size":
            from trading_manager import get_trading_balance, get_trading_portfolio
            from risk_gate import risk_gate

            entry  = float(inputs.get("entry_price") or 0)
            stop   = float(inputs.get("stop_loss")   or 0)
            ticker = inputs.get("ticker", "")

            if entry <= 0:
                return {"error": "entry_price must be > 0"}

            balance_row = get_trading_balance(user_id) or {}
            holdings    = get_trading_portfolio(user_id) or []
            invested    = sum(float(h.get("total_investment") or 0) for h in holdings)
            total_val   = float(balance_row.get("balance") or 100_000) + invested
            avail       = float(balance_row.get("balance") or 100_000)

            # Budget mode: cap available cash to session budget
            if budget is not None:
                avail = min(float(budget), avail)

            return risk_gate.calculate_position_size(
                ticker          = ticker,
                entry_price     = entry,
                stop_loss       = stop,
                portfolio_value = total_val,
                available_cash  = avail,
                user_id         = user_id,
            )

        # ── execute_trade ─────────────────────────────────────────────────────
        elif name == "execute_trade":
            from trading_manager import place_order
            from risk_gate import risk_gate
            from signal_engine import score_stock
            from broker_manager import get_portfolio_state

            # Unified view: real broker holdings/cash when live, paper otherwise.
            pstate        = get_portfolio_state(user_id)
            live_mode     = pstate["mode"] == "live"
            holdings      = pstate["holdings"]
            held_tickers  = {h["ticker"] for h in holdings}
            avail_balance = float(pstate["balance"] or 0)

            # Normalize the ticker ONCE — strip exchange suffixes so live orders
            # send a clean NSE tradingsymbol to the broker (Kite rejects TCS.NS).
            ticker     = inputs.get("ticker", "").upper().replace(".NS", "").replace(".BO", "")
            side       = inputs.get("side", "BUY").upper()
            quantity   = int(inputs.get("quantity") or 1)
            order_type = "MARKET"  # paper trading always executes immediately
            stop_loss  = inputs.get("stop_loss")

            if not ticker:
                return {"error": "ticker is required"}

            # No-rebuy guard
            if side == "BUY" and ticker in held_tickers:
                return {"error": f"Already holding {ticker} — sell first or pick a different stock"}

            # Resolve the execution price BEFORE any risk check. RiskGate's rupee
            # rules (single-stock %, portfolio heat, capital) are meaningless at
            # price 0, so we must never run them on an unpriced order.
            price = float(inputs.get("price") or 0)
            if not price:
                from stock_data import get_stock_price
                p = get_stock_price(ticker) or {}
                price = float(p.get("current_price") or 0)
            if not price:
                return {"error": f"Could not determine price for {ticker}"}

            # RiskGate check (BUY only) — now with a real, non-zero entry price
            if side == "BUY":
                portfolio_ctx = risk_gate.build_portfolio_context(user_id)

                # Fetch market data for risk checks
                signal_result  = score_stock(ticker)
                from stock_data import get_liquidity_and_earnings
                liquidity      = get_liquidity_and_earnings(ticker)
                market_data    = {
                    **signal_result.get("market_data", {}),
                    "avg_daily_volume_cr": liquidity.get("avg_daily_volume_cr"),
                    "days_to_earnings":    liquidity.get("days_to_earnings"),
                }

                gate_passed, gate_failures = risk_gate.check_all(
                    ticker      = ticker,
                    side        = side,
                    quantity    = quantity,
                    entry_price = price,
                    portfolio   = portfolio_ctx,
                    market_data = market_data,
                    confidence  = float(inputs.get("confidence", 0.75)),
                    user_id     = user_id,
                )
                if not gate_passed:
                    return {
                        "error":         "RiskGate blocked this trade",
                        "rule_failures": gate_failures,
                    }

            # Capital check for buys (broker cash when live, paper cash otherwise)
            if side == "BUY" and price * quantity > avail_balance:
                return {
                    "error": (
                        f"Insufficient capital: need ₹{price*quantity:,.0f}, "
                        f"available ₹{avail_balance:,.0f}"
                    )
                }

            # ── LIVE: propose for approval instead of executing ──────────────────
            # Nothing reaches the broker here. The order is queued and only placed
            # once the user approves it (web or Telegram).
            if live_mode:
                from proposal_store import check_rupee_caps, create_proposal
                ok, reason = check_rupee_caps(user_id, side, price * quantity)
                if not ok:
                    return {"error": reason, "cap_block": True}
                proposal_id = create_proposal(
                    user_id, ticker=ticker, side=side, quantity=quantity,
                    order_type=order_type, price=price,
                    stop_loss=float(stop_loss) if stop_loss else None,
                    confidence=float(inputs.get("confidence", 0.75)),
                    reasoning=inputs.get("reasoning", ""),
                    risk_gate_result={"passed": True}, session_id=session_id,
                )
                try:
                    from telegram_notify import notify_proposal
                    notify_proposal(user_id, proposal_id, ticker, side, quantity, price,
                                    inputs.get("reasoning", ""))
                except Exception:
                    pass
                logger.info(
                    f"[AutoTrader:{session_id}] PROPOSED {side} {quantity}x{ticker} "
                    f"@ ₹{price:.2f} (proposal {proposal_id}, awaiting approval)"
                )
                return {
                    "proposed":        True,
                    "proposal_id":     proposal_id,
                    "status":          "AWAITING_APPROVAL",
                    "ticker":          ticker,
                    "side":            side,
                    "quantity":        quantity,
                    "execution_price": round(price, 2),
                    "total_value":     round(quantity * price, 2),
                    "reasoning":       inputs.get("reasoning", ""),
                    "note": "Live order requires your approval (web or Telegram) before it reaches the broker.",
                }

            # ── PAPER: execute immediately (unchanged behavior) ──────────────────
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

            # Post-trade verification: read back order to confirm DB state
            from trading_manager import get_order_by_id
            verified_order = get_order_by_id(user_id, order_id)
            verified = bool(
                verified_order
                and verified_order.get("status") == "EXECUTED"
                and float(verified_order.get("executed_quantity") or 0) == quantity
            )
            if not verified:
                logger.warning(
                    f"[AutoTrader:{session_id}] Post-trade verification FAILED for "
                    f"order {order_id} — DB state may be inconsistent"
                )

            # Publish to shared intelligence bus
            try:
                from shared_context import signal_from_trade
                signal_from_trade(user_id, ticker, side, quantity, price,
                                  reasoning=inputs.get("reasoning", ""))
            except Exception:
                pass

            logger.info(
                f"[AutoTrader:{session_id}] {side} {quantity}x{ticker} @ ₹{price:.2f} "
                f"{'✓' if verified else '⚠ UNVERIFIED'} | "
                f"{inputs.get('reasoning','')[:120]}"
            )

            # Capture signal scores at time of execution for track record
            try:
                _signal = score_stock(ticker)
                trade_signal_scores = _signal.get("scores", {})
                composite_at_entry  = _signal.get("composite_score")
            except Exception:
                trade_signal_scores = {}
                composite_at_entry  = None

            return {
                "success":             True,
                "verified":            verified,
                "order_id":            order_id,
                "status":              "EXECUTED" if order_type == "MARKET" else "PENDING",
                "ticker":              ticker,
                "side":                side,
                "quantity":            quantity,
                "execution_price":     round(price, 2),
                "total_value":         round(quantity * price, 2),
                "signal_scores":       trade_signal_scores,
                "composite_score":     composite_at_entry,
                "stop_loss":           stop_loss,
                "reasoning":           inputs.get("reasoning", ""),
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
_SESSION_LOCK_TTL = 900   # seconds — max time a session can hold the lock before auto-expiry


def _acquire_session_lock(user_id: str) -> bool:
    """Try to acquire a Redis-backed session lock. Returns True if acquired."""
    try:
        from cache import _get_redis
        r = _get_redis()
        if r:
            key = f"session_lock:{user_id}"
            return bool(r.set(key, "1", nx=True, ex=_SESSION_LOCK_TTL))
    except Exception:
        pass
    # Redis unavailable — fall back to in-memory check
    session = _active_sessions.get(user_id)
    return not (session and session.get("status") == "running")


def _release_session_lock(user_id: str) -> None:
    try:
        from cache import _get_redis
        r = _get_redis()
        if r:
            r.delete(f"session_lock:{user_id}")
    except Exception:
        pass


def run_trading_session(user_id: str, tickers: list | None = None,
                        budget: float | None = None,
                        notify: bool = True) -> dict | None:
    """
    Run one autonomous paper-trading session for a user.

    Args:
        budget: Optional cap on capital to deploy in this session (INR).
                If None, the full available balance is usable.

    Returns a structured session summary dict, {"already_running": True} if
    another session is active, or None on failure.
    """
    import llm_client
    from trading_manager import get_trading_balance

    if not _acquire_session_lock(user_id):
        logger.info(f"[{user_id[:8]}] Session already running — skipping duplicate.")
        return {"already_running": True, "trades": [], "reasoning": "A session is already in progress."}

    session_id = f"trade-{user_id[:8]}-{datetime.now().strftime('%H%M%S')}"
    _active_sessions[user_id] = {"session_id": session_id, "status": "running", "user_id": user_id}

    # try/finally guarantees the Redis session lock is released even if the loop
    # raises — otherwise a crash would wedge the user out for the full 900s TTL.
    try:
        if not llm_client.is_available():
            logger.error("No LLM provider configured — agentic trader unavailable")
            return None

        # Determine usable capital for this session
        balance_row    = get_trading_balance(user_id) or {}
        available      = float(balance_row.get('balance') or 0)
        usable_capital = min(float(budget), available) if budget is not None else available

        trades  = []

        per_slot = usable_capital / MAX_OPEN_POSITIONS if budget is not None else 0
        budget_note = (
            f"BUDGET FOR THIS SESSION: ₹{usable_capital:,.2f} split across up to {MAX_OPEN_POSITIONS} positions "
            f"(≈₹{per_slot:,.0f} per stock). "
            f"AIM TO FILL ALL {MAX_OPEN_POSITIONS} SLOTS — scan broadly and pick the best {MAX_OPEN_POSITIONS} opportunities. "
            f"Do not stop at 1 trade if more opportunities exist. "
            f"Your available cash is ₹{available:,.2f}. "
        ) if budget is not None else ""

        # Market regime — shapes the entire session strategy
        try:
            from signal_engine import get_market_regime
            regime_data  = get_market_regime()
            regime_block = (
                f"MARKET REGIME: {regime_data['regime']} | "
                f"{regime_data.get('strategy_note', '')} | "
                f"Reasons: {'; '.join(regime_data.get('reasons', []))}"
            )
        except Exception:
            regime_block = ""

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

        user_prompt = (
            f"Run a paper trading session. Today: {date.today().isoformat()}. "
            f"{regime_block} "
            f"{budget_note}"
            f"{win_rate_note}"
            f"{intel_block}"
            f"Follow the workflow: first check portfolio state, apply exit rules to "
            f"open positions, then scan and execute 1-2 high-conviction new trades. "
            f"Prioritise tickers flagged as bullish in the platform intelligence above. "
            f"Avoid tickers flagged as bearish unless the reversal case is very clear. "
            f"Only trade if risk/reward ≥ 1.5."
        )

        # Record executed paper trades AND queued live proposals as session activity.
        def _track(name, args, result):
            if name == "execute_trade" and (result.get("success") or result.get("proposed")):
                trades.append(result)
                _active_sessions[user_id]["trades"] = trades

        loop = llm_client.run_agent_loop(
            system=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            tools=TRADING_TOOLS,
            dispatch=lambda name, inp: _execute_tool(
                name, inp, user_id, session_id, user_tickers=tickers, budget=budget),
            terminal_tools={"submit_session_summary"},
            max_iterations=MAX_ITERATIONS,
            temperature=0.1,
            max_tokens=4096,
            force_terminal_at=7,
            force_terminal_message=(
                "You have gathered sufficient data. "
                "Call submit_session_summary NOW with your final report."
            ),
            on_tool_result=_track,
        )

        session_result = loop.get("terminal_result")
        model = loop.get("model")

        # Fallback summary if the model never called submit_session_summary
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

        # Push Telegram notification (skip when caller handles its own reply)
        if notify:
            try:
                from telegram_notify import send_trade_summary
                send_trade_summary(final)
            except Exception:
                pass

        return final
    finally:
        _release_session_lock(user_id)
        if _active_sessions.get(user_id, {}).get("status") == "running":
            _active_sessions[user_id]["status"] = "error"
