"""
Real-time Stock Price Streaming Service
Pushes live price updates via WebSocket for watched/subscribed stocks.
"""

import threading
import time
import logging
from datetime import datetime
from stock_data import get_stock_price, get_bulk_prices

logger = logging.getLogger(__name__)

class RealtimePriceService:
    """
    Service that continuously fetches and broadcasts stock prices
    for subscribed stocks via WebSocket.
    """

    def __init__(self, socketio=None, update_interval=5):
        """
        Initialize the realtime price service.

        Args:
            socketio: SocketIO instance for broadcasting
            update_interval: Seconds between price updates (default: 5)
        """
        self.socketio = socketio
        self.update_interval = update_interval
        self.subscribed_stocks = set()  # Stocks being watched
        self.client_subscriptions = {}  # {client_id: [tickers]}
        self.is_running = False
        self._thread = None
        self._lock = threading.Lock()

    def set_socketio(self, socketio):
        """Set or update the SocketIO instance."""
        self.socketio = socketio

    def subscribe(self, client_id, ticker):
        """Subscribe a client to real-time updates for a ticker."""
        ticker = ticker.upper().strip()

        with self._lock:
            # Add to client subscriptions
            if client_id not in self.client_subscriptions:
                self.client_subscriptions[client_id] = set()
            self.client_subscriptions[client_id].add(ticker)

            # Add to global subscribed stocks
            self.subscribed_stocks.add(ticker)

        logger.info(f"Client {client_id} subscribed to {ticker}")
        return True

    def unsubscribe(self, client_id, ticker=None):
        """
        Unsubscribe a client from ticker updates.
        If ticker is None, unsubscribe from all.
        """
        with self._lock:
            if client_id in self.client_subscriptions:
                if ticker:
                    ticker = ticker.upper().strip()
                    self.client_subscriptions[client_id].discard(ticker)
                else:
                    # Unsubscribe from all
                    self.client_subscriptions[client_id].clear()

                # Remove client if no subscriptions left
                if not self.client_subscriptions[client_id]:
                    del self.client_subscriptions[client_id]

            # Rebuild subscribed_stocks from all clients
            self.subscribed_stocks = set()
            for client_tickers in self.client_subscriptions.values():
                self.subscribed_stocks.update(client_tickers)

        logger.info(f"Client {client_id} unsubscribed from {ticker or 'all'}")

    def get_subscribed_tickers(self):
        """Get list of all currently subscribed tickers."""
        with self._lock:
            return list(self.subscribed_stocks)

    def start(self):
        """Start the real-time price update service."""
        if self.is_running:
            logger.warning("Realtime service already running")
            return

        if not self.socketio:
            logger.error("Cannot start realtime service: SocketIO not initialized")
            return

        self.is_running = True
        self._thread = threading.Thread(target=self._update_loop, daemon=True)
        self._thread.start()
        logger.info(f"Realtime price service started (interval: {self.update_interval}s)")

    def stop(self):
        """Stop the real-time price update service."""
        self.is_running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Realtime price service stopped")

    def _update_loop(self):
        """Main loop that fetches and broadcasts price updates."""
        while self.is_running:
            try:
                tickers = self.get_subscribed_tickers()

                if tickers:
                    # Fetch prices for all subscribed stocks
                    prices = get_bulk_prices(tickers)

                    # Broadcast individual stock updates
                    for ticker, price_data in prices.items():
                        if price_data:
                            full_data = get_stock_price(ticker)
                            if full_data:
                                self._broadcast_price_update(ticker, full_data)

                    # Also broadcast bulk update
                    if prices:
                        self.socketio.emit('bulk_price_update', {
                            'prices': prices,
                            'timestamp': datetime.now().isoformat()
                        })

                    logger.debug(f"Updated {len(prices)} stock prices")

            except Exception as e:
                logger.error(f"Error in realtime update loop: {e}")

            # Wait for next update interval
            time.sleep(self.update_interval)

    def _broadcast_price_update(self, ticker, data):
        """Broadcast price update for a single stock."""
        if not self.socketio:
            return

        try:
            self.socketio.emit('price_update', {
                'ticker': ticker,
                'data': data,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            logger.error(f"Error broadcasting price for {ticker}: {e}")


# Global service instance
realtime_service = RealtimePriceService()

def set_socketio(socketio):
    """Set the SocketIO instance for the service."""
    realtime_service.set_socketio(socketio)
