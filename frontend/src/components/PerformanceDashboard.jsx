/**
 * PerformanceDashboard — public track record page.
 * No auth required. This is the trust/marketing page.
 * Shows all paper trades, outcomes, win rate, and equity curve.
 */

import { useEffect, useState } from 'react';
import { TrendingUp, TrendingDown, BarChart2, Target, Award, AlertCircle, RefreshCw } from 'lucide-react';

const API_URL = import.meta.env.VITE_API_URL || '';

function StatCard({ label, value, sub, positive }) {
  const color = positive === true
    ? 'text-emerald-400'
    : positive === false
    ? 'text-red-400'
    : 'text-white';

  return (
    <div className="bg-white/5 border border-white/10 rounded-xl p-5 flex flex-col gap-1">
      <span className="text-xs text-slate-400 uppercase tracking-wider">{label}</span>
      <span className={`text-2xl font-bold ${color}`}>{value}</span>
      {sub && <span className="text-xs text-slate-500">{sub}</span>}
    </div>
  );
}

function RegimeBadge({ regime }) {
  const config = {
    BULL:     { color: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30', label: '🐂 Bull Market' },
    BEAR:     { color: 'bg-red-500/20 text-red-300 border-red-500/30',             label: '🐻 Bear Market' },
    SIDEWAYS: { color: 'bg-amber-500/20 text-amber-300 border-amber-500/30',       label: '↔ Sideways' },
    VOLATILE: { color: 'bg-purple-500/20 text-purple-300 border-purple-500/30',    label: '⚡ Volatile' },
    UNKNOWN:  { color: 'bg-slate-500/20 text-slate-300 border-slate-500/30',       label: '? Unknown' },
  };
  const c = config[regime] || config.UNKNOWN;
  return (
    <span className={`text-xs px-2 py-1 rounded-full border font-medium ${c.color}`}>
      {c.label}
    </span>
  );
}

function EquityCurve({ data }) {
  if (!data || data.length === 0) {
    return (
      <div className="h-40 flex items-center justify-center text-slate-500 text-sm">
        No equity history yet
      </div>
    );
  }

  const values  = data.map(d => d.value).filter(Boolean);
  const min     = Math.min(...values);
  const max     = Math.max(...values);
  const range   = max - min || 1;
  const width   = 600;
  const height  = 120;
  const pad     = 8;

  const points = data.map((d, i) => {
    const x = pad + (i / (data.length - 1)) * (width - pad * 2);
    const y = height - pad - ((d.value - min) / range) * (height - pad * 2);
    return `${x},${y}`;
  }).join(' ');

  const lastVal  = values[values.length - 1];
  const firstVal = values[0];
  const isUp     = lastVal >= firstVal;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-32" preserveAspectRatio="none">
      <polyline
        points={points}
        fill="none"
        stroke={isUp ? '#34d399' : '#f87171'}
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function PerformanceDashboard() {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [days,    setDays]    = useState(90);

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/performance?days=${days}`);
      const json = await res.json();
      setData(json);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, [days]);

  const record = data?.track_record || {};
  const pulse  = data?.market_pulse || {};
  const vix    = pulse.india_vix;
  const fii    = pulse.fii_dii?.fii_net_cr;
  const pcr    = pulse.nifty_pcr;

  return (
    <div className="min-h-screen bg-[#0f0f1a] text-white px-4 py-10 max-w-5xl mx-auto">

      {/* Header */}
      <div className="flex items-start justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">StockEye AI — Live Track Record</h1>
          <p className="text-slate-400 mt-1 text-sm">
            Autonomous paper trading on NSE stocks. Every trade logged. Every loss shown.
          </p>
        </div>
        <button
          onClick={fetchData}
          className="flex items-center gap-2 text-xs text-slate-400 hover:text-white transition-colors mt-1"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Period selector */}
      <div className="flex gap-2 mb-6">
        {[30, 90, 180, 365].map(d => (
          <button
            key={d}
            onClick={() => setDays(d)}
            className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
              days === d
                ? 'bg-indigo-600 text-white'
                : 'bg-white/5 text-slate-400 hover:bg-white/10'
            }`}
          >
            {d}d
          </button>
        ))}
      </div>

      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 animate-pulse">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="bg-white/5 rounded-xl h-24" />
          ))}
        </div>
      ) : !record.total_trades ? (
        <div className="text-center text-slate-500 py-20">
          <BarChart2 size={40} className="mx-auto mb-3 opacity-30" />
          <p>No completed trades yet. Track record builds as the AI trades.</p>
        </div>
      ) : (
        <>
          {/* Stats grid */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <StatCard
              label="Avg Return / Trade"
              value={`${record.avg_return_pct > 0 ? '+' : ''}${record.avg_return_pct}%`}
              sub={`${record.total_trades} closed trades`}
              positive={record.avg_return_pct > 0}
            />
            <StatCard
              label="Win Rate"
              value={`${record.win_rate}%`}
              sub={`${record.winning_trades}W / ${record.losing_trades}L`}
              positive={record.win_rate >= 55}
            />
            <StatCard
              label="Profit Factor"
              value={record.profit_factor || '—'}
              sub="Sum wins / Sum losses"
              positive={record.profit_factor >= 1.5}
            />
            <StatCard
              label="Total Trades"
              value={record.total_trades}
              sub={`Last ${days} days`}
            />
          </div>

          {/* Equity curve */}
          {record.equity_curve?.length > 0 && (
            <div className="bg-white/5 border border-white/10 rounded-xl p-5 mb-8">
              <h2 className="text-sm font-medium text-slate-400 mb-3">Portfolio Value Over Time</h2>
              <EquityCurve data={record.equity_curve} />
            </div>
          )}

          {/* Recent trades */}
          <div className="bg-white/5 border border-white/10 rounded-xl p-5 mb-8">
            <h2 className="text-sm font-medium text-slate-400 mb-4">Recent Closed Trades</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-slate-500 border-b border-white/10">
                    <th className="text-left pb-2 pr-4">Ticker</th>
                    <th className="text-left pb-2 pr-4">Entry</th>
                    <th className="text-left pb-2 pr-4">Exit</th>
                    <th className="text-right pb-2">P&L</th>
                  </tr>
                </thead>
                <tbody>
                  {(record.trades || []).map((t, i) => (
                    <tr key={i} className="border-b border-white/5 hover:bg-white/5 transition-colors">
                      <td className="py-2 pr-4 font-medium">{t.ticker}</td>
                      <td className="py-2 pr-4 text-slate-400 text-xs">
                        {t.entry_date ? new Date(t.entry_date).toLocaleDateString('en-IN') : '—'}
                      </td>
                      <td className="py-2 pr-4 text-slate-400 text-xs">
                        {t.exit_date ? new Date(t.exit_date).toLocaleDateString('en-IN') : 'Open'}
                      </td>
                      <td className={`py-2 text-right font-medium ${
                        t.pnl_pct > 0 ? 'text-emerald-400' : 'text-red-400'
                      }`}>
                        {t.pnl_pct > 0 ? '+' : ''}{t.pnl_pct?.toFixed(2)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Market pulse */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-5 mb-8">
        <h2 className="text-sm font-medium text-slate-400 mb-4">Market Pulse</h2>
        <div className="flex flex-wrap gap-4 text-sm">
          <div>
            <span className="text-slate-500 mr-2">India VIX</span>
            <span className={vix > 20 ? 'text-red-400' : 'text-emerald-400'}>
              {vix?.toFixed(1) ?? '—'}
            </span>
          </div>
          <div>
            <span className="text-slate-500 mr-2">FII Today</span>
            <span className={fii < 0 ? 'text-red-400' : 'text-emerald-400'}>
              {fii != null ? `₹${fii > 0 ? '+' : ''}${fii.toFixed(0)}cr` : '—'}
            </span>
          </div>
          <div>
            <span className="text-slate-500 mr-2">Nifty PCR</span>
            <span className={pcr < 0.8 ? 'text-red-400' : pcr > 1.2 ? 'text-emerald-400' : 'text-slate-300'}>
              {pcr?.toFixed(2) ?? '—'}
            </span>
          </div>
        </div>
      </div>

      {/* Disclaimer */}
      <div className="flex gap-2 text-xs text-slate-600 items-start">
        <AlertCircle size={14} className="mt-0.5 shrink-0" />
        <p>
          Paper trading simulation only. All trades use virtual money at live NSE prices.
          Past performance does not guarantee future results.
          Not investment advice. StockEye is an educational AI trading simulator.
        </p>
      </div>
    </div>
  );
}
