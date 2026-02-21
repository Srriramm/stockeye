"""
News Monitor - Financial news fetching and sentiment analysis.
Integrates News API, RSS feeds, and Reddit for market sentiment.
"""

import os
import requests
import json
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

NEWS_API_KEY = os.getenv('NEWS_API_KEY', '')
REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID', '')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET', '')

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


# ─── News API Integration ──────────────────────────────────────

def fetch_stock_news(ticker, days=7, max_articles=10):
    """Fetch recent news for a specific stock using News API."""
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
                        'image': article.get('urlToImage', ''),
                        'sentiment': _quick_sentiment(article.get('title', '') + ' ' + (article.get('description', '') or '')),
                    })
        except Exception as e:
            print(f"News API error for {ticker}: {e}")

    # Fallback: Fetch from Google News RSS
    if not articles:
        articles = _fetch_google_news_rss(search_term, ticker)

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
            url = 'https://newsapi.org/v2/everything'
            params = {
                'q': '(NIFTY OR SENSEX OR "Indian stock market" OR NSE OR BSE) AND (stocks OR market OR trading)',
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
                        'sentiment': _quick_sentiment(article.get('title', '') + ' ' + (article.get('description', '') or '')),
                    })
        except Exception as e:
            print(f"Market news error: {e}")

    if not articles:
        articles = _fetch_google_news_rss('Indian stock market NIFTY SENSEX', 'MARKET')

    _set_news_cached(cache_key, articles)
    return articles


def _fetch_google_news_rss(query, ticker):
    """Fallback: Fetch news from Google News RSS."""
    articles = []
    try:
        from bs4 import BeautifulSoup
        encoded_query = requests.utils.quote(query)
        url = f'https://news.google.com/rss/search?q={encoded_query}+stock+market&hl=en-IN&gl=IN&ceid=IN:en'
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
                    'sentiment': _quick_sentiment(title + ' ' + description),
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


def _quick_sentiment(text):
    """Quick rule-based sentiment analysis without API calls."""
    if not text:
        return 'neutral'

    text_lower = text.lower()
    words = set(text_lower.split())

    positive_count = len(words.intersection(POSITIVE_WORDS))
    negative_count = len(words.intersection(NEGATIVE_WORDS))

    if positive_count > negative_count:
        return 'positive'
    elif negative_count > positive_count:
        return 'negative'
    return 'neutral'


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

    # Combine scores
    combined_score = (news_score + reddit.get('sentiment_score', 0)) / 2

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
