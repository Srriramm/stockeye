import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bot, TrendingUp, TrendingDown, Minus, Eye,
  RefreshCw, Search, CheckCheck, X, ChevronRight,
  Clock, Cpu, Sparkles, AlertCircle, Info,
} from 'lucide-react';
import { authAxios } from '../utils/api';

const API_URL = process.env.REACT_APP_API_URL || '';

/* ─── Action config ─────────────────────────────────────────── */
const ACTION_CONFIG = {
  BUY: {
    label: 'BUY',
    icon: TrendingUp,
    bg: '#d1fae5',
    color: '#065f46',
    border: '#059669',
    dot: '#10b981',
  },
  SELL: {
    label: 'SELL',
    icon: TrendingDown,
    bg: '#fee2e2',
    color: '#991b1b',
    border: '#dc2626',
    dot: '#ef4444',
  },
  HOLD: {
    label: 'HOLD',
    icon: Minus,
    bg: '#fef9c3',
    color: '#713f12',
    border: '#ca8a04',
    dot: '#eab308',
  },
  WATCH: {
    label: 'WATCH',
    icon: Eye,
    bg: '#dbeafe',
    color: '#1e3a8a',
    border: '#3b82f6',
    dot: '#3b82f6',
  },
};

const FILTERS = ['All', 'BUY', 'SELL', 'HOLD', 'WATCH', 'Unread'];

/* ─── Confidence bar ─────────────────────────────────────────── */
function ConfidenceBar({ value }) {
  const pct = Math.round((value || 0) * 100);
  const color = pct >= 70 ? '#10b981' : pct >= 50 ? '#f59e0b' : '#ef4444';
  return (
    <div className="flex items-center gap-2">
      <div
        style={{
          flex: 1, height: 4, borderRadius: 4,
          background: '#e2e8f0', overflow: 'hidden',
        }}
      >
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 4, transition: 'width 0.6s ease' }} />
      </div>
      <span style={{ fontSize: 11, fontWeight: 700, color, fontFamily: 'monospace', minWidth: 30 }}>
        {pct}%
      </span>
    </div>
  );
}

/* ─── Model badge ─────────────────────────────────────────────── */
function ModelBadge({ model }) {
  const isHaiku = model?.includes('haiku');
  return (
    <span style={{
      fontSize: 10, fontWeight: 600,
      padding: '2px 7px', borderRadius: 6,
      background: isHaiku ? '#f0fdf4' : '#eff6ff',
      color: isHaiku ? '#15803d' : '#1d4ed8',
      border: `1px solid ${isHaiku ? '#bbf7d0' : '#bfdbfe'}`,
      display: 'inline-flex', alignItems: 'center', gap: 4,
    }}>
      <Cpu size={9} />
      {isHaiku ? 'Haiku' : 'Sonnet'}
    </span>
  );
}

/* ─── Session badge ───────────────────────────────────────────── */
function SessionBadge({ session }) {
  const labels = { morning: '☀ Morning', evening: '🌆 Evening', manual: '⚡ On-demand' };
  return (
    <span style={{
      fontSize: 10, fontWeight: 600,
      padding: '2px 7px', borderRadius: 6,
      background: '#f8fafc', color: '#64748b',
      border: '1px solid #e2e8f0',
    }}>
      {labels[session] || session}
    </span>
  );
}

