"""
Intelligence Engine — AI-powered stock profiling.

When a stock is added to the monitor, this module asks Claude/GPT:
  "What IS this asset, and what actually moves its price?"

The result is a *profile* that drives:
  - contextual news fetching (real price-driver queries, not just company name)
  - monitor card context (key drivers, asset type, what to watch)

Example — GOLDBEES:
  Without intelligence: searches "GOLDBEES" → 0 articles
  With intelligence:    searches ["gold price India", "Federal Reserve rates",
                                  "USD rupee exchange", "gold ETF NAV"] → rich context
"""

import json
import logging
import time

logger = logging.getLogger(__name__)

# ── In-memory cache (profiles are stable; 6h TTL) ───────────────
_profile_cache: dict = {}
_CACHE_TTL = 6 * 3600  # 6 hours


def _get_cached(ticker: str):
    entry = _profile_cache.get(ticker)
    if entry and time.time() < entry['exp']:
        return entry['val']
    return None


def _set_cached(ticker: str, val: dict):
    _profile_cache[ticker] = {'val': val, 'exp': time.time() + _CACHE_TTL}


# ── Public API ───────────────────────────────────────────────────

def get_stock_profile(ticker: str, company_name: str = None) -> dict:
    """
    Return the intelligence profile for a ticker.
    Generates via AI on first call; subsequent calls use cache.

    Profile schema:
      type         : "stock" | "index_ETF" | "commodity_ETF" | "sector_ETF" | "liquid_ETF"
      sector       : human-readable sector / category
      underlying   : what the ETF tracks (None for stocks)
      key_drivers  : list[str] — top 3-5 factors that move this asset's price
      news_queries : list[str] — search queries that find price-relevant news
      watch_context: one sentence describing the asset and its primary driver
    """
    # Strip exchange suffix for cache key
    clean = ticker.upper()
    for sfx in ('.NS', '.BO'):
        if clean.endswith(sfx):
            clean = clean[:-len(sfx)]
            break

    cached = _get_cached(clean)
    if cached:
        return cached

    profile = _generate_profile(clean, company_name)
    _set_cached(clean, profile)
    return profile


def invalidate_profile(ticker: str):
    """Force re-generation next time (call after manual override)."""
    clean = ticker.upper().replace('.NS', '').replace('.BO', '')
    _profile_cache.pop(clean, None)


# ── Profile Generation ───────────────────────────────────────────

_PROMPT_TEMPLATE = """You are a financial analyst specializing in Indian equity markets (NSE/BSE).

Analyze the asset: {ticker}{name_hint}

Return ONLY valid JSON — no markdown, no explanation — with exactly this structure:
{{
  "type": "<stock|index_ETF|commodity_ETF|sector_ETF|liquid_ETF>",
  "sector": "<concise sector or category>",
  "underlying": "<what the ETF tracks, or null for stocks>",
  "key_drivers": ["<driver 1>", "<driver 2>", "<driver 3>"],
  "news_queries": ["<query 1>", "<query 2>", "<query 3>", "<query 4>"],
  "watch_context": "<one sentence: what this asset is and its #1 price driver>"
}}

Rules for news_queries — these are REAL NewsAPI / Google News search terms:
- Each query must find articles about actual price-moving events for this asset
- For ETFs: use the UNDERLYING asset as the primary query topic, NOT the ETF brand name
- For GOLDBEES: ["gold price India", "Federal Reserve interest rate", "USD rupee exchange rate", "gold ETF India NAV"]
- For NIFTYBEES: ["Nifty 50 index level", "FII foreign investor India", "RBI monetary policy", "Sensex market"]
- For BANKBEES: ["Bank Nifty index", "RBI interest rate", "banking sector India", "NPA credit growth"]
- For a bank stock like HDFCBANK: ["HDFC Bank quarterly results", "RBI banking regulation", "credit growth India", "HDFC Bank NPA"]
- For RELIANCE: ["Reliance Industries quarterly earnings", "Reliance Jio subscriber", "petrochemical crude oil", "Mukesh Ambani"]
- Queries must be 2-6 words; avoid the exact ticker symbol in queries (newsAPIs rarely index ticker symbols)
- Max 4 queries

Rules for key_drivers:
- Be specific and actionable (not generic like "market sentiment")
- For commodity ETFs: include the commodity price, USD/INR, and relevant macro (Fed rates, inflation)
- For index ETFs: include FII/DII flows, index PE, RBI policy
- For individual stocks: include earnings, sector-specific catalyst, and one macro factor"""

_SYSTEM_MSG = ("You are a quantitative analyst. Output only valid JSON. "
               "No markdown fences. No prose. Just the JSON object.")


