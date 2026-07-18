"""
Broker Manager — abstraction layer for paper and live trading.

BrokerManager (abstract)
├── PaperBrokerManager         — routes to trading_manager.py (default)
└── ZerodhaKiteBrokerManager   — live trading via Zerodha Kite Connect API

Selection logic (get_broker(user_id)):
  - If ZERODHA_API_KEY env var is set → ZerodhaKiteBrokerManager (per-user)
  - Otherwise                         → PaperBrokerManager

Live trading is approval-gated and protected by a per-user kill-switch
(broker_settings.live_trading_enabled, default FALSE). Access tokens are
persisted ENCRYPTED (Fernet) and expire daily (~6 AM IST, Kite Connect rule),
so connections survive a restart but require a morning re-link.

Install for live trading:
  pip install kiteconnect cryptography
"""

import base64
import hashlib
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))


# ─────────────────────────────────────────────────────────────────────────────
# Token encryption (Fernet) — never store raw broker tokens at rest
# ─────────────────────────────────────────────────────────────────────────────
_DEV_FALLBACK_KEY = "stockeye-dev-broker-key"


def _fernet():
    """Build a Fernet cipher from BROKER_TOKEN_KEY (or FLASK_SECRET_KEY fallback).

    Any string works as the key source — we SHA-256 it to a valid 32-byte
    Fernet key, so operators don't need to generate a specific key format.

    SECURITY: real Zerodha access tokens are encrypted with this key. In
    production we refuse to fall back to the public dev constant — otherwise the
    "encryption" would be trivially reversible by anyone with the source. Set
    BROKER_TOKEN_KEY (or at least a strong FLASK_SECRET_KEY) in production.
    """
    from cryptography.fernet import Fernet
    src = os.environ.get("BROKER_TOKEN_KEY") or os.environ.get("FLASK_SECRET_KEY")
    if not src:
        is_prod = os.environ.get("FLASK_ENV", "").lower() == "production"
        if is_prod:
            raise RuntimeError(
                "Refusing to encrypt broker tokens with the public dev key in production. "
                "Set BROKER_TOKEN_KEY (or a strong FLASK_SECRET_KEY) in the environment."
            )
        logger.warning("BROKER_TOKEN_KEY/FLASK_SECRET_KEY unset — using INSECURE dev key. "
                       "Do NOT use this for real broker tokens.")
        src = _DEV_FALLBACK_KEY
    key = base64.urlsafe_b64encode(hashlib.sha256(src.encode()).digest())
    return Fernet(key)


def _encrypt(token: str) -> str:
    try:
        return _fernet().encrypt(token.encode()).decode()
    except Exception as exc:
        logger.error(f"Broker token encryption failed: {exc}")
        return ""


def _decrypt(blob: str) -> str | None:
    if not blob:
        return None
    try:
        return _fernet().decrypt(blob.encode()).decode()
    except Exception as exc:
        logger.error(f"Broker token decryption failed: {exc}")
        return None


def _next_token_expiry() -> datetime:
    """Kite tokens are valid until the next 6 AM IST."""
    now = datetime.now(IST)
    exp = now.replace(hour=6, minute=0, second=0, microsecond=0)
    if now >= exp:
        exp += timedelta(days=1)
    return exp


