"""
News Monitor - Financial news fetching and sentiment analysis.
Integrates News API, RSS feeds, and Reddit for market sentiment.
"""

import os
import re
import requests
import json
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

try:
    import openai as _openai_module
except ImportError:
    _openai_module = None

try:
    import anthropic as _anthropic_module
except ImportError:
    _anthropic_module = None

logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

NEWS_API_KEY        = os.getenv('NEWS_API_KEY', '')
REDDIT_CLIENT_ID    = os.getenv('REDDIT_CLIENT_ID', '')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET', '')
_OPENAI_API_KEY     = os.getenv('OPENAI_API_KEY', '')
_ANTHROPIC_API_KEY  = os.getenv('ANTHROPIC_API_KEY', '')

# ─── Cache ──────────────────────────────────────────────────────
import time

_news_cache = {}
NEWS_CACHE_DURATION = 300  # 5 minutes


def _get_news_cached(key):
    if key in _news_cache:
        value, ts = _news_cache[key]
        if time.time() - ts < NEWS_CACHE_DURATION:
            return value
    return None


def _set_news_cached(key, value):
    _news_cache[key] = (value, time.time())


def clear_news_cache(ticker: str):
    """Bust the cached news for a ticker (e.g. after a fresh intelligence profile)."""
    _news_cache.pop(f'news_{ticker.upper()}', None)


# ─── Dynamic company name resolution (replaces static mapping) ──
# Resolved once per process and cached in-memory.  Any ticker —
# Nifty 50 constituent, mid-cap, ETF, newly listed — works without
# any code change because we pull the longName directly from yfinance.

_name_cache: dict = {}


def _get_search_term(ticker: str) -> str:
    """
    Return a search-friendly company name for *any* ticker.

    Resolution order:
      1. In-process cache (populated on first call)
      2. yfinance .NS suffix  →  .BO suffix  →  bare ticker
      3. Fallback: return the ticker itself (safe, never crashes)

    The returned name is stripped of legal suffixes (Limited, Ltd, etc.)
    that rarely appear in news headlines, so search precision is better.
    """
    if ticker in _name_cache:
        return _name_cache[ticker]

    name = None
    try:
        import yfinance as yf
        for suffix in ('.NS', '.BO', ''):
            try:
                info = yf.Ticker(f'{ticker}{suffix}').info
                candidate = info.get('longName') or info.get('shortName')
                if candidate:
                    name = candidate
                    break
            except Exception:
                continue
    except Exception:
        pass

    if name:
        # Strip legal / exchange suffixes that don't appear in news
        for sfx in (' Limited', ' Ltd.', ' Ltd', ' Pvt. Ltd', ' Pvt Ltd',
                    ' Private Limited', ' Corporation', ' Corp.', ' Inc.',
                    ' (India)', ' - NSE', ' - BSE'):
            name = name.replace(sfx, '')
        name = name.strip()
    else:
        name = ticker   # safe fallback

    _name_cache[ticker] = name
    logger.debug(f"[search_term] {ticker} → '{name}'")
    return name


# ─── Generic article patterns to exclude ───────────────────────

_GENERIC_PATTERNS = [
    'day trading guide',
    'ahead of market',
    '10 things that will',
    'weekly wrap',
    'market outlook for the week',
    'opening bell',
    'closing bell',
    'nifty prediction',
    'sensex prediction',
    'top stocks to watch',
    'stocks to buy today',
    'intraday supports',
    'intraday tips',
]


# Words that are too generic to use as a single relevance signal on their own.
# Any ticker whose company name contains these words will require EITHER the
# ticker symbol itself OR ≥2 significant name words to appear in the article.
_GENERIC_INDUSTRY_WORDS = {
    'oil', 'gas', 'bank', 'steel', 'coal', 'tech', 'power', 'energy',
    'motor', 'motors', 'pharma', 'finance', 'natural', 'industries',
    'enterprise', 'enterprises', 'limited', 'india', 'national',
}


