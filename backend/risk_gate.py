"""
RiskGate — hard rule enforcement for every paper trade.

All checks must pass before any trade executes. Zero AI involvement here.
No override possible. This is what separates a product from a demo.
"""

import logging
from datetime import datetime, time as dtime

logger = logging.getLogger(__name__)

# ── Default risk settings (used when user has no custom settings) ──────────────
DEFAULT_RISK_SETTINGS = {
    "max_risk_per_trade":     1.5,    # % of portfolio at risk per trade
    "max_single_stock_pct":   20.0,   # % max in one stock
    "max_portfolio_heat":     60.0,   # % max total deployed
    "max_open_positions":     5,
    "daily_loss_limit":       5.0,    # % daily loss triggers halt
    "drawdown_pause":         15.0,   # % drawdown from peak pauses strategy
    "min_confidence":         70.0,   # % minimum AI confidence
    "fii_selling_block_cr":   2000,   # ₹cr FII selling that blocks new longs
    "india_vix_limit":        25.0,   # VIX above this = no new longs
    "min_liquidity_cr":       5.0,    # min avg daily volume in crores
    "consecutive_loss_limit": 3,      # losses before HOLD-only mode
    "earnings_blackout_days": 2,      # days before earnings = no entry
}

# Optimal trading window (IST)
TRADING_WINDOW_START = dtime(10, 0)
TRADING_WINDOW_END   = dtime(14, 30)


def get_user_risk_settings(user_id: str) -> dict:
    """
    Load per-user risk settings from DB.
    Falls back to DEFAULT_RISK_SETTINGS for any missing keys.
    """
    try:
        from db import get_db_connection
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT * FROM user_risk_settings WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row:
            saved = dict(row)
            # Merge: saved values override defaults, keep defaults for missing keys
            return {k: saved.get(k, v) for k, v in DEFAULT_RISK_SETTINGS.items()}
    except Exception as e:
        logger.debug(f"[RiskGate] Could not load user settings: {e}")
    return DEFAULT_RISK_SETTINGS.copy()


def save_user_risk_settings(user_id: str, updates: dict) -> dict:
    """
    Save user risk settings. Only accepts keys in DEFAULT_RISK_SETTINGS.
    Returns the merged settings after saving.
    """
    # Only allow valid keys
    clean = {k: updates[k] for k in DEFAULT_RISK_SETTINGS if k in updates}
    try:
        from db import get_db_connection
        with get_db_connection() as conn:
            _ensure_risk_settings_table(conn)
            existing = conn.execute(
                "SELECT user_id FROM user_risk_settings WHERE user_id = ?", (user_id,)
            ).fetchone()
            if existing:
                sets   = ", ".join(f"{k} = ?" for k in clean)
                values = list(clean.values()) + [user_id]
                conn.execute(f"UPDATE user_risk_settings SET {sets} WHERE user_id = ?", values)
            else:
                cols   = "user_id, " + ", ".join(clean.keys())
                placeholders = "?, " + ", ".join("?" * len(clean))
                conn.execute(
                    f"INSERT INTO user_risk_settings ({cols}) VALUES ({placeholders})",
                    [user_id] + list(clean.values())
                )
    except Exception as e:
        logger.error(f"[RiskGate] save_user_risk_settings failed: {e}")
    return get_user_risk_settings(user_id)


