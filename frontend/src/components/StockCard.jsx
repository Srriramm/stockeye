import React, { useState, useCallback } from 'react';
import { TrendingUp, TrendingDown, Eye, Activity, X, BarChart3, ArrowUpRight, ArrowDownRight } from 'lucide-react';
import CandlestickChart, { PERIOD_MAP } from './CandlestickChart';
import axios from 'axios';

export default function StockCard({ stock, apiUrl, onMonitor, onAnalyze, compact = false }) {
  const [expanded, setExpanded] = useState(false);
  const [details, setDetails] = useState(null);
  const [history, setHistory] = useState(null);
  const [loading, setLoading] = useState(false);
  const [chartPeriod, setChartPeriod] = useState('3M');
  const [chartLoading, setChartLoading] = useState(false);

  const isPositive = (stock.change_percent || stock.pnl_percent || 0) >= 0;

  const fetchHistory = useCallback(async (period) => {
    const { period: yp, interval: yi } = PERIOD_MAP[period] || PERIOD_MAP['3M'];
    setChartLoading(true);
    try {
      const res = await axios.get(`${apiUrl}/api/stocks/${stock.ticker}/history?period=${yp}&interval=${yi}`);
      setHistory(res.data.data);
    } catch (err) { console.error(err); }
    finally { setChartLoading(false); }
  }, [apiUrl, stock.ticker]);

  const loadDetails = async () => {
    if (details) { setExpanded(!expanded); return; }
    setLoading(true);
    try {
      const [detailsRes, historyRes] = await Promise.all([
        axios.get(`${apiUrl}/api/stocks/${stock.ticker}`),
        axios.get(`${apiUrl}/api/stocks/${stock.ticker}/history?period=3mo&interval=1d`),
      ]);
      setDetails(detailsRes.data);
      setHistory(historyRes.data.data);
      setExpanded(true);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  const handlePeriodChange = (p) => {
    setChartPeriod(p);
    fetchHistory(p);
  };

  if (compact) {
    return (
      <div className="flex items-center justify-between py-2 px-3 hover:bg-slate-50/50 rounded-lg cursor-pointer transition" onClick={loadDetails}>
        <div className="flex items-center gap-3">
          <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold ${isPositive ? 'bg-green-500/10 text-green-400' : 'bg-red-500/10 text-red-400'}`}>
            {isPositive ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
          </div>
          <div>
            <div className="text-sm font-medium text-slate-800">{stock.ticker}</div>
            <div className="text-xs text-slate-500">{stock.name?.substring(0, 20)}</div>
          </div>
        </div>
        <div className="text-right">
          <div className="text-sm font-medium text-slate-800">₹{stock.current_price?.toLocaleString('en-IN')}</div>
          <div className={`text-xs ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
            {isPositive ? '+' : ''}{(stock.change_percent || stock.pnl_percent || 0).toFixed(2)}%
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 overflow-hidden hover:border-slate-200 transition">
      {/* Card Header */}
      <div className="p-4 cursor-pointer" onClick={loadDetails}>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${isPositive ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
              {isPositive ? <TrendingUp size={18} className="text-green-400" /> : <TrendingDown size={18} className="text-red-400" />}
            </div>
            <div>
              <div className="text-slate-800 font-semibold">{stock.ticker}</div>
              <div className="text-xs text-slate-500">{stock.name?.substring(0, 30)}</div>
            </div>
          </div>
          {stock.sector && <span className="text-xs bg-slate-50 text-slate-600 px-2 py-1 rounded-full">{stock.sector}</span>}
        </div>

        <div className="flex items-end justify-between">
          <div>
            <div className="text-2xl font-bold text-slate-800">₹{stock.current_price?.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</div>
            <div className={`flex items-center gap-1 text-sm font-medium ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
              {isPositive ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
              {stock.change !== undefined && <span>₹{Math.abs(stock.change).toFixed(2)}</span>}
              <span>({isPositive ? '+' : ''}{(stock.change_percent || stock.pnl_percent || 0).toFixed(2)}%)</span>
            </div>
          </div>
          <div className="text-right text-xs text-slate-500 space-y-1">
            {stock.market_cap > 0 && <div>MCap: ₹{(stock.market_cap / 1e7).toFixed(0)} Cr</div>}
            {stock.volume > 0 && <div>Vol: {(stock.volume / 1e6).toFixed(2)}M</div>}
          </div>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="px-4 pb-3 flex gap-2">
        {onAnalyze && (
          <button onClick={() => onAnalyze(stock.ticker)} className="flex-1 flex items-center justify-center gap-1 py-1.5 bg-sky-500/10 text-sky-600 rounded-lg text-xs hover:bg-sky-50 transition">
            <BarChart3 size={12} /> Analyze
          </button>
        )}
        {onMonitor && (
          <button onClick={() => onMonitor(stock.ticker)} className="flex-1 flex items-center justify-center gap-1 py-1.5 bg-blue-600/10 text-sky-600 rounded-lg text-xs hover:bg-blue-600/20 transition">
            <Eye size={12} /> Monitor
          </button>
        )}
      </div>

      {/* Expanded Detail View */}
      {expanded && details && (
        <div className="border-t border-slate-200 p-4 slide-up">
          {/* Price Chart */}
          {history && history.length > 0 && (
            <div className="mb-4 relative">
              <h4 className="text-sm font-medium text-slate-600 mb-2">Price History</h4>
              {chartLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-white/60 z-10 rounded">
                  <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                </div>
              )}
              <CandlestickChart
                data={history}
                height={180}
                currentPrice={stock.current_price}
                selectedPeriod={chartPeriod}
                onPeriodChange={handlePeriodChange}
              />
            </div>
          )}

          {/* Fundamentals */}
          {details.info && (
            <div className="grid grid-cols-3 gap-3">
              <MiniStat label="P/E Ratio" value={details.info.pe_ratio || 'N/A'} />
              <MiniStat label="EPS" value={`₹${details.info.eps || 'N/A'}`} />
              <MiniStat label="Book Value" value={`₹${details.info.book_value || 'N/A'}`} />
              <MiniStat label="Div Yield" value={`${details.info.dividend_yield || 0}%`} />
              <MiniStat label="ROE" value={`${details.info.roe || 0}%`} />
              <MiniStat label="Beta" value={details.info.beta || 'N/A'} />
              <MiniStat label="52W High" value={`₹${details.info.fifty_two_week_high?.toLocaleString('en-IN') || 'N/A'}`} />
              <MiniStat label="52W Low" value={`₹${details.info.fifty_two_week_low?.toLocaleString('en-IN') || 'N/A'}`} />
              <MiniStat label="D/E Ratio" value={details.info.debt_to_equity || 'N/A'} />
            </div>
          )}

          {/* Technical Signals */}
          {details.technicals?.signals && (
            <div className="mt-3 space-y-1">
              <h4 className="text-xs font-medium text-slate-500">Technical Signals</h4>
              {details.technicals.signals.map((signal, i) => (
                <div key={i} className="text-xs text-slate-600 flex items-center gap-2">
                  <span className={`w-1.5 h-1.5 rounded-full ${signal.toLowerCase().includes('bullish') || signal.toLowerCase().includes('above') ? 'bg-green-400' :
                      signal.toLowerCase().includes('bearish') || signal.toLowerCase().includes('below') ? 'bg-red-400' : 'bg-yellow-400'
                    }`} />
                  {signal}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {loading && (
        <div className="p-4 text-center text-sm text-slate-500">
          Loading details...
        </div>
      )}
    </div>
  );
}

function MiniStat({ label, value }) {
  return (
    <div className="bg-slate-50/50 rounded-lg p-2">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-sm font-medium text-slate-800">{value}</div>
    </div>
  );
}
