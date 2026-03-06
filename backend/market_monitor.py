"""
Market Monitor - Background service for continuous stock monitoring.
Checks price movements, volume spikes, news, and sentiment at regular intervals.
Sends alerts via WebSocket and stores them in the database.
"""

import os
import sys
import time
import json
import logging
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from stock_data import get_stock_price, calculate_technical_indicators, get_market_indices
from news_monitor import fetch_stock_news, get_reddit_sentiment, _quick_sentiment
from portfolio_manager import (
    create_alert, trigger_price_alert, save_portfolio_snapshot,
    get_all_monitored_stocks_global, get_all_active_price_alerts_global,
    get_all_holdings_global, update_monitor_baseline_global
)
from stock_data import get_bulk_prices

# Brain engine — imported lazily so startup doesn't fail if prophet isn't installed
try:
    from brain_engine import run_brain_analysis as _brain_fn
    BRAIN_AVAILABLE = True
except Exception:
    BRAIN_AVAILABLE = False
    logger.warning("Brain engine unavailable — signal alerts disabled")

# ─── Configuration ──────────────────────────────────────────────

MONITOR_INTERVAL = 300          # 5 minutes between monitoring cycles
PRICE_ALERT_THRESHOLD = 2.0    # % change to trigger price alert
VOLUME_SPIKE_MULTIPLIER = 3.0  # volume must be this many times avg to alert
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
BRAIN_CYCLE_INTERVAL = 6       # run brain every Nth monitoring cycle (~30 min)

# Cooldown periods per alert type — prevents alert spam
COOLDOWN_HOURS = {
    'price_movement': 1,
    'volume_spike':   2,
    'technical':      4,
    'pattern':        24,
    'news':           3,
    'signal':         4,
    'booming':        6,
}

# ─── WebSocket reference (set by app.py) ───────────────────────

socketio_instance = None


def set_socketio(sio):
    """Set the SocketIO instance for sending real-time alerts."""
    global socketio_instance
    socketio_instance = sio


def emit_alert(alert_data):
    """Send alert to frontend via WebSocket."""
    if socketio_instance:
        try:
            socketio_instance.emit('new_alert', alert_data, namespace='/')
        except Exception as e:
            logger.error(f"WebSocket emit error: {e}")
    try:
        print(f"[ALERT] {alert_data.get('message', 'No message')}")
    except UnicodeEncodeError:
        print(f"[ALERT] {alert_data.get('ticker', '?')} alert fired ({alert_data.get('type', 'unknown')})")


# ─── Monitoring Service ────────────────────────────────────────