# ─────────────────────────────────────────────────────────────────────────────
# Persistence: broker_tokens + broker_settings (lazy-created for SQLite dev;
# the canonical Postgres schema lives in schema.sql)
# ─────────────────────────────────────────────────────────────────────────────
def _ensure_token_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS broker_tokens (
            user_id      TEXT NOT NULL,
            broker       TEXT NOT NULL DEFAULT 'zerodha',
            access_token TEXT,
            public_token TEXT,
            connected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at   TIMESTAMP,
            status       TEXT DEFAULT 'connected',
            updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, broker)
        )
    """)


def save_broker_token(user_id: str, broker: str, access_token: str,
                      public_token: str = "", expires_at: datetime = None) -> None:
    """Persist an encrypted access token (manual upsert, dialect-agnostic)."""
    expires_at = expires_at or _next_token_expiry()
    exp_iso = expires_at.isoformat()
    enc = _encrypt(access_token)
    try:
        from db import get_db_connection
        with get_db_connection() as conn:
            _ensure_token_table(conn)
            existing = conn.execute(
                "SELECT user_id FROM broker_tokens WHERE user_id = ? AND broker = ?",
                (user_id, broker),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE broker_tokens SET access_token = ?, public_token = ?, "
                    "connected_at = CURRENT_TIMESTAMP, expires_at = ?, "
                    "status = 'connected', updated_at = CURRENT_TIMESTAMP "
                    "WHERE user_id = ? AND broker = ?",
                    (enc, public_token, exp_iso, user_id, broker),
                )
            else:
                conn.execute(
                    "INSERT INTO broker_tokens "
                    "(user_id, broker, access_token, public_token, expires_at, status) "
                    "VALUES (?, ?, ?, ?, ?, 'connected')",
                    (user_id, broker, enc, public_token, exp_iso),
                )
        logger.info(f"Broker token persisted for user={user_id} broker={broker}")
    except Exception as exc:
        logger.error(f"save_broker_token failed: {exc}")


def load_broker_token(user_id: str, broker: str) -> dict | None:
    """Return {access_token (decrypted), expires_at (datetime), expired (bool)} or None."""
    try:
        from db import get_db_connection
        with get_db_connection() as conn:
            _ensure_token_table(conn)
            row = conn.execute(
                "SELECT access_token, expires_at, status FROM broker_tokens "
                "WHERE user_id = ? AND broker = ?",
                (user_id, broker),
            ).fetchone()
        if not row:
            return None
        token = _decrypt(row["access_token"])
        if not token:
            return None
        expires_at = _parse_dt(row["expires_at"])
        expired = bool(expires_at and datetime.now(IST) >= expires_at)
        return {"access_token": token, "expires_at": expires_at, "expired": expired}
    except Exception as exc:
        logger.error(f"load_broker_token failed: {exc}")
        return None


def clear_broker_token(user_id: str, broker: str) -> None:
    try:
        from db import get_db_connection
        with get_db_connection() as conn:
            _ensure_token_table(conn)
            conn.execute(
                "DELETE FROM broker_tokens WHERE user_id = ? AND broker = ?",
                (user_id, broker),
            )
    except Exception as exc:
        logger.error(f"clear_broker_token failed: {exc}")


def _parse_dt(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=IST)
    try:
        dt = datetime.fromisoformat(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=IST)
    except Exception:
        return None


# ─── Broker settings (kill-switch + rupee caps) ────────────────────────────────
DEFAULT_BROKER_SETTINGS = {
    "live_trading_enabled":     False,
    "max_order_value_inr":      5000.0,
    "max_daily_deployment_inr": 25000.0,
}


def _ensure_settings_table(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS broker_settings (
            user_id                  TEXT PRIMARY KEY,
            live_trading_enabled     BOOLEAN DEFAULT 0,
            max_order_value_inr      REAL DEFAULT 5000,
            max_daily_deployment_inr REAL DEFAULT 25000,
            updated_at               TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def get_broker_settings(user_id: str) -> dict:
    try:
        from db import get_db_connection
        with get_db_connection() as conn:
            _ensure_settings_table(conn)
            row = conn.execute(
                "SELECT * FROM broker_settings WHERE user_id = ?", (user_id,)
            ).fetchone()
        if row:
            saved = dict(row)
            out = DEFAULT_BROKER_SETTINGS.copy()
            out.update({
                "live_trading_enabled":     bool(saved.get("live_trading_enabled")),
                "max_order_value_inr":      float(saved.get("max_order_value_inr") or DEFAULT_BROKER_SETTINGS["max_order_value_inr"]),
                "max_daily_deployment_inr": float(saved.get("max_daily_deployment_inr") or DEFAULT_BROKER_SETTINGS["max_daily_deployment_inr"]),
            })
            return out
    except Exception as exc:
        logger.debug(f"get_broker_settings fallback: {exc}")
    return DEFAULT_BROKER_SETTINGS.copy()


def save_broker_settings(user_id: str, updates: dict) -> dict:
    clean = {k: updates[k] for k in DEFAULT_BROKER_SETTINGS if k in updates}
    if not clean:
        return get_broker_settings(user_id)
    if "live_trading_enabled" in clean:
        clean["live_trading_enabled"] = 1 if clean["live_trading_enabled"] else 0
    try:
        from db import get_db_connection
        with get_db_connection() as conn:
            _ensure_settings_table(conn)
            existing = conn.execute(
                "SELECT user_id FROM broker_settings WHERE user_id = ?", (user_id,)
            ).fetchone()
            if existing:
                sets   = ", ".join(f"{k} = ?" for k in clean)
                conn.execute(
                    f"UPDATE broker_settings SET {sets}, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                    list(clean.values()) + [user_id],
                )
            else:
                cols = "user_id, " + ", ".join(clean.keys())
                ph   = "?, " + ", ".join("?" * len(clean))
                conn.execute(
                    f"INSERT INTO broker_settings ({cols}) VALUES ({ph})",
                    [user_id] + list(clean.values()),
                )
    except Exception as exc:
        logger.error(f"save_broker_settings failed: {exc}")
    return get_broker_settings(user_id)


def is_live_trading_enabled(user_id: str) -> bool:
    return bool(get_broker_settings(user_id).get("live_trading_enabled"))


# ─────────────────────────────────────────────────────────────────────────────
# Abstract base
# ─────────────────────────────────────────────────────────────────────────────
class BrokerManager(ABC):

    @property
    @abstractmethod
    def broker_name(self) -> str: ...

    @abstractmethod
    def get_login_url(self) -> str | None: ...

    @abstractmethod
    def complete_login(self, request_token: str) -> bool: ...

    @abstractmethod
    def is_connected(self) -> bool: ...

    def needs_relink(self) -> bool:
        """True when a live broker is configured but the token is missing/expired."""
        return False

    @abstractmethod
    def place_order(
        self,
        user_id: str,
        ticker: str,
        side: str,
        quantity: int,
        order_type: str = "MARKET",
        price: float = None,
        stop_price: float = None,
    ) -> dict: ...

    @abstractmethod
    def cancel_order(self, user_id: str, order_id: str) -> bool: ...

    @abstractmethod
    def get_positions(self, user_id: str) -> list: ...

    @abstractmethod
    def get_balance(self, user_id: str) -> dict: ...

    def get_order_status(self, order_id: str) -> dict:
        """Return {status, filled_quantity, average_price} for reconciliation.

        Paper orders fill synchronously, so the default reports EXECUTED.
        """
        return {"status": "EXECUTED", "filled_quantity": None, "average_price": None}

    def get_status(self) -> dict:
        connected = self.is_connected()
        return {
            "broker":       self.broker_name,
            "connected":    connected,
            "mode":         "live" if self.broker_name != "paper" and connected else "paper",
            "needs_relink": self.needs_relink(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Paper trading broker (default)
# ─────────────────────────────────────────────────────────────────────────────
class PaperBrokerManager(BrokerManager):
    """Routes all operations to StockEye's internal paper trading system."""

    @property
    def broker_name(self) -> str:
        return "paper"

    def get_login_url(self) -> str | None:
        return None          # No login needed for paper trading

    def complete_login(self, request_token: str) -> bool:
        return True          # Always connected

    def is_connected(self) -> bool:
        return True

    def place_order(self, user_id, ticker, side, quantity,
                    order_type="MARKET", price=None, stop_price=None) -> dict:
        from trading_manager import place_order
        result = place_order(
            user_id     = user_id,
            ticker      = ticker,
            name        = ticker,
            side        = side,
            order_type  = order_type,
            quantity    = quantity,
            price       = price,
            stop_price  = stop_price,
            limit_price = price if order_type == "LIMIT" else None,
        )
        # trading_manager.place_order returns an order_id (int); normalize to dict
        if isinstance(result, dict):
            return result or {"error": "Paper order failed"}
        if result:
            return {"order_id": str(result), "status": "EXECUTED", "broker": "paper",
                    "ticker": ticker, "side": side, "quantity": quantity}
        return {"error": "Paper order failed"}

    def cancel_order(self, user_id: str, order_id: str) -> bool:
        from trading_manager import cancel_order
        return cancel_order(user_id, order_id)

    def get_positions(self, user_id: str) -> list:
        from trading_manager import get_trading_portfolio
        portfolio = get_trading_portfolio(user_id) or {}
        if isinstance(portfolio, list):
            return portfolio
        return portfolio.get("holdings", [])

    def get_balance(self, user_id: str) -> dict:
        from trading_manager import get_trading_balance
        return get_trading_balance(user_id) or {}


