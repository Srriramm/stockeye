"""
Forecasting Engine - ML-based stock price prediction for Indian markets.
Uses an ensemble approach: Prophet (primary), LinearRegression (fallback).
Provides price forecasts, confidence intervals, risk profiling, and signals.
"""

import numpy as np
import pandas as pd
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ─── Prophet Import (optional) ──────────────────────────────────

PROPHET_AVAILABLE = False
try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
    logger.info("Prophet forecasting available")
except ImportError:
    logger.warning("Prophet not installed. Using LinearRegression fallback.")

# ─── Sklearn Import (fallback) ──────────────────────────────────

SKLEARN_AVAILABLE = False
try:
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import PolynomialFeatures
    from sklearn.pipeline import make_pipeline
    SKLEARN_AVAILABLE = True
except ImportError:
    logger.warning("scikit-learn not installed. Using basic moving-average fallback.")


def forecast_stock_price(historical_data: list, ticker: str, days: int = 30) -> dict:
    """
    Forecast future stock prices using the best available model.

    Args:
        historical_data: List of OHLCV dicts from get_historical_data()
        ticker: Stock ticker symbol
        days: Number of days to forecast (7, 14, or 30)

    Returns:
        {
            'ticker': str,
            'method': 'prophet' | 'linear_regression' | 'moving_average',
            'forecast_days': int,
            'current_price': float,
            'target_price': float,          # price at end of forecast period
            'trend_direction': 'up' | 'down' | 'sideways',
            'trend_pct': float,             # % change forecasted
            'signal': 'BUY' | 'HOLD' | 'SELL',
            'signal_strength': 'Strong' | 'Moderate' | 'Weak',
            'confidence': float,            # 0-100 confidence score
            'forecast': list of {
                'date': str, 'predicted': float,
                'upper': float, 'lower': float
            },
            'key_levels': {'support': float, 'resistance': float},
            'summary': str
        }
    """
    if not historical_data or len(historical_data) < 10:
        return {'error': 'Insufficient historical data for forecasting'}

    try:
        # Build DataFrame
        df = pd.DataFrame(historical_data)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').dropna(subset=['close'])

        current_price = float(df['close'].iloc[-1])

        # Try Prophet first, then LinearRegression, then simple MA
        if PROPHET_AVAILABLE and len(df) >= 30:
            result = _forecast_with_prophet(df, ticker, days, current_price)
        elif SKLEARN_AVAILABLE and len(df) >= 15:
            result = _forecast_with_linear(df, ticker, days, current_price)
        else:
            result = _forecast_with_ma(df, ticker, days, current_price)

        return result

    except Exception as e:
        logger.error(f"Forecasting failed for {ticker}: {e}", exc_info=True)
        return {'error': f'Forecasting error: {str(e)}'}


# ─── Prophet Model ──────────────────────────────────────────────

