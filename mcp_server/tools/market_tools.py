"""
Market Overview Tools for MCP Server
Provides market indices and top movers
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

import json
from stock_data import (
    get_market_indices as _get_market_indices,
    get_top_gainers_losers as _get_top_gainers_losers
)


def get_tool_definitions():
    """Return market tool definitions for MCP server."""
    return [
        {
            "name": "get_market_overview",
            "description": "Get overview of major Indian market indices including NIFTY 50, SENSEX, and Bank NIFTY with current values, change percentages, and trends.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": []
            }
        },
        {
            "name": "get_top_movers",
            "description": "Get top gaining and losing stocks in the Indian market today. Useful for identifying market momentum and opportunities.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of gainers/losers to return",
                        "default": 10
                    }
                },
                "required": []
            }
        }
    ]


def execute_tool(name, arguments):
    """Execute a market tool and return the result."""
    try:
        if name == "get_market_overview":
            indices = _get_market_indices()
            return {"success": True, "data": {"indices": indices}}

        elif name == "get_top_movers":
            movers = _get_top_gainers_losers()
            limit = arguments.get("limit", 10)

            # Limit results
            if movers:
                movers['gainers'] = movers.get('gainers', [])[:limit]
                movers['losers'] = movers.get('losers', [])[:limit]

            return {"success": True, "data": movers}

        else:
            return {"success": False, "error": f"Unknown tool: {name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}
