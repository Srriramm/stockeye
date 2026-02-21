"""
Alert and Monitoring Tools for MCP Server
Manage price alerts and stock monitoring
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

import json
from portfolio_manager import (
    add_price_alert as _add_price_alert,
    get_active_price_alerts as _get_active_price_alerts,
    get_recent_alerts as _get_recent_alerts,
    start_monitoring as _start_monitoring,
    stop_monitoring as _stop_monitoring,
    get_monitored_stocks as _get_monitored_stocks
)
from stock_data import get_stock_price


def get_tool_definitions():
    """Return alert tool definitions for MCP server."""
    return [
        {
            "name": "create_price_alert",
            "description": "Set a price alert for a stock. You'll be notified when the stock price crosses the target price in the specified direction.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol"
                    },
                    "target_price": {
                        "type": "number",
                        "description": "Target price in ₹"
                    },
                    "direction": {
                        "type": "string",
                        "description": "Alert direction: 'above' or 'below'",
                        "enum": ["above", "below"],
                        "default": "above"
                    }
                },
                "required": ["ticker", "target_price"]
            }
        },
        {
            "name": "get_active_alerts",
            "description": "Get all active price alerts that haven't been triggered yet.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "get_recent_alerts",
            "description": "Get recent alerts that have been triggered in the last N hours.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "hours": {
                        "type": "integer",
                        "description": "Number of hours to look back",
                        "default": 24
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of alerts to return",
                        "default": 50
                    }
                },
                "required": []
            }
        },
        {
            "name": "start_monitoring",
            "description": "Start real-time monitoring for a stock. Monitors for significant price changes, volume spikes, and triggers alerts.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol to monitor"
                    }
                },
                "required": ["ticker"]
            }
        },
        {
            "name": "stop_monitoring",
            "description": "Stop real-time monitoring for a stock.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol to stop monitoring"
                    }
                },
                "required": ["ticker"]
            }
        },
        {
            "name": "get_monitored_stocks",
            "description": "Get list of all stocks currently being monitored.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "active_only": {
                        "type": "boolean",
                        "description": "Only return actively monitored stocks",
                        "default": True
                    }
                },
                "required": []
            }
        }
    ]


def execute_tool(name, arguments):
    """Execute an alert tool and return the result."""
    try:
        if name == "create_price_alert":
            ticker = arguments["ticker"].upper()
            target_price = float(arguments["target_price"])
            direction = arguments.get("direction", "above")

            alert_id = _add_price_alert(ticker, target_price, direction)
            return {
                "success": True,
                "data": {
                    "id": alert_id,
                    "message": f"Price alert set for {ticker} at ₹{target_price} ({direction})"
                }
            }

        elif name == "get_active_alerts":
            alerts = _get_active_price_alerts()
            return {"success": True, "data": {"alerts": alerts}}

        elif name == "get_recent_alerts":
            hours = arguments.get("hours", 24)
            limit = arguments.get("limit", 50)
            alerts = _get_recent_alerts(hours=hours, limit=limit)
            return {"success": True, "data": {"alerts": alerts}}

        elif name == "start_monitoring":
            ticker = arguments["ticker"].upper()

            # Get baseline data
            price_data = get_stock_price(ticker)
            if not price_data:
                return {"success": False, "error": f"Could not fetch data for {ticker}"}

            _start_monitoring(
                ticker,
                name=price_data.get('name', ticker),
                price_baseline=price_data['current_price'],
                volume_avg=price_data.get('avg_volume', 0)
            )

            return {
                "success": True,
                "data": {
                    "message": f"Started monitoring {ticker}",
                    "baseline_price": price_data['current_price']
                }
            }

        elif name == "stop_monitoring":
            ticker = arguments["ticker"].upper()
            _stop_monitoring(ticker)
            return {"success": True, "data": {"message": f"Stopped monitoring {ticker}"}}

        elif name == "get_monitored_stocks":
            active_only = arguments.get("active_only", True)
            stocks = _get_monitored_stocks(active_only=active_only)
            return {"success": True, "data": {"stocks": stocks}}

        else:
            return {"success": False, "error": f"Unknown tool: {name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}
