"""
MCP Server for Stock Assistant
Provides MCP tools for Claude Desktop integration with stock data, portfolio management,
technical analysis, alerts, news, and market overview.
"""

import sys
import os
import json
import asyncio
import argparse

# Add parent directory to path for backend imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Import MCP SDK
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Import tool modules
from tools import (
    stock_tools,
    portfolio_tools,
    technical_tools,
    alert_tools,
    news_tools,
    market_tools
)


# ─── Initialize MCP Server ─────────────────────────────────────────

app = Server("stock-assistant-mcp")


# ─── Tool Registration ─────────────────────────────────────────────

ALL_TOOLS = []

# Collect all tool definitions
tool_modules = [
    stock_tools,
    portfolio_tools,
    technical_tools,
    alert_tools,
    news_tools,
    market_tools
]

for module in tool_modules:
    ALL_TOOLS.extend(module.get_tool_definitions())


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List all available MCP tools."""
    return [Tool(**tool_def) for tool_def in ALL_TOOLS]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a tool and return the result."""

    # Route to appropriate module
    result = None

    # Stock tools
    if name in ["get_stock_price", "get_stock_info", "get_historical_data", "search_stocks", "compare_stocks"]:
        result = stock_tools.execute_tool(name, arguments)

    # Portfolio tools
    elif name in ["get_portfolio", "add_holding", "update_holding", "delete_holding", "get_portfolio_stats"]:
        result = portfolio_tools.execute_tool(name, arguments)

    # Technical tools
    elif name in ["calculate_indicators", "get_technical_signals"]:
        result = technical_tools.execute_tool(name, arguments)

    # Alert tools
    elif name in ["create_price_alert", "get_active_alerts", "get_recent_alerts",
                  "start_monitoring", "stop_monitoring", "get_monitored_stocks"]:
        result = alert_tools.execute_tool(name, arguments)

    # News tools
    elif name in ["get_stock_news", "get_market_news", "get_sentiment_analysis"]:
        result = news_tools.execute_tool(name, arguments)

    # Market tools
    elif name in ["get_market_overview", "get_top_movers"]:
        result = market_tools.execute_tool(name, arguments)

    else:
        result = {"success": False, "error": f"Unknown tool: {name}"}

    # Format result
    if result.get("success"):
        response_text = json.dumps(result.get("data", {}), indent=2, ensure_ascii=False)
    else:
        response_text = json.dumps({"error": result.get("error", "Unknown error")}, indent=2)

    return [TextContent(type="text", text=response_text)]


# ─── Main Entry Point ──────────────────────────────────────────────

async def main():
    """Start the MCP server."""
    parser = argparse.ArgumentParser(description='Stock Assistant MCP Server')
    parser.add_argument('--transport', choices=['stdio', 'sse'], default='stdio',
                       help='Transport mode (default: stdio)')
    parser.add_argument('--port', type=int, default=8080,
                       help='Port for SSE transport (default: 8080)')

    args = parser.parse_args()

    print(f"Starting Stock Assistant MCP Server (transport: {args.transport})", file=sys.stderr)
    print(f"Registered {len(ALL_TOOLS)} tools", file=sys.stderr)

    if args.transport == 'sse':
        from mcp.server.sse import sse_server
        print(f"SSE server listening on port {args.port}", file=sys.stderr)
        await sse_server(app, port=args.port)
    else:
        print("STDIO server ready", file=sys.stderr)
        await stdio_server(app)


if __name__ == "__main__":
    asyncio.run(main())