def _forecast_with_prophet(df: pd.DataFrame, ticker: str, days: int, current_price: float) -> dict:
    """Forecast using Facebook Prophet with adaptive changepoint scale."""
    try:
        # Prepare Prophet format
        prophet_df = df[['date', 'close']].rename(columns={'date': 'ds', 'close': 'y'})
        prophet_df['ds'] = prophet_df['ds'].dt.tz_localize(None)

        # Adaptive changepoint_prior_scale: more flexible for volatile stocks
        pct_volatility = prophet_df['y'].pct_change().std() * 100  # daily vol %
        if pct_volatility > 2.5:
            cps = 0.5   # high-volatility: very flexible
        elif pct_volatility > 1.5:
            cps = 0.3
        elif pct_volatility > 0.8:
            cps = 0.15
        else:
            cps = 0.1   # low-volatility: moderate flexibility (not rigid)

        # Build model with Indian market seasonality
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            changepoint_prior_scale=cps,
            seasonality_prior_scale=10,
            interval_width=0.80,
        )
        # Add Indian trading week (Mon-Fri)
        model.add_country_holidays(country_name='IN')

        model.fit(prophet_df)

        # Generate forecast
        future = model.make_future_dataframe(periods=days, freq='B')  # Business days
        forecast = model.predict(future)

        # Extract only future dates
        last_date = prophet_df['ds'].iloc[-1]
        future_mask = forecast['ds'] > last_date
        future_forecast = forecast[future_mask].head(days)

        forecast_list = []
        for _, row in future_forecast.iterrows():
            forecast_list.append({
                'date': row['ds'].strftime('%Y-%m-%d'),
                'predicted': round(float(row['yhat']), 2),
                'upper': round(float(row['yhat_upper']), 2),
                'lower': round(float(row['yhat_lower']), 2),
            })

        target_price = forecast_list[-1]['predicted'] if forecast_list else current_price
        return _build_result(ticker, forecast_list, current_price, target_price, days,
                             method='prophet', df=df, confidence=78)

    except Exception as e:
        logger.warning(f"Prophet failed for {ticker}: {e}. Falling back to LinearRegression.")
        return _forecast_with_linear(df, ticker, days, current_price)


# ─── Linear Regression Model ────────────────────────────────────

def _forecast_with_linear(df: pd.DataFrame, ticker: str, days: int, current_price: float) -> dict:
    """Forecast using polynomial linear regression with technical features."""
    try:
        # Use last 90 days for training
        df_train = df.tail(min(len(df), 90)).copy()
        df_train = df_train.reset_index(drop=True)

        # Feature engineering
        n = len(df_train)
        X = np.array(range(n)).reshape(-1, 1)
        y = df_train['close'].values

        # Add rolling features
        df_train['ma7'] = df_train['close'].rolling(7, min_periods=1).mean()
        df_train['ma21'] = df_train['close'].rolling(21, min_periods=1).mean()
        df_train['momentum'] = df_train['close'].pct_change(5).fillna(0)

        # Polynomial regression (degree 2 captures trends better)
        model = make_pipeline(PolynomialFeatures(degree=2), LinearRegression())
        model.fit(X, y)

        # Forecast
        future_X = np.array(range(n, n + days)).reshape(-1, 1)
        predicted = model.predict(future_X)

        # Calculate confidence band (1.5x recent std dev)
        recent_volatility = df_train['close'].tail(20).std()
        band_width = recent_volatility * 1.5

        last_date = df_train['date'].iloc[-1]
        forecast_list = []
        for i, pred in enumerate(predicted):
            date = last_date + timedelta(days=i + 1)
            # Skip weekends
            while date.weekday() >= 5:
                date += timedelta(days=1)
            forecast_list.append({
                'date': date.strftime('%Y-%m-%d'),
                'predicted': round(max(float(pred), 1.0), 2),
                'upper': round(max(float(pred) + band_width, 1.0), 2),
                'lower': round(max(float(pred) - band_width, 1.0), 2),
            })

        if len(forecast_list) > days:
            forecast_list = forecast_list[:days]

        target_price = forecast_list[-1]['predicted'] if forecast_list else current_price
        return _build_result(ticker, forecast_list, current_price, target_price, days,
                             method='linear_regression', df=df, confidence=62)

    except Exception as e:
        logger.warning(f"LinearRegression failed for {ticker}: {e}. Using MA fallback.")
        return _forecast_with_ma(df, ticker, days, current_price)


# ─── Moving Average Baseline ────────────────────────────────────

