"""
Portfolio Management Tools for MCP Server
CRUD operations for portfolio holdings
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

import json
from portfolio_manager import (
    get_all_holdings as _get_all_holdings,
    add_holding as _add_holding,
    update_holding as _update_holding,
    delete_holding as _delete_holding,
    calculate_portfolio_value as _calculate_portfolio_value,
    get_portfolio_stats as _get_portfolio_stats
)
from stock_data import get_bulk_prices, get_stock_info


def get_tool_definitions():
    """Return portfolio tool definitions for MCP server."""
    return [
        {
            "name": "get_portfolio",
            "description": "Get complete portfolio with all holdings, current prices, and profit/loss calculations. Returns total value, total P&L, and individual holdings.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "add_holding",
            "description": "Add a new stock holding to the portfolio.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol (e.g., RELIANCE, TCS)"
                    },
                    "quantity": {
                        "type": "number",
                        "description": "Number of shares"
                    },
                    "buy_price": {
                        "type": "number",
                        "description": "Purchase price per share in ₹"
                    },
                    "name": {
                        "type": "string",
                        "description": "Stock name (optional, will be auto-fetched if not provided)"
                    },
                    "purchase_date": {
                        "type": "string",
                        "description": "Purchase date in YYYY-MM-DD format (optional, defaults to today)"
                    },
                    "sector": {
                        "type": "string",
                        "description": "Sector (optional, will be auto-fetched if not provided)"
                    }
                },
                "required": ["ticker", "quantity", "buy_price"]
            }
        },
        {
            "name": "update_holding",
            "description": "Update an existing portfolio holding.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "holding_id": {
                        "type": "integer",
                        "description": "ID of the holding to update"
                    },
                    "quantity": {
                        "type": "number",
                        "description": "New quantity (optional)"
                    },
                    "buy_price": {
                        "type": "number",
                        "description": "New buy price (optional)"
                    }
                },
                "required": ["holding_id"]
            }
        },
        {
            "name": "delete_holding",
            "description": "Remove a stock from the portfolio.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "holding_id": {
                        "type": "integer",
                        "description": "ID of the holding to delete"
                    }
                },
                "required": ["holding_id"]
            }
        },
        {
            "name": "get_portfolio_stats",
            "description": "Get comprehensive portfolio analytics including sector allocation, top performers, risk metrics, and diversification analysis.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    ]


def execute_tool(name, arguments):
    """Execute a portfolio tool and return the result."""
    try:
        if name == "get_portfolio":
            holdings = _get_all_holdings()
            if not holdings:
                return {
                    "success": True,
                    "data": {
                        "holdings": [],
                        "total_value": 0,
                        "total_investment": 0,
                        "total_pnl": 0,
                        "total_pnl_percent": 0,
                        "num_holdings": 0
                    }
                }

            tickers = [h['ticker'] for h in holdings]
            prices = get_bulk_prices(tickers)
            portfolio = _calculate_portfolio_value(prices)
            return {"success": True, "data": portfolio}

        elif name == "add_holding":
            ticker = arguments["ticker"].upper()
            name = arguments.get("name", "")

            # Auto-fetch name and sector if not provided
            if not name:
                stock_info = get_stock_info(ticker)
                if stock_info:
                    name = stock_info.get("name", ticker)
                    if "sector" not in arguments:
                        arguments["sector"] = stock_info.get("sector", "")
                else:
                    name = ticker

            from datetime import datetime
            holding_id = _add_holding(
                ticker=ticker,
                name=name,
                quantity=float(arguments["quantity"]),
                buy_price=float(arguments["buy_price"]),
                purchase_date=arguments.get("purchase_date", datetime.now().strftime('%Y-%m-%d')),
                sector=arguments.get("sector", ""),
                exchange=arguments.get("exchange", "NSE")
            )
            return {"success": True, "data": {"id": holding_id, "message": f"{ticker} added to portfolio"}}

        elif name == "update_holding":
            holding_id = arguments["holding_id"]
            update_data = {}
            if "quantity" in arguments:
                update_data["quantity"] = float(arguments["quantity"])
            if "buy_price" in arguments:
                update_data["buy_price"] = float(arguments["buy_price"])

            success = _update_holding(holding_id, update_data)
            if success:
                return {"success": True, "data": {"message": "Holding updated successfully"}}
            return {"success": False, "error": "Holding not found"}

        elif name == "delete_holding":
            _delete_holding(arguments["holding_id"])
            return {"success": True, "data": {"message": "Holding deleted successfully"}}

        elif name == "get_portfolio_stats":
            holdings = _get_all_holdings()
            if not holdings:
                return {"success": False, "error": "No holdings in portfolio"}

            prices = get_bulk_prices([h['ticker'] for h in holdings])
            stats = _get_portfolio_stats(prices)
            return {"success": True, "data": stats}

        else:
            return {"success": False, "error": f"Unknown tool: {name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}
