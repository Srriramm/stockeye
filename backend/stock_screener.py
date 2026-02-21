"""
Stock Screener - Filter stocks by various criteria
Price, market cap, P/E, RSI, sector, volume, etc.
"""

import logging
from stock_data import (
    POPULAR_INDIAN_STOCKS, get_stock_price, get_stock_info,
    calculate_technical_indicators, get_bulk_prices
)

logger = logging.getLogger(__name__)


def screen_stocks(filters):
    """
    Screen stocks based on filters.

    Args:
        filters: dict with screening criteria
            - price_min: Minimum price
            - price_max: Maximum price
            - market_cap_min: Minimum market cap
            - market_cap_max: Maximum market cap
            - pe_min: Minimum P/E ratio
            - pe_max: Maximum P/E ratio
            - dividend_yield_min: Minimum dividend yield %
            - rsi_min: Minimum RSI
            - rsi_max: Maximum RSI
            - volume_min: Minimum volume
            - change_percent_min: Minimum day change %
            - change_percent_max: Maximum day change %
            - sectors: List of sectors to include
            - week_52_high: Include stocks near 52-week high
            - week_52_low: Include stocks near 52-week low

    Returns:
        List of stocks matching criteria
    """
    logger.info(f"Screening stocks with filters: {filters}")

    results = []
    all_tickers = list(POPULAR_INDIAN_STOCKS.keys())

    # Get bulk prices first for efficiency
    prices = get_bulk_prices(all_tickers)

    for ticker, stock_meta in POPULAR_INDIAN_STOCKS.items():
        try:
            # Get price data
            price_data = get_stock_price(ticker)
            if not price_data:
                continue

            current_price = price_data['current_price']
            change_percent = price_data.get('change_percent', 0)
            volume = price_data.get('volume', 0)

            # Filter by price
            if 'price_min' in filters and current_price < filters['price_min']:
                continue
            if 'price_max' in filters and current_price > filters['price_max']:
                continue

            # Filter by day change %
            if 'change_percent_min' in filters and change_percent < filters['change_percent_min']:
                continue
            if 'change_percent_max' in filters and change_percent > filters['change_percent_max']:
                continue

            # Filter by volume
            if 'volume_min' in filters and volume < filters['volume_min']:
                continue

            # Filter by sector
            if 'sectors' in filters and filters['sectors']:
                if stock_meta['sector'] not in filters['sectors']:
                    continue

            # Get detailed info for further filtering
            stock_info = get_stock_info(ticker)
            if not stock_info:
                continue

            market_cap = stock_info.get('market_cap', 0)
            pe_ratio = stock_info.get('pe_ratio', 0)
            dividend_yield = stock_info.get('dividend_yield', 0)
            week_52_high = stock_info.get('fifty_two_week_high', 0)
            week_52_low = stock_info.get('fifty_two_week_low', 0)

            # Filter by market cap
            if 'market_cap_min' in filters and market_cap < filters['market_cap_min']:
                continue
            if 'market_cap_max' in filters and market_cap > filters['market_cap_max']:
                continue

            # Filter by P/E ratio
            if 'pe_min' in filters and (pe_ratio == 0 or pe_ratio < filters['pe_min']):
                continue
            if 'pe_max' in filters and pe_ratio > filters['pe_max']:
                continue

            # Filter by dividend yield
            if 'dividend_yield_min' in filters and dividend_yield < filters['dividend_yield_min']:
                continue

            # 52-week high/low filters
            if 'week_52_high' in filters and filters['week_52_high']:
                # Within 5% of 52-week high
                if week_52_high > 0 and (current_price / week_52_high) < 0.95:
                    continue

            if 'week_52_low' in filters and filters['week_52_low']:
                # Within 10% of 52-week low
                if week_52_low > 0 and (current_price / week_52_low) > 1.10:
                    continue

            # Technical indicator filters
            if 'rsi_min' in filters or 'rsi_max' in filters:
                technicals = calculate_technical_indicators(ticker)
                if technicals:
                    rsi = technicals.get('rsi', 50)

                    if 'rsi_min' in filters and rsi < filters['rsi_min']:
                        continue
                    if 'rsi_max' in filters and rsi > filters['rsi_max']:
                        continue

                    # Add technical data to result
                    stock_info['rsi'] = rsi
                    stock_info['macd'] = technicals.get('macd')
                    stock_info['sma_20'] = technicals.get('sma_20')
                    stock_info['sma_50'] = technicals.get('sma_50')

            # Passed all filters - add to results
            results.append({
                'ticker': ticker,
                'name': stock_meta['name'],
                'sector': stock_meta['sector'],
                'current_price': current_price,
                'change_percent': change_percent,
                'volume': volume,
                'market_cap': market_cap,
                'pe_ratio': pe_ratio,
                'dividend_yield': dividend_yield,
                'week_52_high': week_52_high,
                'week_52_low': week_52_low,
                'rsi': stock_info.get('rsi'),
                'macd': stock_info.get('macd'),
                'sma_20': stock_info.get('sma_20'),
                'sma_50': stock_info.get('sma_50'),
            })

        except Exception as e:
            logger.debug(f"Error screening {ticker}: {e}")
            continue

    logger.info(f"Screener found {len(results)} stocks matching criteria")

    return results


