"""
Technical Analysis Tools for MCP Server
Provides technical indicators and trading signals
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

import json
from stock_data import calculate_technical_indicators as _calculate_technical_indicators


def get_tool_definitions():
    """Return technical analysis tool definitions for MCP server."""
    return [
        {
            "name": "calculate_indicators",
            "description": "Calculate technical indicators for a stock including RSI, MACD, Bollinger Bands, SMA 20/50/200, EMA 12/26, and trading signals. Returns buy/sell/hold signals based on technical analysis.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol"
                    },
                    "period": {
                        "type": "string",
                        "description": "Historical period for calculation (1mo, 3mo, 6mo, 1y)",
                        "default": "6mo"
                    }
                },
                "required": ["ticker"]
            }
        },
        {
            "name": "get_technical_signals",
            "description": "Get buy/sell/hold signals based on technical indicators. Returns specific trading signals and reasoning.",
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
    """Execute a technical analysis tool and return the result."""
    try:
        if name == "calculate_indicators":
            ticker = arguments["ticker"]
            period = arguments.get("period", "6mo")
            result = _calculate_technical_indicators(ticker, period=period)
            return {"success": True, "data": result}

        elif name == "get_technical_signals":
            ticker = arguments["ticker"]
            indicators = _calculate_technical_indicators(ticker)

            if not indicators:
                return {"success": False, "error": f"Could not calculate indicators for {ticker}"}

            # Extract signals
            signals = indicators.get("signals", [])
            overall_signal = "HOLD"

            # Determine overall signal based on indicators
            buy_signals = sum(1 for s in signals if "buy" in s.lower() or "bullish" in s.lower())
            sell_signals = sum(1 for s in signals if "sell" in s.lower() or "bearish" in s.lower())

            if buy_signals > sell_signals and buy_signals >= 2:
                overall_signal = "BUY"
            elif sell_signals > buy_signals and sell_signals >= 2:
                overall_signal = "SELL"

            return {
                "success": True,
                "data": {
                    "ticker": ticker,
                    "overall_signal": overall_signal,
                    "signals": signals,
                    "rsi": indicators.get("rsi"),
                    "macd": indicators.get("macd"),
                    "signal_strength": {
                        "bullish": buy_signals,
                        "bearish": sell_signals,
                        "neutral": len(signals) - buy_signals - sell_signals
                    }
                }
            }

        else:
            return {"success": False, "error": f"Unknown tool: {name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}
