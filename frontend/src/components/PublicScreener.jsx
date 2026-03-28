import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { TrendingUp, TrendingDown, Activity, RefreshCw, AlertTriangle, ArrowRight } from 'lucide-react';
import StockEyeLogo from './StockEyeLogo';

const API_URL = process.env.REACT_APP_API_URL || '';

const SIGNAL_LABELS = {
  fii_dii:   'FII/DII',
  pcr:       'PCR',
  technical: 'Tech',
  delivery:  'Delivery',
  news:      'News',
  global_cues: 'Global',
  fo_oi:     'F&O OI',
};

const REGIME_CFG = {
  BULL:     { bg: '#d1fae5', color: '#065f46', label: 'BULL' },
  BEAR:     { bg: '#fee2e2', color: '#991b1b', label: 'BEAR' },
  SIDEWAYS: { bg: '#f1f5f9', color: '#334155', label: 'SIDEWAYS' },
  VOLATILE: { bg: '#fef3c7', color: '#92400e', label: 'VOLATILE' },
};

function ScoreBar({ score }) {
  const color = score >= 65 ? '#10b981' : score >= 45 ? '#f59e0b' : '#ef4444';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ width: 48, height: 4, background: '#f1f5f9', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ width: `${score}%`, height: '100%', background: color, borderRadius: 2 }} />
      </div>
      <span style={{ fontSize: 11, fontWeight: 700, color, fontFamily: 'monospace', minWidth: 24 }}>{score}</span>
    </div>
  );
}

function SignalDot({ score }) {
  const color = score >= 65 ? '#10b981' : score >= 45 ? '#f59e0b' : '#ef4444';
  return (
    <div style={{ width: 8, height: 8, borderRadius: '50%', background: color }} title={`Score: ${score}`} />
  );
}