def _forecast_with_ma(df: pd.DataFrame, ticker: str, days: int, current_price: float) -> dict:
    """Simple moving average forecast as a last resort."""
    try:
        closes = df['close'].values
        ma = np.mean(closes[-min(len(closes), 20):])
        recent_std = np.std(closes[-min(len(closes), 20):])

        # Simple linear extrapolation from MA trend
        short_ma = np.mean(closes[-min(len(closes), 7):])
        long_ma = np.mean(closes[-min(len(closes), 20):])
        daily_drift = (short_ma - long_ma) / 20  # Smooth daily drift

        last_date = df['date'].iloc[-1]
        forecast_list = []
        price = current_price

        for i in range(days):
            price = price + daily_drift + np.random.normal(0, recent_std * 0.1)
            price = max(price, 1.0)
            date = last_date + timedelta(days=i + 1)
            while date.weekday() >= 5:
                date += timedelta(days=1)
            forecast_list.append({
                'date': date.strftime('%Y-%m-%d'),
                'predicted': round(float(price), 2),
                'upper': round(float(price + recent_std * 0.5), 2),
                'lower': round(float(max(price - recent_std * 0.5, 1.0)), 2),
            })

        target_price = forecast_list[-1]['predicted'] if forecast_list else current_price
        return _build_result(ticker, forecast_list, current_price, target_price, days,
                             method='moving_average', df=df, confidence=45)

    except Exception as e:
        return {'error': f'All forecasting methods failed: {str(e)}'}


# ─── Result Builder ─────────────────────────────────────────────

def _build_result(ticker, forecast_list, current_price, target_price, days,
                  method, df, confidence):
    """Build standardized result dict from forecast data."""
    trend_pct = ((target_price - current_price) / current_price) * 100 if current_price > 0 else 0

    # Determine trend direction
    if trend_pct > 2.0:
        trend_direction = 'up'
    elif trend_pct < -2.0:
        trend_direction = 'down'
    else:
        trend_direction = 'sideways'

    # Generate trading signal
    signal, signal_strength = _generate_signal(trend_pct, confidence, df)

    # Support / resistance from historical data
    key_levels = _calculate_key_levels(df)

    # Generate human-readable summary
    summary = _generate_summary(ticker, current_price, target_price, trend_pct,
                                 trend_direction, signal, days, method)

    return {
        'ticker': ticker,
        'method': method,
        'forecast_days': days,
        'current_price': round(current_price, 2),
        'target_price': round(target_price, 2),
        'trend_direction': trend_direction,
        'trend_pct': round(trend_pct, 2),
        'signal': signal,
        'signal_strength': signal_strength,
        'confidence': confidence,
        'forecast': forecast_list,
        'key_levels': key_levels,
        'summary': summary,
        'generated_at': datetime.now().isoformat(),
        'disclaimer': '⚠️ Forecasts are probabilistic estimates based on historical patterns. Not financial advice.',
    }


def _generate_signal(trend_pct: float, confidence: float, df: pd.DataFrame) -> tuple:
    """Generate BUY/HOLD/SELL signal from trend and momentum."""
    # RSI-like momentum check
    closes = df['close'].values
    if len(closes) >= 14:
        gains = [max(closes[i] - closes[i-1], 0) for i in range(-13, 0)]
        losses = [abs(min(closes[i] - closes[i-1], 0)) for i in range(-13, 0)]
        avg_gain = np.mean(gains) if gains else 0
        avg_loss = np.mean(losses) if losses else 1
        rsi = 100 - (100 / (1 + avg_gain / (avg_loss + 1e-10)))
    else:
        rsi = 50  # neutral

    # Signal decision — thresholds adjusted to be less strict
    if trend_pct > 5 and rsi < 70 and confidence > 60:
        signal, strength = 'BUY', 'Strong'
    elif trend_pct > 2 and rsi < 65:
        signal, strength = 'BUY', 'Moderate'
    elif trend_pct > 0.5 and rsi < 55:
        signal, strength = 'BUY', 'Weak'
    elif trend_pct < -5 and rsi > 30:
        signal, strength = 'SELL', 'Strong'
    elif trend_pct < -2 and rsi > 35:
        signal, strength = 'SELL', 'Moderate'
    elif trend_pct < -0.5 and rsi > 45:
        signal, strength = 'SELL', 'Weak'
    else:
        # Flat forecast — use RSI to break the tie
        if rsi < 40:
            signal, strength = 'BUY', 'Weak'   # Oversold + flat = potential bottom
        elif rsi > 60:
            signal, strength = 'SELL', 'Weak'  # Overbought + flat = potential top
        else:
            signal, strength = 'HOLD', 'Moderate'

    return signal, strength


