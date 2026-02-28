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


# ─── Company name mapping for search ───────────────────────────

TICKER_TO_COMPANY = {
    'RELIANCE': 'Reliance Industries',
    'TCS': 'TCS Tata Consultancy',
    'HDFCBANK': 'HDFC Bank',
    'INFY': 'Infosys',
    'ICICIBANK': 'ICICI Bank',
    'HINDUNILVR': 'Hindustan Unilever',
    'SBIN': 'State Bank of India SBI',
    'BHARTIARTL': 'Bharti Airtel',
    'ITC': 'ITC Limited',
    'KOTAKBANK': 'Kotak Mahindra Bank',
    'LT': 'Larsen Toubro',
    'AXISBANK': 'Axis Bank',
    'WIPRO': 'Wipro',
    'HCLTECH': 'HCL Technologies',
    'MARUTI': 'Maruti Suzuki',
    'SUNPHARMA': 'Sun Pharma',
    'TATAMOTORS': 'Tata Motors',
    'TATASTEEL': 'Tata Steel',
    'BAJFINANCE': 'Bajaj Finance',
    'TITAN': 'Titan Company',
    'ADANIENT': 'Adani Enterprises',
    'COALINDIA': 'Coal India',
    'ONGC': 'ONGC Oil Natural Gas',
    'DRREDDY': 'Dr Reddy',
    'CIPLA': 'Cipla',
    'TECHM': 'Tech Mahindra',
}


def _get_search_term(ticker):
    """Convert ticker to search-friendly company name."""
    return TICKER_TO_COMPANY.get(ticker.upper(), ticker)


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

def fetch_stock_news(ticker, days=7, max_articles=10):
    """Fetch recent news for a specific stock using News API."""
    ticker = ticker.upper()
    # Strip exchange suffix so TCS.NS looks up the same as TCS
    for _sfx in ('.NS', '.BO'):
        if ticker.endswith(_sfx):
            ticker = ticker[:-len(_sfx)]
            break
    cache_key = f"news_{ticker}"
    cached = _get_news_cached(cache_key)
    if cached:
        return cached

    search_term = _get_search_term(ticker)
    articles = []

    # Try News API
    if NEWS_API_KEY:
        try:
            from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            url = 'https://newsapi.org/v2/everything'
            params = {
                'q': f'"{search_term}" AND (stock OR share OR NSE OR BSE OR market)',
                'from': from_date,
                'sortBy': 'relevancy',
                'language': 'en',
                'pageSize': max_articles * 2,  # fetch extra to compensate for filtering
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
                        'image': article.get('urlToImage', ''),
                        'sentiment': 'neutral',  # will be overwritten by AI below
                    })
        except Exception as e:
            print(f"News API error for {ticker}: {e}")

    # Fallback: Fetch from Google News RSS (company-specific query, no generic suffix)
    if not articles:
        articles = _fetch_google_news_rss(search_term, ticker)

    # Filter to stock-relevant articles only, then deduplicate
    articles = [a for a in articles if _is_relevant(a, ticker, search_term)]
    articles = _deduplicate(articles)
    articles = articles[:max_articles]

    # ── AI-classify all headlines in ONE call ───────────────────────────────
    _enrich_with_ai_sentiment(articles)

    _set_news_cached(cache_key, articles)
    return articles


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
    try:
        from bs4 import BeautifulSoup
        for source_name, feed_url in FEED_URLS:
            if len(articles) >= max_articles:
                break
            try:
                resp = requests.get(feed_url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
                if resp.status_code != 200:
                    continue
                soup = BeautifulSoup(resp.content, 'xml')
                items = soup.find_all('item')[:6]
                for item in items:
                    title = item.title.get_text(strip=True) if item.title else ''
                    description = item.description.get_text(strip=True)[:200] if item.description else ''
                    link = item.link.get_text(strip=True) if item.link else ''
                    pub_date = item.pubDate.get_text(strip=True) if item.pubDate else ''
                    if title:
                        articles.append({
                            'title': title,
                            'description': description,
                            'url': link,
                            'source': source_name,
                            'published_at': pub_date,
                            'sentiment': 'neutral',
                        })
            except Exception as e:
                logger.debug(f"RSS feed error ({source_name}): {e}")
                continue
    except Exception as e:
        logger.error(f"Indian market RSS fetch error: {e}")
    return articles[:max_articles]


def _fetch_google_news_rss(query, ticker):
    """Fallback: Fetch news from Google News RSS."""
    articles = []
    try:
        from bs4 import BeautifulSoup
        encoded_query = requests.utils.quote(query)
        url = f'https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en'
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'xml')
            items = soup.find_all('item')[:10]

            for item in items:
                title = item.title.text if item.title else ''
                description = item.description.text if item.description else ''
                link = item.link.text if item.link else ''
                pub_date = item.pubDate.text if item.pubDate else ''
                source = item.source.text if item.source else 'Google News'

                articles.append({
                    'title': title,
                    'description': description[:200],
                    'url': link,
                    'source': source,
                    'published_at': pub_date,
                    'image': '',
                    'sentiment': 'neutral',  # enriched by caller via _enrich_with_ai_sentiment
                })
    except Exception as e:
        print(f"Google News RSS error: {e}")

    return articles


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