export default function PublicScreener() {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const { data: d } = await axios.get(`${API_URL}/api/screener/enhanced`);
      setData(d);
    } catch (e) {
      setError('Could not load screener data. Please try again shortly.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const mc   = data?.market_context || {};
  const vix  = mc.india_vix;
  const fii  = mc.fii_dii?.fii_net_cr;
  const pcr  = mc.nifty_pcr;
  const regime = mc.regime || 'UNKNOWN';
  const rc   = REGIME_CFG[regime] || { bg: '#f1f5f9', color: '#64748b', label: regime };

  return (
    <div style={{ minHeight: '100vh', background: '#f8fafc', fontFamily: 'system-ui, sans-serif' }}>
      {/* Nav */}
      <header style={{
        background: '#ffffff', borderBottom: '1px solid #e2e8f0',
        padding: '0 24px', height: 56, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <StockEyeLogo size={44} dark={false} />
          <span style={{ fontSize: 13, fontWeight: 600, color: '#64748b' }}>Signal Screener</span>
        </div>
        <a
          href="/login"
          style={{
            fontSize: 13, fontWeight: 700, color: '#ffffff',
            background: '#2563eb', padding: '7px 16px', borderRadius: 8,
            textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 6,
          }}
        >
          Try StockEye <ArrowRight size={13} />
        </a>
      </header>

      <div style={{ maxWidth: 1100, margin: '0 auto', padding: '28px 20px' }}>
        {/* Hero */}
        <div style={{ marginBottom: 28, textAlign: 'center' }}>
          <h1 style={{ fontSize: 26, fontWeight: 800, color: '#0f172a', margin: '0 0 8px' }}>
            NSE Signal Screener
          </h1>
          <p style={{ color: '#64748b', fontSize: 14, margin: 0 }}>
            Real-time composite scores using FII/DII flows, F&O PCR, technicals, delivery volume and news sentiment.
            Updated every 15 minutes.
          </p>
        </div>

        {/* Market Context bar */}
        {data && (
          <div style={{
            background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 14,
            padding: '14px 20px', display: 'flex', flexWrap: 'wrap', gap: 20,
            alignItems: 'center', marginBottom: 24,
          }}>
            <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', flex: 1 }}>
              <div>
                <div style={{ fontSize: 10, fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase' }}>India VIX</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: vix > 20 ? '#dc2626' : '#059669', fontFamily: 'monospace' }}>
                  {vix?.toFixed(1) ?? '—'}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase' }}>FII Net</div>
                <div style={{ fontSize: 15, fontWeight: 700, fontFamily: 'monospace', color: fii >= 0 ? '#059669' : '#dc2626' }}>
                  {fii != null ? `₹${fii >= 0 ? '+' : ''}${fii.toLocaleString('en-IN')}cr` : '—'}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase' }}>Nifty PCR</div>
                <div style={{ fontSize: 15, fontWeight: 700, fontFamily: 'monospace', color: '#334155' }}>
                  {pcr?.toFixed(2) ?? '—'}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase' }}>Regime</div>
                <div style={{
                  display: 'inline-block', padding: '2px 10px', borderRadius: 6,
                  background: rc.bg, color: rc.color, fontWeight: 800, fontSize: 12,
                }}>
                  {rc.label}
                </div>
              </div>
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
        )}

        {/* Sector rotation mini-strip */}
        {mc.sector_rotation?.length > 0 && (
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 20 }}>
            {mc.sector_rotation.map(s => (
              <div key={s.sector} style={{
                background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 8,
                padding: '6px 12px', fontSize: 12,
              }}>
                <span style={{ fontWeight: 600, color: '#334155' }}>{s.sector} </span>
                <span style={{ fontWeight: 700, color: s.change_pct >= 0 ? '#059669' : '#dc2626', fontFamily: 'monospace' }}>
                  {s.change_pct >= 0 ? '+' : ''}{s.change_pct?.toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        )}

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

        {loading && !data && (
          <div style={{ textAlign: 'center', padding: '60px 0', color: '#94a3b8', fontSize: 14 }}>
            <Activity size={24} style={{ margin: '0 auto 12px', display: 'block', animation: 'pulse 1.5s infinite' }} />
            Scanning NSE universe…
            <style>{`@keyframes pulse { 0%,100%{opacity:1}50%{opacity:0.4} }`}</style>
          </div>
        )}

        {/* Top picks */}
        {data?.top_picks?.length > 0 && (
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 10 }}>
              Top Picks Today
            </div>
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              {data.top_picks.map(s => {
                const score = s.composite_score;
                const color = score >= 65 ? '#059669' : score >= 50 ? '#f59e0b' : '#dc2626';
                return (
                  <div key={s.ticker} style={{
                    background: '#ffffff', border: `1px solid ${color}30`,
                    borderRadius: 12, padding: '14px 18px', minWidth: 140,
                    borderTop: `3px solid ${color}`,
                  }}>
                    <div style={{ fontWeight: 800, fontSize: 15, color: '#0f172a', marginBottom: 4 }}>{s.ticker}</div>
                    <div style={{ fontSize: 22, fontWeight: 800, color, fontFamily: 'monospace' }}>{score}</div>
                    <div style={{ fontSize: 10, color: '#94a3b8', marginBottom: 6 }}>composite score</div>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                      {Object.entries(s.signal_breakdown || {}).map(([k, v]) => (
                        <span key={k} title={`${SIGNAL_LABELS[k] || k}: ${v}`}>
                          <SignalDot score={v} />
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Full table */}
        {data?.stocks?.length > 0 && (
          <div style={{
            background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 14,
            overflow: 'hidden',
          }}>
            <div style={{ padding: '14px 18px', borderBottom: '1px solid #f1f5f9', display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontWeight: 700, fontSize: 14, color: '#0f172a' }}>
                All Stocks ({data.total_scanned} scanned)
              </span>
              <span style={{ fontSize: 11, color: '#94a3b8' }}>Sorted by composite score</span>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#f8fafc' }}>
                    <th style={TH}>Ticker</th>
                    <th style={TH}>Composite</th>
                    {Object.keys(SIGNAL_LABELS).map(k => (
                      <th key={k} style={TH}>{SIGNAL_LABELS[k]}</th>
                    ))}
                    <th style={TH}>Delivery%</th>
                    <th style={TH}>Quality</th>
                  </tr>
                </thead>
                <tbody>
                  {data.stocks.map((s, i) => (
                    <tr key={s.ticker} style={{ borderBottom: '1px solid #f1f5f9', background: i % 2 === 0 ? '#fff' : '#fafafa' }}>
                      <td style={{ padding: '9px 14px', fontWeight: 700, fontSize: 13, color: '#0f172a' }}>{s.ticker}</td>
                      <td style={{ padding: '9px 14px' }}>
                        <ScoreBar score={s.composite_score} />
                      </td>
                      {Object.keys(SIGNAL_LABELS).map(k => (
                        <td key={k} style={{ padding: '9px 14px', textAlign: 'center' }}>
                          {s.signal_breakdown?.[k] != null
                            ? <SignalDot score={s.signal_breakdown[k]} />
                            : <span style={{ color: '#e2e8f0' }}>—</span>}
                        </td>
                      ))}
                      <td style={{ padding: '9px 14px', fontSize: 12, color: '#64748b', fontFamily: 'monospace' }}>
                        {s.delivery_pct != null ? `${s.delivery_pct.toFixed(1)}%` : '—'}
                      </td>
                      <td style={{ padding: '9px 14px' }}>
                        <span style={{
                          fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 4,
                          background: s.data_quality === 'high' ? '#d1fae5' : s.data_quality === 'medium' ? '#fef3c7' : '#fee2e2',
                          color: s.data_quality === 'high' ? '#065f46' : s.data_quality === 'medium' ? '#92400e' : '#991b1b',
                          textTransform: 'uppercase',
                        }}>{s.data_quality}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Legend + disclaimer */}
        <div style={{ marginTop: 20, display: 'flex', gap: 16, flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div style={{ display: 'flex', gap: 12, fontSize: 11, color: '#64748b', alignItems: 'center' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#10b981', display: 'inline-block' }} /> Bullish (≥65)
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#f59e0b', display: 'inline-block' }} /> Neutral (45–64)
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#ef4444', display: 'inline-block' }} /> Bearish (&lt;45)
            </span>
          </div>
          <p style={{ fontSize: 11, color: '#94a3b8', margin: 0, maxWidth: 480, textAlign: 'right' }}>
            {data?.disclaimer}
          </p>
        </div>
      </div>
    </div>
  );
}

const TH = {
  padding: '8px 14px', textAlign: 'left', fontSize: 10,
  fontWeight: 700, color: '#64748b', textTransform: 'uppercase',
  letterSpacing: '0.04em', whiteSpace: 'nowrap',
};