# ─────────────────────────────────────────────────────────────────────────────
# Zerodha Kite live broker (per-user, token-persisted)
# ─────────────────────────────────────────────────────────────────────────────
class ZerodhaKiteBrokerManager(BrokerManager):
    """
    Live trading via Zerodha Kite Connect API.

    Setup:
    1. Create an app at https://developers.kite.trade
    2. Set env vars: ZERODHA_API_KEY, ZERODHA_API_SECRET
    3. Call get_login_url() → redirect user → on callback call complete_login(request_token)
    4. Access token is persisted (encrypted) and expires next ~6 AM IST.
    """

    def __init__(self, user_id: str | None = None):
        self.user_id      = user_id
        self.api_key      = os.environ.get("ZERODHA_API_KEY", "")
        self.api_secret   = os.environ.get("ZERODHA_API_SECRET", "")
        self._kite        = None
        self._access_token: str | None = None
        self._token_expired = False
        if user_id:
            self._hydrate_token()

    @property
    def broker_name(self) -> str:
        return "zerodha"

    def _hydrate_token(self):
        """Load a previously-persisted token for this user (survives restarts)."""
        rec = load_broker_token(self.user_id, "zerodha")
        if rec and not rec["expired"]:
            self._access_token = rec["access_token"]
            self._token_expired = False
        elif rec and rec["expired"]:
            self._access_token = None
            self._token_expired = True

    def _get_kite(self):
        if self._kite is None:
            try:
                from kiteconnect import KiteConnect
                self._kite = KiteConnect(api_key=self.api_key)
                if self._access_token:
                    self._kite.set_access_token(self._access_token)
            except ImportError:
                logger.error(
                    "kiteconnect package not installed. Run: pip install kiteconnect"
                )
        return self._kite

    def get_login_url(self) -> str | None:
        kite = self._get_kite()
        if not kite:
            return None
        return kite.login_url()

    def complete_login(self, request_token: str) -> bool:
        try:
            kite = self._get_kite()
            if not kite:
                return False
            session = kite.generate_session(request_token, api_secret=self.api_secret)
            self._access_token = session["access_token"]
            self._token_expired = False
            kite.set_access_token(self._access_token)
            if self.user_id:
                save_broker_token(
                    self.user_id, "zerodha", self._access_token,
                    public_token=session.get("public_token", ""),
                    expires_at=_next_token_expiry(),
                )
            logger.info("Zerodha Kite login complete — access token acquired & persisted")
            return True
        except Exception as exc:
            logger.error(f"Zerodha login failed: {exc}")
            return False

    def is_connected(self) -> bool:
        return bool(self._access_token and self._get_kite())

    def needs_relink(self) -> bool:
        # Configured (API key present) but no valid live token → user must re-link.
        return bool(self.api_key) and not self.is_connected()

    def place_order(self, user_id, ticker, side, quantity,
                    order_type="MARKET", price=None, stop_price=None) -> dict:
        try:
            kite = self._get_kite()
            if not kite or not self._access_token:
                return {"error": "Zerodha not connected — re-link required",
                        "needs_relink": True}

            transaction = (
                kite.TRANSACTION_TYPE_BUY if side == "BUY"
                else kite.TRANSACTION_TYPE_SELL
            )
            k_order_type = (
                kite.ORDER_TYPE_MARKET if order_type == "MARKET"
                else kite.ORDER_TYPE_LIMIT
            )

            order_id = kite.place_order(
                variety          = kite.VARIETY_REGULAR,
                exchange         = kite.EXCHANGE_NSE,
                tradingsymbol    = ticker,
                transaction_type = transaction,
                quantity         = int(quantity),
                product          = kite.PRODUCT_CNC,    # Cash and Carry (delivery)
                order_type       = k_order_type,
                price            = price if order_type == "LIMIT" else None,
                trigger_price    = stop_price if stop_price else None,
            )
            logger.info(f"Zerodha order placed: {order_id} — {side} {quantity}×{ticker}")
            return {
                "order_id": str(order_id),
                "status":   "PENDING",   # live orders are async — reconcile to confirm fill
                "broker":   "zerodha",
                "ticker":   ticker,
                "side":     side,
                "quantity": quantity,
            }
        except Exception as exc:
            logger.error(f"Zerodha place_order failed: {exc}")
            return {"error": str(exc)}

    def get_order_status(self, order_id: str) -> dict:
        """Poll Kite for the current state of an order (for fill reconciliation)."""
        try:
            kite = self._get_kite()
            if not kite or not self._access_token:
                return {"status": "UNKNOWN", "filled_quantity": None, "average_price": None}
            history = kite.order_history(order_id) or []
            if not history:
                return {"status": "UNKNOWN", "filled_quantity": None, "average_price": None}
            last = history[-1]
            k_status = (last.get("status") or "").upper()
            status_map = {
                "COMPLETE":  "FILLED",
                "REJECTED":  "FAILED",
                "CANCELLED": "FAILED",
                "OPEN":      "PENDING",
                "TRIGGER PENDING": "PENDING",
            }
            return {
                "status":          status_map.get(k_status, "PENDING"),
                "filled_quantity": last.get("filled_quantity"),
                "average_price":   last.get("average_price"),
                "raw_status":      k_status,
                "message":         last.get("status_message"),
            }
        except Exception as exc:
            logger.error(f"Zerodha get_order_status failed: {exc}")
            return {"status": "UNKNOWN", "filled_quantity": None, "average_price": None}

    def cancel_order(self, user_id: str, order_id: str) -> bool:
        try:
            kite = self._get_kite()
            if not kite:
                return False
            kite.cancel_order(variety=kite.VARIETY_REGULAR, order_id=order_id)
            return True
        except Exception as exc:
            logger.error(f"Zerodha cancel_order failed: {exc}")
            return False

    def get_positions(self, user_id: str) -> list:
        """Real delivery holdings (CNC) normalized to StockEye's holding shape."""
        try:
            kite = self._get_kite()
            if not kite or not self._access_token:
                return []
            holdings = kite.holdings() or []
            return [self._normalize_holding(h) for h in holdings]
        except Exception as exc:
            logger.error(f"Zerodha get_positions failed: {exc}")
            return []

    @staticmethod
    def _normalize_holding(h: dict) -> dict:
        qty       = float(h.get("quantity") or 0) + float(h.get("t1_quantity") or 0)
        avg       = float(h.get("average_price") or 0)
        ltp       = float(h.get("last_price") or 0)
        return {
            "ticker":           h.get("tradingsymbol", ""),
            "name":             h.get("tradingsymbol", ""),
            "quantity":         qty,
            "avg_buy_price":    avg,
            "current_price":    ltp,
            "total_investment": round(qty * avg, 2),
            "current_value":    round(qty * ltp, 2),
            "pnl":              float(h.get("pnl") or round(qty * (ltp - avg), 2)),
            "exchange":         h.get("exchange", "NSE"),
        }

    def get_balance(self, user_id: str) -> dict:
        try:
            kite = self._get_kite()
            if not kite or not self._access_token:
                return {}
            margins = kite.margins()
            equity  = margins.get("equity", {})
            return {
                "balance":  equity.get("available", {}).get("live_balance", 0),
                "used":     equity.get("utilised",  {}).get("debits", 0),
                "broker":   "zerodha",
            }
        except Exception as exc:
            logger.error(f"Zerodha get_balance failed: {exc}")
            return {}