def get_predefined_screens():
    """Get predefined screening strategies."""
    return {
        'value_stocks': {
            'name': 'Value Stocks',
            'description': 'Low P/E, high dividend yield, undervalued stocks',
            'filters': {
                'pe_max': 15,
                'dividend_yield_min': 2,
                'market_cap_min': 1000000000  # 100 Cr
            }
        },
        'growth_stocks': {
            'name': 'Growth Stocks',
            'description': 'High growth potential, momentum stocks',
            'filters': {
                'change_percent_min': 2,
                'rsi_min': 50,
                'volume_min': 100000
            }
        },
        'dividend_stocks': {
            'name': 'Dividend Stocks',
            'description': 'High dividend yielding stocks',
            'filters': {
                'dividend_yield_min': 3,
                'market_cap_min': 500000000  # 50 Cr
            }
        },
        'oversold': {
            'name': 'Oversold Stocks',
            'description': 'RSI < 30, potential reversal candidates',
            'filters': {
                'rsi_max': 30
            }
        },
        'overbought': {
            'name': 'Overbought Stocks',
            'description': 'RSI > 70, potential pullback candidates',
            'filters': {
                'rsi_min': 70
            }
        },
        'near_52_week_high': {
            'name': 'Near 52-Week High',
            'description': 'Stocks within 5% of 52-week high',
            'filters': {
                'week_52_high': True
            }
        },
        'near_52_week_low': {
            'name': 'Near 52-Week Low',
            'description': 'Stocks within 10% of 52-week low',
            'filters': {
                'week_52_low': True
            }
        },
        'blue_chip': {
            'name': 'Blue Chip Stocks',
            'description': 'Large cap, stable companies',
            'filters': {
                'market_cap_min': 10000000000  # 1000 Cr
            }
        },
        'penny_stocks': {
            'name': 'Affordable Stocks',
            'description': 'Low priced stocks under ₹500',
            'filters': {
                'price_max': 500
            }
        },
        'it_sector': {
            'name': 'IT Sector',
            'description': 'Information Technology stocks',
            'filters': {
                'sectors': ['IT']
            }
        },
        'banking_sector': {
            'name': 'Banking Sector',
            'description': 'Banking and financial stocks',
            'filters': {
                'sectors': ['Banking', 'Finance']
            }
        },
        'pharma_sector': {
            'name': 'Pharma Sector',
            'description': 'Pharmaceutical stocks',
            'filters': {
                'sectors': ['Pharma']
            }
        },
    }


def get_sectors():
    """Get list of all available sectors."""
    sectors = set()
    for stock_meta in POPULAR_INDIAN_STOCKS.values():
        sectors.add(stock_meta['sector'])

    return sorted(list(sectors))
