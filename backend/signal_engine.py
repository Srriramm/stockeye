"""
Signal Engine — unified India-specific signal scoring.

Each scorer returns a score 0-100 and a confidence 0-1.
Composite score = weighted average of available signals.

Signal stack (in priority order):
  1. FII/DII flows        weight=0.25  (biggest price mover in India)
  2. F&O PCR              weight=0.20  (sentiment extreme detector)
  3. Technical            weight=0.20  (RSI, MACD, Bollinger)
  4. Delivery volume %    weight=0.15  (conviction signal)
  5. News sentiment       weight=0.20  (catalyst)
"""

import logging
import time
import requests
from functools import lru_cache

logger = logging.getLogger(__name__)

# ── NSE session (reused across calls, refreshed if cookies expire) ─────────────
_nse_session: requests.Session | None = None
_nse_session_ts: float = 0
NSE_SESSION_TTL = 300   # seconds before refreshing cookies

NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         "https://www.nseindia.com/",
    "Connection":      "keep-alive",
}


def _get_nse_session() -> requests.Session:
    global _nse_session, _nse_session_ts
    if _nse_session is None or (time.time() - _nse_session_ts) > NSE_SESSION_TTL:
        s = requests.Session()
        try:
            s.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=10)
            _nse_session_ts = time.time()
        except Exception as e:
            logger.debug(f"[NSE] Session init failed: {e}")
        _nse_session = s
    return _nse_session


