"""
shared_context.py — Cross-module intelligence bus.

Every analysis module (Monitor, Proactive, Advisor, AutoTrader) writes its
findings here and reads from here before it reasons.  This gives all modules
a shared picture of the world, so they debate from the same data.

DB table: shared_signals
  Each row is one signal — a buy/sell recommendation, executed trade,
  price alert, or morning briefing fragment — with a TTL so stale data
  doesn't pollute future sessions.

Write side:  proactive_agent, agentic_trader, market_monitor  → write_signal()
Read side:   ai_advisor, agentic_trader, proactive_agent       → get_context_summary()
"""

import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Max characters stored per signal message (keeps DB rows small)
_MAX_MSG_LEN = 400


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_table(conn) -> None:
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shared_signals (
                id          SERIAL PRIMARY KEY,
                user_id     TEXT NOT NULL,
                source      TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                ticker      TEXT,
                direction   TEXT,
                message     TEXT NOT NULL,
                confidence  REAL,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at  TIMESTAMP
            )
        """)
    except Exception:
        pass  # table may already exist with a slightly different DDL — ignore


# ─────────────────────────────────────────────────────────────────────────────
# Public write API
# ─────────────────────────────────────────────────────────────────────────────

def write_signal(
    user_id:     str,
    source:      str,          # 'proactive' | 'autonomous' | 'monitor' | 'advisor'
    signal_type: str,          # 'buy_rec' | 'sell_rec' | 'hold_rec' | 'trade_buy' | 'trade_sell' | 'alert' | 'briefing'
    message:     str,
    ticker:      str | None = None,
    direction:   str | None = None,   # 'bullish' | 'bearish' | 'neutral'
    confidence:  float | None = None,
    ttl_hours:   int = 24,
) -> None:
    """Write one signal. Silent no-op on any error."""
    try:
        from db import get_db_connection
        expires = (datetime.utcnow() + timedelta(hours=ttl_hours)).isoformat()
        with get_db_connection() as conn:
            _ensure_table(conn)
            conn.execute(
                "INSERT INTO shared_signals "
                "(user_id, source, signal_type, ticker, direction, message, confidence, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, source, signal_type,
                 ticker.upper() if ticker else None,
                 direction,
                 message[:_MAX_MSG_LEN],
                 confidence,
                 expires),
            )
    except Exception as exc:
        logger.debug(f"write_signal failed (non-fatal): {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Public read API
# ─────────────────────────────────────────────────────────────────────────────

def read_signals(
    user_id: str,
    max_age_hours: int = 24,
    limit: int = 20,
) -> list[dict]:
    """Return recent signals newest-first. Returns [] on any error."""
    try:
        from db import get_db_connection
        cutoff = (datetime.utcnow() - timedelta(hours=max_age_hours)).isoformat()
        with get_db_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM shared_signals "
                "WHERE user_id = ? AND created_at > ? "
                "ORDER BY created_at DESC LIMIT ?",
                (user_id, cutoff, limit),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.debug(f"read_signals failed (non-fatal): {exc}")
        return []


_SOURCE_LABELS = {
    "proactive":  "Proactive Analysis Agent",
    "autonomous": "Autonomous Trader",
    "monitor":    "Price / Volume Monitor",
    "advisor":    "AI Advisor",
}


def get_context_summary(user_id: str, max_age_hours: int = 12) -> str:
    """
    Return a compact text block summarising recent signals from all modules.
    Inject this into system prompts so every module reasons from shared data.
    Returns empty string if no signals exist (safe to concatenate).
    """
    signals = read_signals(user_id, max_age_hours=max_age_hours, limit=20)
    if not signals:
        return ""

    by_source: dict[str, list] = {}
    for s in signals:
        by_source.setdefault(s.get("source", "unknown"), []).append(s)

    lines = ["\n=== PLATFORM INTELLIGENCE (shared across all modules, last 12 h) ==="]

    for src, items in by_source.items():
        lines.append(f"\n[{_SOURCE_LABELS.get(src, src).upper()}]")
        for s in items[:6]:
            ticker_part = f" [{s['ticker']}]" if s.get("ticker") else ""
            dir_part    = f" — {s['direction'].upper()}" if s.get("direction") else ""
            conf_part   = f" ({s['confidence']:.0%} confidence)" if s.get("confidence") else ""
            lines.append(f"• {ticker_part}{dir_part}: {s['message']}{conf_part}")

    lines.append("=== END PLATFORM INTELLIGENCE ===\n")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Convenience helpers (called by specific modules)
# ─────────────────────────────────────────────────────────────────────────────

def signal_from_recommendation(user_id: str, ticker: str, rec: dict) -> None:
    """Write a proactive-agent recommendation as a signal."""
    action    = rec.get("action", "HOLD")
    direction = {"BUY": "bullish", "SELL": "bearish"}.get(action, "neutral")
    stype     = {"BUY": "buy_rec", "SELL": "sell_rec",
                 "HOLD": "hold_rec", "WATCH": "hold_rec"}.get(action, "hold_rec")
    msg = f"{action}: {rec.get('reasoning', '')}"
    write_signal(user_id, "proactive", stype, msg,
                 ticker=ticker, direction=direction,
                 confidence=rec.get("confidence"))


def signal_from_trade(user_id: str, ticker: str, side: str,
                      quantity: int | float, price: float, reasoning: str = "") -> None:
    """Write an autonomous-trader execution as a signal."""
    msg = f"{side} {quantity}× {ticker} @ ₹{price:.2f}. {reasoning[:200]}"
    write_signal(user_id, "autonomous", f"trade_{side.lower()}", msg,
                 ticker=ticker,
                 direction="bullish" if side == "BUY" else "bearish")


def signal_from_alert(user_id: str, ticker: str, alert_type: str, message: str) -> None:
    """Write a market-monitor price/volume alert as a signal."""
    write_signal(user_id, "monitor", "alert", message,
                 ticker=ticker, direction=None, ttl_hours=12)
