"""
telegram_bot.py — Stockeye Telegram bot (polling mode).

Run standalone:  python telegram_bot.py
Docker service:  command: python telegram_bot.py

Required env vars:
  TELEGRAM_BOT_TOKEN   — from @BotFather
  TELEGRAM_CHAT_ID     — your personal Telegram chat ID (find via @userinfobot)
  TELEGRAM_USER_ID     — your Supabase user_id (UUID string)

Only the configured TELEGRAM_CHAT_ID can issue commands (single-user security).
Plain text messages are forwarded to the AI Advisor as /chat.
"""

import os
import logging
import threading
import requests as _req

from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes,
)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
USER_ID = os.environ.get("TELEGRAM_USER_ID", "")


# ─────────────────────────────────────────────────────────────────────────────
# Auth guard
# ─────────────────────────────────────────────────────────────────────────────
def _auth(update: Update) -> bool:
    if str(update.effective_chat.id) != CHAT_ID:
        logger.warning(f"Blocked unauthorised chat_id {update.effective_chat.id}")
        return False
    return True


def _tg_send(text: str) -> None:
    """Push a message back to the configured chat (used from background threads)."""
    if not TOKEN or not CHAT_ID:
        return
    try:
        _req.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as exc:
        logger.debug(f"_tg_send failed: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    await update.message.reply_text(
        "👋 <b>Stockeye Bot</b>\n\n"
        "Commands:\n"
        "/portfolio — holdings + live P&L\n"
        "/balance — wallet balance\n"
        "/run [budget] — start autonomous session\n"
        "/buy TICKER QTY — manual buy\n"
        "/sell TICKER QTY — manual sell\n"
        "/history — 7-day returns\n"
        "/status — session status\n"
        "/chat message — talk to AI Advisor\n\n"
        "Or just type any message — it goes to the AI Advisor.",
        parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────────────
# /portfolio
# ─────────────────────────────────────────────────────────────────────────────
async def cmd_portfolio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    try:
        from trading_manager import get_trading_portfolio, get_trading_balance
        from stock_data import get_bulk_prices

        holdings = get_trading_portfolio(USER_ID) or []
        bal      = get_trading_balance(USER_ID) or {}

        if not holdings:
            await update.message.reply_text("📭 No open positions.")
            return

        prices      = get_bulk_prices([h["ticker"] for h in holdings])
        total_unreal = 0
        lines        = ["<b>📊 Portfolio</b>\n"]

        for h in holdings:
            cur   = float(prices.get(h["ticker"]) or h["avg_buy_price"])
            pnl   = (cur - float(h["avg_buy_price"])) * float(h["quantity"])
            pct   = (cur / float(h["avg_buy_price"]) - 1) * 100
            emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(
                f"{emoji} <b>{h['ticker']}</b>  {h['quantity']}×  ₹{cur:.2f}"
                f"  ({pct:+.1f}%  ₹{pnl:+.0f})"
            )
            total_unreal += pnl

        lines.append(f"\n💰 Cash: ₹{float(bal.get('balance', 0)):,.2f}")
        lines.append(f"📈 Unrealised P&L: ₹{total_unreal:+.2f}")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")

    except Exception as exc:
        await update.message.reply_text(f"❌ {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# /balance
# ─────────────────────────────────────────────────────────────────────────────
async def cmd_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    try:
        from trading_manager import get_trading_balance
        bal = get_trading_balance(USER_ID) or {}
        await update.message.reply_text(
            f"💰 <b>Wallet</b>\n"
            f"Cash:     ₹{float(bal.get('balance', 0)):,.2f}\n"
            f"Invested: ₹{float(bal.get('invested', 0)):,.2f}\n"
            f"P&L:      ₹{float(bal.get('pnl', 0)):,.2f}",
            parse_mode="HTML",
        )
    except Exception as exc:
        await update.message.reply_text(f"❌ {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# /run [budget]
# ─────────────────────────────────────────────────────────────────────────────
async def cmd_run(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    args   = ctx.args
    budget = None
    if args:
        try:
            budget = float(args[0])
        except ValueError:
            await update.message.reply_text("Usage: /run [budget_amount]")
            return

    label = f" (budget ₹{budget:,.0f})" if budget else ""
    await update.message.reply_text(f"🚀 Starting autonomous session{label}...")

    def _run_in_thread():
        try:
            from agentic_trader import run_trading_session
            result = run_trading_session(USER_ID, budget=budget, notify=False)
            if not result:
                _tg_send("⚠️ Session finished with no result.")
                return
            if result.get("already_running"):
                _tg_send("⏳ A session is already running — please wait for it to finish.")
                return

            trades  = result.get("trades", [])
            capital = result.get("total_capital_deployed", 0)
            reason  = result.get("reasoning", "")

            lines = [f"✅ <b>Session done</b> — {len(trades)} trade(s), ₹{capital:,.0f} deployed\n"]
            for t in trades:
                emoji = "🟢 BUY" if t.get("side") == "BUY" else "🔴 SELL"
                lines.append(
                    f"{emoji}  <b>{t.get('ticker')}</b>  "
                    f"{t.get('quantity')}×  ₹{t.get('execution_price', 0):.2f}"
                )
            # Truncate cleanly at word boundary (Telegram limit is 4096, keep reasoning readable)
            if len(reason) > 800:
                reason = reason[:800].rsplit(" ", 1)[0] + "…"
            lines.append(f"\n💬 {reason}")
            _tg_send("\n".join(lines))
        except Exception as exc:
            _tg_send(f"❌ Session error: {exc}")

    threading.Thread(target=_run_in_thread, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# /buy TICKER QTY
# ─────────────────────────────────────────────────────────────────────────────
async def cmd_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /buy TICKER QTY\nExample: /buy RELIANCE 5")
        return
    ticker = args[0].upper()
    try:
        qty = int(args[1])
    except ValueError:
        await update.message.reply_text("QTY must be a whole number.")
        return
    try:
        from trading_manager import place_order
        from stock_data import get_stock_price
        p     = get_stock_price(ticker) or {}
        price = float(p.get("current_price") or 0)
        if not price:
            await update.message.reply_text(f"❌ Could not fetch price for {ticker}")
            return
        order_id = place_order(USER_ID, ticker, ticker, "BUY", "MARKET", qty, price=price)
        await update.message.reply_text(
            f"✅ <b>BUY</b> {qty}× <b>{ticker}</b> @ ₹{price:.2f}\n"
            f"Total: ₹{qty * price:,.2f} | Order #{order_id}",
            parse_mode="HTML",
        )
    except Exception as exc:
        await update.message.reply_text(f"❌ {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# /sell TICKER QTY
# ─────────────────────────────────────────────────────────────────────────────
async def cmd_sell(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /sell TICKER QTY\nExample: /sell GOLDBEES 10")
        return
    ticker = args[0].upper()
    try:
        qty = int(args[1])
    except ValueError:
        await update.message.reply_text("QTY must be a whole number.")
        return
    try:
        from trading_manager import place_order
        from stock_data import get_stock_price
        p     = get_stock_price(ticker) or {}
        price = float(p.get("current_price") or 0)
        if not price:
            await update.message.reply_text(f"❌ Could not fetch price for {ticker}")
            return
        order_id = place_order(USER_ID, ticker, ticker, "SELL", "MARKET", qty, price=price)
        await update.message.reply_text(
            f"✅ <b>SELL</b> {qty}× <b>{ticker}</b> @ ₹{price:.2f}\n"
            f"Proceeds: ₹{qty * price:,.2f} | Order #{order_id}",
            parse_mode="HTML",
        )
    except Exception as exc:
        await update.message.reply_text(f"❌ {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# /history
# ─────────────────────────────────────────────────────────────────────────────
async def cmd_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    try:
        from trading_manager import get_performance_history
        rows = get_performance_history(USER_ID, days=7)
        if not rows:
            await update.message.reply_text("No history snapshots yet.")
            return
        lines = ["<b>📅 7-Day Returns</b>\n"]
        for r in rows:
            pnl   = r.get("pnl") or 0
            emoji = "🟢" if pnl >= 0 else "🔴"
            lines.append(
                f"{emoji} {r['date']}  ₹{r.get('portfolio_value', 0):,.0f}"
                f"  {r.get('pnl_pct', 0):+.2f}%"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
    except Exception as exc:
        await update.message.reply_text(f"❌ {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# /status
# ─────────────────────────────────────────────────────────────────────────────
async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    from agentic_trader import get_active_session
    session = get_active_session(USER_ID)
    if session and session.get("status") == "running":
        await update.message.reply_text(
            f"🔄 <b>Session running</b>\nID: {session.get('session_id')}",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("✅ No active session. Ready.")


# ─────────────────────────────────────────────────────────────────────────────
# /chat <message>  and plain text fallback
# ─────────────────────────────────────────────────────────────────────────────
async def _do_chat(update: Update, text: str):
    if not USER_ID:
        await update.message.reply_text("❌ TELEGRAM_USER_ID not configured.")
        return
    await update.message.reply_text("🤔 Thinking...")
    try:
        from conversation_manager import (
            get_conversations, create_conversation, get_messages, add_message
        )
        from ai_advisor import get_ai_response

        # Find or create a persistent "Telegram" conversation for this user
        convs = get_conversations(USER_ID)
        tg_conv = next((c for c in convs if c.get("title") == "Telegram"), None)
        if tg_conv:
            conv_id = tg_conv["id"]
        else:
            conv_id = create_conversation(USER_ID, title="Telegram")

        history  = get_messages(USER_ID, conv_id, limit=20)
        response = get_ai_response(text, conversation_history=history, user_id=USER_ID)
        add_message(USER_ID, conv_id, "user", text)
        add_message(USER_ID, conv_id, "assistant", response)
        # Telegram message limit is 4096 chars
        for chunk in [response[i:i+4090] for i in range(0, len(response), 4090)]:
            await update.message.reply_text(chunk)
    except Exception as exc:
        await update.message.reply_text(f"❌ {exc}")


async def cmd_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    if not ctx.args:
        await update.message.reply_text("Usage: /chat your question here\nOr just type a message directly.")
        return
    await _do_chat(update, " ".join(ctx.args))


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Plain text → AI Advisor."""
    if not _auth(update):
        return
    await _do_chat(update, update.message.text)


# ─────────────────────────────────────────────────────────────────────────────
# /proposals — list pending live-order proposals
# ─────────────────────────────────────────────────────────────────────────────
async def cmd_proposals(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _auth(update):
        return
    try:
        from proposal_store import list_proposals, expire_stale_proposals
        expire_stale_proposals()
        pending = list_proposals(USER_ID, status="PENDING")
        if not pending:
            await update.message.reply_text("✅ No pending proposals.")
            return
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        for p in pending:
            side_emoji = "🟢 BUY" if p["side"] == "BUY" else "🔴 SELL"
            msg = (
                f"🤝 <b>Proposal #{p['id']}</b>\n"
                f"{side_emoji}  <b>{p['ticker']}</b>  {p['quantity']}×  @ ₹{float(p['price'] or 0):,.2f}\n"
                f"💬 {(p.get('reasoning') or '')[:500]}"
            )
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Approve", callback_data=f"approve:{p['id']}"),
                InlineKeyboardButton("❌ Reject",  callback_data=f"reject:{p['id']}"),
            ]])
            await update.message.reply_text(msg, parse_mode="HTML", reply_markup=kb)
    except Exception as exc:
        await update.message.reply_text(f"❌ {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Inline button callbacks → approve / reject proposals
# ─────────────────────────────────────────────────────────────────────────────
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Auth: only the configured chat may act on buttons
    if str(query.message.chat.id) != CHAT_ID:
        await query.answer("Unauthorised", show_alert=True)
        return
    await query.answer()
    data = query.data or ""
    try:
        action, pid_str = data.split(":", 1)
        pid = int(pid_str)
    except ValueError:
        await query.edit_message_text("⚠️ Malformed action.")
        return

    # The live order placement + reconciliation can block; run it off the event loop.
    import asyncio

    def _act():
        from proposal_store import approve_proposal, reject_proposal
        if action == "approve":
            return approve_proposal(pid, USER_ID)
        if action == "reject":
            return reject_proposal(pid, USER_ID)
        return {"error": "Unknown action"}

    result = await asyncio.to_thread(_act)

    if result.get("error"):
        await query.edit_message_text(f"❌ Proposal #{pid}: {result['error']}")
    elif action == "reject":
        await query.edit_message_text(f"❌ Proposal #{pid} rejected — no order placed.")
    else:
        status = result.get("status")
        if status == "FILLED":
            await query.edit_message_text(
                f"✅ Proposal #{pid} <b>FILLED</b> — {result.get('side')} "
                f"{result.get('fill_quantity')}× {result.get('ticker')} "
                f"@ ₹{float(result.get('fill_price') or 0):,.2f}",
                parse_mode="HTML",
            )
        else:
            await query.edit_message_text(
                f"⏳ Proposal #{pid} approved — order placed (status: {status}). "
                f"Reconciling fill…"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
def main():
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set — Telegram bot disabled")
        return

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("portfolio", cmd_portfolio))
    app.add_handler(CommandHandler("balance",   cmd_balance))
    app.add_handler(CommandHandler("run",       cmd_run))
    app.add_handler(CommandHandler("buy",       cmd_buy))
    app.add_handler(CommandHandler("sell",      cmd_sell))
    app.add_handler(CommandHandler("history",   cmd_history))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("chat",      cmd_chat))
    app.add_handler(CommandHandler("proposals", cmd_proposals))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info(f"Stockeye Telegram bot started (chat_id={CHAT_ID})")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