def _nse_get(endpoint: str, timeout: int = 10) -> dict | list | None:
    """GET an NSE API endpoint with session cookies. Returns parsed JSON or None."""
    try:
        s = _get_nse_session()
        url = f"https://www.nseindia.com{endpoint}"
        r   = s.get(url, headers=NSE_HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        # Cookie expired — refresh session once and retry
        if r.status_code in (401, 403):
            global _nse_session_ts
            _nse_session_ts = 0
            s = _get_nse_session()
            r = s.get(url, headers=NSE_HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r.json()
        logger.debug(f"[NSE] {endpoint} returned {r.status_code}")
    except Exception as e:
        logger.debug(f"[NSE] {endpoint} failed: {e}")
    return None


# ── Cache helpers ──────────────────────────────────────────────────────────────
_cache: dict = {}

def _cache_get(key: str, ttl: int) -> object | None:
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < ttl:
        return entry["value"]
    return None

def _cache_set(key: str, value: object) -> None:
    _cache[key] = {"value": value, "ts": time.time()}


# ── FII / DII flows ────────────────────────────────────────────────────────────
def get_fii_dii_today() -> dict:
    """
    Fetch today's FII and DII net buy/sell from NSE.
    Returns: {fii_net_cr, dii_net_cr, date, source}
    All values in crores INR. Negative = net selling.
    Cached for 1 hour (data updates once daily).
    """
    cached = _cache_get("fii_dii_today", ttl=3600)
    if cached:
        return cached

    data = _nse_get("/api/fiidiiTradeReact")
    if data and isinstance(data, list) and len(data) > 0:
        latest = data[0]   # Most recent trading day
        try:
            fii_net = float(latest.get("netVal", 0))        # Already in crores
            dii_net = float(latest.get("netVal2", 0))
            result  = {
                "fii_net_cr": round(fii_net, 2),
                "dii_net_cr": round(dii_net, 2),
                "date":       latest.get("date", ""),
                "source":     "nse",
            }
            _cache_set("fii_dii_today", result)
            return result
        except (TypeError, ValueError) as e:
            logger.debug(f"[FII/DII] Parse error: {e}")

    # Fallback: return neutral (unknown) so risk gate degrades gracefully
    return {"fii_net_cr": None, "dii_net_cr": None, "date": "", "source": "unavailable"}


def get_delivery_pct(ticker: str) -> float | None:
    """
    Fetch delivery-to-traded volume % for a stock from NSE.
    High delivery (>50%) = conviction buying.
    Cached 24 hours (daily data).
    """
    cache_key = f"delivery_{ticker}"
    cached    = _cache_get(cache_key, ttl=86400)
    if cached is not None:
        return cached

    data = _nse_get(f"/api/quote-equity?symbol={ticker.upper()}")
    if data:
        try:
            delivery_pct = float(
                data.get("deliveryInfo", {}).get("deliveryToTradedQuantity") or
                data.get("preOpenMarket", {}).get("totalTradedVolume") or 0
            )
            # NSE returns this as a percentage 0-100
            if 0 <= delivery_pct <= 100:
                _cache_set(cache_key, delivery_pct)
                return delivery_pct
        except (TypeError, ValueError):
            pass

    # Try trade info section
    if data and isinstance(data, dict):
        try:
            trade_info = data.get("tradeInfo", {})
            deliv      = trade_info.get("deliveryToTradedQuantity")
            if deliv is not None:
                pct = float(deliv)
                _cache_set(cache_key, pct)
                return pct
        except (TypeError, ValueError):
            pass

    return None


def get_nifty_pcr() -> float | None:
    """
    Compute Nifty Put-Call Ratio from NSE option chain.
    PCR < 0.7 = bearish extreme, PCR > 1.3 = bullish extreme.
    Cached 15 minutes.
    """
    cached = _cache_get("nifty_pcr", ttl=900)
    if cached is not None:
        return cached

    data = _nse_get("/api/option-chain-indices?symbol=NIFTY")
    if data:
        try:
            records   = data.get("records", {}).get("data", [])
            total_put = sum(
                float(r.get("PE", {}).get("openInterest") or 0)
                for r in records if r.get("PE")
            )
            total_call = sum(
                float(r.get("CE", {}).get("openInterest") or 0)
                for r in records if r.get("CE")
            )
            if total_call > 0:
                pcr = round(total_put / total_call, 3)
                _cache_set("nifty_pcr", pcr)
                return pcr
        except Exception as e:
            logger.debug(f"[PCR] Compute error: {e}")

    return None


def get_india_vix() -> float | None:
    """Fetch India VIX from NSE. Cached 15 minutes."""
    cached = _cache_get("india_vix", ttl=900)
    if cached is not None:
        return cached

    data = _nse_get("/api/allIndices")
    if data and isinstance(data, dict):
        try:
            for idx in data.get("data", []):
                if "VIX" in str(idx.get("index", "")):
                    vix = float(idx.get("last") or idx.get("open") or 0)
                    if vix > 0:
                        _cache_set("india_vix", vix)
                        return vix
        except Exception as e:
            logger.debug(f"[VIX] Parse error: {e}")

    return None


# ── Individual signal scorers (each returns score 0-100) ──────────────────────

def _score_fii_dii(fii_net_cr: float | None, dii_net_cr: float | None) -> tuple[float, float]:
    """Score based on FII/DII net flows. Returns (score, confidence)."""
    if fii_net_cr is None:
        return 50, 0.0   # neutral, zero confidence

    score = 50.0
    # FII contribution (max ±30 points)
    if fii_net_cr > 3000:    score += 30
    elif fii_net_cr > 1500:  score += 20
    elif fii_net_cr > 500:   score += 10
    elif fii_net_cr < -3000: score -= 30
    elif fii_net_cr < -1500: score -= 20
    elif fii_net_cr < -500:  score -= 10

    # DII contribution (max ±10 points — counter-signal weight)
    if dii_net_cr is not None:
        if dii_net_cr > 2000:    score += 10
        elif dii_net_cr > 1000:  score += 5
        elif dii_net_cr < -2000: score -= 10
        elif dii_net_cr < -1000: score -= 5

    confidence = 0.90 if fii_net_cr is not None else 0.0
    return max(0, min(100, score)), confidence


def _score_pcr(pcr: float | None) -> tuple[float, float]:
    """Score based on Nifty PCR. Returns (score, confidence)."""
    if pcr is None:
        return 50, 0.0

    # PCR > 1.2 = market is over-hedged = bullish (contrarian)
    # PCR < 0.7 = market is complacent = bearish (contrarian)
    if pcr >= 1.5:    score = 85
    elif pcr >= 1.3:  score = 75
    elif pcr >= 1.0:  score = 60
    elif pcr >= 0.8:  score = 50
    elif pcr >= 0.7:  score = 40
    else:             score = 25

    return score, 0.85


def _score_delivery(delivery_pct: float | None) -> tuple[float, float]:
    """Score based on delivery volume %. Returns (score, confidence)."""
    if delivery_pct is None:
        return 50, 0.0

    if delivery_pct >= 70:    score = 90
    elif delivery_pct >= 55:  score = 75
    elif delivery_pct >= 40:  score = 55
    elif delivery_pct >= 25:  score = 40
    else:                     score = 20

    return score, 0.80


def _score_technical(ticker: str) -> tuple[float, float]:
    """Score using RSI, MACD, Bollinger from existing stock_data module."""
    try:
        from stock_data import calculate_technical_indicators
        tech = calculate_technical_indicators(ticker, period="3mo") or {}

        score = 50.0
        rsi   = tech.get("rsi")
        macd  = tech.get("macd_direction")
        bb    = tech.get("bollinger_bands", {})
        sig   = tech.get("signal", "")

        # RSI contribution (±25 points)
        if rsi is not None:
            if rsi < 30:      score += 20   # oversold — bounce candidate
            elif rsi < 40:    score += 10
            elif rsi > 70:    score -= 20   # overbought
            elif rsi > 60:    score -= 10

        # MACD (±15 points)
        if macd == "bullish":   score += 15
        elif macd == "bearish": score -= 15

        # Bollinger position (±10 points)
        if isinstance(bb, dict):
            pct_b = bb.get("pct_b")
            if pct_b is not None:
                if pct_b < 0.1:   score += 10   # near lower band
                elif pct_b > 0.9: score -= 10   # near upper band

        # Overall signal override
        if sig in ("BUY", "STRONG_BUY"):   score = max(score, 65)
        elif sig in ("SELL", "STRONG_SELL"): score = min(score, 35)

        return max(0, min(100, score)), 0.90
    except Exception as e:
        logger.debug(f"[Signal] Technical score failed for {ticker}: {e}")
        return 50, 0.0


def _score_news(ticker: str) -> tuple[float, float]:
    """Score based on recent news sentiment."""
    try:
        from news_monitor import fetch_stock_news
        articles = fetch_stock_news(ticker, days=2, max_articles=8) or []
        if not articles:
            return 50, 0.3

        pos = sum(1 for a in articles if a.get("sentiment") == "positive")
        neg = sum(1 for a in articles if a.get("sentiment") == "negative")
        total = pos + neg
        if total == 0:
            return 50, 0.3

        ratio = pos / total
        if ratio >= 0.8:    score = 85
        elif ratio >= 0.6:  score = 70
        elif ratio >= 0.4:  score = 50
        elif ratio >= 0.2:  score = 35
        else:               score = 20

        confidence = min(0.9, 0.4 + (total * 0.1))   # more articles = more confident
        return score, confidence
    except Exception as e:
        logger.debug(f"[Signal] News score failed for {ticker}: {e}")
        return 50, 0.0


# ── Composite scorer ──────────────────────────────────────────────────────────

SIGNAL_WEIGHTS = {
    "fii_dii":      0.22,
    "pcr":          0.18,
    "technical":    0.18,
    "delivery":     0.12,
    "news":         0.13,
    "global_cues":  0.09,
    "fo_oi":        0.08,
}

def score_stock(ticker: str) -> dict:
    """
    Compute all signal scores for a stock.
    Returns a dict with individual scores, composite score, and market data.

    Graceful degradation: unavailable signals are excluded from composite.
    """
    # Fetch India-specific data (fast — most are cached)
    fii_dii    = get_fii_dii_today()
    pcr        = get_nifty_pcr()
    delivery   = get_delivery_pct(ticker)
    vix        = get_india_vix()

    # Score each signal
    fii_score,  fii_conf  = _score_fii_dii(fii_dii["fii_net_cr"], fii_dii["dii_net_cr"])
    pcr_score,  pcr_conf  = _score_pcr(pcr)
    tech_score, tech_conf = _score_technical(ticker)
    deliv_score,deliv_conf= _score_delivery(delivery)
    news_score, news_conf = _score_news(ticker)

    scores = {
        "fii_dii":   {"score": fii_score,   "confidence": fii_conf},
        "pcr":       {"score": pcr_score,   "confidence": pcr_conf},
        "technical": {"score": tech_score,  "confidence": tech_conf},
        "delivery":  {"score": deliv_score, "confidence": deliv_conf},
        "news":      {"score": news_score,  "confidence": news_conf},
    }

    # Weighted composite — only include signals with confidence > 0
    total_weight = 0.0
    weighted_sum = 0.0
    signals_available = 0
    for key, weight in SIGNAL_WEIGHTS.items():
        s = scores[key]
        if s["confidence"] > 0:
            effective_weight = weight * s["confidence"]
            weighted_sum    += s["score"] * effective_weight
            total_weight    += effective_weight
            signals_available += 1

    composite = round(weighted_sum / total_weight, 1) if total_weight > 0 else 50.0

    # Require at least 3 signals to have meaningful confidence
    data_quality = "high" if signals_available >= 4 else \
                   "medium" if signals_available >= 3 else "low"

    return {
        "ticker":             ticker,
        "composite_score":    composite,
        "signals_available":  signals_available,
        "data_quality":       data_quality,
        "scores":             scores,
        "market_data": {
            "fii_net_cr":        fii_dii.get("fii_net_cr"),
            "dii_net_cr":        fii_dii.get("dii_net_cr"),
            "nifty_pcr":         pcr,
            "india_vix":         vix,
            "delivery_pct":      delivery,
        },
    }


def format_scores_for_prompt(signal_result: dict) -> str:
    """Format signal scores as a clean block for injection into Claude prompts."""
    scores = signal_result.get("scores", {})
    md     = signal_result.get("market_data", {})
    lines  = [
        f"=== SIGNAL SCORES: {signal_result['ticker']} ===",
        f"Composite: {signal_result['composite_score']:.0f}/100  "
        f"(Data quality: {signal_result['data_quality']}, "
        f"{signal_result['signals_available']}/5 signals available)",
        "",
        f"FII/DII flows:   {scores.get('fii_dii',{}).get('score', 'N/A'):>5.0f}  "
        f"[FII ₹{md.get('fii_net_cr') or 'N/A'}cr | DII ₹{md.get('dii_net_cr') or 'N/A'}cr]",
        f"F&O PCR:         {scores.get('pcr',{}).get('score', 'N/A'):>5.0f}  "
        f"[PCR = {md.get('nifty_pcr') or 'N/A'}]",
        f"Technical:       {scores.get('technical',{}).get('score', 'N/A'):>5.0f}",
        f"Delivery vol %:  {scores.get('delivery',{}).get('score', 'N/A'):>5.0f}  "
        f"[{md.get('delivery_pct') or 'N/A'}% of trades delivered]",
        f"News sentiment:  {scores.get('news',{}).get('score', 'N/A'):>5.0f}",
        "",
        f"India VIX: {md.get('india_vix') or 'N/A'}",
    ]
    return "\n".join(str(l) for l in lines)


# ── Market regime detector ────────────────────────────────────────────────────

def get_market_regime() -> dict:
    """
    Classify current market regime as BULL / BEAR / SIDEWAYS / VOLATILE.
    Used to adjust strategy — different rules apply in each regime.
    Cached 30 minutes.
    """
    cached = _cache_get("market_regime", ttl=1800)
    if cached:
        return cached

    regime = "SIDEWAYS"
    reasons = []

    try:
        from stock_data import calculate_technical_indicators
        nifty_tech = calculate_technical_indicators("^NSEI", period="3mo") or {}
        vix        = get_india_vix()
        fii_dii    = get_fii_dii_today()
        fii_net    = fii_dii.get("fii_net_cr")

        rsi       = nifty_tech.get("rsi")
        macd_dir  = nifty_tech.get("macd_direction")
        sma_20    = nifty_tech.get("sma_20")
        sma_50    = nifty_tech.get("sma_50")
        price     = nifty_tech.get("current_price") or nifty_tech.get("close")

        bull_score = 0
        bear_score = 0

        # VIX regime
        if vix is not None:
            if vix > 22:
                bear_score += 2
                reasons.append(f"High VIX {vix:.1f} (fear elevated)")
            elif vix < 14:
                bull_score += 1
                reasons.append(f"Low VIX {vix:.1f} (complacency/calm)")

        # Nifty trend vs SMAs
        if price and sma_20 and sma_50:
            if price > sma_20 > sma_50:
                bull_score += 2
                reasons.append("Nifty above SMA-20 and SMA-50 (uptrend)")
            elif price < sma_20 < sma_50:
                bear_score += 2
                reasons.append("Nifty below SMA-20 and SMA-50 (downtrend)")

        # MACD
        if macd_dir == "bullish":
            bull_score += 1
        elif macd_dir == "bearish":
            bear_score += 1

        # RSI
        if rsi:
            if rsi > 60:
                bull_score += 1
            elif rsi < 40:
                bear_score += 1

        # FII flows
        if fii_net is not None:
            if fii_net > 1000:
                bull_score += 2
                reasons.append(f"FII buying ₹{fii_net:,.0f}cr")
            elif fii_net < -1000:
                bear_score += 2
                reasons.append(f"FII selling ₹{abs(fii_net):,.0f}cr")

        # Classify
        if vix is not None and vix > 22:
            regime = "VOLATILE"
        elif bull_score >= 4:
            regime = "BULL"
        elif bear_score >= 4:
            regime = "BEAR"
        else:
            regime = "SIDEWAYS"

    except Exception as e:
        logger.debug(f"[Regime] Detection failed: {e}")
        regime  = "UNKNOWN"
        reasons = ["Insufficient data"]

    result = {
        "regime":     regime,
        "reasons":    reasons,
        "vix":        get_india_vix(),
        "strategy_note": {
            "BULL":     "Ride momentum. Prefer breakouts over mean-reversion.",
            "BEAR":     "No new longs. Protect capital. Wait for reversal confirmation.",
            "SIDEWAYS": "Mean-reversion setups. Buy oversold, sell overbought.",
            "VOLATILE": "Reduce position sizes by 50%. Wider stops. Fewer trades.",
            "UNKNOWN":  "Insufficient data. Proceed cautiously.",
        }.get(regime, ""),
    }

    _cache_set("market_regime", result)
    return result


# ═══════════════════════════════════════════════════════════════
# EARNINGS CALENDAR
# ═══════════════════════════════════════════════════════════════

def get_earnings_calendar(ticker: str) -> dict:
    """
    Check if an earnings/result announcement is imminent.
    Uses NSE corporate announcements + yfinance calendar as fallback.
    Returns: {in_blackout, days_to_event, event_type, event_date}
    Cached 6 hours (corporate calendar doesn't change often).
    """
    cache_key = f"earnings_{ticker}"
    cached = _cache_get(cache_key, ttl=21600)
    if cached is not None:
        return cached

    result = {"in_blackout": False, "days_to_event": None, "event_type": None, "event_date": None}

    # Try NSE corporate announcements
    data = _nse_get(f"/api/corp-info?symbol={ticker.upper()}&corpType=announcements&market=equities")
    if data and isinstance(data, list):
        import re
        from datetime import datetime as _dt
        today = _dt.utcnow()
        keywords = ["results", "quarterly", "annual", "dividend", "board meeting", "agm", "egm"]
        for ann in data[:20]:
            desc = str(ann.get("desc", "") or ann.get("subject", "")).lower()
            date_str = ann.get("date") or ann.get("bdDt") or ""
            if not any(k in desc for k in keywords):
                continue
            # Parse date
            for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    ann_date = _dt.strptime(date_str[:11], fmt)
                    diff = (ann_date - today).days
                    if -1 <= diff <= 7:
                        result = {
                            "in_blackout": diff <= 2,
                            "days_to_event": diff,
                            "event_type": "earnings",
                            "event_date": date_str[:10],
                        }
                        _cache_set(cache_key, result)
                        return result
                    break
                except (ValueError, TypeError):
                    continue

    # Fallback: yfinance calendar
    try:
        import yfinance as yf
        from datetime import datetime as _dt
        info = yf.Ticker(f"{ticker}.NS").calendar
        if info is not None and not (hasattr(info, 'empty') and info.empty):
            today = _dt.utcnow()
            # calendar can be dict or DataFrame
            if hasattr(info, 'get'):
                earnings_date = info.get("Earnings Date")
                if earnings_date and len(earnings_date) > 0:
                    diff = (earnings_date[0].to_pydatetime().replace(tzinfo=None) - today).days
                    if 0 <= diff <= 14:
                        result = {
                            "in_blackout": diff <= 2,
                            "days_to_event": diff,
                            "event_type": "earnings",
                            "event_date": str(earnings_date[0])[:10],
                        }
    except Exception as e:
        logger.debug(f"[Earnings] yfinance calendar failed for {ticker}: {e}")

    _cache_set(cache_key, result)
    return result


# ═══════════════════════════════════════════════════════════════
# GLOBAL CUES (Dow/Nasdaq futures, Crude, Gold, USD/INR)
# ═══════════════════════════════════════════════════════════════

def get_global_cues() -> dict:
    """
    Fetch global market cues via yfinance.
    SGX Nifty proxy = Nifty futures (NF1! not available in yfinance, use ^NSEI prev close).
    Returns % change from previous close for each instrument.
    Cached 15 minutes.
    """
    cached = _cache_get("global_cues", ttl=900)
    if cached is not None:
        return cached

    SYMBOLS = {
        "dow_futures":     "YM=F",
        "nasdaq_futures":  "NQ=F",
        "sp500_futures":   "ES=F",
        "crude_oil":       "CL=F",
        "gold":            "GC=F",
        "usdinr":          "USDINR=X",
        "hang_seng":       "^HSI",
        "nikkei":          "^N225",
    }
    result = {}
    try:
        import yfinance as yf
        tickers_str = " ".join(SYMBOLS.values())
        data = yf.download(tickers_str, period="2d", interval="1d",
                           progress=False, auto_adjust=True, group_by="ticker")
        for name, sym in SYMBOLS.items():
            try:
                if len(SYMBOLS) > 1:
                    df = data[sym].dropna()
                else:
                    df = data.dropna()
                if len(df) >= 2:
                    prev_close = float(df["Close"].iloc[-2])
                    last       = float(df["Close"].iloc[-1])
                    if prev_close > 0:
                        result[name] = round((last - prev_close) / prev_close * 100, 2)
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"[GlobalCues] yfinance failed: {e}")

    _cache_set("global_cues", result)
    return result


def _score_global_cues(cues: dict) -> tuple[float, float]:
    """
    Score global cues. Weight: US futures 40%, Asia 30%, USD/INR 30%.
    Returns (score 0-100, confidence 0-1).
    """
    if not cues:
        return 50, 0.0

    score = 50.0
    signals_found = 0

    # US futures (biggest influence on Nifty gap-open)
    for key in ("sp500_futures", "dow_futures", "nasdaq_futures"):
        pct = cues.get(key)
        if pct is not None:
            signals_found += 1
            if pct > 1.0:    score += 12
            elif pct > 0.3:  score += 6
            elif pct < -1.0: score -= 12
            elif pct < -0.3: score -= 6

    # Asian markets
    for key in ("hang_seng", "nikkei"):
        pct = cues.get(key)
        if pct is not None:
            signals_found += 1
            if pct > 0.5:    score += 5
            elif pct < -0.5: score -= 5

    # USD/INR: rupee depreciation is bearish for equities
    usdinr_pct = cues.get("usdinr")
    if usdinr_pct is not None:
        signals_found += 1
        if usdinr_pct > 0.5:    score -= 8   # rupee weakening = bearish
        elif usdinr_pct < -0.5: score += 8   # rupee strengthening = bullish

    # Crude oil: India is oil importer, high crude = bearish
    crude_pct = cues.get("crude_oil")
    if crude_pct is not None:
        signals_found += 1
        if crude_pct > 2.0:    score -= 6
        elif crude_pct < -2.0: score += 4

    confidence = min(0.85, 0.15 * signals_found) if signals_found > 0 else 0.0
    return max(0, min(100, score)), confidence


# ═══════════════════════════════════════════════════════════════
# F&O OI BUILDUP (stock-level)
# ═══════════════════════════════════════════════════════════════

def get_fo_oi_buildup(ticker: str) -> dict:
    """
    Compute F&O OI buildup for an individual stock from NSE.
    Returns: {call_oi, put_oi, pcr, oi_change_pct, buildup_type}
    buildup_type: 'long_buildup'|'short_buildup'|'long_unwinding'|'short_covering'|'neutral'
    Cached 30 minutes.
    """
    cache_key = f"fo_oi_{ticker}"
    cached = _cache_get(cache_key, ttl=1800)
    if cached is not None:
        return cached

    result = {
        "call_oi": None, "put_oi": None, "pcr": None,
        "oi_change_pct": None, "buildup_type": "neutral",
    }

    data = _nse_get(f"/api/option-chain-equities?symbol={ticker.upper()}")
    if data:
        try:
            records    = data.get("records", {}).get("data", [])
            total_call = sum(float(r.get("CE", {}).get("openInterest") or 0) for r in records if r.get("CE"))
            total_put  = sum(float(r.get("PE", {}).get("openInterest") or 0) for r in records if r.get("PE"))
            call_chg   = sum(float(r.get("CE", {}).get("changeinOpenInterest") or 0) for r in records if r.get("CE"))
            put_chg    = sum(float(r.get("PE", {}).get("changeinOpenInterest") or 0) for r in records if r.get("PE"))

            pcr = round(total_put / total_call, 3) if total_call > 0 else None

            # Classify buildup type
            if call_chg > 0 and put_chg < 0:
                buildup = "short_buildup"    # adds call OI, removes put = bearish
            elif call_chg < 0 and put_chg > 0:
                buildup = "long_buildup"     # adds put OI, removes call = bullish
            elif call_chg < 0 and put_chg < 0:
                buildup = "long_unwinding"   # removing both, leaning bearish
            elif call_chg > 0 and put_chg > 0:
                buildup = "short_covering"   # adding both, leaning bullish
            else:
                buildup = "neutral"

            result = {
                "call_oi": total_call, "put_oi": total_put, "pcr": pcr,
                "call_oi_change": call_chg, "put_oi_change": put_chg,
                "buildup_type": buildup,
            }
        except Exception as e:
            logger.debug(f"[FO OI] Compute error for {ticker}: {e}")

    _cache_set(cache_key, result)
    return result


def _score_fo_oi(fo_data: dict) -> tuple[float, float]:
    """Score F&O OI buildup. Returns (score, confidence)."""
    buildup = fo_data.get("buildup_type", "neutral")
    pcr     = fo_data.get("pcr")

    if buildup == "neutral" and pcr is None:
        return 50, 0.0

    score = 50.0

    buildup_scores = {
        "long_buildup":   75,
        "short_covering": 70,
        "neutral":        50,
        "long_unwinding": 35,
        "short_buildup":  25,
    }
    score = buildup_scores.get(buildup, 50)

    # Adjust with stock-level PCR (contrarian like Nifty PCR)
    if pcr is not None:
        if pcr >= 1.5:    score = min(100, score + 10)
        elif pcr <= 0.5:  score = max(0,   score - 10)

    confidence = 0.75 if fo_data.get("call_oi") else 0.0
    return score, confidence


# ═══════════════════════════════════════════════════════════════
# SECTOR ROTATION
# ═══════════════════════════════════════════════════════════════

# Nifty sector index yfinance symbols
SECTOR_INDICES = {
    "IT":       "^CNXIT",
    "Banking":  "^NSEBANK",
    "Pharma":   "^CNXPHARMA",
    "Auto":     "^CNXAUTO",
    "FMCG":     "^CNXFMCG",
    "Metal":    "^CNXMETAL",
    "Energy":   "^CNXENERGY",
    "Infra":    "^CNXINFRA",
    "Realty":   "^CNXREALTY",
    "Media":    "^CNXMEDIA",
}


def get_sector_rotation(days: int = 5) -> dict:
    """
    Compute N-day performance of Nifty sector indices.
    Returns: {sectors, top_sector, bottom_sector, last_updated}
    Cached 1 hour.
    """
    cache_key = f"sector_rotation_{days}"
    cached = _cache_get(cache_key, ttl=3600)
    if cached is not None:
        return cached

    sectors = []
    try:
        import yfinance as yf
        syms = " ".join(SECTOR_INDICES.values())
        df = yf.download(syms, period=f"{days + 5}d", interval="1d",
                         progress=False, auto_adjust=True, group_by="ticker")
        for name, sym in SECTOR_INDICES.items():
            try:
                s = df[sym]["Close"].dropna() if len(SECTOR_INDICES) > 1 else df["Close"].dropna()
                if len(s) >= 2:
                    change_pct = round((float(s.iloc[-1]) - float(s.iloc[-min(days, len(s)-1)])) /
                                       float(s.iloc[-min(days, len(s)-1)]) * 100, 2)
                    sectors.append({"sector": name, "change_pct": change_pct, "symbol": sym})
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"[SectorRotation] Failed: {e}")

    if not sectors:
        return {"sectors": [], "top_sector": None, "bottom_sector": None}

    sectors.sort(key=lambda x: x["change_pct"], reverse=True)
    result = {
        "sectors":       sectors,
        "top_sector":    sectors[0]["sector"]  if sectors else None,
        "bottom_sector": sectors[-1]["sector"] if sectors else None,
        "days":          days,
    }
    _cache_set(cache_key, result)
    return result


