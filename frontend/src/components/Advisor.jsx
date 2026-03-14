import React, { useState, useEffect, useCallback } from 'react';
import { authAxios } from '../utils/api';
import { useNavigate } from 'react-router-dom';
import {
    TrendingUp, TrendingDown, Zap, Play, RefreshCw,
    Bot, Shield, DollarSign, Target, AlertTriangle,
    CheckCircle, Clock, Activity, ChevronRight, Layers,
    BarChart2, X, Flame
} from 'lucide-react';

const API_URL = import.meta.env.VITE_API_URL || '';
const fmt  = (n) => n != null ? `₹${Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : '—';
const pct  = (n) => n != null ? `${Number(n) >= 0 ? '+' : ''}${Number(n).toFixed(2)}%` : '—';
const conf = (n) => n != null ? `${Math.round(Number(n) * 100)}%` : '—';

const ACTION_CFG = {
    BUY:   { bg: '#f0fdf4', border: '#86efac', text: '#15803d', dot: '#22c55e', label: 'BUY' },
    SELL:  { bg: '#fef2f2', border: '#fca5a5', text: '#b91c1c', dot: '#ef4444', label: 'SELL' },
    HOLD:  { bg: '#fffbeb', border: '#fcd34d', text: '#92400e', dot: '#f59e0b', label: 'HOLD' },
    WATCH: { bg: '#eff6ff', border: '#93c5fd', text: '#1d4ed8', dot: '#3b82f6', label: 'WATCH' },
};

// ── Greeting ───────────────────────────────────────────────────────────────
function greeting() {
    const h = new Date().getHours();
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
}

// ── Action Card (BUY/SELL/HOLD/WATCH recommendation) ──────────────────────
function ActionCard({ rec, onDismiss, onAnalyze }) {
    const cfg = ACTION_CFG[rec.action] || ACTION_CFG.HOLD;
    const factors = Array.isArray(rec.key_factors) ? rec.key_factors : [];

    return (
        <div
            style={{
                background: cfg.bg,
                border: `1.5px solid ${cfg.border}`,
                borderRadius: 16,
                padding: '16px 18px',
                display: 'flex',
                flexDirection: 'column',
                gap: 10,
                position: 'relative',
            }}
        >
            {/* dismiss */}
            <button
                onClick={() => onDismiss(rec.id)}
                style={{ position: 'absolute', top: 10, right: 10, color: '#94a3b8', background: 'none', border: 'none', cursor: 'pointer', padding: 2 }}
            >
                <X size={13} />
            </button>

            {/* Header row */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span
                    style={{
                        fontSize: 11, fontWeight: 800, padding: '3px 10px', borderRadius: 7,
                        background: cfg.dot, color: '#fff', letterSpacing: '0.05em',
                    }}
                >
                    {cfg.label}
                </span>
                <span style={{ fontSize: 16, fontWeight: 800, color: '#0f172a', fontFamily: 'monospace' }}>
                    {rec.ticker}
                </span>
                <span style={{ fontSize: 10, color: '#94a3b8', marginLeft: 'auto', paddingRight: 20 }}>
                    {rec.timeframe || 'short'}-term · {conf(rec.confidence)} confidence
                </span>
            </div>

            {/* Price targets grid */}
            {(rec.entry_price || rec.target_price || rec.stop_loss) && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                    {rec.entry_price && (
                        <div style={{ background: 'rgba(255,255,255,0.7)', borderRadius: 8, padding: '8px 10px', textAlign: 'center' }}>
                            <div style={{ fontSize: 9, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 3 }}>
                                Entry
                            </div>
                            <div style={{ fontSize: 14, fontWeight: 800, color: '#0f172a', fontFamily: 'monospace' }}>
                                {fmt(rec.entry_price)}
                            </div>
                        </div>
                    )}
                    {rec.target_price && (
                        <div style={{ background: 'rgba(255,255,255,0.7)', borderRadius: 8, padding: '8px 10px', textAlign: 'center' }}>
                            <div style={{ fontSize: 9, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 3 }}>
                                Target
                            </div>
                            <div style={{ fontSize: 14, fontWeight: 800, color: '#15803d', fontFamily: 'monospace' }}>
                                {fmt(rec.target_price)}
                            </div>
                        </div>
                    )}
                    {rec.stop_loss && (
                        <div style={{ background: 'rgba(255,255,255,0.7)', borderRadius: 8, padding: '8px 10px', textAlign: 'center' }}>
                            <div style={{ fontSize: 9, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 3 }}>
                                Stop Loss
                            </div>
                            <div style={{ fontSize: 14, fontWeight: 800, color: '#b91c1c', fontFamily: 'monospace' }}>
                                {fmt(rec.stop_loss)}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* R/R ratio */}
            {rec.risk_reward && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <Shield size={11} style={{ color: '#64748b' }} />
                    <span style={{ fontSize: 11, color: '#64748b' }}>
                        Risk/Reward: <strong style={{ color: '#0f172a' }}>{Number(rec.risk_reward).toFixed(1)}×</strong>
                    </span>
                </div>
            )}

            {/* Reasoning */}
            {rec.reasoning && (
                <p style={{ fontSize: 12, color: '#475569', lineHeight: 1.55, margin: 0 }}>
                    {rec.reasoning}
                </p>
            )}

            {/* Key factors */}
            {factors.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                    {factors.slice(0, 4).map((f, i) => (
                        <span key={i} style={{
                            fontSize: 10, fontWeight: 600, padding: '2px 8px', borderRadius: 5,
                            background: 'rgba(255,255,255,0.8)', color: '#475569', border: '1px solid #e2e8f0',
                        }}>
                            {f}
                        </span>
                    ))}
                </div>
            )}

            {/* Analyse button */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 2 }}>
                <span style={{ fontSize: 10, color: '#94a3b8' }}>
                    {rec.created_at ? new Date(rec.created_at).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : ''}
                </span>
                <button
                    onClick={() => onAnalyze(rec.ticker)}
                    style={{
                        fontSize: 11, fontWeight: 700, color: cfg.text,
                        background: 'rgba(255,255,255,0.8)', border: `1px solid ${cfg.border}`,
                        borderRadius: 7, padding: '4px 12px', cursor: 'pointer',
                        display: 'flex', alignItems: 'center', gap: 4,
                    }}
                >
                    Deep Analysis <ChevronRight size={11} />
                </button>
            </div>
        </div>
    );
}

// ── Opportunity mini-card ─────────────────────────────────────────────────
const OPP_TYPE = {
    ETF_NAV_DIVERGENCE: { label: 'ETF Arb',   color: '#1d4ed8', bg: '#eff6ff' },
    PAIRS_DIVERGENCE:   { label: 'Pairs',      color: '#6d28d9', bg: '#f5f3ff' },
    BOLLINGER_EXTREME:  { label: 'Mean Rev',   color: '#92400e', bg: '#fefce8' },
};

function OppCard({ opp, onAnalyze }) {
    const cfg = OPP_TYPE[opp.type] || OPP_TYPE.BOLLINGER_EXTREME;
    const isBuy = (opp.recommended_action || '').toUpperCase().startsWith('BUY');
    return (
        <div
            style={{
                background: '#fff', border: '1px solid #e2e8f0', borderRadius: 12, padding: '12px 14px',
                display: 'flex', flexDirection: 'column', gap: 6,
            }}
        >
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontSize: 10, fontWeight: 700, padding: '2px 7px', borderRadius: 5, background: cfg.bg, color: cfg.color }}>
                    {cfg.label}
                </span>
                <span style={{ fontSize: 13, fontWeight: 800, fontFamily: 'monospace', color: '#0f172a' }}>{opp.ticker}</span>
                <span style={{
                    marginLeft: 'auto', fontSize: 11, fontWeight: 700,
                    color: isBuy ? '#15803d' : '#b91c1c',
                }}>
                    {isBuy ? <TrendingUp size={12} style={{ display: 'inline' }} /> : <TrendingDown size={12} style={{ display: 'inline' }} />}
                    {' '}{opp.expected_profit_pct != null ? `+${Number(opp.expected_profit_pct).toFixed(2)}%` : ''}
                </span>
            </div>
            <p style={{ fontSize: 11, color: '#64748b', margin: 0, lineHeight: 1.5 }}>{opp.reasoning}</p>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: 10, fontFamily: 'monospace', color: '#8b5cf6', fontWeight: 700 }}>
                    {opp.z_score != null ? `z=${opp.z_score}σ` : opp.premium_pct != null ? `${opp.premium_pct > 0 ? '+' : ''}${opp.premium_pct}%` : ''}
                </span>
                <span style={{
                    fontSize: 10, fontWeight: 700, color: isBuy ? '#15803d' : '#b91c1c',
                    background: isBuy ? '#f0fdf4' : '#fef2f2',
                    border: `1px solid ${isBuy ? '#86efac' : '#fca5a5'}`,
                    borderRadius: 5, padding: '2px 8px',
                }}>
                    {opp.recommended_action}
                </span>
            </div>
        </div>
    );
}

// ── Portfolio stat ────────────────────────────────────────────────────────
function PortfolioStat({ label, value, color = '#0f172a', sub }) {
    return (
        <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>{label}</div>
            <div style={{ fontSize: 20, fontWeight: 800, fontFamily: 'monospace', color }}>{value}</div>
            {sub && <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 2 }}>{sub}</div>}
        </div>
    );
}

// ── Main Advisor component ─────────────────────────────────────────────────
export default function Advisor({ indices: globalIndices, liveInsights, onInsightRead }) {
    const navigate = useNavigate();
    const [brief, setBrief]           = useState(null);
    const [loading, setLoading]       = useState(true);
    const [opps, setOpps]             = useState([]);
    const [oppLoading, setOppLoading] = useState(false);
    const [session, setSession]       = useState(null);
    const [running, setRunning]       = useState(false);
    const [error, setError]           = useState('');
    const [budget, setBudget]         = useState('');
    const [addFundsAmt, setAddFundsAmt] = useState('');
    const [addFundsOpen, setAddFundsOpen] = useState(false);
    const [addFundsLoading, setAddFundsLoading] = useState(false);
    const [perfHistory, setPerfHistory] = useState([]);
    const [showReturns, setShowReturns] = useState(false);
    const [resetConfirm, setResetConfirm] = useState(false);
    const [resetting, setResetting] = useState(false);

    const fetchBrief = useCallback(async () => {
        setLoading(true);
        try {
            const res = await authAxios.get(`${API_URL}/api/advisor/brief`);
            setBrief(res.data);
        } catch (e) {
            setError(e.response?.data?.error || e.message);
        } finally {
            setLoading(false);
        }
    }, []);

    const scanOpps = useCallback(async () => {
        setOppLoading(true);
        try {
            const res = await authAxios.post(`${API_URL}/api/advisor/scan`, {});
            setOpps(res.data.opportunities || []);
        } catch { /* silent */ } finally {
            setOppLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchBrief();
        scanOpps();
        authAxios.get(`${API_URL}/api/auto-trading/performance?days=14`)
            .then(r => setPerfHistory(r.data.history || []))
            .catch(() => {});
    }, [fetchBrief, scanOpps]);

    // Merge live WebSocket insights
    useEffect(() => {
        if (liveInsights?.length > 0) {
            setBrief(prev => {
                if (!prev) return prev;
                const existingIds = new Set((prev.recommendations || []).map(r => r.id));
                const fresh = liveInsights.filter(r => !existingIds.has(r.id));
                return { ...prev, recommendations: [...fresh, ...(prev.recommendations || [])] };
            });
        }
    }, [liveInsights]);

    const runSession = async () => {
        setRunning(true);
        setError('');
        try {
            const body = { tickers: brief?.scan_tickers || brief?.watchlist_tickers || [] };
            if (budget && !isNaN(parseFloat(budget)) && parseFloat(budget) > 0) {
                body.budget = parseFloat(budget);
            }
            const res = await authAxios.post(`${API_URL}/api/auto-trading/run`, body, { timeout: 180000 });
            setSession(res.data);
            fetchBrief();
            scanOpps();
            authAxios.get(`${API_URL}/api/auto-trading/performance?days=14`)
                .then(r => setPerfHistory(r.data.history || []))
                .catch(() => {});
        } catch (e) {
            setError('Agent session failed: ' + (e.response?.data?.error || e.message));
        } finally {
            setRunning(false);
        }
    };

    const handleAddFunds = async () => {
        const amount = parseFloat(addFundsAmt);
        if (!amount || amount <= 0) return;
        setAddFundsLoading(true);
        try {
            await authAxios.post(`${API_URL}/api/auto-trading/wallet/add`, { amount });
            setAddFundsAmt('');
            setAddFundsOpen(false);
            fetchBrief();
        } catch (e) {
            setError(e.response?.data?.error || 'Failed to add funds');
        } finally {
            setAddFundsLoading(false);
        }
    };

    const handleReset = async () => {
        setResetting(true);
        try {
            await authAxios.post(`${API_URL}/api/trading/reset`);
            setResetConfirm(false);
            setSession(null);
            setPerfHistory([]);
            fetchBrief();
        } catch (e) {
            setError(e.response?.data?.error || 'Reset failed');
        } finally {
            setResetting(false);
        }
    };

    const dismissRec = async (id) => {
        try {
            await authAxios.patch(`${API_URL}/api/agent/recommendations/${id}/dismiss`);
        } catch { /* silent */ }
        setBrief(prev => prev ? {
            ...prev,
            recommendations: prev.recommendations.filter(r => r.id !== id),
        } : prev);
    };

    const analyzeStock = (ticker) => navigate(`/forecast?ticker=${ticker}`);

    const recs         = brief?.recommendations || [];
    const buys         = recs.filter(r => r.action === 'BUY');
    const sells        = recs.filter(r => r.action === 'SELL');
    const watches      = recs.filter(r => r.action === 'WATCH' || r.action === 'HOLD');
    const portfolio    = brief?.portfolio || {};
    const pnlColor     = (portfolio.unrealised_pnl || 0) >= 0 ? '#15803d' : '#b91c1c';

    const indices = globalIndices || brief?.indices || {};

    return (
        <div style={{ padding: '24px 28px', maxWidth: 1200, margin: '0 auto', fontFamily: 'inherit' }}>

            {/* ── Header ── */}
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
                <div>
                    <h1 style={{ fontSize: 22, fontWeight: 800, color: '#0f172a', margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Bot size={22} style={{ color: '#4f46e5' }} />
                        {greeting()}, here's your briefing
                    </h1>
                    <p style={{ fontSize: 13, color: '#64748b', margin: '4px 0 0', lineHeight: 1.5 }}>
                        Your autonomous AI broker — scanning{' '}
                        <strong style={{ color: '#4f46e5' }}>
                            {brief?.scan_tickers?.length
                                ? `${brief.scan_tickers.length} stocks`
                                : 'your watchlist + live market movers'}
                        </strong>
                        {' '}· entry prices, targets &amp; stop-losses from live technical analysis.
                    </p>
                </div>
                <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                    <button
                        onClick={() => { fetchBrief(); scanOpps(); }}
                        disabled={loading}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px',
                            borderRadius: 10, border: '1px solid #e2e8f0', background: '#fff',
                            color: '#64748b', fontSize: 12, fontWeight: 600, cursor: loading ? 'not-allowed' : 'pointer',
                        }}
                    >
                        <RefreshCw size={12} style={{ animation: loading ? 'spin 0.8s linear infinite' : 'none' }} />
                        Refresh
                    </button>
                    {/* Budget input */}
                    <div style={{ display: 'flex', alignItems: 'center', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 10, overflow: 'hidden' }}>
                        <span style={{ fontSize: 13, color: '#64748b', padding: '0 8px 0 12px', fontWeight: 600 }}>₹</span>
                        <input
                            type="number"
                            placeholder="Budget (optional)"
                            value={budget}
                            onChange={e => setBudget(e.target.value)}
                            style={{ border: 'none', background: 'transparent', fontSize: 13, color: '#0f172a', width: 140, padding: '8px 12px 8px 0', outline: 'none' }}
                        />
                    </div>
                    <button
                        onClick={runSession}
                        disabled={running}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 8, padding: '9px 18px',
                            borderRadius: 12, border: 'none', cursor: running ? 'not-allowed' : 'pointer',
                            background: running ? '#94a3b8' : 'linear-gradient(135deg,#4f46e5,#7c3aed)',
                            color: '#fff', fontSize: 13, fontWeight: 700,
                        }}
                    >
                        {running ? (
                            <>
                                <div style={{ width: 14, height: 14, borderRadius: '50%', border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', animation: 'spin 0.7s linear infinite' }} />
                                Agent Running…
                            </>
                        ) : (
                            <><Zap size={14} /> Run Autonomous Session</>
                        )}
                    </button>
                </div>
            </div>

            <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>

            {/* ── Error banner ── */}
            {error && (
                <div style={{ padding: '10px 14px', borderRadius: 10, background: '#fef2f2', border: '1px solid #fca5a5', color: '#b91c1c', fontSize: 13, display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
                    <AlertTriangle size={14} /> {error}
                    <button onClick={() => setError('')} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#fca5a5', cursor: 'pointer' }}>✕</button>
                </div>
            )}

            {/* ── Portfolio Snapshot ── */}
            <div style={{ background: 'linear-gradient(135deg,#1e1b4b,#312e81)', borderRadius: 18, padding: '20px 28px', marginBottom: 24, display: 'flex', alignItems: 'center', gap: 32, flexWrap: 'wrap' }}>
                <div style={{ flex: 1, minWidth: 180 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 6 }}>Paper Portfolio Value</div>
                    <div style={{ fontSize: 28, fontWeight: 900, fontFamily: 'monospace', color: '#fff' }}>
                        {loading ? '—' : fmt(portfolio.portfolio_value)}
                    </div>
                    {portfolio.unrealised_pnl != null && (
                        <div style={{ fontSize: 13, fontWeight: 700, color: (portfolio.unrealised_pnl || 0) >= 0 ? '#4ade80' : '#f87171', marginTop: 4 }}>
                            {pct((portfolio.unrealised_pnl / Math.max(portfolio.invested || 1, 1)) * 100)} unrealised P&L
                        </div>
                    )}
                </div>
                <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap', alignItems: 'flex-start' }}>
                    {/* Cash Balance with Add Funds */}
                    <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: 11, fontWeight: 700, color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>Cash Balance</div>
                        <div style={{ fontSize: 20, fontWeight: 800, fontFamily: 'monospace', color: '#fff' }}>{loading ? '—' : fmt(portfolio.balance)}</div>
                        {addFundsOpen ? (
                            <div style={{ display: 'flex', gap: 4, marginTop: 6, justifyContent: 'center' }}>
                                <input
                                    type="number"
                                    placeholder="Amount"
                                    value={addFundsAmt}
                                    onChange={e => setAddFundsAmt(e.target.value)}
                                    onKeyDown={e => { if (e.key === 'Enter') handleAddFunds(); if (e.key === 'Escape') setAddFundsOpen(false); }}
                                    autoFocus
                                    style={{ width: 90, fontSize: 11, padding: '4px 7px', borderRadius: 6, border: '1px solid rgba(255,255,255,0.3)', background: 'rgba(255,255,255,0.1)', color: '#fff', outline: 'none' }}
                                />
                                <button onClick={handleAddFunds} disabled={addFundsLoading} style={{ fontSize: 11, fontWeight: 700, padding: '4px 8px', borderRadius: 6, border: 'none', background: '#4ade80', color: '#14532d', cursor: 'pointer' }}>
                                    {addFundsLoading ? '…' : 'Add'}
                                </button>
                                <button onClick={() => setAddFundsOpen(false)} style={{ fontSize: 11, padding: '4px 6px', borderRadius: 6, border: 'none', background: 'rgba(255,255,255,0.1)', color: '#fff', cursor: 'pointer' }}>✕</button>
                            </div>
                        ) : (
                            <button onClick={() => setAddFundsOpen(true)} style={{ fontSize: 10, fontWeight: 700, marginTop: 5, padding: '3px 10px', borderRadius: 6, border: '1px solid rgba(255,255,255,0.2)', background: 'rgba(255,255,255,0.08)', color: 'rgba(255,255,255,0.7)', cursor: 'pointer' }}>
                                + Add Funds
                            </button>
                        )}
                    </div>
                    <PortfolioStat label="Invested" value={loading ? '—' : fmt(portfolio.invested)} color="#c7d2fe" />
                    <PortfolioStat label="Positions" value={loading ? '—' : portfolio.holdings_count || 0} color="#a5b4fc" sub="open holdings" />
                    <PortfolioStat label="P&L" value={loading ? '—' : fmt(portfolio.unrealised_pnl)} color={(portfolio.unrealised_pnl || 0) >= 0 ? '#4ade80' : '#f87171'} />
                </div>
                {/* Holdings */}
                {(portfolio.holdings || []).length > 0 && (
                    <div style={{ width: '100%', display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 8, paddingTop: 12, borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                        {(portfolio.holdings || []).map(h => (
                            <div key={h.ticker} style={{ background: 'rgba(255,255,255,0.08)', borderRadius: 8, padding: '6px 12px', display: 'flex', gap: 10, alignItems: 'center' }}>
                                <span style={{ fontSize: 12, fontWeight: 700, color: '#e0e7ff', fontFamily: 'monospace' }}>{h.ticker}</span>
                                <span style={{ fontSize: 11, color: '#a5b4fc' }}>{h.quantity} × {fmt(h.current_price)}</span>
                                <span style={{ fontSize: 11, fontWeight: 700, color: (h.unrealised_pnl || 0) >= 0 ? '#4ade80' : '#f87171' }}>
                                    {pct(h.pnl_pct)}
                                </span>
                            </div>
                        ))}
                    </div>
                )}
                {/* Reset */}
                <div style={{ width: '100%', display: 'flex', justifyContent: 'flex-end', marginTop: 10 }}>
                    {resetConfirm ? (
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.6)' }}>Reset account? All trades &amp; history will be erased. Balance set to ₹0.</span>
                            <button onClick={handleReset} disabled={resetting} style={{ fontSize: 11, fontWeight: 700, padding: '4px 12px', borderRadius: 6, border: 'none', background: '#ef4444', color: '#fff', cursor: 'pointer' }}>
                                {resetting ? 'Resetting…' : 'Yes, Reset'}
                            </button>
                            <button onClick={() => setResetConfirm(false)} style={{ fontSize: 11, padding: '4px 10px', borderRadius: 6, border: '1px solid rgba(255,255,255,0.2)', background: 'transparent', color: 'rgba(255,255,255,0.6)', cursor: 'pointer' }}>
                                Cancel
                            </button>
                        </div>
                    ) : (
                        <button onClick={() => setResetConfirm(true)} style={{ fontSize: 10, fontWeight: 600, padding: '3px 12px', borderRadius: 6, border: '1px solid rgba(239,68,68,0.3)', background: 'rgba(239,68,68,0.1)', color: 'rgba(239,68,68,0.8)', cursor: 'pointer' }}>
                            Reset Account
                        </button>
                    )}
                </div>
            </div>

            {/* ── Daily Returns ── */}
            <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 14, marginBottom: 24, overflow: 'hidden' }}>
                <button
                    onClick={() => setShowReturns(v => !v)}
                    style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 18px', background: 'none', border: 'none', cursor: 'pointer' }}
                >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                        <Activity size={14} style={{ color: '#4f46e5' }} />
                        <span style={{ fontSize: 13, fontWeight: 700, color: '#0f172a' }}>Daily Returns History</span>
                        {perfHistory.length > 0 && (
                            <span style={{ fontSize: 11, fontWeight: 600, color: '#64748b', background: '#f1f5f9', borderRadius: 5, padding: '2px 8px' }}>
                                {perfHistory.length} days
                            </span>
                        )}
                    </div>
                    <span style={{ fontSize: 12, color: '#94a3b8' }}>{showReturns ? '▲' : '▼'}</span>
                </button>
                {showReturns && (
                    <div style={{ padding: '0 18px 14px' }}>
                        {perfHistory.length === 0 ? (
                            <p style={{ fontSize: 12, color: '#94a3b8', margin: 0 }}>No trading history yet — run a session to start tracking.</p>
                        ) : (
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                                <thead>
                                    <tr style={{ borderBottom: '1px solid #e2e8f0' }}>
                                        {['Date', 'Portfolio Value', 'Cash', 'Invested', 'Daily P&L', '%'].map(h => (
                                            <th key={h} style={{ textAlign: 'left', padding: '6px 8px', fontSize: 10, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {perfHistory.map((row, i) => {
                                        const isPos = (row.pnl || 0) >= 0;
                                        return (
                                            <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                                <td style={{ padding: '7px 8px', fontFamily: 'monospace', color: '#475569' }}>{row.date}</td>
                                                <td style={{ padding: '7px 8px', fontFamily: 'monospace', fontWeight: 700, color: '#0f172a' }}>{fmt(row.portfolio_value)}</td>
                                                <td style={{ padding: '7px 8px', fontFamily: 'monospace', color: '#64748b' }}>{fmt(row.cash_balance)}</td>
                                                <td style={{ padding: '7px 8px', fontFamily: 'monospace', color: '#64748b' }}>{fmt(row.invested)}</td>
                                                <td style={{ padding: '7px 8px', fontFamily: 'monospace', fontWeight: 700, color: isPos ? '#15803d' : '#b91c1c' }}>
                                                    {isPos ? '+' : ''}{fmt(row.pnl)}
                                                </td>
                                                <td style={{ padding: '7px 8px', fontWeight: 700, color: isPos ? '#15803d' : '#b91c1c' }}>
                                                    {isPos ? '+' : ''}{Number(row.pnl_pct || 0).toFixed(2)}%
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        )}
                    </div>
                )}
            </div>

            {/* ── Main grid: picks + opps ── */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 24, alignItems: 'start' }}>

                {/* LEFT: Picks */}
                <div>
                    {/* BUY signals */}
                    {buys.length > 0 && (
                        <section style={{ marginBottom: 24 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
                                <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#22c55e' }} />
                                <h2 style={{ fontSize: 12, fontWeight: 800, color: '#15803d', textTransform: 'uppercase', letterSpacing: '0.08em', margin: 0 }}>
                                    Buy Opportunities ({buys.length})
                                </h2>
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                                {buys.map(r => <ActionCard key={r.id} rec={r} onDismiss={dismissRec} onAnalyze={analyzeStock} />)}
                            </div>
                        </section>
                    )}

                    {/* SELL signals */}
                    {sells.length > 0 && (
                        <section style={{ marginBottom: 24 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
                                <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#ef4444' }} />
                                <h2 style={{ fontSize: 12, fontWeight: 800, color: '#b91c1c', textTransform: 'uppercase', letterSpacing: '0.08em', margin: 0 }}>
                                    Exit Signals ({sells.length})
                                </h2>
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                                {sells.map(r => <ActionCard key={r.id} rec={r} onDismiss={dismissRec} onAnalyze={analyzeStock} />)}
                            </div>
                        </section>
                    )}

                    {/* WATCH/HOLD */}
                    {watches.length > 0 && (
                        <section style={{ marginBottom: 24 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
                                <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#3b82f6' }} />
                                <h2 style={{ fontSize: 12, fontWeight: 800, color: '#1d4ed8', textTransform: 'uppercase', letterSpacing: '0.08em', margin: 0 }}>
                                    Watch / Hold ({watches.length})
                                </h2>
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                                {watches.map(r => <ActionCard key={r.id} rec={r} onDismiss={dismissRec} onAnalyze={analyzeStock} />)}
                            </div>
                        </section>
                    )}

                    {/* Empty state */}
                    {!loading && recs.length === 0 && (
                        <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 16, padding: '40px 24px', textAlign: 'center' }}>
                            <Bot size={32} style={{ color: '#e2e8f0', margin: '0 auto 12px' }} />
                            <p style={{ fontSize: 14, fontWeight: 600, color: '#64748b', margin: '0 0 6px' }}>No picks yet</p>
                            <p style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.6, margin: 0 }}>
                                Add stocks to your <strong>Watchlist</strong>, then click <strong>Run Autonomous Session</strong>.<br />
                                The AI agent will scan them and generate buy/sell signals with price targets.
                            </p>
                            <div style={{ display: 'flex', gap: 10, justifyContent: 'center', marginTop: 16 }}>
                                <button
                                    onClick={() => navigate('/watchlist')}
                                    style={{ fontSize: 12, fontWeight: 700, padding: '8px 18px', borderRadius: 9, border: '1px solid #e2e8f0', background: '#f8fafc', color: '#475569', cursor: 'pointer' }}
                                >
                                    Go to Watchlist
                                </button>
                                <button
                                    onClick={runSession}
                                    disabled={running}
                                    style={{ fontSize: 12, fontWeight: 700, padding: '8px 18px', borderRadius: 9, border: 'none', background: 'linear-gradient(135deg,#4f46e5,#7c3aed)', color: '#fff', cursor: 'pointer' }}
                                >
                                    Run Session Now
                                </button>
                            </div>
                        </div>
                    )}

                    {/* Agent session result */}
                    {session && (
                        <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 16, padding: '18px 20px', marginTop: 8 }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                                <CheckCircle size={14} style={{ color: '#22c55e' }} />
                                <span style={{ fontSize: 12, fontWeight: 700, color: '#0f172a' }}>Last Agent Session</span>
                                <span style={{ marginLeft: 'auto', fontSize: 10, fontWeight: 700, color: '#22c55e', background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 5, padding: '2px 8px' }}>
                                    DONE
                                </span>
                            </div>
                            {session.reasoning && (
                                <p style={{ fontSize: 12, color: '#64748b', lineHeight: 1.6, margin: '0 0 8px' }}>{session.reasoning}</p>
                            )}
                            <div style={{ display: 'flex', gap: 16, fontSize: 12 }}>
                                <span><strong>{session.trades_executed ?? 0}</strong> <span style={{ color: '#94a3b8' }}>trades</span></span>
                                <span><strong>{session.opportunities_found ?? 0}</strong> <span style={{ color: '#94a3b8' }}>opps found</span></span>
                                <span style={{ color: '#94a3b8' }}>{session.model_used?.includes('haiku') ? 'Haiku' : 'Sonnet'}</span>
                            </div>
                        </div>
                    )}
                </div>

                {/* RIGHT: Opportunities + Risk info */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

                    {/* Opportunities panel */}
                    <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 16, padding: '16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12 }}>
                            <Activity size={13} style={{ color: '#8b5cf6' }} />
                            <span style={{ fontSize: 11, fontWeight: 800, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
                                Live Opportunities
                            </span>
                            {oppLoading && (
                                <div style={{ width: 10, height: 10, borderRadius: '50%', border: '2px solid #e2e8f0', borderTopColor: '#8b5cf6', animation: 'spin 0.7s linear infinite', marginLeft: 4 }} />
                            )}
                            <button
                                onClick={scanOpps}
                                disabled={oppLoading}
                                style={{ marginLeft: 'auto', background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: 2 }}
                            >
                                <RefreshCw size={11} />
                            </button>
                        </div>

                        {!oppLoading && opps.length === 0 && (
                            <div style={{ padding: '16px 0', textAlign: 'center' }}>
                                <BarChart2 size={24} style={{ color: '#e2e8f0', margin: '0 auto 8px' }} />
                                <p style={{ fontSize: 12, color: '#94a3b8', margin: 0 }}>No opportunities detected</p>
                                <p style={{ fontSize: 11, color: '#cbd5e1', margin: '4px 0 0' }}>Add stocks to your watchlist</p>
                            </div>
                        )}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                            {opps.slice(0, 5).map((opp, i) => (
                                <OppCard key={i} opp={opp} onAnalyze={analyzeStock} />
                            ))}
                        </div>
                        {opps.length > 5 && (
                            <button
                                onClick={() => navigate('/auto-trading')}
                                style={{ width: '100%', marginTop: 8, fontSize: 11, fontWeight: 700, color: '#4f46e5', background: '#eff6ff', border: '1px solid #c7d2fe', borderRadius: 8, padding: '7px', cursor: 'pointer' }}
                            >
                                View all {opps.length} opportunities →
                            </button>
                        )}
                    </div>

                    {/* Risk Guardrails */}
                    <div style={{ background: '#fff', border: '1px solid #e2e8f0', borderRadius: 16, padding: '16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                            <Shield size={13} style={{ color: '#22c55e' }} />
                            <span style={{ fontSize: 11, fontWeight: 800, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.07em' }}>Risk Guardrails</span>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                            {[
                                ['Max per position', '5% of portfolio'],
                                ['Max open positions', '3 concurrent'],
                                ['Daily loss limit', '2% auto-halt'],
                                ['Min risk/reward', '≥ 1.5×'],
                                ['Min expected profit', '> 0.5%'],
                            ].map(([k, v]) => (
                                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                                    <span style={{ color: '#64748b' }}>{k}</span>
                                    <span style={{ fontWeight: 700, color: '#0f172a' }}>{v}</span>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* How it works */}
                    <div style={{ background: 'linear-gradient(135deg,#f8faff,#eff6ff)', border: '1px solid #dbeafe', borderRadius: 16, padding: '16px' }}>
                        <div style={{ fontSize: 11, fontWeight: 800, color: '#1d4ed8', textTransform: 'uppercase', letterSpacing: '0.07em', marginBottom: 10 }}>
                            How Your AI Broker Works
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                            {[
                                ['1', 'Scans your watchlist stocks using technical analysis (RSI, MACD, Bollinger Bands, support/resistance)'],
                                ['2', 'Generates BUY/SELL signals with exact entry prices, price targets and stop-loss levels'],
                                ['3', 'Detects arbitrage opportunities: ETF mispricing, pairs divergence, mean-reversion setups'],
                                ['4', 'Executes paper trades autonomously with strict risk management'],
                            ].map(([n, t]) => (
                                <div key={n} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                                    <span style={{ width: 18, height: 18, borderRadius: '50%', background: '#1d4ed8', color: '#fff', fontSize: 9, fontWeight: 800, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{n}</span>
                                    <span style={{ fontSize: 11, color: '#3730a3', lineHeight: 1.55 }}>{t}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
