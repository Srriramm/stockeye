import React, { useState, useEffect, useRef } from 'react';
import {
    Search, Sparkles, Filter, ChevronDown, ChevronUp,
    TrendingUp, TrendingDown, RefreshCw, BarChart3, X,
    ArrowUpRight, ArrowDownRight, Zap, Target,
} from 'lucide-react';
import axios from 'axios';

// ─── Preset suggestion chips ────────────────────────────────────────────────
const SUGGESTIONS = [
    'Profitable IT stocks under ₹2000 with RSI below 40',
    'High dividend banking stocks above ₹500',
    'Oversold pharma stocks near 52-week low',
    'Blue chip FMCG stocks with low P/E',
    'Momentum auto stocks with RSI above 60',
    'Value steel stocks with dividend yield above 3%',
];

const PRESET_CHIPS = [
    { key: 'value_stocks', label: 'Value Stocks', color: '#065f46', bg: '#d1fae5' },
    { key: 'growth_stocks', label: 'Growth Stocks', color: '#1d4ed8', bg: '#dbeafe' },
    { key: 'dividend_stocks', label: 'High Dividend', color: '#92400e', bg: '#fef3c7' },
    { key: 'oversold', label: 'Oversold (RSI<30)', color: '#9a3412', bg: '#ffedd5' },
    { key: 'overbought', label: 'Overbought (RSI>70)', color: '#5b21b6', bg: '#ede9fe' },
    { key: 'near_52_week_high', label: 'Near 52W High', color: '#065f46', bg: '#d1fae5' },
    { key: 'near_52_week_low', label: 'Near 52W Low', color: '#991b1b', bg: '#fee2e2' },
    { key: 'blue_chip', label: 'Blue Chip', color: '#1e40af', bg: '#dbeafe' },
];

// ─── Format helpers ──────────────────────────────────────────────────────────
const fmtINR = (n) => {
    if (!n) return '—';
    if (n >= 1e12) return `₹${(n / 1e12).toFixed(1)}T`;
    if (n >= 1e9) return `₹${(n / 1e9).toFixed(1)}B`;
    if (n >= 1e7) return `₹${(n / 1e7).toFixed(1)}Cr`;
    return `₹${n.toLocaleString('en-IN')}`;
};