def get_stock_sector(ticker: str) -> str | None:
    """Return the sector for a given NSE ticker (basic lookup)."""
    SECTOR_MAP = {
        "INFY": "IT", "TCS": "IT", "WIPRO": "IT", "HCLTECH": "IT", "TECHM": "IT",
        "LTI": "IT", "MPHASIS": "IT", "LTIM": "IT", "PERSISTENT": "IT",
        "HDFCBANK": "Banking", "ICICIBANK": "Banking", "KOTAKBANK": "Banking",
        "AXISBANK": "Banking", "SBIN": "Banking", "BANDHANBNK": "Banking",
        "INDUSINDBK": "Banking", "FEDERALBNK": "Banking", "IDFCFIRSTB": "Banking",
        "RELIANCE": "Energy", "ONGC": "Energy", "IOC": "Energy", "BPCL": "Energy",
        "SUNPHARMA": "Pharma", "DRREDDY": "Pharma", "CIPLA": "Pharma",
        "DIVISLAB": "Pharma", "BIOCON": "Pharma", "AUROPHARMA": "Pharma",
        "MARUTI": "Auto", "TATAMOTORS": "Auto", "M&M": "Auto", "BAJAJ-AUTO": "Auto",
        "EICHERMOT": "Auto", "HEROMOTOCO": "Auto", "TVSMOTOR": "Auto",
        "HINDALCO": "Metal", "TATASTEEL": "Metal", "JSWSTEEL": "Metal",
        "SAIL": "Metal", "VEDL": "Metal", "NMDC": "Metal",
        "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG",
        "BRITANNIA": "FMCG", "DABUR": "FMCG", "MARICO": "FMCG",
        "ADANIENT": "Infra", "LT": "Infra", "NTPC": "Energy",
        "POWERGRID": "Energy", "COALINDIA": "Energy",
    }
    return SECTOR_MAP.get(ticker.upper())


