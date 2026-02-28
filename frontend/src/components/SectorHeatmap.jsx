import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
    TrendingUp, TrendingDown, RefreshCw, Grid3X3,
    BarChart2, ArrowUpRight, ArrowDownRight, Minus,
    ChevronRight, Search
} from 'lucide-react';

const API_URL = process.env.REACT_APP_API_URL || '';

// ─────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────

function formatINR(v) {
    if (!v && v !== 0) return '—';
    if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)}Cr`;
    if (v >= 1e5) return `₹${(v / 1e5).toFixed(2)}L`;
    return `₹${Number(v).toLocaleString('en-IN')}`;
}

function formatMCap(v) {
    if (!v) return '—';
    if (v >= 1e12) return `₹${(v / 1e12).toFixed(2)}T`;
    if (v >= 1e9) return `₹${(v / 1e9).toFixed(1)}B`;
    if (v >= 1e7) return `₹${(v / 1e7).toFixed(0)}Cr`;
    return '—';
}

function pctColor(v) {
    if (v > 1.5) return '#10b981';
    if (v > 0) return '#34d399';
    if (v < -1.5) return '#f43f5e';
    if (v < 0) return '#fb7185';
    return '#94a3b8';
}

function pctBg(v) {
    const intensity = Math.min(Math.abs(v) / 4, 1); // scale 0→4% to 0→100%
    if (v > 0) return `rgba(16,185,129,${0.06 + intensity * 0.18})`;
    if (v < 0) return `rgba(244,63,94,${0.06 + intensity * 0.18})`;
    return 'rgba(148,163,184,0.06)';
}

// ─────────────────────────────────────────────────────────────
// Stock Tile
// ─────────────────────────────────────────────────────────────
function StockTile({ stock, onClick }) {
    const cp = stock.change_percent;
    return (
        <button
            onClick={() => onClick(stock.ticker)}
            className="flex flex-col justify-between p-3 rounded-xl border transition-all duration-200 text-left w-full"
            style={{
                background: pctBg(cp),
                borderColor: cp > 0 ? 'rgba(16,185,129,0.25)' : cp < 0 ? 'rgba(244,63,94,0.25)' : 'rgba(148,163,184,0.15)',
                minHeight: '80px',
            }}
            title={stock.name}
        >
            <div className="flex items-start justify-between">
                <span className="text-[11px] font-black text-slate-800 truncate max-w-[70%]">{stock.ticker}</span>
                {cp > 0
                    ? <ArrowUpRight size={12} style={{ color: '#10b981', flexShrink: 0 }} />
                    : cp < 0
                        ? <ArrowDownRight size={12} style={{ color: '#f43f5e', flexShrink: 0 }} />
                        : <Minus size={12} style={{ color: '#94a3b8', flexShrink: 0 }} />}
            </div>
            <div>
                <div className="text-sm font-black font-mono-nums" style={{ color: pctColor(cp) }}>
                    {cp > 0 ? '+' : ''}{cp.toFixed(2)}%
                </div>
                <div className="text-[9px] text-slate-500 truncate">{formatINR(stock.current_price)}</div>
            </div>
        </button>
    );
}

// ─────────────────────────────────────────────────────────────
// Sector Band
// ─────────────────────────────────────────────────────────────
function SectorBand({ name, avg, stocks, onStockClick }) {
    const [expanded, setExpanded] = useState(true);
    const cp = avg;

    return (
        <div className="rounded-2xl border overflow-hidden"
            style={{ borderColor: cp > 0 ? 'rgba(16,185,129,0.2)' : cp < 0 ? 'rgba(244,63,94,0.2)' : 'rgba(148,163,184,0.15)' }}>
            {/* Sector header */}
            <button
                onClick={() => setExpanded(e => !e)}
                className="w-full flex items-center justify-between px-4 py-3"
                style={{ background: pctBg(cp) }}
            >
                <div className="flex items-center gap-3">
                    <span className="text-sm font-bold text-slate-800">{name}</span>
                    <span className="text-[10px] text-slate-500">{stocks.length} stocks</span>
                </div>
                <div className="flex items-center gap-3">
                    <span className="text-sm font-black font-mono-nums" style={{ color: pctColor(cp) }}>
                        {cp > 0 ? '+' : ''}{cp.toFixed(2)}%
                    </span>
                    <ChevronRight
                        size={14}
                        className="text-slate-400 transition-transform"
                        style={{ transform: expanded ? 'rotate(90deg)' : 'none' }}
                    />
                </div>
            </button>

            {/* Stock tiles grid */}
            {expanded && (
                <div className="p-3 grid gap-2"
                    style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(100px, 1fr))' }}>
                    {stocks.map(s => (
                        <StockTile key={s.ticker} stock={s} onClick={onStockClick} />
                    ))}
                </div>
            )}
        </div>
    );
}

// ─────────────────────────────────────────────────────────────
// Peer Comparison Panel
// ─────────────────────────────────────────────────────────────
function PeerPanel({ ticker, onClose }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        setLoading(true);
        axios.get(`${API_URL}/api/stocks/${ticker}/peers`)
            .then(r => setData(r.data))
            .catch(() => { })
            .finally(() => setLoading(false));
    }, [ticker]);

    if (loading) return (
        <div className="glass-panel p-6 flex items-center justify-center h-48">
            <RefreshCw size={20} className="text-violet-400 animate-spin" />
        </div>
    );
    if (!data) return null;

    const all = data.self ? [data.self, ...data.peers] : data.peers;
    const selfTicker = data.ticker;

    const formatMC = v => {
        if (!v) return '—';
        if (v >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
        if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
        if (v >= 1e7) return `${(v / 1e7).toFixed(0)}Cr`;
        return '—';
    };

    return (
        <div className="glass-panel p-5 space-y-4">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <BarChart2 size={16} className="text-indigo-400" />
                    <h3 className="text-slate-800 font-bold text-sm">
                        Peer Comparison · <span className="text-indigo-500">{data.sector}</span>
                    </h3>
                </div>
                <button onClick={onClose} className="text-slate-400 hover:text-slate-700 text-xs">✕ Close</button>
            </div>

            <div className="overflow-x-auto">
                <table className="w-full text-xs">
                    <thead>
                        <tr className="text-slate-400 uppercase text-[9px] font-bold tracking-wider border-b border-slate-100">
                            <th className="text-left pb-2 pr-3">Stock</th>
                            <th className="text-right pb-2 pr-3">Price</th>
                            <th className="text-right pb-2 pr-3">Change</th>
                            <th className="text-right pb-2 pr-3">Mkt Cap</th>
                            <th className="text-right pb-2">RSI</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                        {all.map(row => {
                            const isSelf = row.ticker === selfTicker;
                            const cp = row.change_percent;
                            return (
                                <tr key={row.ticker}
                                    className="transition-colors hover:bg-slate-50/50"
                                    style={isSelf ? { background: 'rgba(99,102,241,0.05)' } : {}}>
                                    <td className="py-2.5 pr-3">
                                        <div className="flex items-center gap-2">
                                            {isSelf && (
                                                <span className="text-[9px] bg-indigo-100 text-indigo-600 px-1.5 py-0.5 rounded font-bold">YOU</span>
                                            )}
                                            <div>
                                                <div className={`font-bold ${isSelf ? 'text-indigo-600' : 'text-slate-800'}`}>
                                                    {row.ticker}
                                                </div>
                                                <div className="text-[9px] text-slate-400 truncate max-w-[110px]">{row.name}</div>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="py-2.5 pr-3 text-right font-mono font-semibold text-slate-700">
                                        ₹{Number(row.current_price).toLocaleString('en-IN')}
                                    </td>
                                    <td className="py-2.5 pr-3 text-right font-mono font-bold"
                                        style={{ color: pctColor(cp) }}>
                                        {cp > 0 ? '+' : ''}{cp.toFixed(2)}%
                                    </td>
                                    <td className="py-2.5 pr-3 text-right text-slate-500">{formatMC(row.market_cap)}</td>
                                    <td className="py-2.5 text-right">
                                        {row.rsi != null ? (
                                            <span className="font-mono font-bold text-xs"
                                                style={{ color: row.rsi > 70 ? '#f43f5e' : row.rsi < 30 ? '#10b981' : '#6366f1' }}>
                                                {row.rsi}
                                            </span>
                                        ) : '—'}
                                    </td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────
// Sector Sidebar (top gainers/losers by sector)
// ─────────────────────────────────────────────────────────────
function SectorSidebar({ sectors }) {
    const sorted = Object.entries(sectors).sort((a, b) => b[1] - a[1]);
    return (
        <div className="glass-panel p-4 space-y-2">
            <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-500 mb-3">Sector Overview</h3>
            {sorted.map(([sec, avg]) => {
                const bar = Math.min(Math.abs(avg) / 3, 1) * 100;
                const isPos = avg >= 0;
                return (
                    <div key={sec} className="space-y-1">
                        <div className="flex justify-between items-center">
                            <span className="text-xs text-slate-700 font-medium truncate max-w-[120px]">{sec}</span>
                            <span className="text-xs font-mono font-bold" style={{ color: pctColor(avg) }}>
                                {avg > 0 ? '+' : ''}{avg.toFixed(2)}%
                            </span>
                        </div>
                        <div className="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                            <div
                                className="h-full rounded-full transition-all duration-500"
                                style={{
                                    width: `${bar}%`,
                                    background: isPos
                                        ? 'linear-gradient(90deg,#10b981,#34d399)'
                                        : 'linear-gradient(90deg,#f43f5e,#fb7185)',
                                    marginLeft: isPos ? '50%' : `${50 - bar}%`,
                                }}
                            />
                        </div>
                    </div>
                );
            })}
        </div>
    );
}

// ─────────────────────────────────────────────────────────────
// Main Page
// ─────────────────────────────────────────────────────────────
export default function SectorHeatmap({ onNavigateToForecast }) {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [selectedTicker, setSelectedTicker] = useState(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [lastUpdated, setLastUpdated] = useState(null);

    const load = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const res = await axios.get(`${API_URL}/api/market/heatmap`);
            setData(res.data);
            setLastUpdated(new Date());
        } catch {
            setError('Failed to load heatmap. Backend may be starting up.');
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { load(); }, [load]);

    // Group stocks by sector and apply search filter
    const grouped = React.useMemo(() => {
        if (!data?.stocks) return {};
        const q = searchQuery.toLowerCase();
        const filtered = q
            ? data.stocks.filter(s =>
                s.ticker.toLowerCase().includes(q) ||
                s.name.toLowerCase().includes(q) ||
                s.sector.toLowerCase().includes(q))
            : data.stocks;

        return filtered.reduce((acc, s) => {
            if (!acc[s.sector]) acc[s.sector] = [];
            acc[s.sector].push(s);
            return acc;
        }, {});
    }, [data, searchQuery]);

    // Sort sectors by absolute avg change
    const sortedSectors = Object.entries(grouped).sort((a, b) => {
        const avgA = a[1].reduce((s, x) => s + x.change_percent, 0) / a[1].length;
        const avgB = b[1].reduce((s, x) => s + x.change_percent, 0) / b[1].length;
        return Math.abs(avgB) - Math.abs(avgA);
    });

    const handleTileClick = (ticker) => {
        setSelectedTicker(t => t === ticker ? null : ticker);
    };

    const advancers = data?.stocks?.filter(s => s.change_percent > 0).length ?? 0;
    const decliners = data?.stocks?.filter(s => s.change_percent < 0).length ?? 0;
    const unchanged = (data?.stocks?.length ?? 0) - advancers - decliners;

    return (
        <div className="space-y-6 p-6">
            {/* Header */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
                <div>
                    <h1 className="text-2xl font-black text-slate-900 flex items-center gap-2">
                        <Grid3X3 size={22} className="text-violet-400" />
                        Sector Heatmap
                    </h1>
                    <p className="text-sm text-slate-500 mt-0.5">
                        Live market breadth across Indian sectors · {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : ''}
                    </p>
                </div>
                <div className="flex items-center gap-3">
                    {/* A/D counter */}
                    <div className="flex items-center gap-2 text-xs">
                        <span className="px-2 py-1 rounded-lg font-bold" style={{ background: 'rgba(16,185,129,0.1)', color: '#10b981' }}>▲ {advancers}</span>
                        <span className="px-2 py-1 rounded-lg font-bold" style={{ background: 'rgba(148,163,184,0.1)', color: '#94a3b8' }}>— {unchanged}</span>
                        <span className="px-2 py-1 rounded-lg font-bold" style={{ background: 'rgba(244,63,94,0.1)', color: '#f43f5e' }}>▼ {decliners}</span>
                    </div>
                    <button
                        onClick={load}
                        disabled={loading}
                        className="flex items-center gap-1.5 text-xs font-semibold px-3 py-2 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 transition-all"
                    >
                        <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
                        Refresh
                    </button>
                </div>
            </div>

            {/* Search bar */}
            <div className="relative max-w-xs">
                <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input
                    type="text"
                    placeholder="Filter by stock or sector…"
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                    className="w-full pl-8 pr-4 py-2 text-sm rounded-xl border border-slate-200 bg-white/60 focus:outline-none focus:ring-2 focus:ring-violet-300"
                />
            </div>

            {error && (
                <div className="text-red-500 text-sm bg-red-50 border border-red-100 rounded-xl p-3">{error}</div>
            )}

            {loading && !data && (
                <div className="flex items-center justify-center h-48 gap-3 text-slate-400">
                    <RefreshCw size={20} className="animate-spin text-violet-400" />
                    <span className="text-sm">Loading live market data…</span>
                </div>
            )}

            {data && (
                <div className="flex gap-5 items-start">
                    {/* Main heatmap */}
                    <div className="flex-1 space-y-4 min-w-0">
                        {sortedSectors.map(([sector, stocks]) => {
                            const avg = stocks.reduce((s, x) => s + x.change_percent, 0) / stocks.length;
                            return (
                                <SectorBand
                                    key={sector}
                                    name={sector}
                                    avg={avg}
                                    stocks={stocks}
                                    onStockClick={handleTileClick}
                                />
                            );
                        })}
                        {sortedSectors.length === 0 && (
                            <p className="text-center text-slate-400 text-sm py-12">No stocks match your filter.</p>
                        )}
                    </div>

                    {/* Sidebar */}
                    <div className="w-52 flex-shrink-0 space-y-4">
                        <SectorSidebar sectors={data.sectors} />
                    </div>
                </div>
            )}

            {/* Peer comparison drawer */}
            {selectedTicker && (
                <PeerPanel
                    ticker={selectedTicker}
                    onClose={() => setSelectedTicker(null)}
                />
            )}

            {/* "Open in Forecast" floating chip */}
            {selectedTicker && onNavigateToForecast && (
                <div className="fixed bottom-6 right-6 z-50">
                    <button
                        onClick={() => onNavigateToForecast(selectedTicker)}
                        className="flex items-center gap-2 px-4 py-3 rounded-2xl text-sm font-bold text-white shadow-xl transition-all hover:scale-105 active:scale-95"
                        style={{ background: 'linear-gradient(135deg,#6366f1,#8b5cf6)' }}
                    >
                        <TrendingUp size={15} />
                        Analyse {selectedTicker}
                        <ArrowUpRight size={13} />
                    </button>
                </div>
            )}
        </div>
    );
}
