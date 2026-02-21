"""
Stock Data Tools for MCP Server
Provides real-time stock price, info, and search functionality
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

import json
from stock_data import (
    get_stock_price as _get_stock_price,
    get_stock_info as _get_stock_info,
    get_historical_data as _get_historical_data,
    search_stocks as _search_stocks,
    get_stock_comparison as _get_stock_comparison
)


def get_tool_definitions():
    """Return stock tool definitions for MCP server."""
    return [
        {
            "name": "get_stock_price",
            "description": "Get real-time price for an Indian stock (NSE/BSE). Returns current price, change, volume, and key metrics.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g., RELIANCE, TCS, INFY, HDFCBANK)"
                    }
                },
                "required": ["ticker"]
            }
        },
        {
            "name": "get_stock_info",
            "description": "Get comprehensive fundamental information for a stock including sector, market cap, P/E ratio, EPS, debt/equity, ROE, dividend yield, 52-week high/low, and beta.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g., RELIANCE, TCS, INFY)"
                    }
                },
                "required": ["ticker"]
            }
        },
        {
            "name": "get_historical_data",
            "description": "Get historical price data for a stock over a specified period. Useful for analyzing trends and patterns.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol"
                    },
                    "period": {
                        "type": "string",
                        "description": "Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)",
                        "default": "1y"
                    },
                    "interval": {
                        "type": "string",
                        "description": "Data interval (1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo)",
                        "default": "1d"
                    }
                },
                "required": ["ticker"]
            }
        },
        {
            "name": "search_stocks",
            "description": "Search for Indian stocks by name or ticker symbol. Returns matching stocks with their tickers and sectors.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (stock name or ticker)"
                    }
                },
                "required": ["query"]
            }
        },
        {
            "name": "compare_stocks",
            "description": "Compare two stocks side-by-side with fundamentals and technical indicators.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker1": {
                        "type": "string",
                        "description": "First stock ticker"
                    },
                    "ticker2": {
                        "type": "string",
                        "description": "Second stock ticker"
                    }
                },
                "required": ["ticker1", "ticker2"]
            }
        }
    ]


def execute_tool(name, arguments):
    """Execute a stock tool and return the result."""
    try:
        if name == "get_stock_price":
            result = _get_stock_price(arguments["ticker"])
            return {"success": True, "data": result}

        elif name == "get_stock_info":
            result = _get_stock_info(arguments["ticker"])
            return {"success": True, "data": result}

        elif name == "get_historical_data":
            ticker = arguments["ticker"]
            period = arguments.get("period", "1y")
            interval = arguments.get("interval", "1d")
            result = _get_historical_data(ticker, period=period, interval=interval)
            return {"success": True, "data": result}

        elif name == "search_stocks":
            result = _search_stocks(arguments["query"])
            return {"success": True, "data": result}

        elif name == "compare_stocks":
            result = _get_stock_comparison(arguments["ticker1"], arguments["ticker2"])
            return {"success": True, "data": result}

        else:
            return {"success": False, "error": f"Unknown tool: {name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}