# ═══════════════════════════════════════════════════════════════
# ADAPTIVE SIGNAL WEIGHTS
# ═══════════════════════════════════════════════════════════════

def get_adaptive_weights(user_id=None) -> dict:
    """
    Compute per-user signal weights based on historical prediction accuracy.
    Queries completed trades in trade_signals table, correlates each signal score
    with the trade's actual return. High correlation → higher weight.

    Falls back to SIGNAL_WEIGHTS if fewer than 30 completed trades exist.
    Cached per-user 24 hours.
    """
    cache_key = f"adaptive_weights_{user_id or 'global'}"
    cached = _cache_get(cache_key, ttl=86400)
    if cached is not None:
        return cached

    weights = dict(SIGNAL_WEIGHTS)  # start with defaults

    try:
        from db import get_db_connection  # noqa: PLC0415

        # Select the 5 scored columns that exist in trade_signals table
        # (global_cues and fo_oi are not stored yet — use defaults for those)
        DB_COLS = "fii_dii_score, pcr_score, technical_score, delivery_score, news_score, entry_price, exit_price"
        with get_db_connection() as conn:
            where = "AND user_id = ?" if user_id else ""
            cur = conn.execute(
                f"""SELECT {DB_COLS}
                   FROM trade_signals
                   WHERE exit_price IS NOT NULL
                     AND entry_price > 0
                     {where}
                   ORDER BY created_at DESC LIMIT 200""",
                (user_id,) if user_id else ()
            )
            rows = cur.fetchall()

        if len(rows) < 30:
            _cache_set(cache_key, weights)
            return weights

        # Build correlation data — only for the 5 stored signals
        # global_cues and fo_oi keep their default weights
        stored_keys = ["fii_dii", "pcr", "technical", "delivery", "news"]
        signal_scores_list = {k: [] for k in stored_keys}
        returns = []

        for row in rows:
            try:
                # row: fii_dii(0), pcr(1), technical(2), delivery(3), news(4), entry(5), exit(6)
                col_map = {
                    "fii_dii": float(row[0] or 50),
                    "pcr":     float(row[1] or 50),
                    "technical": float(row[2] or 50),
                    "delivery":  float(row[3] or 50),
                    "news":      float(row[4] or 50),
                }
                ret = (float(row[6]) - float(row[5])) / float(row[5]) * 100
                returns.append(ret)
                for k in stored_keys:
                    signal_scores_list[k].append(col_map[k])
            except Exception:
                continue

        if len(returns) < 30:
            _cache_set(cache_key, weights)
            return weights

        # Pearson correlation for each signal vs return
        import math
        def _pearson(xs, ys):
            n = len(xs)
            if n < 5:
                return 0.0
            mx, my = sum(xs)/n, sum(ys)/n
            num = sum((x-mx)*(y-my) for x, y in zip(xs, ys))
            den = math.sqrt(sum((x-mx)**2 for x in xs) * sum((y-my)**2 for y in ys))
            return num / den if den > 0 else 0.0

        correlations = {}
        for k in stored_keys:
            r = _pearson(signal_scores_list[k], returns)
            correlations[k] = max(0.01, abs(r))  # keep positive, floor at 0.01

        total = sum(correlations.values())
        adaptive_stored = {k: round(v / total, 4) for k, v in correlations.items()}

        # Blend 50/50 with defaults for stored signals; keep defaults for unstored ones
        blended = {}
        for k in SIGNAL_WEIGHTS:
            if k in adaptive_stored:
                blended[k] = round(0.5 * SIGNAL_WEIGHTS[k] + 0.5 * adaptive_stored[k], 4)
            else:
                blended[k] = SIGNAL_WEIGHTS[k]   # global_cues, fo_oi keep defaults
        total_blended = sum(blended.values())
        weights = {k: round(v / total_blended, 4) for k, v in blended.items()}

        logger.info(f"[AdaptiveWeights] Computed for user={user_id}, n={len(returns)} trades: {weights}")

    except Exception as e:
        logger.debug(f"[AdaptiveWeights] Failed: {e}")

    _cache_set(cache_key, weights)
    return weights