def _is_relevant(article, ticker, company_name):
    """Return True only if the article title is about this specific stock."""
    title = (article.get('title', '') + ' ' + article.get('description', '')).lower()

    # Hard exclude generic daily guides regardless of stock
    for pat in _GENERIC_PATTERNS:
        if pat in title:
            return False

    ticker_lower = ticker.lower()

    # Direct ticker mention is always a hit
    if ticker_lower in title:
        return True

    # Collect significant words from the company name (>3 chars, not generic)
    significant_words = [
        w for w in company_name.lower().split()
        if len(w) > 3 and w not in _GENERIC_INDUSTRY_WORDS
    ]

    if significant_words:
        hits = sum(1 for w in significant_words if w in title)
        # Require the article to mention at least 2 significant name words,
        # OR at least 1 if none of the name words are ambiguous/generic.
        threshold = 2 if any(w in _GENERIC_INDUSTRY_WORDS
                             for w in company_name.lower().split()) else 1
        return hits >= threshold

    # Fallback: any word longer than 3 chars from company name matches
    for word in company_name.lower().split():
        if len(word) > 3 and word in title:
            return True
    return False


def _deduplicate(articles):
    """Remove articles with duplicate or near-identical titles."""
    seen = set()
    out = []
    for a in articles:
        key = ' '.join(a.get('title', '').lower().split())[:80]
        if key and key not in seen:
            seen.add(key)
            out.append(a)
    return out


# ─── News API Integration ──────────────────────────────────────

def fetch_stock_news(ticker, days=7, max_articles=10, intelligence_profile=None):
    """
    Fetch recent news for a stock.

    When `intelligence_profile` is supplied (from intelligence_engine), AI-generated
    queries target the ACTUAL price drivers (e.g. gold prices + Fed rates for GOLDBEES).
    Falls back to company-name lookup when no profile is available.
    """
    ticker = ticker.upper()
    for _sfx in ('.NS', '.BO'):
        if ticker.endswith(_sfx):
            ticker = ticker[:-len(_sfx)]
            break

    cache_key = f"news_{ticker}"
    cached = _get_news_cached(cache_key)
    if cached:
        return cached

    if intelligence_profile and intelligence_profile.get('news_queries'):
        articles = _fetch_via_intelligence(
            ticker, intelligence_profile['news_queries'], days, max_articles
        )
    else:
        articles = _fetch_via_company_name(ticker, days, max_articles)

    _enrich_with_ai_sentiment(articles)
    _set_news_cached(cache_key, articles)
    return articles


def _fetch_via_intelligence(ticker, queries, days, max_articles):
    """
    Fetch using AI-generated, driver-specific queries.
    Each query is a natural phrase ("gold price India"), not an exact company name.
    No strict _is_relevant filter — the AI scoped the queries.
    """
    from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    all_articles = []

    for query in queries[:4]:
        fetched = []
        if NEWS_API_KEY:
            try:
                resp = requests.get(
                    'https://newsapi.org/v2/everything',
                    params={
                        'q': query,
                        'from': from_date,
                        'sortBy': 'relevancy',
                        'language': 'en',
                        'pageSize': 5,
                        'apiKey': NEWS_API_KEY,
                    },
                    timeout=8,
                )
                if resp.status_code == 200:
                    for a in resp.json().get('articles', []):
                        fetched.append({
                            'title':        a.get('title', ''),
                            'description':  a.get('description', ''),
                            'url':          a.get('url', ''),
                            'source':       a.get('source', {}).get('name', 'Unknown'),
                            'published_at': a.get('publishedAt', ''),
                            'image':        a.get('urlToImage', ''),
                            'sentiment':    'neutral',
                            'query_tag':    query,
                        })
            except Exception as e:
                logger.debug(f"[intelligence news] NewsAPI error for '{query}': {e}")

        if not fetched:
            fetched = _fetch_google_news_rss(query, ticker)
        # Last resort: keyword-scan Indian financial RSS (ET, Moneycontrol, etc.)
        if not fetched:
            fetched = _fetch_indian_rss_for_query(query)

        all_articles.extend(fetched)

    all_articles = _deduplicate(all_articles)
    all_articles = [a for a in all_articles if not _is_generic(a)]
    return all_articles[:max_articles]


def _is_generic(article):
    """Return True for articles that are purely generic market noise."""
    title = (article.get('title', '') + ' ' + article.get('description', '')).lower()
    return any(pat in title for pat in _GENERIC_PATTERNS)