def _generate_profile(ticker: str, company_name: str = None) -> dict:
    """Call Claude → OpenAI → rule-based fallback to build the profile."""
    name_hint = f" (also known as '{company_name}')" if company_name else ""
    prompt = _PROMPT_TEMPLATE.format(ticker=ticker, name_hint=name_hint)

    try:
        from ai_advisor import anthropic_client, openai_client
    except Exception:
        anthropic_client, openai_client = None, None

    raw = None

    # Try Anthropic (Claude Haiku — fast, cheap)
    if anthropic_client:
        try:
            resp = anthropic_client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=400,
                temperature=0,
                system=_SYSTEM_MSG,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
        except Exception as e:
            logger.warning(f"[intelligence] Anthropic profile failed for {ticker}: {e}")

    # Try OpenAI fallback
    if raw is None and openai_client:
        try:
            resp = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=400,
                temperature=0,
                messages=[
                    {"role": "system", "content": _SYSTEM_MSG},
                    {"role": "user",   "content": prompt},
                ],
            )
            raw = resp.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"[intelligence] OpenAI profile failed for {ticker}: {e}")

    if raw:
        try:
            # Strip markdown fences if the model added them anyway
            if raw.startswith('```'):
                raw = raw.split('```')[1]
                if raw.startswith('json'):
                    raw = raw[4:]
            profile = json.loads(raw)
            # Validate required keys
            required = {'type', 'sector', 'key_drivers', 'news_queries', 'watch_context'}
            if required.issubset(profile.keys()):
                profile.setdefault('underlying', None)
                logger.info(f"[intelligence] AI profile generated for {ticker}: {profile['type']} / {profile['sector']}")
                return profile
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"[intelligence] Profile parse failed for {ticker}: {e} | raw={raw[:200]}")

    # ── Rule-based fallback (no AI keys or parse failure) ────────
    return _rule_based_profile(ticker, company_name)


def _rule_based_profile(ticker: str, company_name: str = None) -> dict:
    """
    Dynamic fallback when AI is unavailable.

    Uses yfinance to discover the asset's real name, sector, and type —
    so this works for any ticker, not just hardcoded ones.
    """
    name = company_name or ticker
    sector = ''
    industry = ''
    quote_type = 'EQUITY'
    category = ''   # ETF category (e.g. "Precious Metals")

    try:
        import yfinance as yf
        for suffix in ('.NS', '.BO', ''):
            try:
                info = yf.Ticker(f'{ticker}{suffix}').info
                candidate = info.get('longName') or info.get('shortName')
                if candidate:
                    name = candidate
                    sector    = info.get('sector', '')
                    industry  = info.get('industry', '')
                    quote_type = info.get('quoteType', 'EQUITY').upper()
                    category  = info.get('category', '')
                    break
            except Exception:
                continue
    except Exception:
        pass

    # Strip legal suffixes so they don't clutter search queries
    clean_name = name
    for sfx in (' Limited', ' Ltd.', ' Ltd', ' Pvt. Ltd', ' Pvt Ltd',
                ' Private Limited', ' Corporation', ' Corp.'):
        clean_name = clean_name.replace(sfx, '')
    clean_name = clean_name.strip()

    is_etf = quote_type in ('ETF', 'MUTUALFUND') or 'ETF' in name.upper()

    if is_etf:
        # For ETFs, drive news by the UNDERLYING asset, not the fund brand
        underlying = category or industry or sector or 'market'
        return {
            'type': 'ETF',
            'sector': category or sector or 'ETF',
            'underlying': underlying,
            'key_drivers': [
                f'{underlying} price movement',
                'FII/DII institutional fund flows',
                'RBI monetary policy',
                'India macroeconomic outlook',
            ],
            'news_queries': [
                f'{underlying} price India',
                f'{clean_name} ETF NAV',
                f'{underlying} market outlook',
                'India ETF fund flows',
            ],
            'watch_context': (
                f'{clean_name} is an ETF tracking {underlying}. '
                f'Primary driver: {underlying} price and institutional flows.'
            ),
        }

    # ── Individual stock: sector-aware generic queries ───────────
    sector_query = f'{sector} sector India' if sector else 'India stock market'
    return {
        'type': 'stock',
        'sector': sector or industry or 'Equity',
        'underlying': None,
        'key_drivers': [
            'Quarterly earnings & guidance',
            f'{sector} sector momentum' if sector else 'Sector momentum',
            'Institutional (FII/DII) flows',
            'Nifty 50 broader market trend',
        ],
        'news_queries': [
            f'{clean_name} quarterly results',
            f'{clean_name} NSE stock',
            sector_query,
            f'{clean_name} earnings outlook',
        ],
        'watch_context': (
            f'{clean_name} ({sector or "Equity"}). '
            f'Key drivers: earnings performance and {sector.lower() if sector else "sector"} momentum.'
        ),
    }