# ═══════════════════════════════════════════════════════════════
# UPDATED score_stock() with new signals
# ═══════════════════════════════════════════════════════════════

def score_stock_full(ticker: str, user_id=None) -> dict:
    """
    Extended version of score_stock() — includes global cues, F&O OI, earnings blackout,
    sector context, and adaptive weights.

    Use this in agentic_trader and backtest for richer signals.
    The original score_stock() still works for lightweight calls.
    """
    # Fetch all signals
    fii_dii   = get_fii_dii_today()
    pcr       = get_nifty_pcr()
    delivery  = get_delivery_pct(ticker)
    vix       = get_india_vix()
    cues      = get_global_cues()
    fo_data   = get_fo_oi_buildup(ticker)
    earnings  = get_earnings_calendar(ticker)

    # Score each signal
    fii_score,    fii_conf    = _score_fii_dii(fii_dii["fii_net_cr"], fii_dii["dii_net_cr"])
    pcr_score,    pcr_conf    = _score_pcr(pcr)
    tech_score,   tech_conf   = _score_technical(ticker)
    deliv_score,  deliv_conf  = _score_delivery(delivery)
    news_score,   news_conf   = _score_news(ticker)
    cues_score,   cues_conf   = _score_global_cues(cues)
    fo_score,     fo_conf     = _score_fo_oi(fo_data)

    scores = {
        "fii_dii":     {"score": fii_score,   "confidence": fii_conf},
        "pcr":         {"score": pcr_score,   "confidence": pcr_conf},
        "technical":   {"score": tech_score,  "confidence": tech_conf},
        "delivery":    {"score": deliv_score, "confidence": deliv_conf},
        "news":        {"score": news_score,  "confidence": news_conf},
        "global_cues": {"score": cues_score,  "confidence": cues_conf},
        "fo_oi":       {"score": fo_score,    "confidence": fo_conf},
    }

    # Adaptive weights (falls back to SIGNAL_WEIGHTS if <30 trades)
    weights = get_adaptive_weights(user_id)

    # Weighted composite — only include signals with confidence > 0
    total_weight   = 0.0
    weighted_sum   = 0.0
    signals_available = 0
    for key, weight in weights.items():
        s = scores.get(key, {})
        if s.get("confidence", 0) > 0:
            eff = weight * s["confidence"]
            weighted_sum    += s["score"] * eff
            total_weight    += eff
            signals_available += 1

    composite = round(weighted_sum / total_weight, 1) if total_weight > 0 else 50.0

    data_quality = "high"   if signals_available >= 5 else \
                   "medium" if signals_available >= 3 else "low"

    # Sector context
    sector = get_stock_sector(ticker)
    sector_data = {}
    if sector:
        rotation = get_sector_rotation()
        for s in rotation.get("sectors", []):
            if s["sector"] == sector:
                sector_data = s
                break

    return {
        "ticker":             ticker,
        "composite_score":    composite,
        "signals_available":  signals_available,
        "data_quality":       data_quality,
        "scores":             scores,
        "weights_used":       weights,
        "earnings":           earnings,
        "sector":             sector,
        "sector_performance": sector_data,
        "market_data": {
            "fii_net_cr":   fii_dii.get("fii_net_cr"),
            "dii_net_cr":   fii_dii.get("dii_net_cr"),
            "nifty_pcr":    pcr,
            "india_vix":    vix,
            "delivery_pct": delivery,
            "global_cues":  cues,
            "fo_oi":        fo_data,
        },
    }
