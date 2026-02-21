"""
News and Sentiment Tools for MCP Server
Fetch news articles and sentiment analysis
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

import json
from news_monitor import (
    fetch_stock_news as _fetch_stock_news,
    fetch_market_news as _fetch_market_news,
    get_news_summary as _get_news_summary
)


def get_tool_definitions():
    """Return news tool definitions for MCP server."""
    return [
        {
            "name": "get_stock_news",
            "description": "Get recent news articles for a specific stock. Returns headlines, summaries, and publication dates.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of articles to return",
                        "default": 10
                    }
                },
                "required": ["ticker"]
            }
        },
        {
            "name": "get_market_news",
            "description": "Get general market news for Indian stock markets (NIFTY, SENSEX, etc.).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of articles to return",
                        "default": 15
                    }
                },
                "required": []
            }
        },
        {
            "name": "get_sentiment_analysis",
            "description": "Get comprehensive sentiment analysis for a stock from news articles and social media. Returns overall sentiment score, label (positive/negative/neutral), and individual article sentiments.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol"
                    }
                },
                "required": ["ticker"]
            }
        }
    ]


def execute_tool(name, arguments):
    """Execute a news tool and return the result."""
    try:
        if name == "get_stock_news":
            ticker = arguments["ticker"].upper()
            news = _fetch_stock_news(ticker)
            limit = arguments.get("limit", 10)
            return {"success": True, "data": {"ticker": ticker, "news": news[:limit]}}

        elif name == "get_market_news":
            news = _fetch_market_news()
            limit = arguments.get("limit", 15)
            return {"success": True, "data": {"news": news[:limit]}}

        elif name == "get_sentiment_analysis":
            ticker = arguments["ticker"].upper()
            summary = _get_news_summary(ticker)
            return {"success": True, "data": summary}

        else:
            return {"success": False, "error": f"Unknown tool: {name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}
