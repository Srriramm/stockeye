"""
telegram_notify.py — send Telegram messages from anywhere in the app.
Uses direct Bot API calls via requests (no telegram library needed at call sites).
"""
import os
import logging
import requests

logger = logging.getLogger(__name__)

_TOKEN   = None
_CHAT_ID = None


def _cfg():
    global _TOKEN, _CHAT_ID
    if _TOKEN is None:
        _TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        _CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
    return _TOKEN, _CHAT_ID


def send(message: str, chat_id: str | None = None, parse_mode: str = "HTML") -> bool:
    """Send a Telegram message. Silent no-op if token/chat_id not configured."""
    token, default_cid = _cfg()
    cid = chat_id or default_cid
    if not token or not cid:
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": cid, "text": message, "parse_mode": parse_mode},
            timeout=5,
        )
        ok = resp.status_code == 200
        if not ok:
            logger.debug(f"Telegram send failed {resp.status_code}: {resp.text[:200]}")
        return ok
    except Exception as exc:
        logger.debug(f"Telegram notify failed (non-fatal): {exc}")
        return False


def send_trade_summary(session_result: dict) -> None:
    """Format and send an autonomous session summary."""
    trades  = session_result.get("trades", [])
    capital = session_result.get("total_capital_deployed", 0)
    reason  = session_result.get("reasoning", "")

    if not trades:
        msg = (
            f"🤖 <b>Auto-session complete</b> — no trades placed\n"
            f"💬 {reason[:300]}"
        )
    else:
        lines = [f"🤖 <b>Auto-session</b> — {len(trades)} trade(s), ₹{capital:,.0f} deployed\n"]
        for t in trades:
            side_emoji = "🟢 BUY" if t.get("side") == "BUY" else "🔴 SELL"
            lines.append(
                f"{side_emoji}  <b>{t.get('ticker')}</b>  "
                f"{t.get('quantity')}×  ₹{t.get('execution_price', 0):.2f}"
            )
        lines.append(f"\n💬 {reason[:250]}")
        msg = "\n".join(lines)

    send(msg)


def send_price_alert(ticker: str, alert_type: str, price: float, note: str = "") -> None:
    send(
        f"🔔 <b>Price Alert — {ticker}</b>\n"
        f"{alert_type}: ₹{price:.2f}\n"
        f"{note}"
    )