def _calculate_key_levels(df: pd.DataFrame) -> dict:
    """Calculate support and resistance from recent price action."""
    if len(df) < 10:
        return {'support': 0, 'resistance': 0}

    recent = df.tail(min(len(df), 60))
    high = recent['high'].max() if 'high' in recent.columns else recent['close'].max()
    low = recent['low'].min() if 'low' in recent.columns else recent['close'].min()
    pivot = (high + low + recent['close'].iloc[-1]) / 3

    return {
        'support': round(float(2 * pivot - high), 2),
        'resistance': round(float(2 * pivot - low), 2),
        'pivot': round(float(pivot), 2),
    }


def _generate_summary(ticker, current_price, target_price, trend_pct, trend_direction,
                       signal, days, method) -> str:
    """Generate a concise text summary of the forecast."""
    direction_text = 'rise' if trend_direction == 'up' else ('fall' if trend_direction == 'down' else 'remain relatively stable')
    signal_emoji = {'BUY': '📈', 'SELL': '📉', 'HOLD': '⚖️'}.get(signal, '📊')

    return (
        f"{ticker} is forecasted to {direction_text} by {abs(trend_pct):.1f}% "
        f"over the next {days} trading days, reaching ₹{target_price:,.2f} "
        f"from the current ₹{current_price:,.2f}. "
        f"{signal_emoji} Forecast signal: {signal}. "
        f"Model used: {method.replace('_', ' ').title()}."
    )


# ─── Risk Profile ───────────────────────────────────────────────