/* ─── Recommendation Card ─────────────────────────────────────── */
function RecommendationCard({ rec, onRead, onDismiss }) {
  const navigate = useNavigate();
  const cfg = ACTION_CONFIG[rec.action] || ACTION_CONFIG.HOLD;
  const Icon = cfg.icon;

  const handleAnalyze = () => {
    if (!rec.is_read) onRead(rec.id);
    navigate(`/forecast?ticker=${rec.ticker}`);
  };

  const handleCardClick = () => {
    if (!rec.is_read) onRead(rec.id);
  };

  const factors = Array.isArray(rec.key_factors) ? rec.key_factors : [];
  const timeStr = rec.created_at
    ? new Date(rec.created_at).toLocaleString('en-IN', {
        day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
      })
    : '';

  return (
    <div
      onClick={handleCardClick}
      style={{
        background: rec.is_read ? '#ffffff' : '#f0f7ff',
        border: `1px solid ${rec.is_read ? '#e2e8f0' : '#bfdbfe'}`,
        borderLeft: `4px solid ${cfg.border}`,
        borderRadius: 14,
        padding: '16px 18px',
        cursor: 'default',
        transition: 'box-shadow 0.15s',
        position: 'relative',
      }}
      onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.07)'; }}
      onMouseLeave={e => { e.currentTarget.style.boxShadow = ''; }}
    >
      {/* Unread dot */}
      {!rec.is_read && (
        <div style={{
          position: 'absolute', top: 14, right: 14,
          width: 7, height: 7, borderRadius: '50%',
          background: cfg.dot,
        }} />
      )}

      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-3">
          {/* Action badge */}
          <div style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            padding: '4px 10px', borderRadius: 8,
            background: cfg.bg, color: cfg.color,
            fontWeight: 700, fontSize: 12, flexShrink: 0,
          }}>
            <Icon size={13} />
            {cfg.label}
          </div>

          {/* Ticker */}
          <span style={{ fontWeight: 800, fontSize: 16, color: '#0f172a', fontFamily: 'monospace' }}>
            {rec.ticker}
          </span>

          {/* Timeframe pill */}
          <span style={{
            fontSize: 10, fontWeight: 600,
            padding: '2px 8px', borderRadius: 6,
            background: '#f1f5f9', color: '#64748b',
          }}>
            {rec.timeframe === 'short' ? '<3m' : rec.timeframe === 'medium' ? '3–12m' : '>12m'}
          </span>
        </div>

        {/* Dismiss */}
        <button
          onClick={(e) => { e.stopPropagation(); onDismiss(rec.id); }}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: '#cbd5e1', padding: 2, lineHeight: 1, flexShrink: 0,
          }}
          onMouseEnter={e => { e.currentTarget.style.color = '#94a3b8'; }}
          onMouseLeave={e => { e.currentTarget.style.color = '#cbd5e1'; }}
          title="Dismiss"
        >
          <X size={14} />
        </button>
      </div>

      {/* Confidence */}
      <div className="mb-3">
        <div style={{ fontSize: 10, fontWeight: 600, color: '#94a3b8', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          Confidence
        </div>
        <ConfidenceBar value={rec.confidence} />
      </div>

      {/* Reasoning */}
      <p style={{ fontSize: 13, color: '#334155', lineHeight: 1.6, margin: '0 0 12px' }}>
        {rec.reasoning}
      </p>

      {/* Key factors */}
      {factors.length > 0 && (
        <div className="mb-3">
          {factors.map((f, i) => (
            <div key={i} className="flex items-start gap-1.5 mb-1">
              <span style={{ color: cfg.dot, fontWeight: 700, fontSize: 13, lineHeight: 1.4 }}>•</span>
              <span style={{ fontSize: 12, color: '#475569', lineHeight: 1.4 }}>{f}</span>
            </div>
          ))}
        </div>
      )}

      {/* Price targets */}
      {(rec.entry_price || rec.target_price || rec.stop_loss) && (
        <div className="flex items-center gap-4 mb-3 flex-wrap">
          {rec.entry_price && (
            <div>
              <div style={{ fontSize: 10, color: '#94a3b8', fontWeight: 600, marginBottom: 1 }}>ENTRY</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#0f172a', fontFamily: 'monospace' }}>
                ₹{rec.entry_price?.toLocaleString('en-IN')}
              </div>
            </div>
          )}
          {rec.target_price && (
            <div>
              <div style={{ fontSize: 10, color: '#94a3b8', fontWeight: 600, marginBottom: 1 }}>TARGET</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#10b981', fontFamily: 'monospace' }}>
                ₹{rec.target_price?.toLocaleString('en-IN')}
              </div>
            </div>
          )}
          {rec.stop_loss && (
            <div>
              <div style={{ fontSize: 10, color: '#94a3b8', fontWeight: 600, marginBottom: 1 }}>STOP LOSS</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#ef4444', fontFamily: 'monospace' }}>
                ₹{rec.stop_loss?.toLocaleString('en-IN')}
              </div>
            </div>
          )}
          {rec.risk_reward && (
            <div>
              <div style={{ fontSize: 10, color: '#94a3b8', fontWeight: 600, marginBottom: 1 }}>R:R</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#7c3aed', fontFamily: 'monospace' }}>
                {rec.risk_reward?.toFixed(1)}x
              </div>
            </div>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between mt-2">
        <div className="flex items-center gap-2">
          <ModelBadge model={rec.model_used} />
          <SessionBadge session={rec.session} />
          <span style={{ fontSize: 10, color: '#94a3b8', display: 'flex', alignItems: 'center', gap: 3 }}>
            <Clock size={9} /> {timeStr}
          </span>
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); handleAnalyze(); }}
          className="flex items-center gap-1 text-xs font-semibold transition-colors"
          style={{ color: '#2563eb', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
          onMouseEnter={e => { e.currentTarget.style.color = '#1d4ed8'; }}
          onMouseLeave={e => { e.currentTarget.style.color = '#2563eb'; }}
        >
          Analyze <ChevronRight size={12} />
        </button>
      </div>
    </div>
  );
}

/* ─── On-demand analyze input ─────────────────────────────────── */
function OnDemandAnalyze({ onResult }) {
  const [ticker, setTicker] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleAnalyze = async () => {
    if (!ticker.trim()) return;
    setLoading(true);
    setError('');
    try {
      const res = await authAxios.post(`${API_URL}/api/agent/analyze`, {
        ticker: ticker.trim().toUpperCase(),
      });
      onResult(res.data.recommendation);
      setTicker('');
    } catch (err) {
      const msg = err.response?.data?.error || 'Analysis failed. Try again.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      background: '#ffffff', border: '1px solid #e2e8f0',
      borderRadius: 14, padding: '16px 18px',
    }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: '#0f172a', marginBottom: 10 }}>
        On-Demand Analysis
      </div>
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
          <input
            type="text"
            value={ticker}
            onChange={e => setTicker(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleAnalyze()}
            placeholder="Enter ticker (e.g. RELIANCE)"
            style={{
              width: '100%', paddingLeft: 32, paddingRight: 12,
              paddingTop: 9, paddingBottom: 9,
              border: '1px solid #e2e8f0', borderRadius: 10,
              fontSize: 13, color: '#0f172a', outline: 'none',
              background: '#f8fafc', fontFamily: 'monospace',
              boxSizing: 'border-box',
            }}
            onFocus={e => { e.target.style.borderColor = '#3b82f6'; e.target.style.background = '#fff'; }}
            onBlur={e => { e.target.style.borderColor = '#e2e8f0'; e.target.style.background = '#f8fafc'; }}
          />
        </div>
        <button
          onClick={handleAnalyze}
          disabled={loading || !ticker.trim()}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '9px 16px', borderRadius: 10,
            border: 'none', cursor: loading || !ticker.trim() ? 'not-allowed' : 'pointer',
            background: loading || !ticker.trim() ? '#e2e8f0' : 'linear-gradient(135deg, #2563eb, #7c3aed)',
            color: loading || !ticker.trim() ? '#94a3b8' : '#ffffff',
            fontSize: 13, fontWeight: 600, flexShrink: 0,
            transition: 'opacity 0.15s',
          }}
        >
          {loading ? (
            <>
              <div style={{ width: 13, height: 13, border: '2px solid rgba(255,255,255,0.4)', borderTopColor: '#fff', borderRadius: '50%', animation: 'agent-spin 0.7s linear infinite' }} />
              Analyzing...
            </>
          ) : (
            <>
              <Sparkles size={13} />
              Analyze
            </>
          )}
        </button>
      </div>
      {error && (
        <div className="flex items-center gap-1.5 mt-2" style={{ color: '#dc2626', fontSize: 12 }}>
          <AlertCircle size={12} /> {error}
        </div>
      )}
      <p style={{ fontSize: 11, color: '#94a3b8', marginTop: 8 }}>
        Rate limited to 5 analyses per hour. Results cached for 4 hours per session.
      </p>
    </div>
  );
}

