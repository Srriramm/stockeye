"""
Brain Engine - AI-powered unified stock analysis.

Synthesizes 5 data layers into one evidence-based analysis:
  1. Technical Indicators  (RSI, MACD, Bollinger, SMA)
  2. ML Price Forecast     (Prophet → LinearRegression → MA)
  3. Walk-forward Backtest (real MAPE on last 20 days)
  4. News Sentiment        (News API + RSS, last 7 days)
  5. AI Narrative          (GPT-4 / Claude, cites real numbers)
"""

import logging
import time
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)

# ─── In-memory cache (2-minute TTL) ─────────────────────────────

_cache: dict = {}
_CACHE_TTL = 120  # seconds


def _get_cached(key: str):
    entry = _cache.get(key)
    if entry and time.time() < entry['exp']:
        return entry['val']
    return None


def _set_cached(key: str, val):
    _cache[key] = {'val': val, 'exp': time.time() + _CACHE_TTL}


# ─── Public API ──────────────────────────────────────────────────

def run_brain_analysis(ticker: str, days: int = 30) -> dict:
    """
    Run complete AI brain analysis for a stock.

    Returns the standard forecast dict EXTENDED with:
      - technical_indicators : scored technical analysis
      - news_sentiment       : sentiment from news articles
      - backtest             : real MAPE on last 20-day holdout
      - score_breakdown      : per-layer weighted scores
      - weighted_score       : 0-100 composite confidence
      - ai_narrative         : GPT-4/Claude evidence-based text
    """
    cache_key = f"brain_{ticker}_{days}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    result = _run_analysis(ticker, days)
    if 'error' not in result:
        _set_cached(cache_key, result)
    return result


def _run_analysis(ticker: str, days: int) -> dict:
    try:
        from stock_data import get_historical_data, calculate_technical_indicators
        from forecasting_engine import forecast_stock_price, backtest_forecast
        from news_monitor import fetch_stock_news

        # ── Layer 1: Historical data ──────────────────────────────
        period = '2y' if days > 30 else '1y'
        historical = get_historical_data(ticker, period=period, interval='1d')
        if not historical or len(historical) < 30:
            return {'error': f'Insufficient historical data for {ticker}'}

        current_price = historical[-1]['close']

        # ── Layer 2: Technical indicators ────────────────────────
        raw_tech = calculate_technical_indicators(ticker, period='6mo')
        tech = _analyze_technicals(raw_tech)

        # ── Layer 3: ML Forecast ─────────────────────────────────
        forecast = forecast_stock_price(historical, ticker, days=days)
        if 'error' in forecast:
            return forecast

        # ── Layer 4: Backtest (MAPE) ─────────────────────────────
        backtest = backtest_forecast(historical, ticker, holdout_days=20)

        # ── Layer 5: News sentiment (intelligence-driven) ────────
        try:
            from intelligence_engine import get_stock_profile
            intel_profile = get_stock_profile(ticker)
            articles = fetch_stock_news(ticker, days=7, max_articles=8,
                                        intelligence_profile=intel_profile)
        except Exception as e:
            logger.warning(f"News fetch failed for {ticker}: {e}")
            articles = []
        news = _analyze_news(articles)

        # ── Layer 6: Volume signal ────────────────────────────────
        vol_score = _volume_score(historical)

        # ── Weighted composite score ──────────────────────────────
        breakdown = {
            'technical': {'score': tech['score'],                              'weight': 0.35, 'label': 'Technical Analysis'},
            'forecast':  {'score': _trend_to_score(forecast['trend_pct']),    'weight': 0.30, 'label': 'ML Price Forecast'},
            'news':      {'score': news['score'],                              'weight': 0.20, 'label': 'News Sentiment'},
            'volume':    {'score': vol_score,                                  'weight': 0.15, 'label': 'Volume Signal'},
        }
        composite = round(sum(v['score'] * v['weight'] for v in breakdown.values()))

        # ── Brain-derived signal — must agree with BOTH composite AND forecast direction
        # A BUY needs bullish composite (>=62) AND price forecast to be positive (>1%)
        # A SELL needs either very bearish composite (<=38) OR large downward forecast (<-5%)
        # Everything else is HOLD — avoids contradicting signals like "BUY but target < current"
        trend_pct = forecast.get('trend_pct', 0)
        if composite >= 62 and trend_pct > 1:
            brain_signal = 'BUY'
        elif composite <= 38 or trend_pct < -5:
            brain_signal = 'SELL'
        else:
            brain_signal = 'HOLD'

        # ── AI Narrative ──────────────────────────────────────────
        narrative = _generate_narrative(
            ticker, current_price, forecast, tech, news, backtest, composite
        )

        return {
            **forecast,
            'signal':                brain_signal,   # override ML-only signal with brain signal
            'confidence':            composite,
            'technical_indicators':  tech,
            'news_sentiment':        news,
            'backtest':              backtest,
            'score_breakdown':       breakdown,
            'weighted_score':        composite,
            'ai_narrative':          narrative,
        }

    except Exception as e:
        logger.error(f"Brain analysis failed for {ticker}: {e}", exc_info=True)
        return {'error': f'Brain analysis error: {str(e)}'}