# ─────────────────────────────────────────────────────────────────────────────
# Per-user registry + factory
# ─────────────────────────────────────────────────────────────────────────────
_brokers: dict = {}   # keyed by (broker_kind, user_id)


def _live_broker_configured() -> bool:
    return bool(os.environ.get("ZERODHA_API_KEY"))


def get_broker(user_id: str | None = None) -> BrokerManager:
    """Return the broker for a user (auto-selects live vs paper based on env)."""
    kind = "zerodha" if _live_broker_configured() else "paper"
    key  = (kind, user_id)
    if key not in _brokers:
        if kind == "zerodha":
            _brokers[key] = ZerodhaKiteBrokerManager(user_id=user_id)
            logger.info(f"BrokerManager: Zerodha Kite for user={user_id}")
        else:
            _brokers[key] = PaperBrokerManager()
    return _brokers[key]


def reset_broker(user_id: str | None = None):
    """Drop cached broker instance(s). Call after env change or re-link."""
    global _brokers
    if user_id is None:
        _brokers = {}
    else:
        for k in [k for k in _brokers if k[1] == user_id]:
            _brokers.pop(k, None)


# ─────────────────────────────────────────────────────────────────────────────
# Unified portfolio provider — the single seam the "brain" reads from.
# Returns REAL broker holdings/balance when a live broker is connected for the
# user, otherwise the existing paper portfolio. Shape is stable across both.
# ─────────────────────────────────────────────────────────────────────────────
def get_portfolio_state(user_id: str) -> dict:
    """
    {
      "mode": "live" | "paper",
      "broker": "zerodha" | "paper",
      "holdings": [ {ticker, quantity, avg_buy_price, current_price,
                     total_investment, current_value, pnl, ...}, ... ],
      "balance": float,          # available cash
      "invested": float,         # cost basis of open positions
      "total_value": float,      # balance + market value of holdings
    }
    """
    broker = get_broker(user_id)
    live = broker.broker_name != "paper" and broker.is_connected()

    if live:
        try:
            holdings = broker.get_positions(user_id) or []
            bal      = broker.get_balance(user_id) or {}
            balance  = float(bal.get("balance") or 0)
            invested = sum(float(h.get("total_investment") or 0) for h in holdings)
            mkt_val  = sum(float(h.get("current_value") or 0) for h in holdings)
            return {
                "mode": "live", "broker": broker.broker_name,
                "holdings": holdings, "balance": balance, "invested": invested,
                "total_value": round(balance + mkt_val, 2),
            }
        except Exception as exc:
            logger.error(f"get_portfolio_state live fetch failed, falling back to paper: {exc}")

    # Paper fallback
    from trading_manager import get_trading_portfolio, get_trading_balance
    portfolio = get_trading_portfolio(user_id) or {}
    holdings = portfolio if isinstance(portfolio, list) else portfolio.get("holdings", [])
    bal      = get_trading_balance(user_id) or {}
    balance  = float(bal.get("balance") or 0)
    invested = sum(float(h.get("total_investment") or 0) for h in holdings)
    return {
        "mode": "paper", "broker": "paper",
        "holdings": holdings, "balance": balance, "invested": invested,
        "total_value": round(balance + invested, 2),
    }
