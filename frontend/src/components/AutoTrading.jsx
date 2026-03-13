import React, { useState, useEffect, useCallback } from 'react';
import { authAxios } from '../utils/api';
import {
    Zap, Play, RefreshCw, TrendingUp, TrendingDown,
    Shield, AlertTriangle, CheckCircle, Clock, BarChart2,
    Activity, Bot, Link, Layers, Target, DollarSign, Plus, X, Search
} from 'lucide-react';

const API_URL = import.meta.env.VITE_API_URL || '';

const fmt = (n) =>
    n != null ? `₹${Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : '—';
const pct = (n) =>
    n != null ? `${Number(n) >= 0 ? '+' : ''}${Number(n).toFixed(2)}%` : '—';

// ── Opportunity type badges ────────────────────────────────────────────────
const TYPE_CFG = {
    ETF_NAV_DIVERGENCE: { label: 'ETF Arb',    bg: '#eff6ff', color: '#1d4ed8', border: '#bfdbfe' },
    PAIRS_DIVERGENCE:   { label: 'Pairs',       bg: '#f5f3ff', color: '#6d28d9', border: '#ddd6fe' },
    BOLLINGER_EXTREME:  { label: 'Mean Rev',    bg: '#fefce8', color: '#92400e', border: '#fde68a' },
};
const SIG_CFG = {
    BUY:  { bg: 'bg-emerald-50',  text: 'text-emerald-700', border: 'border-emerald-200', dot: '#10b981' },
    SELL: { bg: 'bg-rose-50',     text: 'text-rose-700',    border: 'border-rose-200',    dot: '#ef4444' },
    HOLD: { bg: 'bg-amber-50',    text: 'text-amber-700',   border: 'border-amber-200',   dot: '#f59e0b' },
};

// ── Sub-components ─────────────────────────────────────────────────────────
function StatCard({ icon: Icon, label, value, sub, color = 'text-slate-800' }) {
    return (
        <div className="glass-panel p-5 flex items-start gap-4">
            <div className="w-10 h-10 rounded-xl bg-indigo-500/10 flex items-center justify-center flex-shrink-0">
                <Icon size={18} className="text-indigo-500" />
            </div>
            <div>
                <div className="text-xs text-slate-500 font-semibold uppercase tracking-wider mb-1">{label}</div>
                <div className={`text-xl font-bold font-mono ${color}`}>{value}</div>
                {sub && <div className="text-xs text-slate-400 mt-0.5">{sub}</div>}
            </div>
        </div>
    );
}

function OpportunityCard({ opp, onAnalyse }) {
    const cfg  = TYPE_CFG[opp.type] || TYPE_CFG.BOLLINGER_EXTREME;
    const isUp = (opp.recommended_action || '').toUpperCase().startsWith('BUY');
    const confPct = Math.round((opp.confidence || 0) * 100);

    return (
        <div className="glass-panel p-5 hover:shadow-md transition-shadow">
            <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-base font-bold text-slate-800 font-mono">{opp.ticker}</span>
                    <span style={{
                        fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 6,
                        background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`,
                    }}>{cfg.label}</span>
                    {opp.direction && (
                        <span style={{
                            fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 6,
                            background: opp.direction === 'OVERSOLD' ? '#f0fdf4' : '#fef2f2',
                            color: opp.direction === 'OVERSOLD' ? '#15803d' : '#dc2626',
                            border: `1px solid ${opp.direction === 'OVERSOLD' ? '#bbf7d0' : '#fecaca'}`,
                        }}>{opp.direction}</span>
                    )}
                </div>
                <div className="text-right flex-shrink-0 ml-2">
                    <div className={`text-sm font-bold ${isUp ? 'text-emerald-600' : 'text-rose-500'}`}>
                        {isUp ? <TrendingUp size={14} className="inline mr-1" /> : <TrendingDown size={14} className="inline mr-1" />}
                        {opp.expected_profit_pct != null ? `+${Number(opp.expected_profit_pct).toFixed(2)}%` : '—'}
                    </div>
                    <div className="text-[10px] text-slate-400 mt-0.5">expected profit</div>
                </div>
            </div>

            <p className="text-xs text-slate-500 leading-relaxed mb-3">{opp.reasoning}</p>

            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    {/* Confidence bar */}
                    <div className="flex items-center gap-1.5">
                        <div className="w-20 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                            <div className="h-full rounded-full bg-indigo-500 transition-all"
                                 style={{ width: `${confPct}%` }} />
                        </div>
                        <span className="text-[10px] font-mono font-bold text-slate-500">{confPct}%</span>
                    </div>
                    {/* Key metric */}
                    {opp.z_score != null && (
                        <span className="text-[10px] font-mono text-purple-600 font-bold">
                            z={opp.z_score}σ
                        </span>
                    )}
                    {opp.premium_pct != null && (
                        <span className="text-[10px] font-mono text-blue-600 font-bold">
                            {opp.premium_pct > 0 ? '+' : ''}{opp.premium_pct}%
                        </span>
                    )}
                </div>
                <div className="text-xs font-bold text-indigo-600 bg-indigo-50 border border-indigo-100 px-2 py-0.5 rounded">
                    {opp.recommended_action}
                </div>
            </div>
        </div>
    );
}

