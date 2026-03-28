"""
Backtesting Engine — replays signal logic on historical NSE data.

Uses yfinance for historical OHLCV (free, no API key needed).
Applies same risk rules and signal logic as live trading.
No lookahead bias: signals computed on day N, trade executes at day N+1 open.

Output: equity curve, trades, Sharpe ratio, max drawdown, win rate, CAGR.
"""

import logging
import math
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ── Default config ─────────────────────────────────────────────────────────────
DEFAULT_STARTING_CAPITAL = 100_000.0
DEFAULT_BROKERAGE_PCT    = 0.0003   # 0.03% per leg (Zerodha-like)
DEFAULT_STT_PCT          = 0.00025  # STT on sell side
MIN_COMPOSITE_TO_BUY     = 62       # Composite score threshold for entry signal
MIN_RSI_OVERSOLD         = 38       # RSI must be below this to qualify as oversold
MAX_HOLDING_DAYS         = 10       # Force exit if held longer than this


def _fetch_historical(ticker: str, days: int) -> list[dict]:
    """
    Fetch historical OHLCV for an NSE ticker using yfinance.
    Returns list of dicts sorted oldest-first:
    {date, open, high, low, close, volume}
    """
    try:
        import yfinance as yf
        ns_ticker = ticker if ticker.endswith(".NS") else f"{ticker}.NS"
        end   = datetime.utcnow()
        start = end - timedelta(days=days + 60)   # Extra buffer for indicator warmup
        df = yf.download(ns_ticker, start=start.strftime("%Y-%m-%d"),
                         end=end.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
        if df.empty:
            return []
        df = df.reset_index()
        records = []
        for _, row in df.iterrows():
            records.append({
                "date":   str(row["Date"])[:10],
                "open":   float(row["Open"]),
                "high":   float(row["High"]),
                "low":    float(row["Low"]),
                "close":  float(row["Close"]),
                "volume": float(row["Volume"]),
            })
        return records
    except Exception as e:
        logger.warning(f"[Backtest] yfinance fetch failed for {ticker}: {e}")
        return []


def _compute_indicators(prices: list[dict]) -> list[dict]:
    """
    Compute RSI(14), SMA(20), SMA(50), MACD on price series.
    Appends indicator fields to each price dict.
    Only valid from index 50+ (warmup period).
    """
    closes = [p["close"] for p in prices]
    n      = len(closes)

    # ── RSI(14) ──────────────────────────────────────────────────────────────
    rsi_values = [None] * n
    if n >= 15:
        gains  = [max(closes[i] - closes[i-1], 0) for i in range(1, n)]
        losses = [max(closes[i-1] - closes[i], 0) for i in range(1, n)]
        period = 14
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        rsis = []
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            rs  = avg_gain / avg_loss if avg_loss else 100
            rsi = 100 - (100 / (1 + rs))
            rsis.append(rsi)
        for i, r in enumerate(rsis):
            rsi_values[period + 1 + i] = r

    # ── SMA(20) and SMA(50) ───────────────────────────────────────────────────
    sma20 = [None] * n
    sma50 = [None] * n
    for i in range(19, n):
        sma20[i] = sum(closes[i-19:i+1]) / 20
    for i in range(49, n):
        sma50[i] = sum(closes[i-49:i+1]) / 50

    # ── MACD (12,26,9) ────────────────────────────────────────────────────────
    def ema(data, period):
        result = [None] * len(data)
        k = 2 / (period + 1)
        for i in range(period - 1, len(data)):
            if result[i-1] is None:
                result[i] = sum(data[i-period+1:i+1]) / period
            else:
                result[i] = data[i] * k + result[i-1] * (1 - k)
        return result

    ema12  = ema(closes, 12)
    ema26  = ema(closes, 26)
    macd_line = [
        (e12 - e26) if e12 is not None and e26 is not None else None
        for e12, e26 in zip(ema12, ema26)
    ]
    macd_valid   = [v for v in macd_line if v is not None]
    signal_line  = [None] * n
    if len(macd_valid) >= 9:
        sl = ema(macd_valid, 9)
        offset = next(i for i, v in enumerate(macd_line) if v is not None)
        for i, s in enumerate(sl):
            if s is not None and offset + i < n:
                signal_line[offset + i] = s

    for i, p in enumerate(prices):
        p["rsi"]         = rsi_values[i]
        p["sma20"]       = sma20[i]
        p["sma50"]       = sma50[i]
        p["macd"]        = macd_line[i]
        p["macd_signal"] = signal_line[i]

    return prices


def _compute_atr(prices: list[dict], period: int = 14) -> list[float | None]:
    """Average True Range for position sizing."""
    atrs = [None] * len(prices)
    trs  = []
    for i in range(1, len(prices)):
        high, low = prices[i]["high"], prices[i]["low"]
        prev_close = prices[i-1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
        if len(trs) >= period:
            atrs[i] = sum(trs[-period:]) / period
    return atrs


def _signal_score(p: dict) -> float:
    """
    Simplified composite signal score for backtesting (0-100).
    Uses only indicators available historically.
    """
    score = 50.0
    rsi   = p.get("rsi")
    macd  = p.get("macd")
    msig  = p.get("macd_signal")
    sma20 = p.get("sma20")
    sma50 = p.get("sma50")
    close = p["close"]

    if rsi is not None:
        if rsi < 30:      score += 25
        elif rsi < 40:    score += 15
        elif rsi > 70:    score -= 25
        elif rsi > 60:    score -= 15

    if macd is not None and msig is not None:
        if macd > msig:   score += 15
        else:             score -= 15

    if sma20 and sma50:
        if close > sma20 > sma50: score += 10
        elif close < sma20 < sma50: score -= 10

    return max(0, min(100, score))


def run_backtest(
    tickers: list[str],
    days: int = 90,
    starting_capital: float = DEFAULT_STARTING_CAPITAL,
    max_positions: int = 5,
    risk_per_trade: float = 0.015,
    max_single_stock: float = 0.20,
) -> dict:
    """
    Run a full backtest over `days` of historical data.

    Args:
        tickers:          List of NSE tickers
        days:             Backtest period in calendar days
        starting_capital: Starting portfolio value
        max_positions:    Max concurrent open positions
        risk_per_trade:   Fraction of portfolio at risk per trade
        max_single_stock: Max fraction of portfolio in one stock

    Returns a dict with:
        trades, equity_curve, metrics (CAGR, Sharpe, drawdown, win_rate)
    """
    logger.info(f"[Backtest] Starting {days}-day backtest on {len(tickers)} tickers")

    # ── Fetch and prepare data ──────────────────────────────────────────────
    all_data: dict[str, list[dict]] = {}
    for ticker in tickers:
        raw = _fetch_historical(ticker, days)
        if len(raw) >= 60:
            enriched = _compute_indicators(raw)
            atrs     = _compute_atr(enriched)
            for i, p in enumerate(enriched):
                p["atr"] = atrs[i]
            # Trim to backtest window only (drop warmup)
            cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
            all_data[ticker] = [p for p in enriched if p["date"] >= cutoff]

    if not all_data:
        return {"error": "No historical data available for provided tickers"}

    # Collect all trading days across all tickers
    all_dates = sorted(set(
        p["date"]
        for prices in all_data.values()
        for p in prices
    ))

    # ── Simulate trading day by day ─────────────────────────────────────────
    cash      = starting_capital
    positions = {}   # ticker → {entry_price, quantity, entry_date, stop_loss}
    trades    = []
    equity_curve = []

    for date_idx, today in enumerate(all_dates):
        # ── 1. Mark-to-market all open positions ──────────────────────────
        portfolio_value = cash
        for ticker, pos in list(positions.items()):
            day_data = next((p for p in all_data.get(ticker, []) if p["date"] == today), None)
            if day_data:
                portfolio_value += day_data["close"] * pos["quantity"]
            else:
                portfolio_value += pos["entry_price"] * pos["quantity"]

        equity_curve.append({"date": today, "value": round(portfolio_value, 2)})

        # ── 2. Check exits first ───────────────────────────────────────────
        for ticker in list(positions.keys()):
            pos      = positions[ticker]
            day_data = next((p for p in all_data.get(ticker, []) if p["date"] == today), None)
            if not day_data:
                continue

            cur_price = day_data["close"]
            days_held = (datetime.strptime(today, "%Y-%m-%d") -
                         datetime.strptime(pos["entry_date"], "%Y-%m-%d")).days

            # Stop-loss hit
            stop_hit = cur_price <= pos["stop_loss"]
            # Time exit (held too long)
            time_exit = days_held >= MAX_HOLDING_DAYS
            # Signal exit: score turns bearish
            score     = _signal_score(day_data)
            sig_exit  = score < 35

            if stop_hit or time_exit or sig_exit:
                exit_price = pos["stop_loss"] if stop_hit else cur_price
                proceeds   = exit_price * pos["quantity"]
                charges    = proceeds * (DEFAULT_BROKERAGE_PCT + DEFAULT_STT_PCT)
                cash      += proceeds - charges

                pnl       = (exit_price - pos["entry_price"]) * pos["quantity"] - charges
                pnl_pct   = (exit_price / pos["entry_price"] - 1) * 100

                trades.append({
                    "ticker":       ticker,
                    "entry_date":   pos["entry_date"],
                    "exit_date":    today,
                    "entry_price":  round(pos["entry_price"], 2),
                    "exit_price":   round(exit_price, 2),
                    "quantity":     pos["quantity"],
                    "pnl":          round(pnl, 2),
                    "pnl_pct":      round(pnl_pct, 2),
                    "exit_reason":  "stop_loss" if stop_hit else ("time_exit" if time_exit else "signal"),
                })
                del positions[ticker]

        # ── 3. Scan for entries (signal from today, execute at next day open) ─
        if date_idx + 1 < len(all_dates) and len(positions) < max_positions:
            next_date = all_dates[date_idx + 1]

            for ticker, price_series in all_data.items():
                if ticker in positions:
                    continue
                if len(positions) >= max_positions:
                    break

                today_data = next((p for p in price_series if p["date"] == today), None)
                next_data  = next((p for p in price_series if p["date"] == next_date), None)
                if not today_data or not next_data or today_data.get("atr") is None:
                    continue

                score = _signal_score(today_data)
                rsi   = today_data.get("rsi")

                # Entry conditions: strong signal + oversold RSI
                if score >= MIN_COMPOSITE_TO_BUY and rsi is not None and rsi < MIN_RSI_OVERSOLD:
                    entry_price = next_data["open"]
                    atr         = today_data["atr"]
                    stop_loss   = entry_price - (2 * atr)   # 2 ATR stop

                    # ATR-based position sizing
                    risk_amount    = portfolio_value * risk_per_trade
                    risk_per_share = entry_price - stop_loss
                    if risk_per_share <= 0:
                        continue

                    qty_risk   = risk_amount / risk_per_share
                    qty_cap    = (portfolio_value * max_single_stock) / entry_price
                    qty_cash   = cash / entry_price
                    quantity   = max(1, int(min(qty_risk, qty_cap, qty_cash)))
                    cost       = quantity * entry_price
                    charges    = cost * DEFAULT_BROKERAGE_PCT

                    if cost + charges > cash:
                        continue

                    cash -= (cost + charges)
                    positions[ticker] = {
                        "entry_price": entry_price,
                        "quantity":    quantity,
                        "entry_date":  next_date,
                        "stop_loss":   stop_loss,
                    }

    # ── Close any still-open positions at last available price ─────────────
    last_date = all_dates[-1] if all_dates else ""
    for ticker, pos in positions.items():
        last_data = next((p for p in all_data.get(ticker, []) if p["date"] == last_date), None)
        exit_price = last_data["close"] if last_data else pos["entry_price"]
        proceeds   = exit_price * pos["quantity"]
        charges    = proceeds * (DEFAULT_BROKERAGE_PCT + DEFAULT_STT_PCT)
        cash      += proceeds - charges
        pnl        = (exit_price - pos["entry_price"]) * pos["quantity"] - charges
        pnl_pct    = (exit_price / pos["entry_price"] - 1) * 100
        trades.append({
            "ticker":       ticker,
            "entry_date":   pos["entry_date"],
            "exit_date":    last_date,
            "entry_price":  round(pos["entry_price"], 2),
            "exit_price":   round(exit_price, 2),
            "quantity":     pos["quantity"],
            "pnl":          round(pnl, 2),
            "pnl_pct":      round(pnl_pct, 2),
            "exit_reason":  "end_of_backtest",
        })

    # ── Compute metrics ─────────────────────────────────────────────────────
    final_value = equity_curve[-1]["value"] if equity_curve else starting_capital
    total_return_pct = ((final_value - starting_capital) / starting_capital) * 100

    years = days / 365
    cagr  = ((final_value / starting_capital) ** (1 / years) - 1) * 100 if years > 0 else 0

    wins   = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    win_rate = (len(wins) / len(trades) * 100) if trades else 0

    sum_wins  = sum(t["pnl"] for t in wins)
    sum_loss  = abs(sum(t["pnl"] for t in losses))
    profit_factor = round(sum_wins / sum_loss, 2) if sum_loss else 0

    # Sharpe ratio (annualised, risk-free = 6.5% for India)
    RISK_FREE = 0.065
    daily_returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i-1]["value"]
        curr = equity_curve[i]["value"]
        if prev > 0:
            daily_returns.append((curr - prev) / prev)

    if len(daily_returns) > 1:
        avg_daily = sum(daily_returns) / len(daily_returns)
        std_daily = math.sqrt(sum((r - avg_daily) ** 2 for r in daily_returns) / len(daily_returns))
        sharpe    = ((avg_daily * 252) - RISK_FREE) / (std_daily * math.sqrt(252)) if std_daily else 0
    else:
        sharpe = 0

    # Max drawdown
    peak     = starting_capital
    max_dd   = 0
    for e in equity_curve:
        if e["value"] > peak:
            peak = e["value"]
        dd = (peak - e["value"]) / peak if peak else 0
        if dd > max_dd:
            max_dd = dd

    logger.info(
        f"[Backtest] Done — {len(trades)} trades, "
        f"return={total_return_pct:.1f}%, CAGR={cagr:.1f}%, "
        f"Sharpe={sharpe:.2f}, MaxDD={max_dd*100:.1f}%, WinRate={win_rate:.0f}%"
    )

    return {
        "config": {
            "tickers":          tickers,
            "days":             days,
            "starting_capital": starting_capital,
        },
        "metrics": {
            "total_return_pct": round(total_return_pct, 2),
            "cagr_pct":         round(cagr, 2),
            "sharpe_ratio":     round(sharpe, 2),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "win_rate_pct":     round(win_rate, 1),
            "profit_factor":    profit_factor,
            "total_trades":     len(trades),
            "winning_trades":   len(wins),
            "losing_trades":    len(losses),
            "final_value":      round(final_value, 2),
            "avg_pnl_pct":      round(sum(t["pnl_pct"] for t in trades) / len(trades), 2) if trades else 0,
        },
        "trades":       trades,
        "equity_curve": equity_curve,
    }
