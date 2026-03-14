"""
Arbitrage and statistical opportunity detector for Indian markets (NSE/BSE).

Detects:
1. ETF vs estimated NAV divergence  (GOLDBEES, NIFTYBEES, BANKBEES …)
2. Statistical pairs divergence     (TCS/INFY, HDFCBANK/ICICIBANK …)
3. Bollinger Band extremes          (mean-reversion plays on any watchlist ticker)
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)

# ── ETF mappings ──────────────────────────────────────────────────────────────
# expense_ratio is annual; we use it to adjust NAV estimate slightly
ETF_MAPPINGS = {
    "GOLDBEES":   {"underlying": "GC=F",     "type": "commodity", "expense_ratio": 0.0059, "units_per_gram": 0.01},
    "NIFTYBEES":  {"underlying": "^NSEI",    "type": "index",     "expense_ratio": 0.0004, "divisor": 100},
    "BANKBEES":   {"underlying": "^NSEBANK", "type": "index",     "expense_ratio": 0.0019, "divisor": 100},
    "ITBEES":     {"underlying": "^CNXIT",   "type": "index",     "expense_ratio": 0.0019, "divisor": 100},
    "SILVERBEES": {"underlying": "SI=F",     "type": "commodity", "expense_ratio": 0.0040, "units_per_gram": 0.01},
}


ETF_DIVERGENCE_THRESHOLD = 0.30   # % — minimum premium/discount to flag
PAIRS_Z_THRESHOLD        = 1.5    # standard deviations (was 2.0 — too strict for daily scans)
BB_EXTREME_THRESHOLD     = 0.85   # band position (was 0.95 — near band edge, not past it)


# ─────────────────────────────────────────────────────────────────────────────
# 1. ETF NAV Divergence
# ─────────────────────────────────────────────────────────────────────────────
def detect_etf_nav_divergence(etf_ticker: str) -> dict | None:
    """
    Compare live ETF price vs estimated NAV.
    Returns an opportunity dict if |premium| > ETF_DIVERGENCE_THRESHOLD %.
    """
    try:
        import yfinance as yf
        from stock_data import get_stock_price

        mapping = ETF_MAPPINGS.get(etf_ticker.upper())
        if not mapping:
            return None

        etf_data = get_stock_price(etf_ticker)
        if not etf_data or not etf_data.get("current_price"):
            return None
        etf_price = float(etf_data["current_price"])

        # Fetch underlying price via yfinance
        underlying = yf.Ticker(mapping["underlying"])
        hist = underlying.history(period="1d", interval="5m")
        if hist.empty:
            return None
        underlying_price = float(hist["Close"].iloc[-1])

        # Compute NAV estimate
        if mapping["type"] == "commodity":
            # GOLDBEES / SILVERBEES: price is in USD/oz, convert to INR/unit
            try:
                fx_hist = yf.Ticker("USDINR=X").history(period="1d", interval="5m")
                fx_rate = float(fx_hist["Close"].iloc[-1]) if not fx_hist.empty else 84.0
            except Exception:
                fx_rate = 84.0
            # 1 troy oz ≈ 31.1g; GOLDBEES ≈ 0.01g gold per unit
            grams_per_unit = mapping.get("units_per_gram", 0.01)
            nav_estimate = underlying_price * fx_rate / 31.1 * grams_per_unit
        else:
            # Index ETFs: NAV ≈ index / divisor
            nav_estimate = underlying_price / mapping.get("divisor", 100)

        if nav_estimate <= 0:
            return None

        premium_pct = (etf_price - nav_estimate) / nav_estimate * 100

        if abs(premium_pct) < ETF_DIVERGENCE_THRESHOLD:
            return None

        direction     = "PREMIUM" if premium_pct > 0 else "DISCOUNT"
        trade_action  = "SELL" if premium_pct > 0 else "BUY"
        net_profit    = round(abs(premium_pct) - 0.15, 3)   # minus estimated txn cost

        return {
            "type":               "ETF_NAV_DIVERGENCE",
            "ticker":             etf_ticker,
            "etf_price":          round(etf_price, 2),
            "nav_estimate":       round(nav_estimate, 2),
            "premium_pct":        round(premium_pct, 3),
            "direction":          direction,
            "recommended_action": trade_action,
            "expected_profit_pct": max(0, net_profit),
            "confidence":         round(min(0.90, abs(premium_pct) / 1.5 * 0.7 + 0.3), 2),
            "reasoning": (
                f"{etf_ticker} trading at {abs(premium_pct):.2f}% {direction.lower()} "
                f"vs NAV ₹{nav_estimate:.2f} (ETF price ₹{etf_price:.2f}). "
                f"Mean-reversion trade: {trade_action} {etf_ticker}."
            ),
        }

    except Exception as exc:
        logger.debug(f"ETF NAV check failed for {etf_ticker}: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Statistical Pairs Divergence
# ─────────────────────────────────────────────────────────────────────────────
def detect_pairs_divergence(ticker1: str, ticker2: str,
                             label: str = "", lookback: int = 60) -> dict | None:
    """
    Z-score of price ratio spread between two correlated stocks.
    |z| > PAIRS_Z_THRESHOLD → flags a mean-reversion trade.
    """
    try:
        from stock_data import get_historical_data

        h1 = get_historical_data(ticker1, period="3mo", interval="1d")
        h2 = get_historical_data(ticker2, period="3mo", interval="1d")
        if not h1 or not h2 or len(h1) < 20 or len(h2) < 20:
            return None

        p1 = np.array([bar["close"] for bar in h1[-lookback:]], dtype=float)
        p2 = np.array([bar["close"] for bar in h2[-lookback:]], dtype=float)
        n  = min(len(p1), len(p2))
        p1, p2 = p1[-n:], p2[-n:]

        spread     = p1 / p2
        mean       = float(np.mean(spread))
        std        = float(np.std(spread))
        if std == 0:
            return None

        z = float((spread[-1] - mean) / std)
        if abs(z) < PAIRS_Z_THRESHOLD:
            return None

        # High z → ticker1 expensive relative to ticker2 → short t1 / long t2
        if z > 0:
            action, long_leg, short_leg = f"BUY {ticker2} / SELL {ticker1}", ticker2, ticker1
        else:
            action, long_leg, short_leg = f"BUY {ticker1} / SELL {ticker2}", ticker1, ticker2

        expected_pct = round(abs(z) * std / mean * 50, 2)
        confidence   = round(min(0.85, 0.55 + (abs(z) - 2.0) / 4.0), 2)

        return {
            "type":               "PAIRS_DIVERGENCE",
            "ticker":             f"{ticker1}/{ticker2}",
            "ticker1":            ticker1,
            "ticker2":            ticker2,
            "label":              label,
            "long_leg":           long_leg,
            "short_leg":          short_leg,
            "z_score":            round(z, 2),
            "spread_mean":        round(mean, 4),
            "current_spread":     round(float(spread[-1]), 4),
            "recommended_action": action,
            "expected_profit_pct": expected_pct,
            "confidence":         confidence,
            "reasoning": (
                f"{ticker1}/{ticker2} z-score at {z:.2f}σ "
                f"(mean: {mean:.4f}, now: {spread[-1]:.4f}). "
                f"Mean-reversion: {action}."
            ),
        }

    except Exception as exc:
        logger.debug(f"Pairs divergence failed {ticker1}/{ticker2}: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Bollinger Band Extremes
# ─────────────────────────────────────────────────────────────────────────────
def detect_bollinger_extreme(ticker: str) -> dict | None:
    """
    Flags stocks at Bollinger Band extremes (>2σ outside bands) for
    mean-reversion plays.
    """
    try:
        from stock_data import calculate_technical_indicators

        ind = calculate_technical_indicators(ticker, period="3mo")
        if not ind or ind.get("error"):
            return None

        bb     = ind.get("bollinger_bands", {})
        price  = float(ind.get("current_price") or ind.get("close") or 0)
        upper  = float(bb.get("upper") or 0)
        lower  = float(bb.get("lower") or 0)
        middle = float(bb.get("middle") or 0)

        if not all([price, upper, lower, middle]) or (upper - lower) == 0:
            return None

        band_width = upper - lower
        position   = (price - lower) / band_width   # 0 = at lower, 1 = at upper

        if position >= BB_EXTREME_THRESHOLD:
            return {
                "type":               "BOLLINGER_EXTREME",
                "ticker":             ticker,
                "direction":          "OVERBOUGHT",
                "recommended_action": "SELL",
                "price":              round(price, 2),
                "upper_band":         round(upper, 2),
                "lower_band":         round(lower, 2),
                "middle_band":        round(middle, 2),
                "band_position_pct":  round(position * 100, 1),
                "expected_profit_pct": round((price - middle) / price * 100, 2),
                "confidence":         round(min(0.80, 0.50 + (position - 0.95) * 6), 2),
                "reasoning": (
                    f"{ticker} at {position*100:.0f}% of Bollinger Band — "
                    f"price ₹{price:.2f} above upper band ₹{upper:.2f}. "
                    f"Mean reversion target: ₹{middle:.2f} ({((middle-price)/price*100):+.2f}%)."
                ),
            }

        if position <= (1 - BB_EXTREME_THRESHOLD):
            return {
                "type":               "BOLLINGER_EXTREME",
                "ticker":             ticker,
                "direction":          "OVERSOLD",
                "recommended_action": "BUY",
                "price":              round(price, 2),
                "upper_band":         round(upper, 2),
                "lower_band":         round(lower, 2),
                "middle_band":        round(middle, 2),
                "band_position_pct":  round(position * 100, 1),
                "expected_profit_pct": round((middle - price) / price * 100, 2),
                "confidence":         round(min(0.80, 0.50 + (0.05 - position) * 6), 2),
                "reasoning": (
                    f"{ticker} at {position*100:.0f}% of Bollinger Band — "
                    f"price ₹{price:.2f} below lower band ₹{lower:.2f}. "
                    f"Mean reversion target: ₹{middle:.2f} ({((middle-price)/price*100):+.2f}%)."
                ),
            }

        return None

    except Exception as exc:
        logger.debug(f"Bollinger extreme failed for {ticker}: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Dynamic correlation finder
# ─────────────────────────────────────────────────────────────────────────────
def find_correlated_pairs(tickers: list, min_correlation: float = 0.60) -> list:
    """
    From a list of tickers, find all pairs with Pearson correlation ≥ min_correlation.
    Returns list of (ticker1, ticker2, correlation) sorted by correlation desc.
    """
    from stock_data import get_historical_data
    from itertools import combinations

    # Fetch 3-month daily closes for all tickers
    price_series = {}
    for t in tickers:
        hist = get_historical_data(t, period="3mo", interval="1d")
        if hist and len(hist) >= 20:
            price_series[t] = np.array([bar["close"] for bar in hist], dtype=float)

    pairs = []
    for t1, t2 in combinations(price_series.keys(), 2):
        p1, p2 = price_series[t1], price_series[t2]
        n = min(len(p1), len(p2))
        if n < 20:
            continue
        corr = float(np.corrcoef(p1[-n:], p2[-n:])[0, 1])
        if corr >= min_correlation:
            pairs.append((t1, t2, round(corr, 3)))

    pairs.sort(key=lambda x: x[2], reverse=True)
    return pairs


# ─────────────────────────────────────────────────────────────────────────────
# Full scan
# ─────────────────────────────────────────────────────────────────────────────
def scan_opportunities(tickers: list) -> list:
    """
    Run all three detectors on user-chosen tickers.

    Args:
        tickers: any list of NSE tickers the user wants to scan
    """
    opportunities = []
    ticker_set = [t.upper().replace(".NS", "").replace(".BO", "") for t in tickers]

    # 1. ETF NAV divergence — only scan ETFs the user explicitly chose, or all if no tickers given
    if ticker_set:
        etfs_to_scan = {t for t in ticker_set if t in ETF_MAPPINGS}
    else:
        etfs_to_scan = set(ETF_MAPPINGS.keys())   # default: scan all when no specific tickers
    for etf in etfs_to_scan:
        result = detect_etf_nav_divergence(etf)
        if result:
            opportunities.append(result)
            logger.info(f"ETF divergence: {etf} {result['direction']} {result['premium_pct']:.2f}%")

    # 2. Dynamic pairs — find correlated pairs among user's chosen tickers
    if len(ticker_set) >= 2:
        correlated = find_correlated_pairs(ticker_set)
        for t1, t2, corr in correlated[:10]:   # cap at 10 pairs
            result = detect_pairs_divergence(t1, t2, label=f"corr={corr:.2f}")
            if result:
                result["correlation"] = corr
                opportunities.append(result)
                logger.info(f"Pairs divergence: {t1}/{t2} z={result['z_score']:.2f} corr={corr:.2f}")

    # 3. Bollinger extremes on all user tickers
    for ticker in ticker_set:
        result = detect_bollinger_extreme(ticker)
        if result:
            opportunities.append(result)
            logger.info(f"BB extreme: {ticker} {result['direction']} pos={result['band_position_pct']}%")

    opportunities.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    logger.info(f"scan_opportunities: {len(opportunities)} found across {len(ticker_set)} tickers")
    return opportunities