class MonitoringService:
    """Background service that monitors stocks and generates alerts."""

    def __init__(self):
        self.is_running = False
        self._thread = None
        self._signal_states = {}       # {ticker: 'BUY'|'HOLD'|'SELL'}
        self._brain_cycle_counter = 0  # increments each check cycle

    def start(self):
        """Start the monitoring service in a background thread."""
        if self.is_running:
            print("Monitoring service already running")
            return

        self.is_running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        print(f"[{datetime.now()}] Monitoring service started")

    def stop(self):
        """Stop the monitoring service."""
        self.is_running = False
        print(f"[{datetime.now()}] Monitoring service stopped")

    def _run_loop(self):
        """Main monitoring loop."""
        while self.is_running:
            try:
                self._check_all_stocks()
                self._check_price_alerts()
                self._check_portfolio_snapshot()
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}", exc_info=True)

            # Sleep for the monitoring interval
            for _ in range(MONITOR_INTERVAL):
                if not self.is_running:
                    break
                time.sleep(1)

    def _check_all_stocks(self):
        """Check all monitored stocks for alerts."""
        monitored = get_all_monitored_stocks_global(active_only=True)
        if not monitored:
            return

        self._brain_cycle_counter += 1
        run_brain = BRAIN_AVAILABLE and (self._brain_cycle_counter % BRAIN_CYCLE_INTERVAL == 0)

        print(f"[{datetime.now()}] Checking {len(monitored)} monitored stocks"
              f"{' + brain analysis' if run_brain else ''}...")

        for stock in monitored:
            ticker = stock['ticker']
            try:
                self._check_stock(ticker, stock)
                if run_brain:
                    self._run_brain_check(ticker, stock)
            except Exception as e:
                logger.error(f"Error checking {ticker}: {e}")

    def _check_stock(self, ticker, monitor_data):
        """Run all checks for a single stock."""
        price_data = get_stock_price(ticker)
        if not price_data:
            return

        current_price = price_data['current_price']
        baseline_price = monitor_data.get('price_baseline', 0)
        # Extract user_id once; used for per-user cooldown checks throughout this method
        user_id = monitor_data.get('user_id', 'system')

        # ─── Initialize baseline on first check ─────────────────
        # When a stock is newly added, baseline_price is 0.
        # Set it to current price so subsequent cycles compute real % change.
        if baseline_price == 0 and current_price > 0:
            avg_vol = price_data.get('avg_volume', 0)
            update_monitor_baseline_global(ticker, current_price, avg_vol)
            logger.info(f"Initialized baseline for {ticker}: {current_price:,.2f}")
            return  # Skip checks this cycle — no historical baseline to compare against

        # Track conditions for combined booming detection
        price_surge = False
        volume_surge = False
        news_positive = False
        price_change_pct = 0.0
        volume_ratio = 1.0

        # ─── Price Movement Check ───────────────────────────────
        if baseline_price > 0:
            price_change_pct = ((current_price - baseline_price) / baseline_price) * 100

            if abs(price_change_pct) >= PRICE_ALERT_THRESHOLD:
                if not self._is_on_cooldown(ticker, 'price_movement', user_id=user_id):
                    direction = 'up' if price_change_pct > 0 else 'down'
                    severity = 'warning' if abs(price_change_pct) >= 5 else 'info'
                    sign = '+' if price_change_pct > 0 else ''

                    avg_vol = monitor_data.get('volume_avg_30d', 0) or price_data.get('avg_volume', 0)
                    vol_str = (f" | Vol: {price_data.get('volume', 0) / avg_vol:.1f}x avg"
                               if avg_vol > 0 else '')

                    alert_msg = f"{ticker} {sign}{price_change_pct:.1f}% → ₹{current_price:,.2f}{vol_str}"
                    user_id = monitor_data.get('user_id', 'system')
                    alert_id = create_alert(user_id, ticker, 'price_movement', alert_msg, severity, json.dumps({
                        'current_price': current_price,
                        'baseline_price': baseline_price,
                        'change_percent': round(price_change_pct, 2),
                        'direction': direction,
                    }))
                    emit_alert({
                        'id': alert_id, 'ticker': ticker, 'type': 'price_movement',
                        'message': alert_msg, 'severity': severity,
                        'timestamp': datetime.now().isoformat(),
                    })
                    self._set_cooldown(ticker, 'price_movement')

                # Always update baseline after movement so next alert is relative to new price
                update_monitor_baseline_global(ticker, current_price, monitor_data.get('volume_avg_30d', 0))

            if price_change_pct >= 3.0:
                price_surge = True

        # ─── Volume Spike Check ─────────────────────────────────
        current_volume = price_data.get('volume', 0)
        avg_volume = monitor_data.get('volume_avg_30d', 0) or price_data.get('avg_volume', 0)

        if avg_volume > 0 and current_volume > 0:
            volume_ratio = current_volume / avg_volume
            if volume_ratio >= VOLUME_SPIKE_MULTIPLIER:
                if not self._is_on_cooldown(ticker, 'volume_spike', user_id=user_id):
                    alert_msg = (
                        f"{ticker} volume surge: {volume_ratio:.1f}x 30-day average "
                        f"({current_volume:,} vs avg {avg_volume:,.0f}) — possible institutional activity"
                    )
                    user_id = monitor_data.get('user_id', 'system')
                    alert_id = create_alert(user_id, ticker, 'volume_spike', alert_msg, 'warning', json.dumps({
                        'current_volume': current_volume,
                        'avg_volume': avg_volume,
                        'ratio': round(volume_ratio, 2),
                    }))
                    emit_alert({
                        'id': alert_id, 'ticker': ticker, 'type': 'volume_spike',
                        'message': alert_msg, 'severity': 'warning',
                        'timestamp': datetime.now().isoformat(),
                    })
                    self._set_cooldown(ticker, 'volume_spike')

            if volume_ratio >= 2.0:
                volume_surge = True

        # ─── Technical Indicator Check ──────────────────────────
        try:
            technicals = calculate_technical_indicators(ticker)
            if technicals:
                rsi = technicals.get('rsi', 50)

                if rsi >= RSI_OVERBOUGHT and not self._is_on_cooldown(ticker, 'technical', user_id=user_id):
                    alert_msg = f"{ticker} RSI {rsi:.0f} — overbought zone. Consider booking partial profits."
                    user_id = monitor_data.get('user_id', 'system')
                    create_alert(user_id, ticker, 'technical', alert_msg, 'warning')
                    emit_alert({
                        'ticker': ticker, 'type': 'technical',
                        'message': alert_msg, 'severity': 'warning',
                        'timestamp': datetime.now().isoformat(),
                    })
                    self._set_cooldown(ticker, 'technical')

                elif rsi <= RSI_OVERSOLD and not self._is_on_cooldown(ticker, 'technical', user_id=user_id):
                    alert_msg = f"{ticker} RSI {rsi:.0f} — oversold zone. Potential buying opportunity."
                    user_id = monitor_data.get('user_id', 'system')
                    create_alert(user_id, ticker, 'technical', alert_msg, 'info')
                    emit_alert({
                        'ticker': ticker, 'type': 'technical',
                        'message': alert_msg, 'severity': 'info',
                        'timestamp': datetime.now().isoformat(),
                    })
                    self._set_cooldown(ticker, 'technical')

                # Moving average crossover (bullish)
                sma_20 = technicals.get('sma_20', 0)
                sma_50 = technicals.get('sma_50', 0)
                if sma_20 and sma_50 and current_price > sma_50 and sma_20 > sma_50:
                    if not self._is_on_cooldown(ticker, 'pattern', user_id=user_id):
                        alert_msg = (
                            f"{ticker} bullish momentum — price above 50-day SMA "
                            f"with SMA20 crossing above SMA50"
                        )
                        user_id = monitor_data.get('user_id', 'system')
                        create_alert(user_id, ticker, 'pattern', alert_msg, 'info')
                        emit_alert({
                            'ticker': ticker, 'type': 'pattern',
                            'message': alert_msg, 'severity': 'info',
                            'timestamp': datetime.now().isoformat(),
                        })
                        self._set_cooldown(ticker, 'pattern')
        except Exception as e:
            logger.error(f"Technical check error for {ticker}: {e}")

        # ─── News Check ─────────────────────────────────────────
        try:
            news = fetch_stock_news(ticker, days=1, max_articles=5)
            neg_articles = [a for a in news if a.get('sentiment') == 'negative']
            pos_articles = [a for a in news if a.get('sentiment') == 'positive']

            if neg_articles and not self._is_on_cooldown(ticker, 'news', user_id=user_id):
                neg_count = len(neg_articles)
                title = neg_articles[0]['title'][:80]
                alert_msg = (
                    f"{ticker}: {neg_count} negative news article{'s' if neg_count > 1 else ''} today "
                    f"— monitor closely. \"{title}\""
                )
                user_id = monitor_data.get('user_id', 'system')
                create_alert(user_id, ticker, 'news', alert_msg, 'warning')
                emit_alert({
                    'ticker': ticker, 'type': 'news',
                    'message': alert_msg, 'severity': 'warning',
                    'timestamp': datetime.now().isoformat(),
                })
                self._set_cooldown(ticker, 'news')

            if pos_articles:
                news_positive = True
        except Exception as e:
            logger.error(f"News check error for {ticker}: {e}")

        # ─── Booming Detection (multi-signal confluence) ────────
        if price_surge and volume_surge and news_positive:
            if not self._is_on_cooldown(ticker, 'booming', user_id=user_id):
                alert_msg = (
                    f"🔥 {ticker} is BOOMING — +{price_change_pct:.1f}% with {volume_ratio:.1f}x "
                    f"volume surge and positive news! Strong momentum signal."
                )
                user_id = monitor_data.get('user_id', 'system')
                alert_id = create_alert(user_id, ticker, 'price_movement', alert_msg, 'critical', json.dumps({
                    'current_price': current_price,
                    'price_change': round(price_change_pct, 2),
                    'volume_ratio': round(volume_ratio, 2),
                }))
                emit_alert({
                    'id': alert_id, 'ticker': ticker, 'type': 'booming',
                    'message': alert_msg, 'severity': 'critical',
                    'timestamp': datetime.now().isoformat(),
                })
                self._set_cooldown(ticker, 'booming')

    def _check_price_alerts(self):
        """Check custom price alerts set by all users."""
        try:
            price_alerts = get_all_active_price_alerts_global()
            for alert in price_alerts:
                ticker = alert['ticker']
                target = alert['target_price']
                direction = alert['direction']

                price_data = get_stock_price(ticker)
                if not price_data:
                    continue

                current_price = price_data['current_price']
                triggered = False

                if direction == 'above' and current_price >= target:
                    triggered = True
                elif direction == 'below' and current_price <= target:
                    triggered = True

                if triggered:
                    user_id = alert.get('user_id', 'system')
                    trigger_price_alert(user_id, alert['id'])
                    alert_msg = f"🎯 Price Alert: {ticker} reached ₹{current_price:,.2f} (target: ₹{target:,.2f} {direction})"
                    create_alert(user_id, ticker, 'price_alert', alert_msg, 'critical')
                    emit_alert({
                        'ticker': ticker, 'type': 'price_alert',
                        'message': alert_msg, 'severity': 'critical',
                        'timestamp': datetime.now().isoformat(),
                    })
        except Exception as e:
            logger.error(f"Price alerts check error: {e}")

    def _check_portfolio_snapshot(self):
        """Save portfolio snapshot per-user, periodically."""
        try:
            holdings = get_all_holdings_global()
            if not holdings:
                return

            # Group holdings by user_id for per-user snapshots
            from collections import defaultdict
            user_holdings = defaultdict(list)
            for h in holdings:
                user_holdings[h['user_id']].append(h)

            all_tickers = list({h['ticker'] for h in holdings})
            prices = get_bulk_prices(all_tickers)

            for uid, user_h in user_holdings.items():
                total_value = 0
                total_investment = 0
                for h in user_h:
                    price = prices.get(h['ticker'], h['buy_price'])
                    total_value += h['quantity'] * price
                    total_investment += h['quantity'] * h['buy_price']

                pnl = total_value - total_investment
                pnl_percent = (pnl / total_investment * 100) if total_investment > 0 else 0

                save_portfolio_snapshot(uid, total_value, total_investment, pnl, pnl_percent)
        except Exception as e:
            logger.error(f"Portfolio snapshot error: {e}")

    # ─── Cooldown Helpers ─────────────────────────────────────

    def _is_on_cooldown(self, ticker, alert_type, user_id=None):
        """Return True if this alert type fired recently for this user+ticker combo.

        When user_id is provided, the cooldown is scoped per-user so that one user's
        alert does not block another user from receiving the same alert type.
        Checks the alerts DB table so cooldowns survive server restarts.
        """
        from portfolio_manager import get_db_connection
        hours = COOLDOWN_HOURS.get(alert_type, 2)
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        try:
            with get_db_connection() as conn:
                if user_id and user_id != 'system':
                    row = conn.execute(
                        'SELECT COUNT(*) AS cnt FROM alerts '
                        'WHERE ticker = ? AND alert_type = ? AND user_id = ? AND created_at >= ?',
                        (ticker, alert_type, user_id, cutoff)
                    ).fetchone()
                else:
                    # System-level fallback: check across all users for the ticker
                    row = conn.execute(
                        'SELECT COUNT(*) AS cnt FROM alerts '
                        'WHERE ticker = ? AND alert_type = ? AND created_at >= ?',
                        (ticker, alert_type, cutoff)
                    ).fetchone()
                return (row['cnt'] if row else 0) > 0
        except Exception:
            return False

    def _set_cooldown(self, ticker, alert_type):
        """No-op: cooldown is now derived from the alerts table itself."""
        pass

    # ─── Brain Engine Integration ─────────────────────────────

    def _build_reason_string(self, result):
        """Extract a short human-readable reason from brain analysis output."""
        parts = []
        technicals = result.get('technical_indicators', {})
        rsi = technicals.get('rsi')
        if rsi is not None:
            label = 'oversold' if rsi < 30 else ('overbought' if rsi > 70 else 'neutral')
            parts.append(f"RSI {rsi:.0f} ({label})")
        signals = technicals.get('signals', [])
        if signals:
            parts.append(signals[0])
        news_label = result.get('news_sentiment', {}).get('label', '')
        if news_label:
            parts.append(f"{news_label} news")
        return ' | '.join(parts) if parts else 'multiple indicators aligned'

    def _run_brain_check(self, ticker, stock=None):
        """Run brain engine and alert on strong BUY/SELL signals or signal transitions."""
        try:
            result = _brain_fn(ticker, days=7)
            score = result.get('weighted_score', 50)
            signal = result.get('signal', 'HOLD')
            prev_signal = self._signal_states.get(ticker)

            # Update state memory
            self._signal_states[ticker] = signal

            # Alert conditions:
            # 1. Signal changed (HOLD→BUY or BUY→SELL etc.)
            # 2. First time we see this ticker with a strong score
            signal_changed = (prev_signal is not None and signal != prev_signal)
            first_strong = (prev_signal is None and (score >= 70 or score <= 30))

            if not (signal_changed or first_strong):
                return

            brain_user_id = (stock or {}).get('user_id', 'system')
            if self._is_on_cooldown(ticker, 'signal', user_id=brain_user_id):
                return

            reasons = self._build_reason_string(result)

            if score >= 70:
                alert_msg = f"🚀 {ticker} STRONG BUY (Score {score:.0f}/100) — {reasons}"
                severity = 'warning'
            elif score <= 30:
                alert_msg = f"⚠️ {ticker} SELL SIGNAL (Score {score:.0f}/100) — {reasons}"
                severity = 'critical'
            else:
                return  # Signal changed but not strong enough to warrant alert

            user_id = (stock or {}).get('user_id', 'system')
            alert_id = create_alert(user_id, ticker, 'signal', alert_msg, severity, json.dumps({
                'score': score,
                'signal': signal,
                'prev_signal': prev_signal,
            }))
            emit_alert({
                'id': alert_id, 'ticker': ticker, 'type': 'signal',
                'message': alert_msg, 'severity': severity,
                'timestamp': datetime.now().isoformat(),
            })
            self._set_cooldown(ticker, 'signal')

        except Exception as e:
            logger.error(f"Brain check error for {ticker}: {e}")