/* ─── Empty state ─────────────────────────────────────────────── */
function EmptyState({ filter }) {
  return (
    <div style={{
      textAlign: 'center', padding: '60px 24px',
      color: '#94a3b8',
    }}>
      <Bot size={40} style={{ margin: '0 auto 16px', color: '#cbd5e1' }} />
      <div style={{ fontWeight: 700, color: '#64748b', fontSize: 15, marginBottom: 6 }}>
        {filter === 'Unread' ? 'All caught up!' : `No ${filter === 'All' ? '' : filter + ' '}recommendations yet`}
      </div>
      <p style={{ fontSize: 13, lineHeight: 1.6 }}>
        {filter === 'Unread'
          ? 'No unread recommendations right now.'
          : 'Add stocks to your monitor list. The agent runs daily at 9 AM and 4 PM IST, or use on-demand analysis above.'}
      </p>
    </div>
  );
}

/* ─── Main page ───────────────────────────────────────────────── */
export default function AgentInsights({ apiUrl, liveInsights = [], onInsightRead }) {
  const [recs, setRecs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('All');
  const [refreshing, setRefreshing] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  const fetchRecs = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const res = await authAxios.get(`${API_URL}/api/agent/recommendations?limit=50`);
      setRecs(res.data.recommendations || []);
      setUnreadCount(res.data.unread_count || 0);
    } catch (err) {
      console.error('Failed to fetch recommendations:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchRecs();
  }, [fetchRecs]);

  // Merge live WebSocket-pushed recs into state
  useEffect(() => {
    if (liveInsights.length === 0) return;
    setRecs(prev => {
      const existingIds = new Set(prev.map(r => r.id));
      const newOnes = liveInsights.filter(r => !existingIds.has(r.id));
      return newOnes.length > 0 ? [...newOnes, ...prev] : prev;
    });
  }, [liveInsights]);

  const handleMarkRead = async (id) => {
    try {
      await authAxios.patch(`${API_URL}/api/agent/recommendations/${id}/read`);
      setRecs(prev => prev.map(r => r.id === id ? { ...r, is_read: true } : r));
      setUnreadCount(prev => Math.max(0, prev - 1));
      if (onInsightRead) onInsightRead();
    } catch (err) {
      console.error('Mark read failed:', err);
    }
  };

  const handleDismiss = async (id) => {
    try {
      await authAxios.patch(`${API_URL}/api/agent/recommendations/${id}/dismiss`);
      setRecs(prev => prev.filter(r => r.id !== id));
    } catch (err) {
      console.error('Dismiss failed:', err);
    }
  };

  const handleNewResult = (rec) => {
    setRecs(prev => [rec, ...prev]);
    setUnreadCount(prev => prev + 1);
  };

  const filtered = recs.filter(r => {
    if (filter === 'All') return true;
    if (filter === 'Unread') return !r.is_read;
    return r.action === filter;
  });

  const counts = {
    All: recs.length,
    BUY: recs.filter(r => r.action === 'BUY').length,
    SELL: recs.filter(r => r.action === 'SELL').length,
    HOLD: recs.filter(r => r.action === 'HOLD').length,
    WATCH: recs.filter(r => r.action === 'WATCH').length,
    Unread: unreadCount,
  };

  return (
    <div style={{ padding: '28px 32px', maxWidth: 900, margin: '0 auto' }}>
      <style>{`
        @keyframes agent-spin { to { transform: rotate(360deg); } }
      `}</style>

      {/* Page header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: 'linear-gradient(135deg, #2563eb, #7c3aed)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Bot size={18} color="#fff" />
            </div>
            <h1 style={{ fontSize: 22, fontWeight: 800, color: '#0f172a', margin: 0 }}>
              Agent Insights
            </h1>
            {unreadCount > 0 && (
              <span style={{
                fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 12,
                background: '#fee2e2', color: '#dc2626',
              }}>
                {unreadCount} new
              </span>
            )}
          </div>
          <p style={{ fontSize: 13, color: '#64748b', margin: 0 }}>
            Autonomous BUY / SELL / HOLD / WATCH recommendations — runs at 9 AM &amp; 4 PM IST
          </p>
        </div>
        <button
          onClick={() => fetchRecs(true)}
          disabled={refreshing}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '8px 14px', borderRadius: 10,
            border: '1px solid #e2e8f0', background: '#fff',
            color: '#64748b', fontSize: 13, fontWeight: 600,
            cursor: refreshing ? 'not-allowed' : 'pointer',
          }}
          onMouseEnter={e => { if (!refreshing) e.currentTarget.style.background = '#f8fafc'; }}
          onMouseLeave={e => { e.currentTarget.style.background = '#fff'; }}
        >
          <RefreshCw size={13} style={{ animation: refreshing ? 'agent-spin 0.7s linear infinite' : 'none' }} />
          Refresh
        </button>
      </div>

      {/* On-demand analyze */}
      <div className="mb-6">
        <OnDemandAnalyze onResult={handleNewResult} />
      </div>

      {/* Info banner */}
      <div className="flex items-start gap-2 mb-5 px-4 py-3 rounded-xl" style={{ background: '#eff6ff', border: '1px solid #bfdbfe' }}>
        <Info size={14} style={{ color: '#3b82f6', flexShrink: 0, marginTop: 1 }} />
        <p style={{ fontSize: 12, color: '#1e40af', margin: 0, lineHeight: 1.6 }}>
          The agent uses Claude with real-time tool calls (price, technicals, news, brain score) to produce structured recommendations.
          High-signal stocks (brain score &ge;65 or &le;35) are analyzed with Claude Sonnet for deeper reasoning.
          Results are cached for 4 hours per session. Not financial advice — always do your own research.
        </p>
      </div>

      {/* Filter tabs */}
      <div className="flex items-center gap-2 mb-5 flex-wrap">
        {FILTERS.map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              padding: '6px 14px', borderRadius: 20,
              border: `1px solid ${filter === f ? (ACTION_CONFIG[f]?.border || '#2563eb') : '#e2e8f0'}`,
              background: filter === f ? (ACTION_CONFIG[f]?.bg || '#eff6ff') : '#fff',
              color: filter === f ? (ACTION_CONFIG[f]?.color || '#1d4ed8') : '#64748b',
              fontSize: 12, fontWeight: 600,
              cursor: 'pointer', transition: 'all 0.15s',
              display: 'flex', alignItems: 'center', gap: 5,
            }}
          >
            {f}
            {counts[f] > 0 && (
              <span style={{
                fontSize: 10, fontWeight: 700,
                background: filter === f ? 'rgba(0,0,0,0.12)' : '#f1f5f9',
                color: filter === f ? 'inherit' : '#64748b',
                padding: '0px 5px', borderRadius: 8,
              }}>
                {counts[f]}
              </span>
            )}
          </button>
        ))}
        {unreadCount > 0 && (
          <button
            onClick={async () => {
              const unread = recs.filter(r => !r.is_read);
              await Promise.all(unread.map(r => authAxios.patch(`${API_URL}/api/agent/recommendations/${r.id}/read`)));
              setRecs(prev => prev.map(r => ({ ...r, is_read: true })));
              setUnreadCount(0);
              if (onInsightRead) onInsightRead();
            }}
            style={{
              marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5,
              padding: '6px 12px', borderRadius: 20,
              border: '1px solid #e2e8f0', background: '#fff',
              color: '#64748b', fontSize: 12, fontWeight: 600, cursor: 'pointer',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = '#f8fafc'; }}
            onMouseLeave={e => { e.currentTarget.style.background = '#fff'; }}
          >
            <CheckCheck size={12} /> Mark all read
          </button>
        )}
      </div>

      {/* Content */}
      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '60px 0' }}>
          <div style={{ width: 28, height: 28, border: '3px solid #e2e8f0', borderTopColor: '#2563eb', borderRadius: '50%', animation: 'agent-spin 0.8s linear infinite' }} />
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState filter={filter} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {filtered.map(rec => (
            <RecommendationCard
              key={rec.id}
              rec={rec}
              onRead={handleMarkRead}
              onDismiss={handleDismiss}
            />
          ))}
        </div>
      )}
    </div>
  );
}