def _ensure_risk_settings_table(conn) -> None:
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS user_risk_settings (
            user_id                TEXT PRIMARY KEY,
            max_risk_per_trade     REAL DEFAULT {DEFAULT_RISK_SETTINGS['max_risk_per_trade']},
            max_single_stock_pct   REAL DEFAULT {DEFAULT_RISK_SETTINGS['max_single_stock_pct']},
            max_portfolio_heat     REAL DEFAULT {DEFAULT_RISK_SETTINGS['max_portfolio_heat']},
            max_open_positions     INTEGER DEFAULT {DEFAULT_RISK_SETTINGS['max_open_positions']},
            daily_loss_limit       REAL DEFAULT {DEFAULT_RISK_SETTINGS['daily_loss_limit']},
            drawdown_pause         REAL DEFAULT {DEFAULT_RISK_SETTINGS['drawdown_pause']},
            min_confidence         REAL DEFAULT {DEFAULT_RISK_SETTINGS['min_confidence']},
            fii_selling_block_cr   REAL DEFAULT {DEFAULT_RISK_SETTINGS['fii_selling_block_cr']},
            india_vix_limit        REAL DEFAULT {DEFAULT_RISK_SETTINGS['india_vix_limit']},
            min_liquidity_cr       REAL DEFAULT {DEFAULT_RISK_SETTINGS['min_liquidity_cr']},
            consecutive_loss_limit INTEGER DEFAULT {DEFAULT_RISK_SETTINGS['consecutive_loss_limit']},
            earnings_blackout_days INTEGER DEFAULT {DEFAULT_RISK_SETTINGS['earnings_blackout_days']},
            updated_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


class RiskGate:
    """
    All checks return (passed: bool, failures: list[str]).
    Every check must pass — majority vote is NOT enough.
    Settings are loaded per-user from DB, falling back to defaults.
    """

    def check_all(
        self,
        ticker: str,
        side: str,
        quantity: int,
        entry_price: float,
        portfolio: dict,
        market_data: dict | None = None,
        confidence: float = 1.0,
        user_id: str | None = None,
    ) -> tuple[bool, list[str]]:
        """
        Run all hard rules.

        portfolio dict expected keys:
            balance         float   — cash available
            total_value     float   — cash + market value of holdings
            heat            float   — fraction of portfolio currently deployed (0-1)
            open_positions  list    — list of dicts with 'ticker', 'value', 'pnl_pct'
            today_pnl_pct   float   — today's P&L as fraction
            peak_value      float   — highest portfolio value ever (for drawdown)
            consecutive_losses int  — recent consecutive losing trades

        market_data dict expected keys (all optional — degrade gracefully):
            india_vix           float
            fii_net_today_cr    float   — FII net in crores (negative = selling)
            days_to_earnings    int     — days until next earnings for this ticker
            avg_daily_volume_cr float   — avg daily traded value in crores
            correlations        dict    — {ticker: correlation_coeff}
        """
        if side != "BUY":
            return True, []   # SELL orders skip risk checks

        # Load per-user settings (falls back to defaults if not configured)
        s  = get_user_risk_settings(user_id) if user_id else DEFAULT_RISK_SETTINGS.copy()
        failures = []
        md = market_data or {}

        # ── 1. Confidence ────────────────────────────────────────────────────
        min_conf = s["min_confidence"] / 100
        if confidence < min_conf:
            failures.append(
                f"AI confidence {confidence:.0%} below your minimum {s['min_confidence']:.0f}%"
            )

        # ── 2. Position value cap ─────────────────────────────────────────────
        position_value = quantity * entry_price
        total_value    = portfolio.get("total_value", 0)
        max_stock_pct  = s["max_single_stock_pct"] / 100
        if total_value > 0:
            position_pct = position_value / total_value
            if position_pct > max_stock_pct:
                failures.append(
                    f"Position ₹{position_value:,.0f} = {position_pct:.1%} of portfolio "
                    f"— exceeds your {s['max_single_stock_pct']:.0f}% cap"
                )

        # ── 3. Portfolio heat ─────────────────────────────────────────────────
        current_heat  = portfolio.get("heat", 0)
        new_heat      = current_heat + (position_value / total_value if total_value else 0)
        max_heat      = s["max_portfolio_heat"] / 100
        if new_heat > max_heat:
            failures.append(
                f"Portfolio heat would reach {new_heat:.1%} — your cap is {s['max_portfolio_heat']:.0f}%"
            )

        # ── 4. Max open positions ─────────────────────────────────────────────
        open_count = len(portfolio.get("open_positions", []))
        if open_count >= s["max_open_positions"]:
            failures.append(
                f"Already at your max {s['max_open_positions']} open positions"
            )

        # ── 5. Daily loss limit ───────────────────────────────────────────────
        today_pnl       = portfolio.get("today_pnl_pct", 0)
        daily_loss_frac = s["daily_loss_limit"] / 100
        if today_pnl < -daily_loss_frac:
            failures.append(
                f"Daily loss {today_pnl:.1%} exceeds your -{s['daily_loss_limit']:.0f}% limit — no new trades today"
            )

        # ── 6. Drawdown pause ─────────────────────────────────────────────────
        peak_value    = portfolio.get("peak_value", total_value)
        drawdown_frac = s["drawdown_pause"] / 100
        if peak_value and total_value:
            drawdown = (peak_value - total_value) / peak_value
            if drawdown > drawdown_frac:
                failures.append(
                    f"Portfolio drawdown {drawdown:.1%} from peak — strategy paused (your limit: {s['drawdown_pause']:.0f}%)"
                )

        # ── 7. Consecutive losses ─────────────────────────────────────────────
        consec = portfolio.get("consecutive_losses", 0)
        if consec >= s["consecutive_loss_limit"]:
            failures.append(
                f"{consec} consecutive losses — HOLD-only mode (your limit: {s['consecutive_loss_limit']})"
            )

        # ── 8. Earnings blackout ──────────────────────────────────────────────
        days_to_earnings = md.get("days_to_earnings")
        if days_to_earnings is not None and days_to_earnings <= s["earnings_blackout_days"]:
            failures.append(
                f"Earnings in {days_to_earnings} day(s) — your {s['earnings_blackout_days']}-day blackout applies"
            )

        # ── 9. India VIX ──────────────────────────────────────────────────────
        vix = md.get("india_vix")
        if vix is not None and vix > s["india_vix_limit"]:
            failures.append(
                f"India VIX {vix:.1f} > your limit {s['india_vix_limit']:.0f} — avoid new longs"
            )

        # ── 10. FII heavy selling ─────────────────────────────────────────────
        fii_net = md.get("fii_net_today_cr")
        if fii_net is not None and fii_net < -s["fii_selling_block_cr"]:
            failures.append(
                f"FII sold ₹{abs(fii_net):,.0f}cr — exceeds your block threshold ₹{s['fii_selling_block_cr']:,.0f}cr"
            )

        # ── 11. Liquidity filter ──────────────────────────────────────────────
        avg_vol = md.get("avg_daily_volume_cr")
        if avg_vol is not None and avg_vol < s["min_liquidity_cr"]:
            failures.append(
                f"Low liquidity: avg volume ₹{avg_vol:.1f}cr < your minimum ₹{s['min_liquidity_cr']:.0f}cr"
            )

        # ── 12. Correlation with existing positions ───────────────────────────
        correlations = md.get("correlations", {})
        for held_ticker, corr in correlations.items():
            if abs(corr) > 0.85:   # Fixed — correlation threshold not user-configurable
                failures.append(
                    f"High correlation ({corr:.2f}) with held {held_ticker} — concentration risk"
                )

        # ── 13. Sufficient capital ────────────────────────────────────────────
        balance = portfolio.get("balance", 0)
        if position_value > balance:
            failures.append(
                f"Insufficient cash: need ₹{position_value:,.0f}, available ₹{balance:,.0f}"
            )

        # ── 14. Trading window ────────────────────────────────────────────────
        now_utc  = datetime.utcnow()
        ist_hour = (now_utc.hour * 60 + now_utc.minute + 330) // 60 % 24
        ist_min  = (now_utc.hour * 60 + now_utc.minute + 330) % 60
        now_ist  = dtime(ist_hour, ist_min)
        if not (TRADING_WINDOW_START <= now_ist <= TRADING_WINDOW_END):
            logger.debug(f"Trade outside optimal window {TRADING_WINDOW_START}–{TRADING_WINDOW_END} IST")

        passed = len(failures) == 0
        if not passed:
            logger.info(
                f"[RiskGate] BLOCKED {side} {ticker}: {len(failures)} rule(s) failed: "
                + " | ".join(failures)
            )
        return passed, failures

    # ── ATR-based position sizing ─────────────────────────────────────────────
    def calculate_position_size(
        self,
        ticker: str,
        entry_price: float,
        stop_loss: float,
        portfolio_value: float,
        available_cash: float,
        risk_fraction: float | None = None,
        user_id: str | None = None,
    ) -> dict:
        """
        ATR/stop-loss based position sizing.

        Risk per trade = portfolio_value * risk_fraction
        Position size  = risk_amount / risk_per_share
        Capped at:      20% of portfolio OR available cash (whichever is smaller)

        Returns dict with quantity, capital_required, capital_at_risk, within_limits.
        """
        if entry_price <= 0:
            return {"error": "entry_price must be > 0", "quantity": 0}

        risk_per_share = abs(entry_price - stop_loss) if stop_loss else entry_price * 0.02
        if risk_per_share == 0:
            return {"error": "stop_loss must differ from entry_price", "quantity": 0}

        # Load user settings to get their configured risk % and stock cap
        s = get_user_risk_settings(user_id) if user_id else DEFAULT_RISK_SETTINGS.copy()
        effective_risk   = (risk_fraction if risk_fraction is not None else s["max_risk_per_trade"]) / 100
        max_stock_frac   = s["max_single_stock_pct"] / 100

        risk_amount      = portfolio_value * effective_risk
        qty_by_risk      = risk_amount / risk_per_share
        max_by_pct       = (portfolio_value * max_stock_frac) / entry_price
        max_by_cash      = available_cash / entry_price
        quantity         = max(1, int(min(qty_by_risk, max_by_pct, max_by_cash)))
        capital_required = round(quantity * entry_price, 2)

        return {
            "ticker":            ticker,
            "quantity":          quantity,
            "entry_price":       entry_price,
            "stop_loss":         stop_loss,
            "capital_required":  capital_required,
            "capital_at_risk":   round(quantity * risk_per_share, 2),
            "risk_pct_portfolio": round((quantity * risk_per_share / portfolio_value) * 100, 2)
                                  if portfolio_value else 0,
            "available_cash":    round(available_cash, 2),
            "within_limits":     capital_required <= available_cash,
        }

    # ── Portfolio state helpers ───────────────────────────────────────────────
    def build_portfolio_context(self, user_id: str) -> dict:
        """
        Fetch live portfolio state for risk checks.
        Returns portfolio dict matching the schema expected by check_all().
        """
        try:
            from trading_manager import get_trading_balance, get_trading_portfolio
            from stock_data import get_bulk_prices
            from db import get_db_connection

            balance_row = get_trading_balance(user_id) or {}
            holdings    = get_trading_portfolio(user_id) or []
            prices      = get_bulk_prices([h["ticker"] for h in holdings]) if holdings else {}

            balance     = float(balance_row.get("balance") or 0)
            market_val  = sum(
                float(h["quantity"]) * float(prices.get(h["ticker"]) or h["avg_buy_price"])
                for h in holdings
            )
            total_value = balance + market_val
            heat        = market_val / total_value if total_value else 0

            # Today's P&L from snapshot table
            today_pnl_pct = 0.0
            try:
                today = datetime.utcnow().strftime("%Y-%m-%d")
                with get_db_connection() as conn:
                    snap = conn.execute(
                        "SELECT pnl_pct FROM trading_daily_snapshots "
                        "WHERE user_id = ? AND date = ?",
                        (user_id, today)
                    ).fetchone()
                    if snap:
                        today_pnl_pct = float(snap["pnl_pct"] or 0) / 100
            except Exception:
                pass

            # Peak value from snapshot history
            peak_value = total_value
            try:
                with get_db_connection() as conn:
                    peak_row = conn.execute(
                        "SELECT MAX(portfolio_value) as peak FROM trading_daily_snapshots "
                        "WHERE user_id = ?",
                        (user_id,)
                    ).fetchone()
                    if peak_row and peak_row["peak"]:
                        peak_value = float(peak_row["peak"])
            except Exception:
                pass

            # Consecutive losses from recent trades
            consecutive_losses = 0
            try:
                with get_db_connection() as conn:
                    recent_sells = conn.execute(
                        "SELECT t_sell.ticker, t_sell.price as sell_price, t_buy.price as buy_price "
                        "FROM trades t_sell "
                        "JOIN trades t_buy ON t_buy.user_id = t_sell.user_id "
                            "AND t_buy.ticker = t_sell.ticker AND t_buy.side = 'BUY' "
                        "WHERE t_sell.user_id = ? AND t_sell.side = 'SELL' "
                        "ORDER BY t_sell.executed_at DESC LIMIT 5",
                        (user_id,)
                    ).fetchall()
                    for row in recent_sells:
                        if float(row["sell_price"]) < float(row["buy_price"]):
                            consecutive_losses += 1
                        else:
                            break  # Win breaks the streak
            except Exception:
                pass

            open_positions = [
                {"ticker": h["ticker"], "value": float(h["quantity"]) * float(
                    prices.get(h["ticker"]) or h["avg_buy_price"]
                )}
                for h in holdings
            ]

            return {
                "balance":            balance,
                "total_value":        total_value,
                "heat":               heat,
                "open_positions":     open_positions,
                "today_pnl_pct":      today_pnl_pct,
                "peak_value":         peak_value,
                "consecutive_losses": consecutive_losses,
            }
        except Exception as e:
            logger.error(f"[RiskGate] build_portfolio_context failed: {e}")
            return {
                "balance": 0, "total_value": 0, "heat": 0,
                "open_positions": [], "today_pnl_pct": 0,
                "peak_value": 0, "consecutive_losses": 0,
            }


# Module-level singleton
risk_gate = RiskGate()
