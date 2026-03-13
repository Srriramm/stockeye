"""
Broker Manager — abstraction layer for paper and live trading.

BrokerManager (abstract)
├── PaperBrokerManager         — routes to trading_manager.py (default)
└── ZerodhaKiteBrokerManager   — live trading via Zerodha Kite Connect API

Selection logic (get_broker()):
  - If ZERODHA_API_KEY env var is set → ZerodhaKiteBrokerManager
  - Otherwise                         → PaperBrokerManager

Install for live trading:
  pip install kiteconnect
"""

import logging
import os
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


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

    def get_status(self) -> dict:
        return {
            "broker":    self.broker_name,
            "connected": self.is_connected(),
            "mode":      "live" if self.broker_name != "paper" and self.is_connected() else "paper",
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
        return result or {"error": "Paper order failed"}

    def cancel_order(self, user_id: str, order_id: str) -> bool:
        from trading_manager import cancel_order
        return cancel_order(user_id, order_id)

    def get_positions(self, user_id: str) -> list:
        from trading_manager import get_trading_portfolio
        portfolio = get_trading_portfolio(user_id) or {}
        return portfolio.get("holdings", [])

    def get_balance(self, user_id: str) -> dict:
        from trading_manager import get_trading_balance
        return get_trading_balance(user_id) or {}


# ─────────────────────────────────────────────────────────────────────────────
# Zerodha Kite live broker
# ─────────────────────────────────────────────────────────────────────────────
class ZerodhaKiteBrokerManager(BrokerManager):
    """
    Live trading via Zerodha Kite Connect API.

    Setup:
    1. Create an app at https://developers.kite.trade
    2. Set env vars: ZERODHA_API_KEY, ZERODHA_API_SECRET
    3. Call get_login_url() → redirect user → on callback call complete_login(request_token)
    4. Access token is stored in memory (restart requires re-login)
    """

    def __init__(self):
        self.api_key      = os.environ.get("ZERODHA_API_KEY", "")
        self.api_secret   = os.environ.get("ZERODHA_API_SECRET", "")
        self._kite        = None
        self._access_token: str | None = None

    @property
    def broker_name(self) -> str:
        return "zerodha"

    def _get_kite(self):
        if self._kite is None:
            try:
                from kiteconnect import KiteConnect
                self._kite = KiteConnect(api_key=self.api_key)
                if self._access_token:
                    self._kite.set_access_token(self._access_token)
            except ImportError:
                logger.error(
                    "kiteconnect package not installed. "
                    "Run: pip install kiteconnect"
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
            session = kite.generate_session(
                request_token, api_secret=self.api_secret
            )
            self._access_token = session["access_token"]
            kite.set_access_token(self._access_token)
            logger.info("Zerodha Kite login complete — access token acquired")
            return True
        except Exception as exc:
            logger.error(f"Zerodha login failed: {exc}")
            return False

    def is_connected(self) -> bool:
        return bool(self._access_token and self._get_kite())

    def place_order(self, user_id, ticker, side, quantity,
                    order_type="MARKET", price=None, stop_price=None) -> dict:
        try:
            kite = self._get_kite()
            if not kite or not self._access_token:
                return {"error": "Zerodha not connected — call get_login_url() first"}

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
                quantity         = quantity,
                product          = kite.PRODUCT_CNC,    # Cash and Carry (delivery)
                order_type       = k_order_type,
                price            = price if order_type == "LIMIT" else None,
                trigger_price    = stop_price if stop_price else None,
            )
            logger.info(
                f"Zerodha order placed: {order_id} — {side} {quantity}×{ticker}"
            )
            return {
                "order_id": str(order_id),
                "status":   "EXECUTED",
                "broker":   "zerodha",
                "ticker":   ticker,
                "side":     side,
                "quantity": quantity,
            }
        except Exception as exc:
            logger.error(f"Zerodha place_order failed: {exc}")
            return {"error": str(exc)}

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
        try:
            kite = self._get_kite()
            if not kite:
                return []
            positions = kite.positions()
            return positions.get("net", [])
        except Exception as exc:
            logger.error(f"Zerodha get_positions failed: {exc}")
            return []

    def get_balance(self, user_id: str) -> dict:
        try:
            kite = self._get_kite()
            if not kite:
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
# Singleton + factory
# ─────────────────────────────────────────────────────────────────────────────
_broker: BrokerManager | None = None


def get_broker() -> BrokerManager:
    """Return the singleton broker instance (auto-selects based on env vars)."""
    global _broker
    if _broker is None:
        if os.environ.get("ZERODHA_API_KEY"):
            _broker = ZerodhaKiteBrokerManager()
            logger.info("BrokerManager: Zerodha Kite (live mode available)")
        else:
            _broker = PaperBrokerManager()
            logger.info("BrokerManager: Paper trading (set ZERODHA_API_KEY to enable live)")
    return _broker


def reset_broker():
    """Force re-initialisation of broker (useful after env var changes)."""
    global _broker
    _broker = None
