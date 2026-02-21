/**
 * RealtimePrice Component
 * Displays stock price with real-time updates and animated changes
 * Similar to Groww/Zerodha price display
 */

import React, { useState, useEffect, useRef } from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';
import wsManager from '../utils/websocket';

export default function RealtimePrice({ ticker, showChange = true, showPercentage = true, className = '' }) {
  const [priceData, setPriceData] = useState(null);
  const [priceChange, setPriceChange] = useState('neutral'); // 'up', 'down', 'neutral'
  const [flashAnimation, setFlashAnimation] = useState(false);
  const prevPriceRef = useRef(null);

  useEffect(() => {
    if (!ticker) return;

    // Subscribe to real-time price updates
    const unsubscribe = wsManager.subscribe(ticker, (data) => {
      if (data && data.current_price) {
        // Detect price change direction
        if (prevPriceRef.current !== null && prevPriceRef.current !== data.current_price) {
          if (data.current_price > prevPriceRef.current) {
            setPriceChange('up');
          } else if (data.current_price < prevPriceRef.current) {
            setPriceChange('down');
          }

          // Trigger flash animation
          setFlashAnimation(true);
          setTimeout(() => setFlashAnimation(false), 300);
        }

        prevPriceRef.current = data.current_price;
        setPriceData(data);
      }
    });

    // Cleanup subscription on unmount
    return () => {
      unsubscribe();
    };
  }, [ticker]);

  if (!priceData) {
    return (
      <div className={`animate-pulse ${className}`}>
        <div className="h-6 bg-slate-50 rounded w-24"></div>
      </div>
    );
  }

  const { current_price, change, change_percent } = priceData;
  const isPositive = change >= 0;

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {/* Current Price */}
      <span
        className={`font-bold text-lg transition-all duration-300 ${
          flashAnimation
            ? priceChange === 'up'
              ? 'text-green-400 scale-110'
              : priceChange === 'down'
              ? 'text-red-400 scale-110'
              : 'text-slate-800'
            : 'text-slate-800'
        }`}
      >
        ₹{current_price?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </span>

      {/* Price Change */}
      {showChange && (
        <div className={`flex items-center gap-1 text-sm font-medium ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
          {isPositive ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
          <span>
            {isPositive ? '+' : ''}
            {change?.toFixed(2)}
          </span>
          {showPercentage && (
            <span className="ml-1">
              ({isPositive ? '+' : ''}
              {change_percent?.toFixed(2)}%)
            </span>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * RealtimePriceCard Component
 * Full card showing stock name and real-time price
 */
export function RealtimePriceCard({ ticker, name, className = '' }) {
  const [priceData, setPriceData] = useState(null);

  useEffect(() => {
    if (!ticker) return;

    const unsubscribe = wsManager.subscribe(ticker, (data) => {
      setPriceData(data);
    });

    return () => unsubscribe();
  }, [ticker]);

  if (!priceData) {
    return (
      <div className={`bg-white rounded-lg p-4 border border-slate-200 animate-pulse ${className}`}>
        <div className="h-4 bg-slate-50 rounded w-32 mb-2"></div>
        <div className="h-6 bg-slate-50 rounded w-24"></div>
      </div>
    );
  }

  const { current_price, change, change_percent } = priceData;
  const isPositive = change >= 0;

  return (
    <div className={`bg-white rounded-lg p-4 border border-slate-200 hover:border-slate-200 transition ${className}`}>
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="text-sm font-medium text-slate-600">{ticker}</div>
          {name && <div className="text-xs text-slate-500 mt-0.5">{name}</div>}
        </div>
        <div className={`text-xs font-medium px-2 py-1 rounded ${isPositive ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
          {isPositive ? '+' : ''}
          {change_percent?.toFixed(2)}%
        </div>
      </div>

      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold text-slate-800">₹{current_price?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
        <span className={`text-sm font-medium ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
          {isPositive ? '+' : ''}₹{change?.toFixed(2)}
        </span>
      </div>
    </div>
  );
}

/**
 * PriceChangeIndicator Component
 * Minimal price change indicator (just the colored arrow and percentage)
 */
export function PriceChangeIndicator({ value, percentage, size = 'md' }) {
  const isPositive = value >= 0;
  const sizeClasses = {
    sm: 'text-xs',
    md: 'text-sm',
    lg: 'text-base',
  };

  return (
    <div className={`flex items-center gap-1 font-medium ${isPositive ? 'text-green-400' : 'text-red-400'} ${sizeClasses[size]}`}>
      {isPositive ? <TrendingUp size={size === 'sm' ? 12 : size === 'lg' ? 18 : 14} /> : <TrendingDown size={size === 'sm' ? 12 : size === 'lg' ? 18 : 14} />}
      <span>
        {isPositive ? '+' : ''}
        {percentage?.toFixed(2)}%
      </span>
    </div>
  );
}
