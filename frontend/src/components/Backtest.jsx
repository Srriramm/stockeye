import React, { useState, useCallback } from 'react';
import { authAxios } from '../utils/api';
import {
  TrendingUp, TrendingDown, BarChart3, RefreshCw, ChevronUp, ChevronDown,
  AlertTriangle, CheckCircle, XCircle, Zap, Target, Activity,
} from 'lucide-react';

const API_URL = process.env.REACT_APP_API_URL || '';

/* ── helpers ─────────────────────────────────────────────────── */
function fmt(n, decimals = 2) {
  if (n == null || isNaN(n)) return '—';
  return n.toFixed(decimals);
}
function fmtINR(n) {
  if (n == null || isNaN(n)) return '—';
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n);
}
function fmtPct(n) {
  if (n == null || isNaN(n)) return '—';
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;
}

/* ── Mini equity curve (SVG) ─────────────────────────────────── */
function EquityCurve({ data }) {
  if (!data || data.length < 2) return null;
  const values = data.map(d => d.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const W = 500, H = 100;
  const pts = data.map((d, i) => {
    const x = (i / (data.length - 1)) * W;
    const y = H - ((d.value - min) / range) * H * 0.9 - H * 0.05;
    return `${x},${y}`;
  }).join(' ');
  const isUp = values[values.length - 1] >= values[0];
  const color = isUp ? '#10b981' : '#ef4444';
  const fill  = isUp ? '#d1fae520' : '#fee2e220';
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 80 }}>
      <polyline fill="none" stroke={color} strokeWidth="2.5" points={pts} strokeLinejoin="round" />
      <polygon
        fill={fill}
        points={`0,${H} ${pts} ${W},${H}`}
      />
    </svg>
  );
}

/* ── Stat card ────────────────────────────────────────────────── */
function Stat({ label, value, color, icon: Icon, tip }) {
  return (
    <div style={{
      background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 12,
      padding: '16px 18px', display: 'flex', flexDirection: 'column', gap: 4,
    }} title={tip}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#64748b', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {Icon && <Icon size={12} />}{label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color: color || '#0f172a', fontFamily: 'monospace' }}>{value}</div>
    </div>
  );
}

/* ── Trade row ────────────────────────────────────────────────── */
function TradeRow({ t }) {
  const isWin = (t.pnl ?? 0) >= 0;
  return (
    <tr style={{ borderBottom: '1px solid #f1f5f9' }}>
      <td style={{ padding: '8px 12px', fontWeight: 700, fontSize: 13, color: '#0f172a' }}>{t.ticker}</td>
      <td style={{ padding: '8px 12px', fontSize: 12, color: '#64748b' }}>{t.entry_date}</td>
      <td style={{ padding: '8px 12px', fontSize: 12, color: '#64748b' }}>{t.exit_date || '—'}</td>
      <td style={{ padding: '8px 12px', fontSize: 12, fontFamily: 'monospace', color: '#334155' }}>{fmtINR(t.entry_price)}</td>
      <td style={{ padding: '8px 12px', fontSize: 12, fontFamily: 'monospace', color: '#334155' }}>{fmtINR(t.exit_price)}</td>
      <td style={{ padding: '8px 12px', fontSize: 12, fontFamily: 'monospace' }}>
        <span style={{
          color: isWin ? '#059669' : '#dc2626',
          fontWeight: 700,
        }}>{fmtPct(t.pnl_pct)}</span>
      </td>
      <td style={{ padding: '8px 12px', fontSize: 12, fontFamily: 'monospace' }}>
        <span style={{ color: isWin ? '#059669' : '#dc2626' }}>{fmtINR(t.pnl)}</span>
      </td>
      <td style={{ padding: '8px 12px', fontSize: 12, color: '#64748b' }}>{t.exit_reason || '—'}</td>
    </tr>
  );
}

