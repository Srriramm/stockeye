"""
proposal_store.py — approval-gated live order queue.

When a live broker is connected, the agentic trader writes PENDING proposals
here instead of executing. Nothing reaches the broker until the user approves
(via web or Telegram). On approval we:
  1. re-check the kill-switch + rupee caps + RiskGate (price moved since proposal)
  2. place the real order through broker_manager
  3. reconcile the async fill (poll Kite) and record the result

Paper mode never touches this module — it executes immediately as before.
"""

import json
import logging
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
DEFAULT_TTL_MIN = 30          # a proposal lapses if not acted on within 30 min
RECONCILE_POLLS = 6           # poll the broker up to N times for a fill
RECONCILE_DELAY = 2.0         # seconds between polls


# ─────────────────────────────────────────────────────────────────────────────
# Persistence (lazy-create for SQLite dev; canonical schema in schema.sql)
# ─────────────────────────────────────────────────────────────────────────────
def _ensure_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS proposed_orders (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id          TEXT NOT NULL,
            ticker           TEXT NOT NULL,
            name             TEXT,
            side             TEXT NOT NULL,
            order_type       TEXT NOT NULL DEFAULT 'MARKET',
            quantity         REAL NOT NULL,
            price            REAL,
            stop_loss        REAL,
            limit_price      REAL,
            confidence       REAL,
            reasoning        TEXT DEFAULT '',
            risk_gate_result TEXT DEFAULT '{}',
            status           TEXT DEFAULT 'PENDING',
            broker           TEXT DEFAULT 'zerodha',
            broker_order_id  TEXT,
            fill_price       REAL,
            fill_quantity    REAL,
            session_id       TEXT,
            decided_at       TIMESTAMP,
            created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at       TIMESTAMP
        )
    """)


def create_proposal(user_id: str, *, ticker: str, side: str, quantity: float,
                    order_type: str = "MARKET", price: float = None,
                    stop_loss: float = None, limit_price: float = None,
                    confidence: float = None, reasoning: str = "",
                    risk_gate_result: dict = None, broker: str = "zerodha",
                    session_id: str = None, name: str = None,
                    ttl_min: int = DEFAULT_TTL_MIN) -> int | None:
    """Insert a PENDING proposal. Returns its id."""
    expires = (datetime.now(IST) + timedelta(minutes=ttl_min)).isoformat()
    try:
        from db import get_db_connection
        with get_db_connection() as conn:
            _ensure_table(conn)
            cur = conn.execute(
                "INSERT INTO proposed_orders "
                "(user_id, ticker, name, side, order_type, quantity, price, stop_loss, "
                " limit_price, confidence, reasoning, risk_gate_result, status, broker, "
                " session_id, expires_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?, ?)",
                (user_id, ticker, name or ticker, side, order_type, quantity, price,
                 stop_loss, limit_price, confidence, reasoning,
                 json.dumps(risk_gate_result or {}), broker, session_id, expires),
            )
            return cur.lastrowid
    except Exception as exc:
        logger.error(f"create_proposal failed: {exc}")
        return None


def list_proposals(user_id: str, status: str = "PENDING", limit: int = 50) -> list:
    try:
        from db import get_db_connection
        with get_db_connection() as conn:
            _ensure_table(conn)
            if status:
                rows = conn.execute(
                    "SELECT * FROM proposed_orders WHERE user_id = ? AND status = ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (user_id, status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM proposed_orders WHERE user_id = ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (user_id, limit),
                ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.error(f"list_proposals failed: {exc}")
        return []


def get_proposal(proposal_id: int, user_id: str = None) -> dict | None:
    try:
        from db import get_db_connection
        with get_db_connection() as conn:
            _ensure_table(conn)
            if user_id:
                row = conn.execute(
                    "SELECT * FROM proposed_orders WHERE id = ? AND user_id = ?",
                    (proposal_id, user_id),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM proposed_orders WHERE id = ?", (proposal_id,)
                ).fetchone()
        return dict(row) if row else None
    except Exception as exc:
        logger.error(f"get_proposal failed: {exc}")
        return None


def _update(proposal_id: int, **fields) -> None:
    if not fields:
        return
    try:
        from db import get_db_connection
        with get_db_connection() as conn:
            _ensure_table(conn)
            sets = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(
                f"UPDATE proposed_orders SET {sets} WHERE id = ?",
                list(fields.values()) + [proposal_id],
            )
    except Exception as exc:
        logger.error(f"_update proposal failed: {exc}")


def _claim_pending(proposal_id: int, user_id: str, new_status: str = "APPROVED") -> bool:
    """
    Atomically transition a proposal out of PENDING. Returns True only for the
    single caller that won the race. This is the guard against a double-tap
    (web + Telegram, or two fast Telegram taps) placing the same real order twice.
    """
    try:
        from db import get_db_connection
        with get_db_connection() as conn:
            _ensure_table(conn)
            cur = conn.execute(
                "UPDATE proposed_orders SET status = ?, decided_at = ? "
                "WHERE id = ? AND user_id = ? AND status = 'PENDING'",
                (new_status, datetime.now(IST).isoformat(), proposal_id, user_id),
            )
            return (cur.rowcount or 0) == 1
    except Exception as exc:
        logger.error(f"_claim_pending failed: {exc}")
        return False


def expire_stale_proposals() -> int:
    """Mark PENDING proposals past their expiry as EXPIRED. Returns count."""
    now = datetime.now(IST).isoformat()
    try:
        from db import get_db_connection
        with get_db_connection() as conn:
            _ensure_table(conn)
            cur = conn.execute(
                "UPDATE proposed_orders SET status = 'EXPIRED' "
                "WHERE status = 'PENDING' AND expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )
            return cur.rowcount or 0
    except Exception as exc:
        logger.error(f"expire_stale_proposals failed: {exc}")
        return 0


def _today_live_deployment(user_id: str) -> float:
    """Sum of ₹ deployed in BUY proposals that were filled/approved today."""
    today = datetime.now(IST).date().isoformat()
    try:
        from db import get_db_connection
        with get_db_connection() as conn:
            _ensure_table(conn)
            rows = conn.execute(
                "SELECT fill_price, fill_quantity, price, quantity FROM proposed_orders "
                "WHERE user_id = ? AND side = 'BUY' AND status IN ('FILLED','APPROVED') "
                "AND substr(decided_at, 1, 10) = ?",
                (user_id, today),
            ).fetchall()
        total = 0.0
        for r in rows:
            px = float(r["fill_price"] or r["price"] or 0)
            qt = float(r["fill_quantity"] or r["quantity"] or 0)
            total += px * qt
        return total
    except Exception as exc:
        logger.debug(f"_today_live_deployment fallback: {exc}")
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Cap enforcement (rupee guardrails on top of RiskGate %-rules)
# ─────────────────────────────────────────────────────────────────────────────
def check_rupee_caps(user_id: str, side: str, value_inr: float) -> tuple[bool, str]:
    """Return (ok, reason). SELLs are never capped (they reduce exposure)."""
    if side != "BUY":
        return True, ""
    from broker_manager import get_broker_settings
    s = get_broker_settings(user_id)
    if value_inr > float(s["max_order_value_inr"]):
        return False, (f"Order ₹{value_inr:,.0f} exceeds per-order cap "
                       f"₹{s['max_order_value_inr']:,.0f}")
    deployed = _today_live_deployment(user_id)
    if deployed + value_inr > float(s["max_daily_deployment_inr"]):
        return False, (f"Would exceed daily deployment cap "
                       f"₹{s['max_daily_deployment_inr']:,.0f} "
                       f"(already ₹{deployed:,.0f} today)")
    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# Approval → live execution → reconciliation
# ─────────────────────────────────────────────────────────────────────────────
def approve_proposal(proposal_id: int, user_id: str) -> dict:
    """Validate, place the real order, reconcile the fill. Returns a result dict."""
    from broker_manager import get_broker, is_live_trading_enabled

    prop = get_proposal(proposal_id, user_id)
    if not prop:
        return {"error": "Proposal not found"}
    if prop["status"] != "PENDING":
        return {"error": f"Proposal is {prop['status']}, not actionable"}

    # Expiry guard
    exp = prop.get("expires_at")
    if exp and datetime.fromisoformat(str(exp)) < datetime.now(IST):
        _update(proposal_id, status="EXPIRED")
        return {"error": "Proposal expired"}

    # Hard kill-switch
    if not is_live_trading_enabled(user_id):
        return {"error": "Live trading is disabled. Enable it in broker settings first.",
                "live_trading_disabled": True}

    broker = get_broker(user_id)
    if broker.broker_name == "paper" or not broker.is_connected():
        return {"error": "Broker not connected — re-link required", "needs_relink": True}

    side  = prop["side"]
    qty   = float(prop["quantity"])
    price = float(prop["price"] or 0)

    # Re-check rupee caps at approval time (price may have moved)
    ok, reason = check_rupee_caps(user_id, side, price * qty)
    if not ok:
        _update(proposal_id, status="REJECTED",
                decided_at=datetime.now(IST).isoformat(),
                risk_gate_result=json.dumps({"cap_block": reason}))
        return {"error": reason, "cap_block": True}

    # Re-run RiskGate for BUYs (market conditions may have changed)
    if side == "BUY":
        try:
            from risk_gate import risk_gate
            from signal_engine import score_stock
            from stock_data import get_liquidity_and_earnings
            portfolio_ctx = risk_gate.build_portfolio_context(user_id)
            sig = score_stock(prop["ticker"])
            liq = get_liquidity_and_earnings(prop["ticker"])
            market_data = {**sig.get("market_data", {}),
                           "avg_daily_volume_cr": liq.get("avg_daily_volume_cr"),
                           "days_to_earnings":    liq.get("days_to_earnings")}
            passed, failures = risk_gate.check_all(
                ticker=prop["ticker"], side=side, quantity=int(qty),
                entry_price=price, portfolio=portfolio_ctx, market_data=market_data,
                confidence=float(prop.get("confidence") or 0.75), user_id=user_id,
            )
            if not passed:
                _update(proposal_id, status="REJECTED",
                        decided_at=datetime.now(IST).isoformat(),
                        risk_gate_result=json.dumps({"passed": False, "failures": failures}))
                return {"error": "RiskGate blocked at approval time", "rule_failures": failures}
        except Exception as exc:
            logger.error(f"RiskGate re-check failed for proposal {proposal_id}: {exc}")
            return {"error": f"Risk re-check failed: {exc}"}

    # Atomically claim the proposal (PENDING → APPROVED). Only one caller wins;
    # a concurrent approve (e.g. web + Telegram) gets False and bails, so the
    # real order is never placed twice.
    if not _claim_pending(proposal_id, user_id, "APPROVED"):
        return {"error": "Proposal is no longer pending (already approved, rejected, or expired)."}

    # Place the real order
    result = broker.place_order(
        user_id=user_id, ticker=prop["ticker"], side=side, quantity=int(qty),
        order_type=prop["order_type"] or "MARKET",
        price=price if (prop["order_type"] == "LIMIT") else None,
        stop_price=float(prop["stop_loss"]) if prop.get("stop_loss") else None,
    )
    if result.get("error"):
        _update(proposal_id, status="FAILED")
        return {"error": result["error"], "needs_relink": result.get("needs_relink", False)}

    broker_order_id = result.get("order_id")
    _update(proposal_id, broker_order_id=str(broker_order_id))

    # Reconcile the async fill
    recon = _reconcile_fill(broker, broker_order_id)
    fill_price = recon.get("average_price") or price
    fill_qty   = recon.get("filled_quantity") or qty
    final_status = recon["status"] if recon["status"] in ("FILLED", "FAILED") else "APPROVED"

    _update(proposal_id, status=final_status,
            fill_price=fill_price, fill_quantity=fill_qty)

    # Cross-module awareness + audit on a confirmed fill
    if final_status == "FILLED":
        try:
            from shared_context import signal_from_trade
            signal_from_trade(user_id, prop["ticker"], side, fill_qty, fill_price,
                              reasoning=f"LIVE {side} via Zerodha (approved): {prop.get('reasoning','')[:120]}")
        except Exception:
            pass
        try:
            from audit import log_event
            log_event(user_id, "order.live_fill", entity_type="proposed_order",
                      entity_id=proposal_id,
                      details={"ticker": prop["ticker"], "side": side,
                               "qty": fill_qty, "price": fill_price,
                               "broker_order_id": str(broker_order_id)})
        except Exception:
            pass

    return {
        "success": final_status == "FILLED",
        "status": final_status,
        "proposal_id": proposal_id,
        "broker_order_id": str(broker_order_id),
        "fill_price": fill_price,
        "fill_quantity": fill_qty,
        "ticker": prop["ticker"],
        "side": side,
        "message": recon.get("message"),
    }


def reject_proposal(proposal_id: int, user_id: str) -> dict:
    prop = get_proposal(proposal_id, user_id)
    if not prop:
        return {"error": "Proposal not found"}
    if prop["status"] != "PENDING":
        return {"error": f"Proposal is {prop['status']}, not actionable"}
    # Atomic claim — avoids the same TOCTOU race as approve.
    if not _claim_pending(proposal_id, user_id, "REJECTED"):
        return {"error": "Proposal is no longer pending"}
    try:
        from audit import log_event
        log_event(user_id, "proposal.reject", entity_type="proposed_order",
                  entity_id=proposal_id, details={"ticker": prop["ticker"]})
    except Exception:
        pass
    return {"success": True, "status": "REJECTED", "proposal_id": proposal_id}


def reconcile_open_orders() -> int:
    """Finalize APPROVED proposals whose broker order hadn't filled yet.

    Run periodically (Celery beat). Re-polls the broker once per open order and
    moves it to FILLED/FAILED, recording the fill + audit on success.
    """
    from broker_manager import get_broker
    from db import get_db_connection
    finalized = 0
    try:
        with get_db_connection() as conn:
            _ensure_table(conn)
            rows = conn.execute(
                "SELECT id, user_id, ticker, side, quantity, price, broker_order_id, reasoning "
                "FROM proposed_orders WHERE status = 'APPROVED' AND broker_order_id IS NOT NULL"
            ).fetchall()
        for r in [dict(x) for x in rows]:
            broker = get_broker(r["user_id"])
            if broker.broker_name == "paper" or not broker.is_connected():
                continue
            st = broker.get_order_status(str(r["broker_order_id"]))
            if st.get("status") not in ("FILLED", "FAILED"):
                continue
            fill_price = st.get("average_price") or r["price"]
            fill_qty   = st.get("filled_quantity") or r["quantity"]
            _update(r["id"], status=st["status"], fill_price=fill_price, fill_quantity=fill_qty)
            finalized += 1
            if st["status"] == "FILLED":
                try:
                    from shared_context import signal_from_trade
                    signal_from_trade(r["user_id"], r["ticker"], r["side"], fill_qty, fill_price,
                                      reasoning=f"LIVE {r['side']} via Zerodha (reconciled)")
                except Exception:
                    pass
                try:
                    from audit import log_event
                    log_event(r["user_id"], "order.live_fill", entity_type="proposed_order",
                              entity_id=r["id"],
                              details={"ticker": r["ticker"], "side": r["side"],
                                       "qty": fill_qty, "price": fill_price, "reconciled": True})
                except Exception:
                    pass
    except Exception as exc:
        logger.error(f"reconcile_open_orders failed: {exc}")
    return finalized


def _reconcile_fill(broker, broker_order_id) -> dict:
    """Poll the broker until the order reaches a terminal state (or polls run out)."""
    last = {"status": "PENDING", "filled_quantity": None, "average_price": None}
    for _ in range(RECONCILE_POLLS):
        status = broker.get_order_status(str(broker_order_id))
        last = status
        if status.get("status") in ("FILLED", "FAILED"):
            return status
        time.sleep(RECONCILE_DELAY)
    # Timed out still pending — leave as APPROVED, a later reconcile sweep can finalize.
    logger.warning(f"Order {broker_order_id} still unfilled after {RECONCILE_POLLS} polls")
    return last