# ─── Layer Analysis Helpers ──────────────────────────────────────

def _analyze_technicals(raw: dict) -> dict:
    """Score technical indicators 0-100."""
    if not raw:
        return {'score': 50, 'rsi': None, 'macd': None, 'macd_histogram': None,
                'bb_upper': None, 'bb_lower': None, 'bb_middle': None,
                'sma_50': None, 'sma_200': None, 'sma_20': None,
                'rsi_signal': 'unknown', 'macd_direction': 'unknown',
                'bb_position': 'unknown', 'trend': 'unknown',
                'signals': [], 'volume_ratio': None, 'current_price': None}

    rsi   = float(raw.get('rsi', 50) or 50)
    macd  = float(raw.get('macd', 0) or 0)
    msig  = float(raw.get('macd_signal', 0) or 0)
    price = float(raw.get('current_price', 0) or 0)
    sma50 = raw.get('sma_50')
    sma200 = raw.get('sma_200')
    bbu   = raw.get('bb_upper', price * 1.02)
    bbl   = raw.get('bb_lower', price * 0.98)

    # RSI score
    if rsi < 30:
        rsi_score, rsi_signal = 80, 'oversold'
    elif rsi < 50:
        rsi_score, rsi_signal = 55, 'neutral-bearish'
    elif rsi < 70:
        rsi_score, rsi_signal = 65, 'neutral-bullish'
    else:
        rsi_score, rsi_signal = 30, 'overbought'

    # MACD score
    bullish_macd = macd > msig
    macd_score   = 70 if bullish_macd else 35
    macd_dir     = 'bullish' if bullish_macd else 'bearish'

    # Bollinger score
    if price > bbu:
        bb_score, bb_pos = 30, 'above_upper'
    elif price < bbl:
        bb_score, bb_pos = 75, 'below_lower'
    else:
        bb_score, bb_pos = 55, 'inside_band'

    # Trend vs SMA score
    trend_score, trend = 50, 'neutral'
    if sma50 and sma200:
        if price > sma50 > sma200:
            trend_score, trend = 80, 'strong_bullish'
        elif price > sma50:
            trend_score, trend = 65, 'bullish'
        elif price < sma50 < sma200:
            trend_score, trend = 25, 'strong_bearish'
        else:
            trend_score, trend = 40, 'bearish'
    elif sma50:
        if price > sma50:
            trend_score, trend = 65, 'bullish'
        else:
            trend_score, trend = 40, 'bearish'

    composite = round(rsi_score * 0.30 + macd_score * 0.30 +
                      bb_score * 0.20 + trend_score * 0.20)

    return {
        'score':         composite,
        'rsi':           round(rsi, 2),
        'macd':          round(macd, 4),
        'macd_signal':   round(msig, 4),
        'macd_histogram': round(float(raw.get('macd_histogram', 0) or 0), 4),
        'bb_upper':      raw.get('bb_upper'),
        'bb_lower':      raw.get('bb_lower'),
        'bb_middle':     raw.get('bb_middle'),
        'sma_20':        raw.get('sma_20'),
        'sma_50':        sma50,
        'sma_200':       sma200,
        'rsi_signal':    rsi_signal,
        'macd_direction': macd_dir,
        'bb_position':   bb_pos,
        'trend':         trend,
        'signals':       raw.get('signals', []),
        'volume_ratio':  raw.get('volume_ratio'),
        'current_price': price,
    }


def _analyze_news(articles: list) -> dict:
    """Score news sentiment 0-100."""
    if not articles:
        return {'score': 50, 'label': 'Neutral', 'raw_score': 0.0,
                'articles': [], 'positive': 0, 'negative': 0, 'neutral': 0, 'total': 0}

    counts = {'positive': 0, 'negative': 0, 'neutral': 0}
    for a in articles:
        s = a.get('sentiment', 'neutral')
        counts[s] = counts.get(s, 0) + 1

    total = len(articles)
    raw   = (counts['positive'] - counts['negative']) / total   # -1 to 1
    score = round((raw + 1) / 2 * 100)
    label = 'Positive' if raw > 0.2 else ('Negative' if raw < -0.2 else 'Neutral')

    return {
        'score':     score,
        'label':     label,
        'raw_score': round(raw, 3),
        'articles':  articles[:5],
        'positive':  counts['positive'],
        'negative':  counts['negative'],
        'neutral':   counts['neutral'],
        'total':     total,
    }