def _fetch_via_company_name(ticker, days, max_articles):
    """Legacy fetch: exact phrase search on company/ETF name."""
    search_term = _get_search_term(ticker)
    articles = []

    if NEWS_API_KEY:
        try:
            from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            resp = requests.get(
                'https://newsapi.org/v2/everything',
                params={
                    'q': f'"{search_term}" AND (stock OR share OR NSE OR BSE OR market)',
                    'from': from_date,
                    'sortBy': 'relevancy',
                    'language': 'en',
                    'pageSize': max_articles * 2,
                    'apiKey': NEWS_API_KEY,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                for a in resp.json().get('articles', []):
                    articles.append({
                        'title':        a.get('title', ''),
                        'description':  a.get('description', ''),
                        'url':          a.get('url', ''),
                        'source':       a.get('source', {}).get('name', 'Unknown'),
                        'published_at': a.get('publishedAt', ''),
                        'image':        a.get('urlToImage', ''),
                        'sentiment':    'neutral',
                    })
        except Exception as e:
            logger.debug(f"[company news] NewsAPI error for {ticker}: {e}")

    if not articles:
        rss_query = search_term if search_term != ticker else f'{ticker} stock NSE'
        articles = _fetch_google_news_rss(rss_query, ticker)

    articles = [a for a in articles if _is_relevant(a, ticker, search_term)]
    articles = _deduplicate(articles)
    return articles[:max_articles]


def fetch_market_news(max_articles=15):
    """Fetch general Indian stock market news."""
    cache_key = "market_news"
    cached = _get_news_cached(cache_key)
    if cached:
        return cached

    articles = []

    if NEWS_API_KEY:
        try:
            from_date = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
            url = 'https://newsapi.org/v2/everything'
            params = {
                'q': '(NIFTY OR SENSEX OR "Indian stock market" OR NSE OR BSE) AND (stocks OR market OR trading)',
                'from': from_date,
                'sortBy': 'publishedAt',
                'language': 'en',
                'pageSize': max_articles,
                'apiKey': NEWS_API_KEY,
            }
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                for article in data.get('articles', []):
                    articles.append({
                        'title': article.get('title', ''),
                        'description': article.get('description', ''),
                        'url': article.get('url', ''),
                        'source': article.get('source', {}).get('name', 'Unknown'),
                        'published_at': article.get('publishedAt', ''),
                        'sentiment': 'neutral',  # will be overwritten by AI below
                    })
        except Exception as e:
            print(f"Market news error: {e}")

    if not articles:
        articles = _fetch_indian_market_news_rss(max_articles)

    # ── AI-classify all headlines in ONE call ───────────────────────────────
    _enrich_with_ai_sentiment(articles)

    _set_news_cached(cache_key, articles)
    return articles


def _fetch_indian_market_news_rss(max_articles=15):
    """Fetch Indian stock market news from reliable financial RSS feeds."""
    # Dedicated Indian financial news RSS feeds (more reliable than Google News RSS)
    FEED_URLS = [
        ('Economic Times Markets', 'https://economictimes.indiatimes.com/markets/stocks/rss.cms'),
        ('Moneycontrol', 'https://www.moneycontrol.com/rss/latestnews.xml'),
        ('Business Standard', 'https://www.business-standard.com/rss/markets-106.rss'),
        ('LiveMint Markets', 'https://www.livemint.com/rss/markets'),
    ]
    articles = []
    for source_name, feed_url in FEED_URLS:
        if len(articles) >= max_articles:
            break
        try:
            resp = requests.get(feed_url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
            if resp.status_code != 200:
                continue
            for item in _parse_rss_items(resp.content)[:6]:
                title    = _item_text(item.find('title'))
                desc     = _item_text(item.find('description'))[:200]
                pub_date = _item_text(item.find('pubDate'))
                link_tag = item.find('link')
                link = ''
                if link_tag:
                    link = link_tag.get_text(strip=True) or link_tag.get('href', '')
                if title:
                    articles.append({
                        'title':        title,
                        'description':  desc,
                        'url':          link,
                        'source':       source_name,
                        'published_at': pub_date,
                        'sentiment':    'neutral',
                    })
        except Exception as e:
            logger.debug(f"RSS feed error ({source_name}): {e}")
    return articles[:max_articles]


def _parse_rss_items(content: bytes):
    """
    Parse RSS/XML bytes into BeautifulSoup <item> tags.
    Tries parsers in order: lxml-xml → xml → html.parser.
    Never raises — returns [] on any failure.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    for parser in ('lxml-xml', 'xml', 'lxml', 'html.parser'):
        try:
            soup = BeautifulSoup(content, parser)
            items = soup.find_all('item')
            if items:
                return items
        except Exception:
            continue
    return []


def _item_text(tag) -> str:
    """Safely extract text from a BS4 tag, handling missing tags."""
    if tag is None:
        return ''
    return (tag.get_text(strip=True) if hasattr(tag, 'get_text') else str(tag)).strip()


def _fetch_google_news_rss(query, ticker):
    """Fallback: Fetch news from Google News RSS (parser-resilient)."""
    articles = []
    try:
        encoded_query = requests.utils.quote(query)
        url = f'https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en'
        response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})

        if response.status_code == 200:
            for item in _parse_rss_items(response.content)[:10]:
                title   = _item_text(item.find('title'))
                desc    = _item_text(item.find('description'))[:200]
                pub     = _item_text(item.find('pubDate'))
                source  = _item_text(item.find('source')) or 'Google News'
                # <link> in RSS is a text node *between* tags; navigate differently
                link_tag = item.find('link')
                link = ''
                if link_tag:
                    link = link_tag.get_text(strip=True) or link_tag.get('href', '')
                if title:
                    articles.append({
                        'title':        title,
                        'description':  desc,
                        'url':          link,
                        'source':       source,
                        'published_at': pub,
                        'image':        '',
                        'sentiment':    'neutral',
                    })
    except Exception as e:
        logger.debug(f"Google News RSS error for '{query}': {e}")

    return articles


def _fetch_indian_rss_for_query(query: str) -> list:
    """
    Scan Indian financial RSS feeds (ET, Moneycontrol, etc.) and return
    articles whose title/description match the query keywords.
    Used as a last-resort fallback when NewsAPI and Google RSS both fail.
    """
    keywords = [w.lower() for w in query.split() if len(w) > 3]
    if not keywords:
        return []

    all_articles = _fetch_indian_market_news_rss(max_articles=40)

    matched = []
    for a in all_articles:
        text = (a.get('title', '') + ' ' + a.get('description', '')).lower()
        # Require at least 2 keyword hits, or 1 if query is short (≤2 significant words)
        hits = sum(1 for kw in keywords if kw in text)
        if hits >= min(2, len(keywords)):
            a['query_tag'] = query
            matched.append(a)

    return matched[:3]


# ─── Reddit Sentiment ──────────────────────────────────────────

def get_reddit_sentiment(ticker, subreddits=None):
    """Fetch Reddit discussions and sentiment for a stock."""
    if subreddits is None:
        subreddits = ['IndiaInvestments', 'IndianStockMarket', 'StockMarketIndia']

    cache_key = f"reddit_{ticker}"
    cached = _get_news_cached(cache_key)
    if cached:
        return cached

    discussions = []
    overall_sentiment = {'positive': 0, 'negative': 0, 'neutral': 0}

    # Try using PRAW (Reddit API)
    if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
        try:
            import praw
            reddit = praw.Reddit(
                client_id=REDDIT_CLIENT_ID,
                client_secret=REDDIT_CLIENT_SECRET,
                user_agent='StockAssistant/1.0'
            )

            search_term = _get_search_term(ticker)

            for sub_name in subreddits:
                try:
                    subreddit = reddit.subreddit(sub_name)
                    for submission in subreddit.search(search_term, limit=5, time_filter='month'):
                        sentiment = _quick_sentiment(submission.title + ' ' + (submission.selftext[:500] if submission.selftext else ''))
                        overall_sentiment[sentiment] += 1

                        discussions.append({
                            'title': submission.title,
                            'subreddit': sub_name,
                            'score': submission.score,
                            'num_comments': submission.num_comments,
                            'url': f"https://reddit.com{submission.permalink}",
                            'created': datetime.fromtimestamp(submission.created_utc).isoformat(),
                            'sentiment': sentiment,
                        })
                except Exception as e:
                    logger.debug(f"Failed to process Reddit submission: {e}")
                    continue

        except ImportError:
            print("PRAW not installed, skipping Reddit sentiment")
        except Exception as e:
            print(f"Reddit API error: {e}")

    # Calculate overall sentiment score
    total = sum(overall_sentiment.values()) or 1
    sentiment_score = (overall_sentiment['positive'] - overall_sentiment['negative']) / total

    result = {
        'ticker': ticker.upper(),
        'discussions': discussions[:10],
        'sentiment_breakdown': overall_sentiment,
        'sentiment_score': round(sentiment_score, 2),  # -1 to 1
        'sentiment_label': 'Positive' if sentiment_score > 0.2 else ('Negative' if sentiment_score < -0.2 else 'Neutral'),
        'total_mentions': total,
    }

    _set_news_cached(cache_key, result)
    return result


# ─── Sentiment Analysis ────────────────────────────────────────

# Word lists for quick sentiment without OpenAI
POSITIVE_WORDS = {
    'bullish', 'surge', 'gain', 'profit', 'rally', 'growth', 'outperform', 'upgrade',
    'buy', 'strong', 'positive', 'record', 'high', 'boom', 'breakthrough', 'momentum',
    'soar', 'beat', 'expand', 'dividend', 'revenue', 'earnings', 'upside', 'recovery',
    'optimistic', 'opportunity', 'favorable', 'promising', 'success', 'innovation',
    'up', 'rise', 'jump', 'climb', 'advance', 'improve', 'boost', 'best', 'top',
}

NEGATIVE_WORDS = {
    'bearish', 'crash', 'loss', 'decline', 'fall', 'drop', 'downgrade', 'sell',
    'weak', 'negative', 'low', 'concern', 'risk', 'warning', 'trouble', 'debt',
    'fear', 'miss', 'cut', 'worst', 'bottom', 'crisis', 'fraud', 'scandal',
    'pessimistic', 'volatile', 'uncertain', 'recession', 'inflation', 'default',
    'down', 'sink', 'plunge', 'slump', 'struggle', 'fail', 'pressure', 'threat',
}


# Common negation words — when one precedes a sentiment word, flip its polarity
_NEGATION_WORDS = {'not', 'no', 'never', 'neither', 'without', 'unable', 'fail',
                   'failed', 'fails', 'cannot', "can't", "won't", "doesn't",
                   "isn't", "wasn't", "aren't", 'hardly', 'barely', 'rarely'}


def _quick_sentiment(text):
    """Rule-based sentiment — used only as a last-resort fallback."""
    if not text:
        return 'neutral'

    text_lower = text.lower()
    tokens = re.findall(r"[\w']+", text_lower)

    positive_count = 0
    negative_count = 0

    for i, word in enumerate(tokens):
        negated = i > 0 and tokens[i - 1] in _NEGATION_WORDS
        if word in POSITIVE_WORDS:
            if negated:
                negative_count += 1
            else:
                positive_count += 1
        elif word in NEGATIVE_WORDS:
            if negated:
                positive_count += 1
            else:
                negative_count += 1

    if positive_count > negative_count:
        return 'positive'
    elif negative_count > positive_count:
        return 'negative'
    return 'neutral'


def _ai_sentiment_batch(headlines: list[str]) -> list[str]:
    """
    Send all headlines in ONE API call and get back a list of
    'positive' | 'negative' | 'neutral' labels.

    Tries OpenAI (gpt-4o-mini) first, then Anthropic (claude-haiku),
    then rule-based fallback.
    """
    if not headlines:
        return []

    numbered = '\n'.join(f"{i+1}. {h}" for i, h in enumerate(headlines))
    system_prompt = (
        "You are a financial news sentiment classifier for Indian stock markets. "
        "For each numbered headline, output ONLY a JSON array of strings where each "
        "string is exactly one of: positive, negative, neutral. "
        "The array length MUST equal the number of input headlines. "
        "Return ONLY the JSON array, no explanation."
    )
    user_prompt = f"Classify the sentiment of each headline:\n{numbered}"

    # ── Try OpenAI first ────────────────────────────────────────────
    if _openai_module and _OPENAI_API_KEY:
        try:
            client = _openai_module.OpenAI(api_key=_OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model='gpt-4o-mini',
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user',   'content': user_prompt},
                ],
                max_tokens=len(headlines) * 12,
                temperature=0,
            )
            raw = resp.choices[0].message.content.strip()
            # Strip markdown code fences if present (gpt-4o-mini sometimes wraps in ```json ... ```)
            raw = re.sub(r'^```[a-z]*\s*', '', raw, flags=re.IGNORECASE)
            raw = re.sub(r'\s*```$', '', raw)
            labels = json.loads(raw)
            if isinstance(labels, list) and len(labels) == len(headlines):
                cleaned = []
                for lbl in labels:
                    s = str(lbl).lower().strip()
                    cleaned.append(s if s in ('positive', 'negative', 'neutral') else 'neutral')
                logger.info(f"AI sentiment (OpenAI): classified {len(headlines)} headlines")
                return cleaned
        except Exception as e:
            logger.warning(f"OpenAI batch sentiment failed: {e}")

    # ── Try Anthropic as fallback ────────────────────────────────────
    if _anthropic_module and _ANTHROPIC_API_KEY:
        try:
            client = _anthropic_module.Anthropic(api_key=_ANTHROPIC_API_KEY)
            msg = client.messages.create(
                model='claude-haiku-20240307',
                max_tokens=len(headlines) * 12,
                messages=[{'role': 'user', 'content': f"{system_prompt}\n\n{user_prompt}"}],
            )
            raw = msg.content[0].text.strip()
            labels = json.loads(raw)
            if isinstance(labels, list) and len(labels) == len(headlines):
                cleaned = []
                for lbl in labels:
                    s = str(lbl).lower().strip()
                    cleaned.append(s if s in ('positive', 'negative', 'neutral') else 'neutral')
                logger.info(f"AI sentiment (Anthropic): classified {len(headlines)} headlines")
                return cleaned
        except Exception as e:
            logger.warning(f"Anthropic batch sentiment failed: {e}")

    # ── Final rule-based fallback ────────────────────────────────────
    logger.info("Falling back to rule-based sentiment (no AI key available)")
    return [_quick_sentiment(h) for h in headlines]


def _enrich_with_ai_sentiment(articles: list) -> None:
    """In-place: set 'sentiment' on each article using batched AI."""
    if not articles:
        return
    headlines = [
        (a.get('title') or '') + '. ' + (a.get('description') or '')
        for a in articles
    ]
    labels = _ai_sentiment_batch(headlines)
    for article, label in zip(articles, labels):
        article['sentiment'] = label



def analyze_sentiment_ai(text, openai_client=None):
    """
    Use OpenAI for more accurate sentiment analysis.
    Falls back to rule-based if OpenAI not available.
    """
    if not openai_client:
        return _quick_sentiment(text)

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": "Analyze the sentiment of this financial news text. Respond with exactly one word: 'positive', 'negative', or 'neutral'."
                },
                {"role": "user", "content": text[:500]}
            ],
            max_tokens=10,
            temperature=0,
        )
        sentiment = response.choices[0].message.content.strip().lower()
        if sentiment in ('positive', 'negative', 'neutral'):
            return sentiment
        return 'neutral'
    except Exception as e:
        logger.debug(f"AI sentiment analysis failed: {e}")
        return _quick_sentiment(text)


def get_news_summary(ticker):
    """Get a formatted summary of news and sentiment for a stock."""
    news = fetch_stock_news(ticker)
    reddit = get_reddit_sentiment(ticker)

    # Count news sentiment
    news_sentiment = {'positive': 0, 'negative': 0, 'neutral': 0}
    for article in news:
        s = article.get('sentiment', 'neutral')
        news_sentiment[s] = news_sentiment.get(s, 0) + 1

    total_news = len(news)
    news_score = ((news_sentiment['positive'] - news_sentiment['negative']) / total_news) if total_news > 0 else 0

    # Combine scores — only include Reddit when it actually has data so that
    # an unconfigured Reddit account doesn't drag every score toward neutral.
    scores = [news_score]
    if reddit.get('discussions'):
        scores.append(reddit['sentiment_score'])
    combined_score = sum(scores) / len(scores)

    return {
        'ticker': ticker.upper(),
        'news_articles': news[:5],
        'news_sentiment': news_sentiment,
        'news_sentiment_score': round(news_score, 2),
        'reddit_sentiment': reddit,
        'combined_sentiment_score': round(combined_score, 2),
        'combined_sentiment_label': 'Positive' if combined_score > 0.2 else ('Negative' if combined_score < -0.2 else 'Neutral'),
        'summary': _generate_news_summary_text(ticker, news, news_sentiment, reddit),
    }


def _generate_news_summary_text(ticker, news, news_sentiment, reddit):
    """Generate a human-readable news summary."""
    lines = [f"News & Sentiment Summary for {ticker.upper()}:"]

    if news:
        lines.append(f"\nRecent News ({len(news)} articles):")
        for i, article in enumerate(news[:3], 1):
            sentiment_emoji = '🟢' if article['sentiment'] == 'positive' else ('🔴' if article['sentiment'] == 'negative' else '🟡')
            lines.append(f"  {i}. {sentiment_emoji} {article['title']}")
            lines.append(f"     Source: {article['source']}")
    else:
        lines.append("\nNo recent news articles found.")

    lines.append(f"\nNews Sentiment: {news_sentiment['positive']} positive, {news_sentiment['negative']} negative, {news_sentiment['neutral']} neutral")

    if reddit.get('discussions'):
        lines.append(f"\nReddit Discussions: {reddit.get('total_mentions', 0)} mentions")
        lines.append(f"Reddit Sentiment: {reddit.get('sentiment_label', 'Neutral')}")
    else:
        lines.append("\nNo recent Reddit discussions found.")

    return '\n'.join(lines)
