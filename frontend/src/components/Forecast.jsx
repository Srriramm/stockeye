import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
    TrendingUp, TrendingDown, Minus, Search, RefreshCw,
    AlertTriangle, Target, BarChart2, Zap, Shield,
    ChevronRight, Info, Activity, Brain, Newspaper, CheckCircle, Lightbulb, Bot, Layers, ArrowUp, ArrowDown
} from 'lucide-react';
import axios from 'axios';
import { ComposedChart, Area, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import CandlestickChart, { PERIOD_MAP } from './CandlestickChart';

const PERIOD_OPTIONS = [
    { label: '7 Days', value: 7 },
    { label: '14 Days', value: 14 },
    { label: '30 Days', value: 30 },
    { label: '60 Days', value: 60 },
];

const POPULAR_TICKERS = ['RELIANCE', 'TCS', 'HDFC', 'INFY', 'ICICIBANK', 'BAJFINANCE', 'ITC', 'WIPRO', 'HDFCBANK', 'LT'];

export default function Forecast({ apiUrl }) {
    const [searchParams] = useSearchParams();
    const [ticker, setTicker] = useState('');
    const [selectedTicker, setSelectedTicker] = useState('');
    const [forecastDays, setForecastDays] = useState(30);
    const [forecastData, setForecastData] = useState(null);
    const [riskData, setRiskData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const [searchResults, setSearchResults] = useState([]);
    const [showDropdown, setShowDropdown] = useState(false);
    const [histChartData, setHistChartData] = useState([]);
    const [fcastChartData, setFcastChartData] = useState([]);
    const [histPeriod, setHistPeriod] = useState('3M');
    const [zones, setZones] = useState(null);

    // Compute Y-axis domain from actual lower/upper values — avoids stacked area pulling domain to 0
    const fcastYDomain = React.useMemo(() => {
        if (!fcastChartData.length) return ['auto', 'auto'];
        const vals = [];
        fcastChartData.forEach(d => {
            if (d.lower != null && !isNaN(d.lower)) vals.push(d.lower);
            if (d.upper != null && !isNaN(d.upper)) vals.push(d.upper);
            if (d.predicted != null && !isNaN(d.predicted)) vals.push(d.predicted);
        });
        if (!vals.length) return ['auto', 'auto'];
        const min = Math.min(...vals);
        const max = Math.max(...vals);
        const pad = (max - min) * 0.15;
        return [Math.floor(min - pad), Math.ceil(max + pad)];
    }, [fcastChartData]);
    const [histLoading, setHistLoading] = useState(false);
    const dropdownRef = useRef(null);
    const inputRef = useRef(null);

    // Close dropdown on outside click
    useEffect(() => {
        const handler = (e) => {
            if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
                setShowDropdown(false);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    // Debounced search effect
    useEffect(() => {
        const timer = setTimeout(async () => {
            if (ticker.length < 1) {
                setSearchResults([]);
                setShowDropdown(false);
                return;
            }
            // Don't search if we just selected this ticker from the list
            if (ticker === selectedTicker) return;

            try {
                const res = await axios.get(`${apiUrl}/api/stocks/search?q=${ticker}`);
                setSearchResults(res.data.results?.slice(0, 6) || []);
                setShowDropdown(true);
            } catch {
                setSearchResults([]);
            }
        }, 500);

        return () => clearTimeout(timer);
    }, [ticker, apiUrl, selectedTicker]);

    // Auto-load ticker from URL query param (e.g., /forecast?ticker=RELIANCE from alert panel)
    // This effect runs after render so selectStock/fetchForecast are fully initialized
    const urlTickerRef = useRef(null);
    useEffect(() => {
        const urlTicker = searchParams.get('ticker');
        if (urlTicker && urlTicker !== urlTickerRef.current) {
            urlTickerRef.current = urlTicker;
            selectStock(urlTicker);
        }
    }, [searchParams]); // eslint-disable-line

    const handleSearch = (q) => {
        setTicker(q);
        setShowDropdown(true);
    };

    const selectStock = async (t) => {
        setSelectedTicker(t);
        setTicker(t);
        setShowDropdown(false);
        setSearchResults([]);
        await fetchForecast(t, forecastDays);
    };

    const fetchHistory = async (t, period) => {
        const { period: yp, interval: yi } = PERIOD_MAP[period] || PERIOD_MAP['3M'];
        setHistLoading(true);
        try {
            const histRes = await axios.get(`${apiUrl}/api/stocks/${t}/history?period=${yp}&interval=${yi}`);
            const hist = (histRes.data.data || []).map(d => ({
                time: d.date,
                open: d.open,
                high: d.high,
                low: d.low,
                close: d.close
            }));
            setHistChartData(hist);
        } catch (err) {
            console.error('History fetch failed', err);
        } finally {
            setHistLoading(false);
        }
    };

    const handleHistPeriodChange = (p) => {
        setHistPeriod(p);
        if (selectedTicker) fetchHistory(selectedTicker, p);
    };

    const fetchForecast = async (t = selectedTicker, days = forecastDays) => {
        if (!t) return;
        setLoading(true);
        setError('');
        setForecastData(null);
        setRiskData(null);
        setZones(null);
        setHistChartData([]);
        setFcastChartData([]);


        try {
            const { period: yp, interval: yi } = PERIOD_MAP['3M'];
            const [forecastRes, riskRes, histRes, zonesRes] = await Promise.all([
                axios.get(`${apiUrl}/api/stocks/${t}/forecast?days=${days}`),
                axios.get(`${apiUrl}/api/stocks/${t}/risk-profile`),
                axios.get(`${apiUrl}/api/stocks/${t}/history?period=${yp}&interval=${yi}`),
                axios.get(`${apiUrl}/api/stocks/${t}/zones?period=6mo`).catch(() => ({ data: null })),
            ]);
            setForecastData(forecastRes.data);
            setRiskData(riskRes.data);
            setZones(zonesRes.data);
            setHistPeriod('3M');

            const hist = (histRes.data.data || []).map(d => ({
                time: d.date,
                open: d.open,
                high: d.high,
                low: d.low,
                close: d.close
            }));
            setHistChartData(hist);

            // Forecast data for recharts ComposedChart — preserve upper/lower confidence bands
            const fcast = (forecastRes.data.forecast || []).map(d => ({
                date: d.date,
                predicted: d.predicted,
                upper: d.upper,
                lower: d.lower,
            }));
            setFcastChartData(fcast);
        } catch (err) {
            setError(err.response?.data?.error || 'Failed to fetch forecast. Please try again.');
        } finally {
            setLoading(false);
        }
    };

    const handlePeriodChange = (days) => {
        setForecastDays(days);
        if (selectedTicker) fetchForecast(selectedTicker, days);
    };

    const signalConfig = {
        BUY: { color: '#10b981', bg: 'from-emerald-500/10 to-emerald-600/5', border: 'border-emerald-500/20', icon: TrendingUp, text: 'text-emerald-400', label: 'BUY' },
        SELL: { color: '#f43f5e', bg: 'from-rose-500/10 to-rose-600/5', border: 'border-rose-500/20', icon: TrendingDown, text: 'text-rose-400', label: 'SELL' },
        HOLD: { color: '#f59e0b', bg: 'from-amber-500/10 to-amber-600/5', border: 'border-amber-500/20', icon: Minus, text: 'text-amber-400', label: 'HOLD' },
    };

    const riskColors = { Low: '#10b981', Medium: '#f59e0b', High: '#f97316', 'Very High': '#ef4444' };

    const formatINR = (v) => {
        if (!v) return '₹0';
        if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)}Cr`;
        if (v >= 1e5) return `₹${(v / 1e5).toFixed(2)}L`;
        return `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
    };

    const CustomTooltip = ({ active, payload, label }) => {
        if (!active || !payload?.length) return null;
        return (
            <div className="bg-white/90 backdrop-blur-md border border-slate-200 rounded-xl p-4 shadow-xl">
                <p className="text-slate-500 text-xs mb-2 font-mono">{label}</p>
                {payload.map((p, i) => p.value != null && (
                    <div key={i} className="flex items-center gap-3 mb-1 last:mb-0">
                        <span className="w-2 h-2 rounded-full" style={{ background: p.color }}></span>
                        <span className="text-slate-600 text-xs w-20">{p.name}:</span>
                        <span className="text-slate-800 text-sm font-bold font-mono-nums">
                            ₹{Number(p.value).toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                        </span>
                    </div>
                ))}
            </div>
        );
    };

    const sig = forecastData ? signalConfig[forecastData.signal] || signalConfig.HOLD : null;

    return (
        <div className="p-8 space-y-8 fade-in max-w-[1600px] mx-auto min-h-screen">
            {/* Header Area */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
                <div>
                    <h1 className="text-2xl font-bold text-slate-800 tracking-tight flex items-center gap-3">
                        <Brain size={24} className="text-indigo-400" />
                        AI Stock Forecast
                    </h1>
                    <p className="text-slate-500 text-sm mt-1 ml-9 max-w-xl leading-relaxed">
                        Institutional-grade analysis combining technicals, ML forecasting, and news sentiment processing.
                    </p>
                </div>

                {/* Search Bar */}
                <div className="relative w-full md:w-[480px] z-50" ref={dropdownRef}>
                    <div className={`flex items-center gap-3 bg-white/[0.03] backdrop-blur-xl border transition-all rounded-xl px-4 py-3 group focus-within:bg-white/[0.05] focus-within:border-indigo-500/50 focus-within:ring-2 focus-within:ring-indigo-500/20 ${showDropdown ? 'border-indigo-500/50 ring-2 ring-indigo-500/20 rounded-b-none' : 'border-slate-200 hover:border-white/20'}`}>
                        <Search size={18} className="text-slate-500 group-focus-within:text-indigo-400 transition-colors" />
                        <input
                            ref={inputRef}
                            type="text"
                            value={ticker}
                            onChange={(e) => handleSearch(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && ticker && selectStock(ticker.toUpperCase())}
                            placeholder="Search stock (e.g., RELIANCE, TCS)..."
                            className="flex-1 bg-transparent text-slate-800 text-base placeholder-slate-500 focus:outline-none font-medium tracking-wide"
                        />
                        {selectedTicker && (
                            <button
                                onClick={() => fetchForecast()}
                                className="p-1.5 hover:bg-white/10 rounded-lg text-slate-500 hover:text-slate-800 transition-all"
                                title="Refresh Analysis"
                            >
                                <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
                            </button>
                        )}
                        {ticker && (
                            <button
                                onClick={() => { setTicker(''); setSelectedTicker(''); setForecastData(null); setRiskData(null); inputRef.current?.focus(); }}
                                className="p-1 hover:bg-white/10 rounded-full text-slate-500 hover:text-slate-800 transition-colors"
                            >
                                <span className="sr-only">Clear</span>
                                <PlusIcon className="rotate-45" size={16} />
                            </button>
                        )}
                    </div>

                    {/* Suggestions Dropdown */}
                    {showDropdown && searchResults.length > 0 && (
                        <div className="absolute top-full left-0 right-0 bg-[#0f172a] border-x border-b border-indigo-500/30 rounded-b-xl shadow-2xl overflow-hidden z-[60]">
                            {searchResults.map((r, i) => (
                                <button
                                    key={i}
                                    onClick={() => selectStock(r.ticker)}
                                    className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/[0.04] transition-colors text-left border-b border-slate-100 last:border-0 group"
                                >
                                    <div>
                                        <div className="flex items-center gap-2">
                                            <span className="text-slate-800 font-bold text-sm tracking-wide group-hover:text-indigo-400 transition-colors">{r.ticker}</span>
                                            <span className="px-1.5 py-0.5 rounded text-[10px] bg-white/5 text-slate-500 border border-slate-100">{r.exchDisp || 'NSE'}</span>
                                        </div>
                                        <span className="text-slate-500 text-xs block mt-0.5">{r.name}</span>
                                    </div>
                                    <ChevronRight size={14} className="text-slate-700 group-hover:text-indigo-400 transition-colors" />
                                </button>
                            ))}
                        </div>
                    )}
                </div>
            </div>

            {/* Empty State / Popular Tickers */}
            {!selectedTicker && !loading && (
                <div className="flex flex-col items-center justify-center py-24 animate-in fade-in slide-in-from-bottom-4 duration-700">
                    <div className="w-24 h-24 bg-gradient-to-br from-indigo-500/10 to-blue-500/5 rounded-3xl flex items-center justify-center mb-8 border border-indigo-500/20 shadow-2xl shadow-indigo-500/10">
                        <BarChart2 size={40} className="text-indigo-400" />
                    </div>
                    <h3 className="text-slate-800 font-bold text-2xl tracking-tight mb-3">Begin Market Analysis</h3>
                    <p className="text-slate-500 text-base max-w-md text-center mb-10 leading-relaxed">
                        Select a popular stock below or use the search bar to access real-time ML forecasts and risk metrics.
                    </p>

                    <div className="flex flex-wrap justify-center gap-3 max-w-3xl">
                        {POPULAR_TICKERS.map(t => (
                            <button
                                key={t}
                                onClick={() => selectStock(t)}
                                className="px-4 py-2 text-xs font-semibold bg-white/[0.03] hover:bg-indigo-500/10 border border-slate-200 hover:border-indigo-500/30 text-slate-600 hover:text-indigo-300 rounded-full transition-all active:scale-95"
                            >
                                {t}
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {/* Error State */}
            {error && (
                <div className="glass-panel p-4 border-l-4 border-l-red-500 flex items-start gap-4 rounded-r-xl">
                    <div className="p-2 bg-red-500/10 rounded-lg">
                        <AlertTriangle size={20} className="text-red-400" />
                    </div>
                    <div>
                        <h4 className="text-red-400 font-bold text-sm">Analysis Failed</h4>
                        <p className="text-red-200/60 text-sm mt-1">{error}</p>
                    </div>
                </div>
            )}

            {/* Loading State */}
            {loading && (
                <div className="flex flex-col items-center justify-center py-32 gap-8 animate-in fade-in duration-500">
                    <div className="relative">
                        <div className="w-20 h-20 border-2 border-indigo-500/10 rounded-full" />
                        <div className="absolute inset-0 border-2 border-indigo-500/80 border-t-transparent rounded-full animate-spin" />
                        <div className="absolute inset-0 flex items-center justify-center">
                            <Brain size={24} className="text-indigo-400 animate-pulse" />
                        </div>
                    </div>
                    <div className="text-center space-y-2">
                        <h3 className="text-slate-800 font-bold text-lg tracking-wide">Processing Market Data</h3>
                        <div className="flex items-center gap-2 text-slate-500 text-sm justify-center">
                            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse"></span>
                            <span>Crunching technicals</span>
                            <span className="w-1.5 h-1.5 rounded-full bg-slate-100"></span>
                            <span>Running ML models</span>
                            <span className="w-1.5 h-1.5 rounded-full bg-slate-100"></span>
                            <span>Analyzing news</span>
                        </div>
                    </div>
                </div>
            )}

            {/* Forecast Content */}
            {forecastData && !loading && (
                <div className="space-y-6 animate-in fade-in slide-in-from-bottom-8 duration-700">

                    {/* Top Controls Row */}
                    <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                        <div className="flex items-center gap-4">
                            <h2 className="text-3xl font-bold text-slate-800 tracking-tight">{selectedTicker}</h2>
                            <span className="px-2.5 py-1 rounded bg-white/5 border border-slate-100 text-xs font-mono text-slate-500">NSE</span>
                        </div>
                        <div className="flex gap-1 bg-white/[0.03] p-1 rounded-lg border border-slate-100">
                            {PERIOD_OPTIONS.map(({ label, value }) => (
                                <button
                                    key={value}
                                    onClick={() => handlePeriodChange(value)}
                                    className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${forecastDays === value
                                        ? 'bg-indigo-600/90 text-slate-800 shadow-lg shadow-indigo-500/20'
                                        : 'text-slate-500 hover:text-slate-800 hover:bg-white/5'
                                        }`}
                                >
                                    {label}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Signal + Kpi Cards */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {/* Signal Card */}
                        <div className={`glass-panel p-6 bg-gradient-to-br ${sig.bg} border ${sig.border}`}>
                            <div className="flex justify-between items-start mb-4">
                                <div className="space-y-1">
                                    <span className="text-slate-500 text-xs font-bold uppercase tracking-wider">Algorithmic Signal</span>
                                    <div className="flex items-center gap-2">
                                        <h3 className={`text-4xl font-black tracking-tight ${sig.text}`}>{forecastData.signal}</h3>
                                    </div>
                                </div>
                                <div className={`w-12 h-12 rounded-xl flex items-center justify-center border ${sig.border} bg-slate-100`}>
                                    <sig.icon size={24} className={sig.text} />
                                </div>
                            </div>
                            <div className="flex items-center gap-2 mt-2">
                                <div className="h-1.5 flex-1 bg-slate-100 rounded-full overflow-hidden">
                                    <div
                                        className={`h-full rounded-full ${sig.text.replace('text-', 'bg-')}`}
                                        style={{ width: `${forecastData.confidence}%` }}
                                    />
                                </div>
                                <span className="text-xs font-mono font-bold text-slate-600">{forecastData.confidence}% Conf.</span>
                            </div>
                        </div>

                        {/* Target Price Card */}
                        <div className="glass-panel p-6">
                            <div className="flex items-center gap-2 mb-4">
                                <Target size={16} className="text-sky-600" />
                                <span className="text-slate-500 text-xs font-bold uppercase tracking-wider">
                                    {forecastDays}-Day Target
                                </span>
                            </div>
                            <div className="flex items-baseline gap-3">
                                <span className="text-4xl font-bold text-slate-800 font-mono-nums tracking-tight">
                                    {formatINR(forecastData.target_price)}
                                </span>
                                <div className={`flex items-center gap-1 text-sm font-bold px-2 py-0.5 rounded ${forecastData.trend_pct >= 0 ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                                    {forecastData.trend_pct >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                                    {forecastData.trend_pct >= 0 ? '+' : ''}{forecastData.trend_pct?.toFixed(2)}%
                                </div>
                            </div>
                            <div className="mt-3 text-xs text-slate-500 font-mono">
                                Current: <span className="text-slate-600">{formatINR(forecastData.current_price)}</span>
                            </div>
                        </div>

                        {/* Model Confidence Card */}
                        <div className="glass-panel p-6">
                            <div className="flex items-center gap-2 mb-4">
                                <Zap size={16} className="text-amber-400" />
                                <span className="text-slate-500 text-xs font-bold uppercase tracking-wider">Brain Confidence</span>
                            </div>

                            <div className="flex items-end justify-between mb-2">
                                <span className="text-4xl font-bold text-slate-800 font-mono-nums">{forecastData.weighted_score}<span className="text-lg text-slate-500 font-normal">/100</span></span>
                                <span className="text-xs text-slate-500 bg-white/5 px-2 py-1 rounded border border-slate-100">
                                    {forecastData.method?.replace(/_/g, ' ')}
                                </span>
                            </div>

                            <div className="w-full bg-white/5 rounded-full h-2 mt-3">
                                <div
                                    className="h-2 rounded-full transition-all duration-1000 ease-out"
                                    style={{
                                        width: `${forecastData.weighted_score ?? forecastData.confidence}%`,
                                        background: 'linear-gradient(90deg, #ec4899, #8b5cf6)'
                                    }}
                                />
                            </div>
                        </div>
                    </div>

                    {/* Panel 1: Price History */}
                    <div className="glass-panel p-6 pb-4 relative">
                        <h3 className="text-slate-800 font-bold text-sm flex items-center gap-2 mb-4">
                            <Activity size={16} className="text-emerald-400" /> Price History
                        </h3>
                        {histLoading && (
                            <div className="absolute inset-0 flex items-center justify-center bg-white/60 z-10 rounded-xl">
                                <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                            </div>
                        )}
                        <CandlestickChart
                            data={histChartData}
                            height={300}
                            selectedPeriod={histPeriod}
                            onPeriodChange={handleHistPeriodChange}
                        />
                    </div>

                    {/* Panel 2: ML Forecast Projection */}
                    {fcastChartData.length > 0 && (
                        <div className="glass-panel p-6">
                            <div className="flex justify-between items-start mb-6">
                                <div>
                                    <h3 className="text-slate-800 font-bold text-sm flex items-center gap-2">
                                        <Zap size={16} className="text-purple-400" /> ML Forecast Projection
                                    </h3>
                                    <p className="text-slate-500 text-xs mt-1">
                                        {forecastDays}-day price projection with 80% confidence interval
                                    </p>
                                </div>
                                <div className="flex items-center gap-4 text-[10px] font-medium">
                                    <div className="flex items-center gap-1.5">
                                        <span className="w-8 h-0.5 bg-purple-500" />
                                        <span className="text-slate-500">Predicted</span>
                                    </div>
                                    <div className="flex items-center gap-1.5">
                                        <span className="w-3 h-3 rounded-sm bg-indigo-500/20 border border-indigo-500/30" />
                                        <span className="text-slate-500">Confidence Band</span>
                                    </div>
                                </div>
                            </div>
                            <ResponsiveContainer width="100%" height={260}>
                                <ComposedChart data={fcastChartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                                    <defs>
                                        <linearGradient id="bandGrad" x1="0" y1="0" x2="0" y2="1">
                                            <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                                            <stop offset="95%" stopColor="#6366f1" stopOpacity={0.12} />
                                        </linearGradient>
                                    </defs>
                                    <XAxis
                                        dataKey="date"
                                        tick={{ fill: '#64748b', fontSize: 10 }}
                                        axisLine={false}
                                        tickLine={false}
                                        dy={8}
                                        minTickGap={40}
                                    />
                                    <YAxis
                                        tick={{ fill: '#64748b', fontSize: 10 }}
                                        tickFormatter={v => formatINR(v)}
                                        axisLine={false}
                                        tickLine={false}
                                        dx={-6}
                                        domain={fcastYDomain}
                                        width={80}
                                    />
                                    <Tooltip
                                        content={({ active, payload, label }) => {
                                            if (!active || !payload?.length) return null;
                                            const pred = payload.find(p => p.dataKey === 'predicted');
                                            if (!pred) return null;
                                            const d = pred.payload;
                                            return (
                                                <div style={{ background: 'rgba(15,23,42,0.97)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, padding: '10px 14px', fontSize: 12 }}>
                                                    <p style={{ color: '#94a3b8', fontSize: 11, marginBottom: 8 }}>{label}</p>
                                                    <p style={{ color: '#f1f5f9', fontWeight: 600 }}>Forecast: {formatINR(pred.value)}</p>
                                                    {d.upper != null && d.lower != null && (
                                                        <p style={{ color: '#6366f1', fontSize: 10, marginTop: 4 }}>
                                                            80% band: {formatINR(d.lower)} – {formatINR(d.upper)}
                                                        </p>
                                                    )}
                                                </div>
                                            );
                                        }}
                                    />
                                    {/* Upper bound — fills from domain min up to upper with indigo gradient */}
                                    <Area type="monotone" dataKey="upper" baseValue={typeof fcastYDomain[0] === 'number' ? fcastYDomain[0] : 'dataMin'} stroke="none" fill="url(#bandGrad)" legendType="none" dot={false} activeDot={false} />
                                    {/* Cover area — fills from domain min up to lower, hiding the gradient below the band */}
                                    <Area type="monotone" dataKey="lower" baseValue={typeof fcastYDomain[0] === 'number' ? fcastYDomain[0] : 'dataMin'} stroke="none" fill="#020617" legendType="none" dot={false} activeDot={false} />
                                    {/* Predicted price line */}
                                    <Line type="monotone" dataKey="predicted" stroke="#a855f7" strokeWidth={2} dot={false}
                                        activeDot={{ r: 4, fill: '#a855f7', strokeWidth: 0 }} />
                                    {forecastData?.current_price && (
                                        <ReferenceLine y={forecastData.current_price} stroke="#64748b" strokeDasharray="4 3"
                                            label={{ value: 'Now', position: 'insideTopLeft', fill: '#64748b', fontSize: 9 }} />
                                    )}
                                    {forecastData?.target_price && (
                                        <ReferenceLine y={forecastData.target_price} stroke="#10b981" strokeDasharray="4 3"
                                            label={{ value: 'Target', position: 'insideTopLeft', fill: '#10b981', fontSize: 9 }} />
                                    )}
                                </ComposedChart>
                            </ResponsiveContainer>
                        </div>
                    )}

                    {/* ── Smart Entry/Exit Zones Panel ── */}
                    {zones && <ZonesPanel zones={zones} formatINR={formatINR} />}

                    {/* ─── AI EVIDENCE PANELS ─────────────────────────────── */}

                    {/* 1. AI Narrative */}
                    {forecastData.ai_narrative && (
                        <div className="glass-panel p-6 bg-gradient-to-r from-indigo-500/10 to-blue-500/5 border-l-4 border-l-indigo-500">
                            <div className="flex items-center gap-2 mb-3">
                                <Bot size={18} className="text-indigo-400" />
                                <span className="text-slate-800 font-bold text-sm tracking-wide uppercase">AI Executive Summary</span>
                                <span className="ml-auto text-[10px] font-mono font-medium px-2 py-0.5 bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 rounded">
                                    {forecastData.method === 'prophet' ? 'GPT-4o + PROPHET' : 'ENSEMBLE ML'}
                                </span>
                            </div>
                            <p className="text-slate-700 text-sm leading-7 font-light tracking-wide">
                                {forecastData.ai_narrative}
                            </p>
                        </div>
                    )}

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                        {/* 2. Evidence Breakdown */}
                        {forecastData.score_breakdown && (
                            <div className="glass-panel p-6">
                                <div className="flex items-center justify-between mb-6">
                                    <div className="flex items-center gap-2">
                                        <Lightbulb size={16} className="text-amber-400" />
                                        <h3 className="text-slate-800 font-bold text-sm">Signal Contributors</h3>
                                    </div>
                                    <span className="text-xs font-mono text-slate-500">Composite Weighting</span>
                                </div>
                                <div className="space-y-4">
                                    {Object.entries(forecastData.score_breakdown).map(([key, v]) => (
                                        <EvidenceBar
                                            key={key}
                                            label={v.label}
                                            score={v.score}
                                            weight={Math.round(v.weight * 100)}
                                        />
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* 3. News Sentiment */}
                        {forecastData.news_sentiment && forecastData.news_sentiment.total > 0 && (
                            <NewsPanel news={forecastData.news_sentiment} />
                        )}

                    </div>

                    {/* 4. Technical Indicators */}
                    {forecastData.technical_indicators && (
                        <TechnicalPanel indicators={forecastData.technical_indicators} />
                    )}

                    {/* 5. Backtest & Stats Row */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {/* Model Transparency */}
                        {forecastData.backtest && (
                            <BacktestPanel backtest={forecastData.backtest} method={forecastData.method} />
                        )}

                        {/* Risk Profile */}
                        {riskData && !riskData.error && (
                            <div className="glass-panel p-6">
                                <div className="flex items-center justify-between mb-5">
                                    <div className="flex items-center gap-2">
                                        <Shield size={16} className="text-emerald-400" />
                                        <h3 className="text-slate-800 font-bold text-sm">Risk Assessment</h3>
                                    </div>
                                    <span
                                        className="px-2.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider"
                                        style={{
                                            color: riskColors[riskData.risk_tier] || '#64748b',
                                            background: `${riskColors[riskData.risk_tier]}15`,
                                            border: `1px solid ${riskColors[riskData.risk_tier]}30`,
                                        }}
                                    >
                                        {riskData.risk_tier} Volatility
                                    </span>
                                </div>
                                <div className="grid grid-cols-3 gap-3">
                                    <RiskMetric label="Beta" value={riskData.beta?.toFixed(2)} />
                                    <RiskMetric label="Sharpe" value={riskData.sharpe_ratio?.toFixed(2)} />
                                    <RiskMetric label="Max DD" value={`${riskData.max_drawdown_pct?.toFixed(1)}%`} valueColor="text-rose-400" />
                                    <RiskMetric label="1D VaR" value={`${riskData.var_95_pct?.toFixed(2)}%`} valueColor="text-amber-400" />
                                    <RiskMetric label="Vol (Ann)" value={`${riskData.annual_volatility_pct?.toFixed(1)}%`} />
                                    <RiskMetric label="Points" value={riskData.data_points} />
                                </div>
                                <div className="mt-4 pt-4 border-t border-slate-100">
                                    <h4 className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Risk Summary</h4>
                                    <p className="text-slate-500 text-xs leading-relaxed">{riskData.risk_description}</p>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Key Levels Footer */}
                    {forecastData.key_levels && (
                        <div className="glass-panel px-6 py-4 flex flex-wrap justify-between items-center gap-4">
                            <div className="flex items-center gap-2">
                                <Activity size={16} className="text-slate-500" />
                                <span className="text-xs text-slate-500 uppercase font-bold tracking-wider">Key Levels</span>
                            </div>
                            <div className="flex items-center gap-6 text-sm font-mono-nums">
                                <div className="flex items-center gap-2">
                                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                                    <span className="text-slate-500 text-xs">Support</span>
                                    <span className="text-emerald-400 font-bold">{formatINR(forecastData.key_levels.support)}</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
                                    <span className="text-slate-500 text-xs">Pivot</span>
                                    <span className="text-sky-600 font-bold">{formatINR(forecastData.key_levels.pivot)}</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                                    <span className="text-slate-500 text-xs">Resist</span>
                                    <span className="text-rose-400 font-bold">{formatINR(forecastData.key_levels.resistance)}</span>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

function RiskMetric({ label, value, valueColor = 'text-slate-800' }) {
    return (
        <div className="bg-white/[0.03] rounded-lg p-2.5 text-center border border-slate-100">
            <div className="text-slate-500 text-[10px] uppercase font-bold tracking-wider mb-1">{label}</div>
            <div className={`font-mono font-bold text-sm ${valueColor}`}>{value}</div>
        </div>
    );
}
// Using PlusIcon as a clear icon (rotated)
const PlusIcon = ({ size, className, ...props }) => (
    <svg
        xmlns="http://www.w3.org/2000/svg"
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={className}
        {...props}
    >
        <path d="M5 12h14" />
        <path d="M12 5v14" />
    </svg>
);

// ─── Evidence Bar ────────────────────────────────────────────────
function EvidenceBar({ label, score, weight }) {
    const color = score >= 65 ? '#10b981' : score >= 45 ? '#f59e0b' : '#f43f5e';
    return (
        <div>
            <div className="flex justify-between items-center mb-1.5">
                <span className="text-slate-500 text-xs font-medium">{label}</span>
                <span className="text-xs text-slate-500 font-mono">
                    <span className="font-bold" style={{ color }}>{score}</span>
                    <span className="opacity-50">/100</span>
                    <span className="text-slate-600 ml-2 text-[10px]">({weight}% w)</span>
                </span>
            </div>
            <div className="w-full bg-slate-100/50 rounded-full h-1.5 shadow-inner border border-slate-100">
                <div
                    className="h-1.5 rounded-full transition-all duration-1000 ease-out shadow-[0_0_10px_rgba(0,0,0,0.3)]"
                    style={{ width: `${score}%`, background: color }}
                />
            </div>
        </div>
    );
}

// ─── Technical Indicators Panel ──────────────────────────────────
function TechnicalPanel({ indicators: ind }) {
    const rsiColor = ind.rsi < 30 ? '#10b981' : ind.rsi > 70 ? '#f43f5e' : '#f59e0b';
    const macdColor = ind.macd_direction === 'bullish' ? '#10b981' : '#f43f5e';
    const trendMap = {
        strong_bullish: { label: 'Strong Bullish', color: '#10b981' },
        bullish: { label: 'Bullish', color: '#34d399' },
        neutral: { label: 'Neutral', color: '#f59e0b' },
        bearish: { label: 'Bearish', color: '#f97316' },
        strong_bearish: { label: 'Strong Bearish', color: '#f43f5e' },
    };
    const trend = trendMap[ind.trend] || { label: ind.trend, color: '#6b7280' };

    return (
        <div className="glass-panel p-6">
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                    <Activity size={16} className="text-emerald-400" />
                    <h3 className="text-slate-800 font-bold text-sm">Technical Signals</h3>
                </div>
                <span className="text-[10px] font-mono font-bold px-2 py-0.5 bg-white/5 text-slate-600 border border-slate-200 rounded">
                    TECH SCORE: {ind.score}
                </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {/* RSI */}
                <div className="bg-white/[0.02] rounded-xl p-4 text-center border border-slate-100 hover:bg-white/[0.04] transition-colors">
                    <div className="text-slate-500 text-[10px] uppercase font-bold tracking-wider mb-1">RSI (14)</div>
                    <div className="text-2xl font-black font-mono-nums" style={{ color: rsiColor }}>{ind.rsi?.toFixed(1) ?? 'N/A'}</div>
                    <div className="text-[10px] font-bold mt-1 uppercase" style={{ color: rsiColor }}>{ind.rsi_signal?.replace('-', ' ')}</div>
                </div>
                {/* MACD */}
                <div className="bg-white/[0.02] rounded-xl p-4 text-center border border-slate-100 hover:bg-white/[0.04] transition-colors">
                    <div className="text-slate-500 text-[10px] uppercase font-bold tracking-wider mb-1">MACD</div>
                    <div className="text-lg font-black font-mono-nums" style={{ color: macdColor }}>{ind.macd?.toFixed(2) ?? 'N/A'}</div>
                    <div className="text-[10px] font-bold mt-1 uppercase" style={{ color: macdColor }}>{ind.macd_direction}</div>
                </div>
                {/* Bollinger */}
                <div className="bg-white/[0.02] rounded-xl p-4 text-center border border-slate-100 hover:bg-white/[0.04] transition-colors">
                    <div className="text-slate-500 text-[10px] uppercase font-bold tracking-wider mb-1">Bollinger</div>
                    <div className="text-xs font-bold text-slate-600 mt-1 mb-1">
                        {ind.bb_position === 'above_upper' ? 'Above Upper' :
                            ind.bb_position === 'below_lower' ? 'Below Lower' : 'Inside Bands'}
                    </div>
                    <div className="text-[10px] text-slate-500 font-mono-nums">
                        ₹{ind.bb_lower?.toFixed(0)} — ₹{ind.bb_upper?.toFixed(0)}
                    </div>
                </div>
                {/* SMA Trend */}
                <div className="bg-white/[0.02] rounded-xl p-4 text-center border border-slate-100 hover:bg-white/[0.04] transition-colors">
                    <div className="text-slate-500 text-[10px] uppercase font-bold tracking-wider mb-1">Trend (SMA)</div>
                    <div className="text-xs font-bold mt-1 mb-1 uppercase" style={{ color: trend.color }}>{trend.label}</div>
                    {ind.sma_50 && <div className="text-[10px] text-slate-500 font-mono-nums">SMA50: ₹{ind.sma_50?.toFixed(0)}</div>}
                </div>
            </div>
        </div>
    );
}

// ─── News Sentiment Panel ─────────────────────────────────────────
function NewsPanel({ news }) {
    const sentimentDot = { positive: '#10b981', negative: '#f43f5e', neutral: '#f59e0b' };
    const labelColor = news.label === 'Positive' ? 'text-emerald-400' : news.label === 'Negative' ? 'text-rose-400' : 'text-amber-400';
    const labelBg = news.label === 'Positive' ? 'bg-emerald-400/10 border-emerald-400/20' : news.label === 'Negative' ? 'bg-rose-400/10 border-rose-400/20' : 'bg-amber-400/10 border-amber-400/20';

    return (
        <div className="glass-panel p-6 flex flex-col">
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                    <Newspaper size={16} className="text-sky-600" />
                    <h3 className="text-slate-800 font-bold text-sm">Media Sentiment</h3>
                </div>
                <span className={`text-[10px] uppercase px-2 py-0.5 border rounded-full font-bold tracking-wide ${labelColor} ${labelBg}`}>
                    {news.label}
                </span>
            </div>

            {/* Score bar */}
            <div className="flex items-center gap-3 mb-6">
                <span className="text-[10px] font-bold uppercase text-emerald-500/80 w-12 text-right">Bullish</span>
                <div className="flex-1 bg-slate-100/50 rounded-full h-2 shadow-inner border border-slate-100 overflow-hidden">
                    <div
                        className="h-full rounded-full transition-all duration-1000 ease-out"
                        style={{
                            width: `${news.score}%`,
                            background: news.score >= 60 ? '#10b981' : news.score >= 40 ? '#f59e0b' : '#f43f5e',
                        }}
                    />
                </div>
                <span className="text-[10px] font-bold uppercase text-rose-500/80 w-12">Bearish</span>
            </div>

            {/* Headlines */}
            <div className="flex-1 space-y-2 overflow-y-auto max-h-[220px] custom-scrollbar pr-2">
                {news.articles?.slice(0, 5).map((a, i) => (
                    <a key={i} href={a.link} target="_blank" rel="noopener noreferrer" className="flex items-start gap-3 py-2.5 px-2 hover:bg-white/5 rounded-lg transition-colors group border border-transparent hover:border-slate-100">
                        <div
                            className="w-1.5 h-1.5 rounded-full mt-2 flex-shrink-0 shadow-[0_0_8px_rgba(0,0,0,0.5)]"
                            style={{ background: sentimentDot[a.sentiment] || '#6b7280' }}
                        />
                        <div className="flex-1 min-w-0">
                            <h4 className="text-slate-600 text-xs font-medium leading-snug group-hover:text-sky-600 transition-colors line-clamp-2">
                                {a.title}
                            </h4>
                            <div className="flex items-center gap-2 mt-1">
                                <span className="text-[10px] text-slate-500 font-mono">{a.source}</span>
                                <span className="text-[10px] text-slate-600">•</span>
                                <span className="text-[10px] text-slate-500 capitalize">{a.sentiment}</span>
                            </div>
                        </div>
                    </a>
                ))}
            </div>
        </div>
    );
}

// ─── Backtest / Model Transparency Panel ─────────────────────────
function BacktestPanel({ backtest: bt, method }) {
    const mapeColor = bt.mape === null ? '#6b7280'
        : bt.mape < 3 ? '#10b981'
            : bt.mape < 7 ? '#f59e0b'
                : '#f43f5e';
    const mapeLabel = bt.mape === null ? 'N/A'
        : bt.mape < 3 ? 'High Precision'
            : bt.mape < 7 ? 'Standard'
                : 'Low Precision';
    const modelName = method?.replace(/_/g, ' ').toUpperCase() ?? 'ML Model';

    return (
        <div className="glass-panel p-6">
            <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-2">
                    <CheckCircle size={16} className="text-purple-400" />
                    <h3 className="text-slate-800 font-bold text-sm">Model Integrity</h3>
                </div>
                <span className="text-[10px] text-slate-500 bg-slate-100 px-2 py-0.5 rounded border border-slate-100 font-mono">
                    Holdout: {bt.holdout_days}d
                </span>
            </div>

            <div className="grid grid-cols-3 gap-4 mb-4">
                <div className="bg-white/[0.02] rounded-xl p-3 text-center border border-slate-100">
                    <div className="text-slate-500 text-[10px] uppercase font-bold tracking-wider mb-1">Validation</div>
                    <div className="text-xl font-black font-mono-nums" style={{ color: mapeColor }}>
                        {bt.mape !== null ? `${bt.mape}%` : '—'}
                    </div>
                    <div className="text-[10px] font-bold mt-1 uppercase opacity-80" style={{ color: mapeColor }}>{mapeLabel} (MAPE)</div>
                </div>
                <div className="bg-white/[0.02] rounded-xl p-3 text-center border border-slate-100">
                    <div className="text-slate-500 text-[10px] uppercase font-bold tracking-wider mb-1">Architecture</div>
                    <div className="text-xs font-bold text-slate-700 mt-2">{modelName}</div>
                    <div className="text-[10px] text-slate-600 mt-1">Ensemble</div>
                </div>
                <div className="bg-white/[0.02] rounded-xl p-3 text-center border border-slate-100">
                    <div className="text-slate-500 text-[10px] uppercase font-bold tracking-wider mb-1">Training</div>
                    <div className="text-xl font-black text-sky-600 font-mono-nums">{bt.data_points_trained ?? '—'}</div>
                    <div className="text-[10px] text-slate-600 mt-1">Data Points</div>
                </div>
            </div>
            <p className="text-slate-500 text-[10px] leading-relaxed italic border-t border-slate-100 pt-3">
                Current performance metrics derived from backtesting against unseen market data from the last {bt.holdout_days} sessions.
            </p>
        </div>
    );
}

// ─── Smart Entry/Exit Zones Panel ────────────────────────────────
function ZonesPanel({ zones, formatINR }) {
    if (!zones || zones.error) return null;

    const curr = zones.current_price;
    const supports = (zones.support_levels || []).slice(0, 4);
    const resistances = (zones.resistance_levels || []).slice(0, 4);
    const fibLevels = zones.fibonacci_levels || {};

    // Sort fib levels high → low for display
    const fibEntries = Object.entries(fibLevels)
        .map(([label, price]) => ({ label, price: Number(price) }))
        .sort((a, b) => b.price - a.price);

    const pctFrom = (p) => curr ? `${((p - curr) / curr * 100).toFixed(1)}%` : '—';

    return (
        <div className="glass-panel p-6 space-y-5">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Layers size={16} className="text-violet-400" />
                    <h3 className="text-slate-800 font-bold text-sm">Smart Entry/Exit Zones</h3>
                </div>
                <span className="text-[10px] text-slate-500 font-mono bg-white/5 border border-slate-100 px-2 py-0.5 rounded">
                    6-Month Analysis
                </span>
            </div>

            {/* Entry / Exit callout cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {zones.entry_zone && (
                    <div className="rounded-xl p-4 flex items-start gap-3"
                        style={{ background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.2)' }}>
                        <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                            style={{ background: 'rgba(16,185,129,0.12)' }}>
                            <ArrowDown size={14} style={{ color: '#10b981' }} />
                        </div>
                        <div>
                            <div className="text-[10px] uppercase font-bold tracking-wider" style={{ color: '#10b981' }}>
                                {zones.entry_zone.label}
                            </div>
                            <div className="text-lg font-black font-mono-nums mt-0.5" style={{ color: '#059669' }}>
                                {formatINR(zones.entry_zone.price)}
                            </div>
                            <div className="text-[11px] mt-1" style={{ color: '#64748b' }}>
                                {zones.entry_zone.note}
                            </div>
                        </div>
                    </div>
                )}
                {zones.exit_zone && (
                    <div className="rounded-xl p-4 flex items-start gap-3"
                        style={{ background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)' }}>
                        <div className="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0"
                            style={{ background: 'rgba(239,68,68,0.12)' }}>
                            <ArrowUp size={14} style={{ color: '#ef4444' }} />
                        </div>
                        <div>
                            <div className="text-[10px] uppercase font-bold tracking-wider" style={{ color: '#ef4444' }}>
                                {zones.exit_zone.label}
                            </div>
                            <div className="text-lg font-black font-mono-nums mt-0.5" style={{ color: '#dc2626' }}>
                                {formatINR(zones.exit_zone.price)}
                            </div>
                            <div className="text-[11px] mt-1" style={{ color: '#64748b' }}>
                                {zones.exit_zone.note}
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* Support / Resistance levels */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Support */}
                {supports.length > 0 && (
                    <div>
                        <div className="text-[10px] uppercase font-bold tracking-wider mb-2" style={{ color: '#10b981' }}>
                            Support Levels
                        </div>
                        <div className="space-y-2">
                            {supports.map((p, i) => {
                                const dist = curr ? Math.abs((p - curr) / curr * 100) : 0;
                                return (
                                    <div key={i} className="flex items-center gap-3">
                                        <span className="text-xs font-mono font-bold w-28 text-emerald-500">
                                            {formatINR(p)}
                                        </span>
                                        <div className="flex-1 h-2 rounded-full overflow-hidden bg-slate-100">
                                            <div
                                                className="h-full rounded-full"
                                                style={{
                                                    width: `${Math.min(100, 100 - (i * 15))}%`,
                                                    background: 'linear-gradient(90deg, #10b981, #34d399)',
                                                }}
                                            />
                                        </div>
                                        <span className="text-[10px] font-mono text-slate-500 w-12 text-right">
                                            {pctFrom(p)}
                                        </span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}

                {/* Resistance */}
                {resistances.length > 0 && (
                    <div>
                        <div className="text-[10px] uppercase font-bold tracking-wider mb-2" style={{ color: '#f43f5e' }}>
                            Resistance Levels
                        </div>
                        <div className="space-y-2">
                            {resistances.map((p, i) => (
                                <div key={i} className="flex items-center gap-3">
                                    <span className="text-xs font-mono font-bold w-28 text-rose-500">
                                        {formatINR(p)}
                                    </span>
                                    <div className="flex-1 h-2 rounded-full overflow-hidden bg-slate-100">
                                        <div
                                            className="h-full rounded-full"
                                            style={{
                                                width: `${Math.min(100, 100 - (i * 15))}%`,
                                                background: 'linear-gradient(90deg, #f43f5e, #fb7185)',
                                            }}
                                        />
                                    </div>
                                    <span className="text-[10px] font-mono text-slate-500 w-12 text-right">
                                        {pctFrom(p)}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
            </div>

            {/* Fibonacci levels */}
            {fibEntries.length > 0 && (
                <div>
                    <div className="text-[10px] uppercase font-bold tracking-wider mb-2 text-slate-500">
                        Fibonacci Retracement Levels
                    </div>
                    <div className="flex flex-wrap gap-2">
                        {fibEntries.map(({ label, price }) => {
                            const isCurrent = curr && Math.abs(price - curr) / curr < 0.01;
                            return (
                                <div
                                    key={label}
                                    className="flex items-center gap-2 px-3 py-1.5 rounded-lg"
                                    style={{
                                        background: isCurrent ? 'rgba(99,102,241,0.12)' : '#f8fafc',
                                        border: `1px solid ${isCurrent ? 'rgba(99,102,241,0.4)' : '#e2e8f0'}`,
                                    }}
                                >
                                    <span className="text-[10px] font-bold" style={{ color: isCurrent ? '#6366f1' : '#94a3b8' }}>
                                        {label}
                                    </span>
                                    <span className="text-xs font-mono font-semibold" style={{ color: isCurrent ? '#4f46e5' : '#334155' }}>
                                        {formatINR(price)}
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* Context note */}
            {zones.analysis && (
                <p className="text-slate-500 text-xs italic border-t border-slate-100 pt-3 leading-relaxed">
                    {zones.analysis}
                </p>
            )}
        </div>
    );
}

