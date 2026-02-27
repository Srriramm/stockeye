/**
 * WebSocket Real-time Price Streaming Utility
 * Manages WebSocket connection and real-time stock price subscriptions
 */

import React from 'react';
import io from 'socket.io-client';

class WebSocketManager {
  constructor() {
    this.socket = null;
    this.subscribers = new Map(); // ticker -> Set of callbacks
    this.connected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
  }

  /**
   * Initialize WebSocket connection
   * @param {string} url - Backend WebSocket URL
   */
  connect(url = 'http://localhost:5000', token = null) {
    if (this.socket && this.connected) {
      console.log('[WS] Already connected');
      return;
    }

    console.log('[WS] Connecting to', url);

    this.socket = io(url, {
      query: token ? { token } : {},
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      reconnectionAttempts: this.maxReconnectAttempts,
    });

    this.socket.on('connect', () => {
      console.log('[WS] Connected');
      this.connected = true;
      this.reconnectAttempts = 0;

      // Resubscribe to all tickers after reconnection
      this.subscribers.forEach((callbacks, ticker) => {
        this._sendSubscribe(ticker);
      });
    });

    this.socket.on('disconnect', () => {
      console.log('[WS] Disconnected');
      this.connected = false;
    });

    this.socket.on('connected', (data) => {
      console.log('[WS] Server acknowledged connection:', data);
    });

    // Listen for individual price updates
    this.socket.on('price_update', (data) => {
      const { ticker, data: priceData } = data;
      if (ticker && this.subscribers.has(ticker)) {
        this.subscribers.get(ticker).forEach(callback => {
          callback(priceData);
        });
      }
    });

    // Listen for bulk price updates
    this.socket.on('bulk_price_update', (data) => {
      const { prices } = data;
      if (prices) {
        Object.entries(prices).forEach(([ticker, price]) => {
          if (this.subscribers.has(ticker)) {
            this.subscribers.get(ticker).forEach(callback => {
              callback({ ticker, current_price: price });
            });
          }
        });
      }
    });

    this.socket.on('connect_error', (error) => {
      console.error('[WS] Connection error:', error);
      this.reconnectAttempts++;
    });

    this.socket.on('error', (error) => {
      console.error('[WS] Socket error:', error);
    });
  }

  /**
   * Subscribe to real-time price updates for a ticker
   * @param {string} ticker - Stock ticker symbol
   * @param {function} callback - Callback function(priceData)
   * @returns {function} Unsubscribe function
   */
  subscribe(ticker, callback) {
    if (!ticker || typeof callback !== 'function') {
      console.error('[WS] Invalid subscribe parameters');
      return () => {};
    }

    ticker = ticker.toUpperCase();

    // Add callback to subscribers
    if (!this.subscribers.has(ticker)) {
      this.subscribers.set(ticker, new Set());
    }
    this.subscribers.get(ticker).add(callback);

    // Send subscription request to server
    if (this.connected) {
      this._sendSubscribe(ticker);
    }

    console.log(`[WS] Subscribed to ${ticker}`);

    // Return unsubscribe function
    return () => this.unsubscribe(ticker, callback);
  }

  /**
   * Unsubscribe from price updates
   * @param {string} ticker - Stock ticker symbol
   * @param {function} callback - Specific callback to remove (optional)
   */
  unsubscribe(ticker, callback = null) {
    ticker = ticker.toUpperCase();

    if (!this.subscribers.has(ticker)) {
      return;
    }

    if (callback) {
      // Remove specific callback
      this.subscribers.get(ticker).delete(callback);

      // If no more callbacks for this ticker, remove it
      if (this.subscribers.get(ticker).size === 0) {
        this.subscribers.delete(ticker);
        this._sendUnsubscribe(ticker);
      }
    } else {
      // Remove all callbacks for this ticker
      this.subscribers.delete(ticker);
      this._sendUnsubscribe(ticker);
    }

    console.log(`[WS] Unsubscribed from ${ticker}`);
  }

  /**
   * Disconnect WebSocket
   */
  disconnect() {
    if (this.socket) {
      console.log('[WS] Disconnecting...');
      this.socket.disconnect();
      this.socket = null;
      this.connected = false;
      this.subscribers.clear();
    }
  }

  /**
   * Send subscribe request to server
   * @private
   */
  _sendSubscribe(ticker) {
    if (this.socket && this.connected) {
      this.socket.emit('subscribe_stock', { ticker });
    }
  }

  /**
   * Send unsubscribe request to server
   * @private
   */
  _sendUnsubscribe(ticker) {
    if (this.socket && this.connected) {
      this.socket.emit('unsubscribe_stock', { ticker });
    }
  }

  /**
   * Check if connected
   */
  isConnected() {
    return this.connected;
  }

  /**
   * Get number of active subscriptions
   */
  getSubscriptionCount() {
    return this.subscribers.size;
  }
}

// Global singleton instance
const wsManager = new WebSocketManager();

export default wsManager;

/**
 * React Hook for real-time stock price updates
 * @param {string} ticker - Stock ticker symbol
 * @returns {object} Price data object
 *
 * Usage:
 * const priceData = useRealtimePrice('RELIANCE');
 */
export function useRealtimePrice(ticker) {
  const [priceData, setPriceData] = React.useState(null);
  const [isSubscribed, setIsSubscribed] = React.useState(false);

  React.useEffect(() => {
    if (!ticker) return;

    // Subscribe to price updates
    const unsubscribe = wsManager.subscribe(ticker, (data) => {
      setPriceData(data);
    });

    setIsSubscribed(true);

    // Cleanup on unmount
    return () => {
      unsubscribe();
      setIsSubscribed(false);
    };
  }, [ticker]);

  return { priceData, isSubscribed };
}