function TradeRow({ trade }) {
    const isUp = trade.side === 'BUY';
    return (
        <div className="flex items-center gap-3 py-2.5 border-b border-slate-50 last:border-0">
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${isUp ? 'bg-emerald-50' : 'bg-rose-50'}`}>
                {isUp ? <TrendingUp size={14} className="text-emerald-600" />
                      : <TrendingDown size={14} className="text-rose-500" />}
            </div>
            <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-slate-800">{trade.ticker}</span>
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${isUp ? 'text-emerald-700 bg-emerald-50' : 'text-rose-700 bg-rose-50'}`}>
                        {trade.side}
                    </span>
                </div>
                <div className="text-xs text-slate-400 mt-0.5">
                    {trade.quantity}× @ {fmt(trade.execution_price)}
                </div>
            </div>
            <div className="text-right">
                <div className="text-sm font-bold text-slate-800 font-mono">{fmt(trade.total_value)}</div>
                <div className="text-[10px] text-slate-400">{trade.status || 'EXECUTED'}</div>
            </div>
        </div>
    );
}

// ── Main component ─────────────────────────────────────────────────────────
export default function AutoTrading() {
    const [opportunities, setOpportunities]   = useState([]);
    const [oppLoading, setOppLoading]         = useState(false);
    const [session, setSession]               = useState(null);
    const [sessionRunning, setSessionRunning] = useState(false);
    const [brokerStatus, setBrokerStatus]     = useState(null);
    const [error, setError]                   = useState('');
    const [selectedTickers, setSelectedTickers] = useState([]);
    const [tickerInput, setTickerInput]         = useState('');

    // ── Ticker picker helpers ────────────────────────────────────────────
    const addTicker = (raw) => {
        const parts = raw.toUpperCase().split(/[\s,;]+/).map(t => t.trim()).filter(Boolean);
        setSelectedTickers(prev => {
            const existing = new Set(prev);
            const toAdd = parts.filter(t => t && !existing.has(t));
            return [...prev, ...toAdd];
        });
        setTickerInput('');
    };

    const removeTicker = (t) => setSelectedTickers(prev => prev.filter(x => x !== t));

    const handleTickerKey = (e) => {
        if (e.key === 'Enter' || e.key === ',' || e.key === ' ') {
            e.preventDefault();
            if (tickerInput.trim()) addTicker(tickerInput);
        } else if (e.key === 'Backspace' && !tickerInput && selectedTickers.length > 0) {
            setSelectedTickers(prev => prev.slice(0, -1));
        }
    };

    // ── Fetch helpers ────────────────────────────────────────────────────
    const fetchOpportunities = useCallback(async (tickers) => {
        setOppLoading(true);
        try {
            const tickerList = tickers ?? selectedTickers;
            const params = tickerList.length > 0 ? `?tickers=${tickerList.join(',')}` : '';
            const res = await authAxios.get(`${API_URL}/api/auto-trading/opportunities${params}`);
            setOpportunities(res.data.opportunities || []);
        } catch (e) {
            setError('Could not load opportunities: ' + (e.response?.data?.error || e.message));
        } finally {
            setOppLoading(false);
        }
    }, [selectedTickers]);

    const fetchSession = useCallback(async () => {
        try {
            const res = await authAxios.get(`${API_URL}/api/auto-trading/session/active`);
            setSession(res.data);
        } catch { /* silent */ }
    }, []);

    const fetchBroker = useCallback(async () => {
        try {
            const res = await authAxios.get(`${API_URL}/api/auto-trading/broker/status`);
            setBrokerStatus(res.data);
        } catch { /* silent */ }
    }, []);

    useEffect(() => {
        fetchSession();
        fetchBroker();
    }, []);

    // ── Run session ──────────────────────────────────────────────────────
    const runSession = async () => {
        setSessionRunning(true);
        setError('');
        try {
            const res = await authAxios.post(
                `${API_URL}/api/auto-trading/run`,
                { tickers: selectedTickers },
                { timeout: 180000 }
            );
            setSession(res.data);
            // Refresh opportunities panel with same tickers after session completes
            fetchOpportunities();
        } catch (e) {
            setError('Session failed: ' + (e.response?.data?.error || e.message));
        } finally {
            setSessionRunning(false);
        }
    };

    // ── Broker connect ───────────────────────────────────────────────────
    const connectBroker = async () => {
        try {
            const res = await authAxios.get(`${API_URL}/api/auto-trading/broker/login-url`);
            if (res.data.login_url) window.open(res.data.login_url, '_blank');
        } catch (e) {
            setError(e.response?.data?.error || 'Broker connection error');
        }
    };

    // ── Derived stats ────────────────────────────────────────────────────
    const totalCapitalDeployed = session?.total_capital_deployed || 0;
    const tradesExecuted       = session?.trades_executed || 0;
    const oppsFound            = session?.opportunities_found || 0;

    return (
        <div className="p-6 space-y-6 max-w-6xl mx-auto">

            {/* ── Header ── */}
            <div className="flex items-start justify-between gap-4 flex-wrap">
                <div>
                    <h1 className="text-2xl font-bold text-slate-800 flex items-center gap-2">
                        <Zap size={22} className="text-indigo-500" />
                        Auto Trading
                    </h1>
                    <p className="text-sm text-slate-500 mt-1">
                        Autonomous Claude agent — scans for ETF arbitrage, pairs divergence &amp; mean-reversion, then executes paper trades.
                    </p>
                </div>
                <div className="flex items-center gap-3 flex-wrap">
                    {/* Broker badge */}
                    {brokerStatus && (
                        <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-bold ${
                            brokerStatus.mode === 'live'
                                ? 'bg-emerald-50 border-emerald-200 text-emerald-700'
                                : 'bg-slate-50 border-slate-200 text-slate-500'
                        }`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${brokerStatus.mode === 'live' ? 'bg-emerald-500' : 'bg-slate-400'}`} />
                            {brokerStatus.mode === 'live' ? 'Live · Zerodha' : 'Paper Mode'}
                        </div>
                    )}
                    <button
                        onClick={() => fetchOpportunities()}
                        disabled={oppLoading}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-slate-600 text-xs font-semibold hover:bg-slate-50 disabled:opacity-50 transition"
                    >
                        <RefreshCw size={12} className={oppLoading ? 'animate-spin' : ''} />
                        {selectedTickers.length > 0 ? `Scan (${selectedTickers.length})` : 'Scan Watchlist'}
                    </button>
                    <button
                        onClick={runSession}
                        disabled={sessionRunning}
                        className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold text-white disabled:opacity-60 transition"
                        style={{
                            background: sessionRunning ? '#94a3b8' : 'linear-gradient(135deg,#4f46e5,#7c3aed)',
                            cursor: sessionRunning ? 'not-allowed' : 'pointer',
                        }}
                    >
                        {sessionRunning ? (
                            <>
                                <div style={{ width: 14, height: 14, borderRadius: '50%', border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', animation: 'spin 0.7s linear infinite' }} />
                                Agent Running…
                            </>
                        ) : (
                            <><Play size={14} /> Run Agent</>
                        )}
                    </button>
                </div>
            </div>

            <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>

            {/* ── Error banner ── */}
            {error && (
                <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-sm flex items-center gap-2">
                    <AlertTriangle size={15} /> {error}
                    <button onClick={() => setError('')} className="ml-auto text-rose-400 hover:text-rose-600">✕</button>
                </div>
            )}

            {/* ── Stats row ── */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <StatCard icon={Target}     label="Opportunities"     value={opportunities.length}     sub="detected now" />
                <StatCard icon={Play}       label="Trades This Session" value={tradesExecuted}          sub="executed by agent" />
                <StatCard icon={DollarSign} label="Capital Deployed"  value={fmt(totalCapitalDeployed)} sub="this session" />
                <StatCard icon={Layers}     label="Signals Scanned"   value={`${oppsFound || opportunities.length}`} sub="opportunities found" />
            </div>

            {/* ── Stock Picker ── */}
            <div className="glass-panel p-4">
                <div className="flex items-center gap-2 mb-3">
                    <Search size={13} className="text-indigo-400" />
                    <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">Scan Specific Stocks</span>
                    <span className="text-[10px] text-slate-400 ml-1">— type any NSE ticker and press Enter</span>
                    {selectedTickers.length > 0 && (
                        <button
                            onClick={() => setSelectedTickers([])}
                            className="ml-auto text-[10px] text-slate-400 hover:text-rose-500 transition"
                        >
                            Clear all
                        </button>
                    )}
                </div>

                <div className="flex flex-wrap gap-2 items-center min-h-[36px] bg-slate-50 border border-slate-200 rounded-xl px-3 py-2 focus-within:border-indigo-400 focus-within:ring-1 focus-within:ring-indigo-200 transition">
                    {selectedTickers.map(t => (
                        <span key={t} className="flex items-center gap-1 text-xs font-bold bg-indigo-100 text-indigo-700 border border-indigo-200 px-2 py-0.5 rounded-lg">
                            {t}
                            <button onClick={() => removeTicker(t)} className="text-indigo-400 hover:text-indigo-700 ml-0.5 leading-none">
                                <X size={10} />
                            </button>
                        </span>
                    ))}
                    <input
                        type="text"
                        value={tickerInput}
                        onChange={e => setTickerInput(e.target.value.toUpperCase())}
                        onKeyDown={handleTickerKey}
                        onBlur={() => { if (tickerInput.trim()) addTicker(tickerInput); }}
                        placeholder={selectedTickers.length === 0 ? 'e.g. TCS, INFY, RELIANCE, HDFCBANK…' : 'Add more…'}
                        className="flex-1 min-w-[160px] bg-transparent text-xs text-slate-700 placeholder:text-slate-400 outline-none"
                    />
                </div>

                <div className="flex items-center gap-2 mt-3 flex-wrap">
                    {/* Quick-add popular tickers */}
                    <span className="text-[10px] text-slate-400 font-semibold">Quick add:</span>
                    {['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'NIFTYBEES', 'GOLDBEES', 'BANKBEES'].map(t => (
                        <button
                            key={t}
                            onClick={() => addTicker(t)}
                            disabled={selectedTickers.includes(t)}
                            className="text-[10px] font-bold px-2 py-0.5 rounded border transition disabled:opacity-30 disabled:cursor-not-allowed"
                            style={{ background: selectedTickers.includes(t) ? '#e0e7ff' : '#f8fafc', color: '#4f46e5', borderColor: '#c7d2fe' }}
                        >
                            + {t}
                        </button>
                    ))}
                    <button
                        onClick={() => fetchOpportunities()}
                        disabled={oppLoading}
                        className="ml-auto flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-bold text-white disabled:opacity-60 transition"
                        style={{ background: oppLoading ? '#94a3b8' : 'linear-gradient(135deg,#4f46e5,#6d28d9)' }}
                    >
                        <Search size={11} />
                        {selectedTickers.length > 0 ? `Scan ${selectedTickers.length} stock${selectedTickers.length > 1 ? 's' : ''}` : 'Scan Watchlist'}
                    </button>
                </div>
            </div>

            {/* ── Main grid ── */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                {/* Left: Opportunities (2 cols) */}
                <div className="lg:col-span-2 space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-sm font-bold text-slate-700 uppercase tracking-wider flex items-center gap-2">
                            <Activity size={14} className="text-indigo-400" />
                            Market Opportunities
                        </h2>
                        <span className="text-xs text-slate-400">{opportunities.length} found</span>
                    </div>

                    {oppLoading && (
                        <div className="glass-panel p-8 text-center text-slate-400 text-sm">
                            <div style={{ width: 28, height: 28, borderRadius: '50%', border: '3px solid #e2e8f0', borderTopColor: '#6366f1', animation: 'spin 0.8s linear infinite', margin: '0 auto 12px' }} />
                            Scanning {Object.keys({ETF_NAV_DIVERGENCE: 1, PAIRS_DIVERGENCE: 1, BOLLINGER_EXTREME: 1}).length} detectors…
                        </div>
                    )}

                    {!oppLoading && opportunities.length === 0 && (
                        <div className="glass-panel p-8 text-center">
                            <BarChart2 size={28} className="text-slate-300 mx-auto mb-3" />
                            <p className="text-sm font-semibold text-slate-500">No opportunities detected</p>
                            <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                                Type any NSE tickers above (e.g. TCS, INFY, RELIANCE) and click Scan.<br />
                                Detects ETF arbitrage, pairs divergence &amp; Bollinger Band extremes.
                            </p>
                        </div>
                    )}

                    {opportunities.map((opp, i) => (
                        <OpportunityCard key={i} opp={opp} />
                    ))}
                </div>

                {/* Right: Agent panel + Broker */}
                <div className="space-y-4">

                    {/* Agent Session */}
                    <div className="glass-panel p-5">
                        <div className="flex items-center gap-2 mb-4">
                            <Bot size={15} className="text-indigo-400" />
                            <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">Agent Session</span>
                            {session?.status === 'running' && (
                                <span className="ml-auto text-[10px] font-bold text-indigo-600 bg-indigo-50 border border-indigo-100 px-2 py-0.5 rounded animate-pulse">
                                    LIVE
                                </span>
                            )}
                            {session?.status === 'complete' && (
                                <span className="ml-auto text-[10px] font-bold text-emerald-600 bg-emerald-50 border border-emerald-100 px-2 py-0.5 rounded">
                                    DONE
                                </span>
                            )}
                        </div>

                        {!session || session.status === 'idle' ? (
                            <div className="text-center py-4 text-slate-400">
                                <Clock size={24} className="mx-auto mb-2 text-slate-300" />
                                <p className="text-xs">No session yet</p>
                                <p className="text-[11px] text-slate-300 mt-1">Click <strong>Run Agent</strong> to start</p>
                            </div>
                        ) : (
                            <div className="space-y-3">
                                {/* Session meta */}
                                <div className="flex gap-3 text-xs">
                                    <div className="flex-1 bg-slate-50 rounded-lg p-2 text-center">
                                        <div className="font-bold text-slate-800 text-base">{session.trades_executed ?? 0}</div>
                                        <div className="text-slate-400">Trades</div>
                                    </div>
                                    <div className="flex-1 bg-slate-50 rounded-lg p-2 text-center">
                                        <div className="font-bold text-slate-800 text-base">{session.opportunities_found ?? 0}</div>
                                        <div className="text-slate-400">Opps</div>
                                    </div>
                                    <div className="flex-1 bg-slate-50 rounded-lg p-2 text-center">
                                        <div className="font-bold text-indigo-600 text-xs">{session.model_used?.includes('haiku') ? 'Haiku' : 'Sonnet'}</div>
                                        <div className="text-slate-400">Model</div>
                                    </div>
                                </div>

                                {/* Reasoning */}
                                {session.reasoning && (
                                    <div className="bg-indigo-50/50 border border-indigo-100 rounded-lg p-3">
                                        <div className="text-[10px] font-bold text-indigo-600 uppercase tracking-wider mb-1">Agent Reasoning</div>
                                        <p className="text-xs text-slate-600 leading-relaxed">{session.reasoning}</p>
                                    </div>
                                )}

                                {/* Market conditions */}
                                {session.market_conditions && (
                                    <div className="text-xs text-slate-500">
                                        <span className="font-semibold text-slate-600">Market: </span>
                                        {session.market_conditions}
                                    </div>
                                )}

                                {/* Trades list */}
                                {session.trades?.length > 0 && (
                                    <div>
                                        <div className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">Executed Trades</div>
                                        {session.trades.map((t, i) => <TradeRow key={i} trade={t} />)}
                                    </div>
                                )}

                                {/* Skipped */}
                                {session.skipped_trades && (
                                    <div className="text-[10px] text-slate-400 italic leading-relaxed">
                                        <span className="font-semibold not-italic text-slate-500">Skipped: </span>
                                        {session.skipped_trades}
                                    </div>
                                )}

                                {session.generated_at && (
                                    <div className="text-[10px] text-slate-300 text-right">
                                        {new Date(session.generated_at).toLocaleString('en-IN', {
                                            day: 'numeric', month: 'short',
                                            hour: '2-digit', minute: '2-digit',
                                        })}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Broker Connection */}
                    <div className="glass-panel p-5">
                        <div className="flex items-center gap-2 mb-4">
                            <Link size={14} className="text-slate-400" />
                            <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">Broker</span>
                        </div>

                        {brokerStatus ? (
                            <div className="space-y-3">
                                <div className="flex items-center justify-between text-sm">
                                    <span className="text-slate-500">Status</span>
                                    <span className={`font-bold ${brokerStatus.connected ? 'text-emerald-600' : 'text-slate-400'}`}>
                                        {brokerStatus.connected ? <><CheckCircle size={12} className="inline mr-1" />Connected</> : 'Not connected'}
                                    </span>
                                </div>
                                <div className="flex items-center justify-between text-sm">
                                    <span className="text-slate-500">Mode</span>
                                    <span className={`font-bold ${brokerStatus.mode === 'live' ? 'text-emerald-600' : 'text-amber-500'}`}>
                                        {brokerStatus.mode === 'live' ? '🟢 Live' : '📄 Paper'}
                                    </span>
                                </div>
                                <div className="flex items-center justify-between text-sm">
                                    <span className="text-slate-500">Broker</span>
                                    <span className="font-bold text-slate-700 capitalize">{brokerStatus.broker}</span>
                                </div>

                                {brokerStatus.broker !== 'zerodha' && (
                                    <div className="mt-3 pt-3 border-t border-slate-100">
                                        <button
                                            onClick={connectBroker}
                                            className="w-full py-2 rounded-lg text-xs font-bold text-white transition"
                                            style={{ background: 'linear-gradient(135deg,#1e40af,#3730a3)' }}
                                        >
                                            Connect Zerodha Kite
                                        </button>
                                        <p className="text-[10px] text-slate-400 text-center mt-2 leading-relaxed">
                                            Set ZERODHA_API_KEY + ZERODHA_API_SECRET<br />
                                            in .env to enable live trading
                                        </p>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className="text-xs text-slate-400 text-center py-2">Loading broker status…</div>
                        )}
                    </div>

                    {/* Risk limits info */}
                    <div className="glass-panel p-5">
                        <div className="flex items-center gap-2 mb-3">
                            <Shield size={14} className="text-emerald-500" />
                            <span className="text-xs font-bold text-slate-700 uppercase tracking-wider">Hard Risk Limits</span>
                        </div>
                        <div className="space-y-2 text-xs text-slate-500">
                            {[
                                ['Max position size', '5% of portfolio'],
                                ['Max open positions', '3 concurrent'],
                                ['Daily loss limit',  '2% auto-halt'],
                                ['Min risk/reward',   '≥ 1.5×'],
                                ['Min expected profit','> 0.5% (after costs)'],
                            ].map(([k, v]) => (
                                <div key={k} className="flex justify-between">
                                    <span>{k}</span>
                                    <span className="font-bold text-slate-700">{v}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