const fmtPrice = (n) => n != null ? `₹${Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : '—';
const fmtPct = (n) => n != null ? `${n >= 0 ? '+' : ''}${Number(n).toFixed(2)}%` : '—';

// ─── Result row ──────────────────────────────────────────────────────────────
function ResultRow({ stock, onAnalyze }) {
    const up = stock.change_percent >= 0;
    return (
        <div
            className="grid items-center px-4 py-3 transition-colors"
            style={{
                gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 80px 80px',
                borderBottom: '1px solid #f1f5f9',
                gap: 8,
            }}
            onMouseEnter={e => { e.currentTarget.style.background = '#f8fafc'; }}
            onMouseLeave={e => { e.currentTarget.style.background = ''; }}
        >
            {/* Name + sector */}
            <div>
                <div className="font-semibold text-sm" style={{ color: '#0f172a' }}>{stock.ticker}</div>
                <div className="text-[11px]" style={{ color: '#94a3b8' }}>{stock.name} · {stock.sector}</div>
            </div>

            {/* Price */}
            <div className="text-sm font-mono font-semibold text-right" style={{ color: '#0f172a' }}>
                {fmtPrice(stock.current_price)}
            </div>

            {/* Change */}
            <div className={`flex items-center justify-end gap-1 text-sm font-semibold`}
                style={{ color: up ? '#059669' : '#dc2626' }}>
                {up ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}
                {fmtPct(stock.change_percent)}
            </div>

            {/* P/E */}
            <div className="text-sm text-right" style={{ color: '#334155' }}>
                {stock.pe_ratio > 0 ? stock.pe_ratio.toFixed(1) : '—'}
            </div>

            {/* RSI */}
            <div className="text-sm text-right font-mono" style={{
                color: stock.rsi > 70 ? '#dc2626' : stock.rsi < 30 ? '#059669' : '#334155',
            }}>
                {stock.rsi ? stock.rsi.toFixed(0) : '—'}
            </div>

            {/* Market Cap */}
            <div className="text-[11px] text-right" style={{ color: '#64748b' }}>
                {fmtINR(stock.market_cap)}
            </div>

            {/* Analyse button */}
            <div className="flex justify-end">
                <button
                    onClick={() => onAnalyze(stock.ticker)}
                    className="text-[11px] font-semibold px-2 py-1 rounded-lg transition-all"
                    style={{ background: '#eff6ff', color: '#2563eb' }}
                    onMouseEnter={e => { e.currentTarget.style.background = '#dbeafe'; }}
                    onMouseLeave={e => { e.currentTarget.style.background = '#eff6ff'; }}
                >
                    Analyse →
                </button>
            </div>
        </div>
    );
}

// ─── Main component ──────────────────────────────────────────────────────────
export default function Screener({ apiUrl, onNavigateToForecast }) {
    const [query, setQuery] = useState('');
    const [results, setResults] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [parsedDesc, setParsedDesc] = useState('');
    const [filtersApplied, setFiltersApplied] = useState({});
    const [showFilters, setShowFilters] = useState(false);
    const [sortBy, setSortBy] = useState('change_percent');
    const [sortDir, setSortDir] = useState(-1);
    const [activeSuggestion, setActiveSuggestion] = useState(null);
    const inputRef = useRef(null);

    // Focus input on mount
    useEffect(() => { inputRef.current?.focus(); }, []);

    const runNaturalQuery = async (q) => {
        if (!q.trim()) return;
        setLoading(true);
        setError(null);
        setResults(null);
        setParsedDesc('');
        try {
            const res = await axios.post(`${apiUrl}/api/screener/natural`, { query: q });
            setResults(res.data.results || []);
            setParsedDesc(res.data.parsed_description || '');
            setFiltersApplied(res.data.filters_applied || {});
        } catch (err) {
            setError(err.response?.data?.error || 'Screener failed. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const runPreset = async (key) => {
        setLoading(true);
        setError(null);
        setResults(null);
        setParsedDesc('');
        try {
            const res = await axios.get(`${apiUrl}/api/screener/presets/${key}`);
            setResults(res.data.results || []);
            setParsedDesc(res.data.preset_description || '');
            setFiltersApplied({});
        } catch (err) {
            setError('Failed to load preset screen.');
        } finally {
            setLoading(false);
        }
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter') { runNaturalQuery(query); }
    };

    const handleSuggestion = (s) => {
        setQuery(s);
        setActiveSuggestion(s);
        runNaturalQuery(s);
    };

    // Sort helpers
    const sorted = results
        ? [...results].sort((a, b) => {
            const av = a[sortBy] ?? -Infinity;
            const bv = b[sortBy] ?? -Infinity;
            return sortDir * (bv - av);
        })
        : [];

    const toggleSort = (col) => {
        if (sortBy === col) setSortDir(d => -d);
        else { setSortBy(col); setSortDir(-1); }
    };

    const SortHeader = ({ col, label }) => (
        <button
            onClick={() => toggleSort(col)}
            className="flex items-center justify-end gap-1 text-right w-full"
            style={{ color: sortBy === col ? '#2563eb' : '#94a3b8', fontSize: 11, fontWeight: 700, letterSpacing: '0.05em', textTransform: 'uppercase' }}
        >
            {label}
            {sortBy === col ? (sortDir === -1 ? <ChevronDown size={11} /> : <ChevronUp size={11} />) : null}
        </button>
    );

    return (
        <div className="p-6 space-y-5 max-w-6xl mx-auto">

            {/* ── Header ── */}
            <div className="flex items-start justify-between">
                <div>
                    <h1 className="text-xl font-bold" style={{ color: '#0f172a' }}>
                        AI Stock Screener
                    </h1>
                    <p className="text-sm mt-0.5" style={{ color: '#64748b' }}>
                        Describe what you're looking for in plain English
                    </p>
                </div>
            </div>

            {/* ── Search bar ── */}
            <div
                className="relative flex items-center rounded-2xl transition-all"
                style={{ background: '#ffffff', border: '2px solid #e2e8f0', boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}
                onFocusCapture={e => { e.currentTarget.style.borderColor = '#3b82f6'; e.currentTarget.style.boxShadow = '0 0 0 3px rgba(59,130,246,0.12)'; }}
                onBlurCapture={e => { e.currentTarget.style.borderColor = '#e2e8f0'; e.currentTarget.style.boxShadow = '0 2px 12px rgba(0,0,0,0.06)'; }}
            >
                <div className="pl-5 pr-3 flex-shrink-0" style={{ color: '#94a3b8' }}>
                    <Sparkles size={18} />
                </div>
                <input
                    ref={inputRef}
                    type="text"
                    value={query}
                    onChange={e => setQuery(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="e.g. 'Profitable IT stocks under ₹2000 with RSI below 40'"
                    className="flex-1 py-4 text-sm outline-none bg-transparent"
                    style={{ color: '#0f172a' }}
                />
                {query && (
                    <button
                        onClick={() => { setQuery(''); setResults(null); setError(null); }}
                        className="px-3" style={{ color: '#94a3b8' }}
                    >
                        <X size={15} />
                    </button>
                )}
                <button
                    onClick={() => runNaturalQuery(query)}
                    disabled={loading || !query.trim()}
                    className="flex items-center gap-2 px-5 py-3 m-1.5 rounded-xl font-semibold text-sm transition-all disabled:opacity-50"
                    style={{ background: 'linear-gradient(135deg, #2563eb, #3b82f6)', color: '#fff', boxShadow: '0 2px 8px rgba(37,99,235,0.35)' }}
                >
                    {loading ? <RefreshCw size={14} className="animate-spin" /> : <Search size={14} />}
                    Screen
                </button>
            </div>

            {/* ── Suggestion chips ── */}
            <div className="flex flex-wrap gap-2">
                {SUGGESTIONS.map(s => (
                    <button
                        key={s}
                        onClick={() => handleSuggestion(s)}
                        className="text-[11px] px-3 py-1.5 rounded-full font-medium transition-all"
                        style={{
                            background: activeSuggestion === s ? '#eff6ff' : '#f8fafc',
                            color: activeSuggestion === s ? '#2563eb' : '#64748b',
                            border: `1px solid ${activeSuggestion === s ? '#bfdbfe' : '#e2e8f0'}`,
                        }}
                    >
                        {s}
                    </button>
                ))}
            </div>

            {/* ── Preset chips ── */}
            <div>
                <div className="text-[11px] font-bold uppercase tracking-wider mb-2" style={{ color: '#94a3b8' }}>
                    Quick Presets
                </div>
                <div className="flex flex-wrap gap-2">
                    {PRESET_CHIPS.map(p => (
                        <button
                            key={p.key}
                            onClick={() => runPreset(p.key)}
                            className="flex items-center gap-1.5 text-[11px] px-3 py-1.5 rounded-lg font-semibold transition-all"
                            style={{ background: p.bg, color: p.color }}
                            onMouseEnter={e => { e.currentTarget.style.opacity = '0.8'; }}
                            onMouseLeave={e => { e.currentTarget.style.opacity = '1'; }}
                        >
                            <Zap size={10} />
                            {p.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* ── Results ── */}
            {loading && (
                <div className="py-16 text-center">
                    <div className="inline-flex items-center gap-3" style={{ color: '#64748b' }}>
                        <RefreshCw size={18} className="animate-spin" style={{ color: '#3b82f6' }} />
                        <span className="text-sm">AI is parsing your query and screening stocks…</span>
                    </div>
                </div>
            )}

            {error && (
                <div className="px-4 py-3 rounded-xl text-sm flex items-center gap-2" style={{ background: '#fee2e2', color: '#991b1b', border: '1px solid #fecaca' }}>
                    <X size={14} /> {error}
                </div>
            )}

            {results && !loading && (
                <div className="rounded-2xl overflow-hidden" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}>
                    {/* Result header */}
                    <div className="px-4 py-3 flex items-center justify-between" style={{ borderBottom: '1px solid #f1f5f9', background: '#fafbfc' }}>
                        <div>
                            <span className="text-sm font-semibold" style={{ color: '#0f172a' }}>
                                {results.length} stocks matched
                            </span>
                            {parsedDesc && (
                                <div className="text-[11px] mt-0.5 flex items-center gap-1" style={{ color: '#64748b' }}>
                                    <Sparkles size={10} style={{ color: '#3b82f6' }} />
                                    {parsedDesc}
                                </div>
                            )}
                        </div>
                        {/* Active filter pills */}
                        {Object.keys(filtersApplied).length > 0 && (
                            <div className="flex flex-wrap gap-1.5">
                                {Object.entries(filtersApplied).map(([k, v]) => (
                                    <span
                                        key={k}
                                        className="text-[10px] px-2 py-0.5 rounded-full font-mono"
                                        style={{ background: '#eff6ff', color: '#1d4ed8', border: '1px solid #bfdbfe' }}
                                    >
                                        {k}: {Array.isArray(v) ? v.join(', ') : String(v)}
                                    </span>
                                ))}
                            </div>
                        )}
                    </div>

                    {results.length === 0 ? (
                        <div className="py-16 text-center">
                            <BarChart3 size={32} className="mx-auto mb-3" style={{ color: '#e2e8f0' }} />
                            <p className="text-sm" style={{ color: '#94a3b8' }}>No stocks matched these criteria.</p>
                            <p className="text-xs mt-1" style={{ color: '#cbd5e1' }}>Try relaxing the filters — e.g. raise the price range or widen the RSI.</p>
                        </div>
                    ) : (
                        <>
                            {/* Column headers */}
                            <div
                                className="grid px-4 py-2"
                                style={{
                                    gridTemplateColumns: '2fr 1fr 1fr 1fr 1fr 80px 80px',
                                    gap: 8,
                                    borderBottom: '1px solid #f1f5f9',
                                    background: '#fafbfc',
                                }}
                            >
                                <div className="text-[11px] font-bold uppercase tracking-wider" style={{ color: '#94a3b8' }}>Stock</div>
                                <SortHeader col="current_price" label="Price" />
                                <SortHeader col="change_percent" label="Change" />
                                <SortHeader col="pe_ratio" label="P/E" />
                                <SortHeader col="rsi" label="RSI" />
                                <SortHeader col="market_cap" label="Mkt Cap" />
                                <div />
                            </div>

                            {/* Rows */}
                            <div className="divide-y" style={{ maxHeight: 520, overflowY: 'auto' }}>
                                {sorted.map(stock => (
                                    <ResultRow
                                        key={stock.ticker}
                                        stock={stock}
                                        onAnalyze={(t) => onNavigateToForecast && onNavigateToForecast(t)}
                                    />
                                ))}
                            </div>
                        </>
                    )}
                </div>
            )}

            {/* Empty state — no query yet */}
            {!results && !loading && !error && (
                <div className="py-14 text-center">
                    <div
                        className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-4"
                        style={{ background: 'linear-gradient(135deg, #eff6ff, #dbeafe)' }}
                    >
                        <Filter size={26} style={{ color: '#2563eb' }} />
                    </div>
                    <p className="text-sm font-semibold" style={{ color: '#334155' }}>Ask in plain English</p>
                    <p className="text-xs mt-1" style={{ color: '#94a3b8' }}>
                        Try a suggestion above or type your own criteria
                    </p>
                </div>
            )}
        </div>
    );
}