def _volume_score(historical: list) -> int:
    """Volume confirmation score 0-100."""
    if len(historical) < 20:
        return 50
    recent = [d['volume'] for d in historical[-5:]  if d.get('volume', 0) > 0]
    base   = [d['volume'] for d in historical[-20:-5] if d.get('volume', 0) > 0]
    if not recent or not base:
        return 50
    ratio = np.mean(recent) / np.mean(base) if np.mean(base) > 0 else 1
    if ratio > 1.5:  return 78
    if ratio > 1.2:  return 65
    if ratio < 0.7:  return 38
    return 55


def _trend_to_score(trend_pct: float) -> int:
    """Map forecast trend % → 0-100 score."""
    if trend_pct > 10:  return 90
    if trend_pct > 5:   return 75
    if trend_pct > 2:   return 65
    if trend_pct >= -2: return 50
    if trend_pct > -5:  return 35
    return 20


# ─── AI Narrative ────────────────────────────────────────────────

def _generate_narrative(ticker, price, forecast, tech, news, backtest, score) -> str:
    """Generate evidence-based narrative via GPT-4/Claude (with rule-based fallback)."""
    rsi       = tech.get('rsi', 'N/A')
    rsi_sig   = tech.get('rsi_signal', 'neutral')
    macd_dir  = tech.get('macd_direction', 'unknown')
    trend     = tech.get('trend', 'neutral').replace('_', ' ')
    signal    = forecast.get('signal', 'HOLD')
    target    = forecast.get('target_price', price)
    trend_pct = forecast.get('trend_pct', 0)
    news_lbl  = news.get('label', 'Neutral')
    mape      = backtest.get('mape')
    model_nm  = forecast.get('method', 'ML').replace('_', ' ').title()
    mape_str  = f"{mape:.1f}%" if mape is not None else "N/A"

    context = (
        f"Stock: {ticker} | Current: ₹{price:,.2f} | Signal: {signal}\n"
        f"{forecast.get('forecast_days', 30)}-Day Target: ₹{target:,.2f} ({trend_pct:+.1f}%)\n"
        f"RSI: {rsi} ({rsi_sig}) | MACD: {macd_dir} | Trend: {trend}\n"
        f"News: {news_lbl} ({news.get('positive',0)}+ / {news.get('negative',0)}-)\n"
        f"Backtest MAPE: {mape_str} on last 20 days | Model: {model_nm}\n"
        f"Composite score: {score}/100"
    )

    prompt = (
        f"Write a 2-3 sentence, fact-based investment note for {ticker} using ONLY "
        f"the data below. Cite actual numbers (RSI, target price, MAPE). "
        f"End with the key risk.\n\n{context}"
    )

    sys_msg = ("You are a quantitative analyst. Write factual, concise stock notes "
               "using provided data only. No hype. No speculation.")

    try:
        from ai_advisor import anthropic_client, openai_client
    except Exception:
        anthropic_client, openai_client = None, None

    # Try Anthropic first
    if anthropic_client:
        try:
            resp = anthropic_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=220,
                temperature=0.3,
                system=sys_msg,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()
        except Exception as e:
            logger.warning(f"Anthropic narrative failed for {ticker}: {e} — trying OpenAI...")

    # Fall through to OpenAI
    if openai_client:
        try:
            resp = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=220,
                temperature=0.3,
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user",   "content": prompt},
                ],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"OpenAI narrative failed for {ticker}: {e}")

    # Rule-based fallback
    direction = "rise" if trend_pct > 0 else "fall"
    mape_clause = f" Backtest MAPE: {mape_str}." if mape is not None else ""
    return (
        f"{ticker} shows a {signal} signal with a composite AI score of {score}/100.{mape_clause} "
        f"The {model_nm} model forecasts a {abs(trend_pct):.1f}% {direction} to ₹{target:,.2f}, "
        f"with RSI at {rsi} ({rsi_sig}) and {macd_dir} MACD momentum. "
        f"News sentiment is {news_lbl.lower()}. ⚠️ Past patterns do not guarantee future results."
    )
