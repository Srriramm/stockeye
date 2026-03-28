import React, { useState, useEffect } from 'react';
import { authAxios } from '../utils/api';
import { RefreshCw, TrendingUp, TrendingDown, Activity, Target, BookOpen } from 'lucide-react';

const API_URL = process.env.REACT_APP_API_URL || '';

function fmtINR(n) {
  if (n == null) return '—';
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n);
}

const REGIME_COLORS = {
  BULL:     { bg: '#d1fae5', color: '#065f46' },
  BEAR:     { bg: '#fee2e2', color: '#991b1b' },
  SIDEWAYS: { bg: '#f1f5f9', color: '#334155' },
  VOLATILE: { bg: '#fef3c7', color: '#92400e' },
  UNKNOWN:  { bg: '#f1f5f9', color: '#64748b' },
};

export default function WeeklyReview() {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const { data: d } = await authAxios.get(`${API_URL}/api/trading/weekly-review`);
      setData(d);
    } catch (e) {
      setError(e.response?.data?.error || 'Failed to load review');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const m  = data?.metrics || {};
  const n  = data?.narrative || {};
  const up = (m.week_return_pct ?? 0) >= 0;
  const regime = m.market_regime || 'UNKNOWN';
  const rc = REGIME_COLORS[regime] || REGIME_COLORS.UNKNOWN;

  return (
    <div style={{
      background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 16,
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '14px 18px', borderBottom: '1px solid #f1f5f9',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <BookOpen size={16} style={{ color: '#2563eb' }} />
          <span style={{ fontWeight: 700, fontSize: 14, color: '#0f172a' }}>Weekly Review</span>
          <span style={{ fontSize: 11, color: '#94a3b8' }}>AI-generated · last 7 days</span>
        </div>
        <button
          onClick={load}
          disabled={loading}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', padding: 4 }}
        >
          <RefreshCw size={14} style={{ animation: loading ? 'spin 0.8s linear infinite' : 'none' }} />
        </button>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>

      {loading && !data && (
        <div style={{ padding: '32px', textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>
          Generating review…
        </div>
      )}

      {error && (
        <div style={{ padding: '16px 18px', color: '#dc2626', fontSize: 13 }}>{error}</div>
      )}

      {data && (
        <div style={{ padding: '16px 18px' }}>
          {/* Metrics strip */}
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 16 }}>
            {[
              {
                icon: up ? TrendingUp : TrendingDown,
                color: up ? '#059669' : '#dc2626',
                label: 'Week P&L',
                value: fmtINR(m.week_pnl_inr),
              },
              {
                icon: Activity,
                color: up ? '#059669' : '#dc2626',
                label: 'Return',
                value: `${(m.week_return_pct ?? 0) >= 0 ? '+' : ''}${(m.week_return_pct ?? 0).toFixed(2)}%`,
              },
              {
                icon: Target,
                color: '#64748b',
                label: 'Up / Down',
                value: `${m.up_days ?? 0}d / ${m.down_days ?? 0}d`,
              },
            ].map(({ icon: Icon, color, label, value }) => (
              <div key={label} style={{
                flex: '1 1 120px', background: '#f8fafc', borderRadius: 10,
                padding: '10px 14px',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#64748b', fontSize: 10, fontWeight: 600, textTransform: 'uppercase', marginBottom: 4 }}>
                  <Icon size={11} />{label}
                </div>
                <div style={{ fontSize: 16, fontWeight: 700, color, fontFamily: 'monospace' }}>{value}</div>
              </div>
            ))}

            {/* Regime badge */}
            <div style={{
              flex: '1 1 100px', background: rc.bg, borderRadius: 10,
              padding: '10px 14px', display: 'flex', flexDirection: 'column', justifyContent: 'center',
            }}>
              <div style={{ fontSize: 10, fontWeight: 600, color: rc.color, textTransform: 'uppercase', marginBottom: 4 }}>Regime</div>
              <div style={{ fontSize: 15, fontWeight: 800, color: rc.color }}>{regime}</div>
            </div>
          </div>

          {/* AI narrative */}
          {(n.performance || n.summary) && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[
                { key: 'performance', label: 'Performance', color: '#1d4ed8' },
                { key: 'market',      label: 'Market Context', color: '#7c3aed' },
                { key: 'focus',       label: 'Next Week Focus', color: '#059669' },
                { key: 'summary',     label: 'Summary', color: '#334155' },
              ].filter(({ key }) => n[key]).map(({ key, label, color }) => (
                <div key={key} style={{
                  background: '#f8fafc', borderRadius: 10, padding: '10px 14px',
                  borderLeft: `3px solid ${color}`,
                }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color, textTransform: 'uppercase', marginBottom: 4 }}>{label}</div>
                  <p style={{ fontSize: 13, color: '#334155', margin: 0, lineHeight: 1.6 }}>{n[key]}</p>
                </div>
              ))}
            </div>
          )}

          {/* Holdings footnote */}
          {m.tickers_held?.length > 0 && (
            <div style={{ marginTop: 12, fontSize: 11, color: '#94a3b8' }}>
              Open positions: {m.tickers_held.join(', ')}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