# ─── Insight Generator ─────────────────────────────────────────

def generate_insights(monitored_stocks_data):
    """Generate hourly insights for monitored stocks."""
    insights = []

    for ticker, data in monitored_stocks_data.items():
        price_data = data.get('price', {})
        technicals = data.get('technicals', {})
        sentiment = data.get('sentiment', 'neutral')

        if not price_data:
            continue

        change_pct = price_data.get('change_percent', 0)
        rsi = technicals.get('rsi', 50) if technicals else 50

        if change_pct > 3:
            insights.append(f"📈 {ticker} showing strong bullish momentum (+{change_pct:.1f}%) - consider holding")
        elif change_pct < -3:
            insights.append(f"📉 {ticker} under selling pressure ({change_pct:.1f}%) - review your position")

        if rsi > 70:
            insights.append(f"⚠️ {ticker} RSI at {rsi:.0f} (overbought) - consider booking partial profits")
        elif rsi < 30:
            insights.append(f"💡 {ticker} RSI at {rsi:.0f} (oversold) - could be a good entry point")

        if sentiment == 'negative':
            insights.append(f"📰 {ticker} news sentiment turned negative - monitor closely")
        elif sentiment == 'positive':
            insights.append(f"✅ {ticker} news sentiment is positive - favorable for holding")

    if not insights:
        insights.append("📊 All monitored stocks are within normal ranges. Market is stable.")

    return insights


# ─── Singleton Instance ────────────────────────────────────────

monitor_service = MonitoringService()


# ─── Standalone Entry Point ─────────────────────────────────────

if __name__ == '__main__':
    print("=" * 60)
    print("  Stock Market Monitoring Service")
    print("  Press Ctrl+C to stop")
    print("=" * 60)

    monitor_service.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        monitor_service.stop()
        print("\nMonitoring service stopped.")