def get_risk_profile(historical_data: list, ticker: str) -> dict:
    """
    Calculate comprehensive risk metrics for a stock.

    Returns volatility, beta (vs NIFTY proxy), Sharpe ratio,
    max drawdown, Value at Risk (95%), and a risk tier.
    """
    if not historical_data or len(historical_data) < 20:
        return {'error': 'Insufficient data for risk profiling'}

    try:
        df = pd.DataFrame(historical_data)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').dropna(subset=['close'])
        df['returns'] = df['close'].pct_change().dropna()

        returns = df['returns'].dropna().values

        # Annualized volatility
        daily_vol = np.std(returns)
        annual_vol = daily_vol * np.sqrt(252) * 100

        # Approximate beta (using market correlation estimate)
        # Since we don't fetch NIFTY here, use a heuristic beta
        vol_ratio = annual_vol / 20.0  # Assume 20% as market baseline
        approx_beta = min(max(vol_ratio, 0.2), 3.0)

        # Sharpe ratio (assume 6.5% risk-free rate for India)
        risk_free_daily = 0.065 / 252
        avg_return = np.mean(returns)
        sharpe = ((avg_return - risk_free_daily) / (daily_vol + 1e-10)) * np.sqrt(252)

        # Max drawdown
        prices = df['close'].values
        peak = np.maximum.accumulate(prices)
        drawdown = (prices - peak) / peak
        max_drawdown = float(np.min(drawdown)) * 100

        # Value at Risk (95% confidence, 1-day)
        var_95 = float(np.percentile(returns, 5)) * 100

        # Average daily volume trend
        avg_vol = int(df['volume'].mean()) if 'volume' in df.columns else 0

        # Risk tier
        if annual_vol < 20:
            risk_tier = 'Low'
            risk_color = 'green'
            risk_description = 'This stock shows relatively stable price movements, suitable for conservative investors.'
        elif annual_vol < 35:
            risk_tier = 'Medium'
            risk_color = 'yellow'
            risk_description = 'Moderate price fluctuations. Suitable for balanced investors with medium risk tolerance.'
        elif annual_vol < 55:
            risk_tier = 'High'
            risk_color = 'orange'
            risk_description = 'High price volatility. Best suited for aggressive investors with long time horizons.'
        else:
            risk_tier = 'Very High'
            risk_color = 'red'
            risk_description = 'Extremely volatile. Only suitable for experienced, aggressive traders.'

        return {
            'ticker': ticker,
            'annual_volatility_pct': round(annual_vol, 2),
            'daily_volatility_pct': round(daily_vol * 100, 4),
            'beta': round(approx_beta, 2),
            'sharpe_ratio': round(sharpe, 3),
            'max_drawdown_pct': round(max_drawdown, 2),
            'var_95_pct': round(var_95, 3),
            'avg_daily_volume': avg_vol,
            'risk_tier': risk_tier,
            'risk_color': risk_color,
            'risk_description': risk_description,
            'data_points': len(df),
            'analysis_period_days': (df['date'].iloc[-1] - df['date'].iloc[0]).days,
            'generated_at': datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Risk profile failed for {ticker}: {e}", exc_info=True)
        return {'error': f'Risk analysis error: {str(e)}'}


# ─── Backtest (Walk-Forward MAPE) ───────────────────────────────

def backtest_forecast(historical_data: list, ticker: str, holdout_days: int = 20) -> dict:
    """
    Walk-forward backtest: train on all data except last N days,
    predict those N days, compare to actual prices → compute MAPE.

    Returns:
        {
            'mape': float,              # Mean Absolute Percentage Error (%)
            'model_used': str,          # Which model ran
            'holdout_days': int,        # How many days were tested
            'data_points_trained': int, # Training set size
        }
    """
    min_required = holdout_days + 30
    if not historical_data or len(historical_data) < min_required:
        return {
            'mape': None,
            'model_used': 'insufficient_data',
            'holdout_days': holdout_days,
            'data_points_trained': len(historical_data) if historical_data else 0,
        }

    try:
        df = pd.DataFrame(historical_data)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').dropna(subset=['close']).reset_index(drop=True)

        # Split into train and holdout
        train_df = df.iloc[:-holdout_days].copy()
        test_df  = df.iloc[-holdout_days:].copy()

        train_last_price = float(train_df['close'].iloc[-1])

        # Run the same model cascade on the training split
        if PROPHET_AVAILABLE and len(train_df) >= 30:
            method = 'prophet'
            result = _forecast_with_prophet(train_df, ticker, holdout_days, train_last_price)
        elif SKLEARN_AVAILABLE and len(train_df) >= 15:
            method = 'linear_regression'
            result = _forecast_with_linear(train_df, ticker, holdout_days, train_last_price)
        else:
            method = 'moving_average'
            result = _forecast_with_ma(train_df, ticker, holdout_days, train_last_price)

        if 'error' in result or not result.get('forecast'):
            return {
                'mape': None, 'model_used': method,
                'holdout_days': holdout_days,
                'data_points_trained': len(train_df),
            }

        predicted = [f['predicted'] for f in result['forecast']]
        actual    = test_df['close'].values
        n = min(len(predicted), len(actual))

        if n == 0:
            return {
                'mape': None, 'model_used': method,
                'holdout_days': holdout_days,
                'data_points_trained': len(train_df),
            }

        mape = float(np.mean([
            abs(p - a) / a * 100
            for p, a in zip(predicted[:n], actual[:n])
            if a > 0
        ]))

        return {
            'mape': round(mape, 2),
            'model_used': method,
            'holdout_days': n,
            'data_points_trained': len(train_df),
            'generated_at': datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Backtest failed for {ticker}: {e}", exc_info=True)
        return {
            'mape': None, 'model_used': 'error',
            'holdout_days': holdout_days, 'data_points_trained': 0,
        }