/* ── Main component ───────────────────────────────────────────── */
export default function Backtest() {
  const [days,     setDays]     = useState(90);
  const [capital,  setCapital]  = useState(100000);
  const [tickers,  setTickers]  = useState('');
  const [loading,  setLoading]  = useState(false);
  const [result,   setResult]   = useState(null);
  const [error,    setError]    = useState('');
  const [sortKey,  setSortKey]  = useState('entry_date');
  const [sortAsc,  setSortAsc]  = useState(false);

  const run = useCallback(async () => {
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const params = new URLSearchParams({ days, capital });
      if (tickers.trim()) params.set('tickers', tickers.trim());
      const { data } = await authAxios.get(`${API_URL}/api/trading/backtest?${params}`);
      setResult(data);
    } catch (e) {
      setError(e.response?.data?.error || e.response?.data?.detail || 'Backtest failed');
    } finally {
      setLoading(false);
    }
  }, [days, capital, tickers]);

  const metrics = result?.metrics || {};
  const trades  = result?.trades  || [];
  const curve   = result?.equity_curve || [];

  const sorted = [...trades].sort((a, b) => {
    const av = a[sortKey] ?? 0;
    const bv = b[sortKey] ?? 0;
    if (typeof av === 'string') return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
    return sortAsc ? av - bv : bv - av;
  });

  function toggleSort(key) {
    if (sortKey === key) setSortAsc(!sortAsc);
    else { setSortKey(key); setSortAsc(false); }
  }

  const SortIcon = ({ k }) => sortKey === k
    ? (sortAsc ? <ChevronUp size={11} /> : <ChevronDown size={11} />)
    : null;

  const winners = trades.filter(t => (t.pnl ?? 0) >= 0).length;
  const losers  = trades.length - winners;

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: '24px 20px' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 800, color: '#0f172a', margin: 0 }}>Strategy Backtester</h1>
        <p style={{ color: '#64748b', fontSize: 13, margin: '4px 0 0' }}>
          Replay your signal logic on historical NSE data. No lookahead bias — signals fire on day N, trades execute at day N+1 open.
        </p>
      </div>

      {/* Config bar */}
      <div style={{
        background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 14,
        padding: '16px 20px', display: 'flex', flexWrap: 'wrap', gap: 16,
        alignItems: 'flex-end', marginBottom: 24,
      }}>
        {/* Tickers */}
        <div style={{ flex: '1 1 240px' }}>
          <label style={{ fontSize: 11, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', marginBottom: 6 }}>
            Tickers (blank = your watchlist)
          </label>
          <input
            value={tickers}
            onChange={e => setTickers(e.target.value)}
            placeholder="RELIANCE,TCS,INFY,HDFC..."
            style={{
              width: '100%', padding: '8px 10px', borderRadius: 8, fontSize: 13,
              border: '1px solid #e2e8f0', outline: 'none', color: '#0f172a',
              background: '#f8fafc',
            }}
          />
        </div>

        {/* Period */}
        <div>
          <label style={{ fontSize: 11, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', marginBottom: 6 }}>
            Period
          </label>
          <select
            value={days}
            onChange={e => setDays(Number(e.target.value))}
            style={{ padding: '8px 10px', borderRadius: 8, fontSize: 13, border: '1px solid #e2e8f0', background: '#f8fafc', color: '#0f172a' }}
          >
            <option value={30}>30 days</option>
            <option value={60}>60 days</option>
            <option value={90}>90 days</option>
            <option value={180}>180 days</option>
            <option value={365}>365 days</option>
          </select>
        </div>

        {/* Capital */}
        <div>
          <label style={{ fontSize: 11, fontWeight: 600, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'block', marginBottom: 6 }}>
            Starting Capital
          </label>
          <select
            value={capital}
            onChange={e => setCapital(Number(e.target.value))}
            style={{ padding: '8px 10px', borderRadius: 8, fontSize: 13, border: '1px solid #e2e8f0', background: '#f8fafc', color: '#0f172a' }}
          >
            <option value={50000}>₹50,000</option>
            <option value={100000}>₹1,00,000</option>
            <option value={500000}>₹5,00,000</option>
            <option value={1000000}>₹10,00,000</option>
          </select>
        </div>

        {/* Run button */}
        <button
          onClick={run}
          disabled={loading}
          style={{
            padding: '9px 22px', borderRadius: 10, border: 'none', cursor: loading ? 'not-allowed' : 'pointer',
            background: loading ? '#e2e8f0' : '#2563eb', color: loading ? '#94a3b8' : '#fff',
            fontWeight: 700, fontSize: 13, display: 'flex', alignItems: 'center', gap: 8,
          }}
        >
          {loading
            ? <><RefreshCw size={14} style={{ animation: 'spin 0.8s linear infinite' }} /> Running…</>
            : <><Zap size={14} /> Run Backtest</>
          }
        </button>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 10,
          padding: '12px 16px', color: '#991b1b', fontSize: 13,
          display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20,
        }}>
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <>
          {/* Metrics grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 12, marginBottom: 20 }}>
            <Stat
              label="Total Return"
              value={fmtPct(metrics.total_return_pct)}
              color={metrics.total_return_pct >= 0 ? '#059669' : '#dc2626'}
              icon={metrics.total_return_pct >= 0 ? TrendingUp : TrendingDown}
            />
            <Stat
              label="CAGR"
              value={fmtPct(metrics.cagr_pct)}
              color={metrics.cagr_pct >= 0 ? '#059669' : '#dc2626'}
              icon={BarChart3}
              tip="Compound Annual Growth Rate"
            />
            <Stat
              label="Sharpe Ratio"
              value={fmt(metrics.sharpe_ratio)}
              color={metrics.sharpe_ratio >= 1 ? '#059669' : metrics.sharpe_ratio >= 0 ? '#f59e0b' : '#dc2626'}
              icon={Activity}
              tip=">1 is good, >2 is excellent"
            />
            <Stat
              label="Max Drawdown"
              value={fmtPct(metrics.max_drawdown_pct)}
              color="#dc2626"
              icon={TrendingDown}
              tip="Largest peak-to-trough decline"
            />
            <Stat
              label="Win Rate"
              value={fmtPct(metrics.win_rate_pct)}
              color={metrics.win_rate_pct >= 50 ? '#059669' : '#f59e0b'}
              icon={Target}
            />
            <Stat
              label="Profit Factor"
              value={fmt(metrics.profit_factor)}
              color={metrics.profit_factor >= 1.5 ? '#059669' : metrics.profit_factor >= 1 ? '#f59e0b' : '#dc2626'}
              tip=">1.5 is solid, >2 is excellent"
            />
            <Stat
              label="Total Trades"
              value={metrics.total_trades ?? '—'}
              icon={BarChart3}
            />
            <Stat
              label="Final Value"
              value={fmtINR(metrics.final_value)}
              color={metrics.final_value >= (result.config?.starting_capital ?? 100000) ? '#059669' : '#dc2626'}
            />
          </div>

          {/* W/L mini bar + equity curve card */}
          <div style={{
            background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 14,
            padding: '16px 20px', marginBottom: 20,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a' }}>Equity Curve</div>
              <div style={{ display: 'flex', gap: 14, fontSize: 12 }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#059669' }}>
                  <CheckCircle size={12} /> {winners} wins
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#dc2626' }}>
                  <XCircle size={12} /> {losers} losses
                </span>
              </div>
            </div>
            <EquityCurve data={curve} />
          </div>

          {/* Trade log */}
          {trades.length > 0 && (
            <div style={{
              background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 14,
              overflow: 'hidden',
            }}>
              <div style={{ padding: '14px 18px', borderBottom: '1px solid #f1f5f9', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 700, fontSize: 14, color: '#0f172a' }}>Trade Log ({trades.length})</span>
                <span style={{ fontSize: 11, color: '#94a3b8' }}>Click headers to sort</span>
              </div>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ background: '#f8fafc' }}>
                      {[
                        ['ticker',     'Ticker'],
                        ['entry_date', 'Entry'],
                        ['exit_date',  'Exit'],
                        ['entry_price','Buy @'],
                        ['exit_price', 'Sell @'],
                        ['pnl_pct',    'Return%'],
                        ['pnl',        'P&L (₹)'],
                        ['exit_reason','Reason'],
                      ].map(([key, label]) => (
                        <th
                          key={key}
                          onClick={() => toggleSort(key)}
                          style={{
                            padding: '8px 12px', textAlign: 'left', fontSize: 11,
                            fontWeight: 700, color: '#64748b', cursor: 'pointer',
                            textTransform: 'uppercase', letterSpacing: '0.04em',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {label} <SortIcon k={key} />
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sorted.map((t, i) => <TradeRow key={i} t={t} />)}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Config summary */}
          {result.config && (
            <div style={{ marginTop: 12, fontSize: 11, color: '#94a3b8', textAlign: 'center' }}>
              Tickers: {result.config.tickers?.join(', ')} ·
              Period: {result.config.days} days ·
              Capital: {fmtINR(result.config.starting_capital)} ·
              Max positions: {result.config.max_positions} ·
              Risk/trade: {result.config.risk_per_trade * 100}%
            </div>
          )}
        </>
      )}

      {/* Empty state */}
      {!result && !loading && !error && (
        <div style={{
          background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 14,
          padding: '48px 24px', textAlign: 'center',
        }}>
          <BarChart3 size={36} style={{ color: '#cbd5e1', margin: '0 auto 12px' }} />
          <div style={{ fontSize: 15, fontWeight: 700, color: '#0f172a', marginBottom: 6 }}>No results yet</div>
          <div style={{ fontSize: 13, color: '#64748b' }}>
            Configure your parameters above and click <strong>Run Backtest</strong>.
            <br />Leave tickers blank to test your entire watchlist.
          </div>
        </div>
      )}
    </div>
  );
}
