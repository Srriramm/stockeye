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
    """Send a Telegram message. Silent no-op if token/chat_id not configured.
    Auto-splits messages exceeding Telegram's 4096-char limit."""
    token, default_cid = _cfg()
    cid = chat_id or default_cid
    if not token or not cid:
        return False

    # Telegram max is 4096 chars; split if needed
    chunks = [message[i:i+4096] for i in range(0, len(message), 4096)]

    try:
        ok = True
        for chunk in chunks:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": cid, "text": chunk, "parse_mode": parse_mode},
                timeout=5,
            )
            if resp.status_code != 200:
                logger.debug(f"Telegram send failed {resp.status_code}: {resp.text[:200]}")
                ok = False
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
            f"💬 {reason[:3000]}"
        )
    else:
        lines = [f"🤖 <b>Auto-session</b> — {len(trades)} trade(s), ₹{capital:,.0f} deployed\n"]
        for t in trades:
            side_emoji = "🟢 BUY" if t.get("side") == "BUY" else "🔴 SELL"
            lines.append(
                f"{side_emoji}  <b>{t.get('ticker')}</b>  "
                f"{t.get('quantity')}×  ₹{t.get('execution_price', 0):.2f}"
            )
        lines.append(f"\n💬 {reason[:3000]}")
        msg = "\n".join(lines)

    send(msg)


def send_price_alert(ticker: str, alert_type: str, price: float, note: str = "") -> None:
    send(
        f"🔔 <b>Price Alert — {ticker}</b>\n"
        f"{alert_type}: ₹{price:.2f}\n"
        f"{note}"
    )


def send_stop_loss_alert(ticker: str, current_price: float, stop_price: float,
                         qty_sold: int, pnl: float) -> None:
    """Urgent alert when a stop-loss is auto-triggered."""
    emoji = "🔴" if pnl < 0 else "🟢"
    send(
        f"🚨 <b>STOP-LOSS TRIGGERED — {ticker}</b>\n\n"
        f"Stop: ₹{stop_price:.2f}  →  Price: ₹{current_price:.2f}\n"
        f"Sold: {qty_sold} shares\n"
        f"{emoji} P&L: ₹{pnl:+,.2f}\n\n"
        f"<i>Auto-executed by stop-loss monitor</i>"
    )
