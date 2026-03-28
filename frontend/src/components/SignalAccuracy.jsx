import React, { useState, useEffect } from 'react';
import { authAxios } from '../utils/api';
import { BarChart3, TrendingUp, TrendingDown, RefreshCw, AlertTriangle, CheckCircle } from 'lucide-react';

const API_URL = process.env.REACT_APP_API_URL || '';

const SIGNAL_META = {
  fii_dii:     { label: 'FII/DII Flows',    color: '#2563eb' },
  pcr:         { label: 'Nifty PCR',        color: '#7c3aed' },
  technical:   { label: 'Technical (RSI/MACD)', color: '#059669' },
  delivery:    { label: 'Delivery Volume %', color: '#f59e0b' },
  news:        { label: 'News Sentiment',    color: '#64748b' },
  global_cues: { label: 'Global Cues',       color: '#0891b2' },
  fo_oi:       { label: 'F&O OI Buildup',    color: '#dc2626' },
};

function CorrBar({ value }) {
  // value is -1 to +1 Pearson correlation
  const pct = Math.abs(value) * 100;
  const color = value >= 0.1 ? '#10b981' : value >= 0 ? '#f59e0b' : '#ef4444';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height: 6, background: '#f1f5f9', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 3, transition: 'width 0.5s' }} />
      </div>
      <span style={{ fontSize: 11, fontFamily: 'monospace', color, fontWeight: 700, minWidth: 40, textAlign: 'right' }}>
        {value >= 0 ? '+' : ''}{value.toFixed(3)}
      </span>
    </div>
  );
}

export default function SignalAccuracy() {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState('');
  const [days,    setDays]    = useState(90);
  const [scope,   setScope]   = useState('user');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const { data: d } = await authAxios.get(
        `${API_URL}/api/trading/signal-accuracy?days=${days}&scope=${scope}`
      );
      setData(d);
    } catch (e) {
      setError(e.response?.data?.error || 'Failed to load signal accuracy');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [days, scope]);

  const stats  = data?.signal_stats  || {};
  const ranked = Object.entries(stats).sort((a, b) => b[1].correlation - a[1].correlation);

  return (
    <div style={{
      background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 16,
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '14px 18px', borderBottom: '1px solid #f1f5f9',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <BarChart3 size={16} style={{ color: '#2563eb' }} />
          <span style={{ fontWeight: 700, fontSize: 14, color: '#0f172a' }}>Signal Accuracy</span>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select
            value={days}
            onChange={e => setDays(Number(e.target.value))}
            style={{ fontSize: 12, padding: '4px 8px', borderRadius: 6, border: '1px solid #e2e8f0', background: '#f8fafc' }}
          >
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
            <option value={180}>180 days</option>
          </select>
          <select
            value={scope}
            onChange={e => setScope(e.target.value)}
            style={{ fontSize: 12, padding: '4px 8px', borderRadius: 6, border: '1px solid #e2e8f0', background: '#f8fafc' }}
          >
            <option value="user">My trades</option>
            <option value="all">All users</option>
          </select>
          <button
            onClick={load}
            disabled={loading}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', padding: 4 }}
          >
            <RefreshCw size={13} style={{ animation: loading ? 'spin 0.8s linear infinite' : 'none' }} />
          </button>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      </div>

      {loading && !data && (
        <div style={{ padding: '32px', textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>Loading…</div>
      )}

      {error && (
        <div style={{ padding: '16px 18px', color: '#dc2626', fontSize: 13, display: 'flex', gap: 6 }}>
          <AlertTriangle size={14} />{error}
        </div>
      )}

      {data?.message && (
        <div style={{ padding: '32px', textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>
          {data.message}
        </div>
      )}

      {data && ranked.length > 0 && (
        <div style={{ padding: '16px 18px' }}>
          {/* Summary strip */}
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 20 }}>
            {[
              { label: 'Trades analysed', value: data.total_trades },
              { label: 'Avg return', value: `${data.avg_return_pct >= 0 ? '+' : ''}${data.avg_return_pct?.toFixed(2)}%`,
                color: data.avg_return_pct >= 0 ? '#059669' : '#dc2626' },
              { label: 'Win rate', value: `${data.win_rate_pct?.toFixed(1)}%`,
                color: data.win_rate_pct >= 50 ? '#059669' : '#f59e0b' },
            ].map(({ label, value, color }) => (
              <div key={label} style={{
                flex: '1 1 100px', background: '#f8fafc', borderRadius: 10,
                padding: '10px 14px',
              }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', marginBottom: 3 }}>{label}</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: color || '#0f172a', fontFamily: 'monospace' }}>{value}</div>
              </div>
            ))}
            {data.top_signal && (
              <div style={{
                flex: '1 1 140px', background: '#d1fae5', borderRadius: 10, padding: '10px 14px',
              }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: '#065f46', textTransform: 'uppercase', marginBottom: 3, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <CheckCircle size={10} /> Best signal
                </div>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#065f46' }}>
                  {SIGNAL_META[data.top_signal]?.label || data.top_signal}
                </div>
              </div>
            )}
          </div>

          {/* Per-signal breakdown */}
          <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
            Predictive Correlation (higher = more accurate)
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {ranked.map(([key, s]) => {
              const meta = SIGNAL_META[key] || { label: key, color: '#64748b' };
              return (
                <div key={key}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <div style={{ width: 8, height: 8, borderRadius: '50%', background: meta.color }} />
                      <span style={{ fontSize: 12, fontWeight: 600, color: '#334155' }}>{meta.label}</span>
                    </div>
                    <div style={{ display: 'flex', gap: 12, fontSize: 11, color: '#64748b' }}>
                      <span title="Average score on winning trades">
                        <TrendingUp size={9} style={{ color: '#10b981', display: 'inline', marginRight: 2 }} />
                        {s.avg_score_on_wins?.toFixed(0)}
                      </span>
                      <span title="Average score on losing trades">
                        <TrendingDown size={9} style={{ color: '#ef4444', display: 'inline', marginRight: 2 }} />
                        {s.avg_score_on_losses?.toFixed(0)}
                      </span>
                      <span title="Win-score gap" style={{ color: s.predictive_gap >= 5 ? '#059669' : '#94a3b8', fontWeight: 700 }}>
                        Δ{s.predictive_gap?.toFixed(1)}
                      </span>
                    </div>
                  </div>
                  <CorrBar value={s.correlation} />
                </div>
              );
            })}
          </div>

          <p style={{ fontSize: 11, color: '#94a3b8', marginTop: 16, lineHeight: 1.5 }}>
            Correlation measures how well each signal's score predicted actual trade returns.
            Positive = signal was predictive, Negative = signal was contrarian.
            Gap (Δ) = difference in average score between winning and losing trades.
          </p>
        </div>
      )}
    </div>
  );
}
