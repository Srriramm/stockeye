import React, { useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';

export const PERIOD_MAP = {
    '1D': { period: '1d', interval: '15m' },
    '1W': { period: '5d', interval: '60m' },
    '1M': { period: '1mo', interval: '1d' },
    '3M': { period: '3mo', interval: '1d' },
    '6M': { period: '6mo', interval: '1d' },
    '1Y': { period: '1y', interval: '1d' },
};

export const CHART_PERIODS = Object.keys(PERIOD_MAP);

function formatXTick(val) {
    if (typeof val === 'number') {
        return new Date(val * 1000).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false });
    }
    if (typeof val === 'string') {
        const d = new Date(val);
        return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
    }
    return val;
}

function formatPrice(v) {
    if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)}Cr`;
    if (v >= 1e5) return `₹${(v / 1e5).toFixed(2)}L`;
    return `₹${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
}

function CustomTooltip({ active, payload, label }) {
    if (!active || !payload?.length) return null;
    const d = payload[0]?.payload;
    return (
        <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 10, padding: '10px 14px', boxShadow: '0 4px 16px rgba(0,0,0,0.1)' }}>
            <p style={{ color: '#64748b', fontSize: 11, marginBottom: 8, fontFamily: 'JetBrains Mono, monospace' }}>
                {typeof label === 'number'
                    ? new Date(label * 1000).toLocaleString('en-IN', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false })
                    : new Date(label).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
                }
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 24 }}>
                    <span style={{ color: '#64748b', fontSize: 11 }}>Close</span>
                    <span style={{ color: '#0f172a', fontWeight: 700, fontSize: 12 }}>{formatPrice(d?.close)}</span>
                </div>
                {d?.open != null && <>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 24 }}>
                        <span style={{ color: '#64748b', fontSize: 11 }}>Open</span>
                        <span style={{ color: '#475569', fontSize: 11 }}>{formatPrice(d.open)}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 24 }}>
                        <span style={{ color: '#64748b', fontSize: 11 }}>High</span>
                        <span style={{ color: '#059669', fontSize: 11, fontWeight: 600 }}>{formatPrice(d.high)}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 24 }}>
                        <span style={{ color: '#64748b', fontSize: 11 }}>Low</span>
                        <span style={{ color: '#dc2626', fontSize: 11, fontWeight: 600 }}>{formatPrice(d.low)}</span>
                    </div>
                </>}
            </div>
        </div>
    );
}

export default function CandlestickChart({ data, height = 300, currentPrice = null, selectedPeriod = '3M', onPeriodChange = null }) {
    const chartData = useMemo(() => {
        if (!data || data.length === 0) return [];
        const seen = new Set();
        const result = [];
        data.forEach(item => {
            const raw = item.time !== undefined ? item.time : item.date;
            const key = String(raw);
            if (raw != null && !seen.has(key)) {
                seen.add(key);
                result.push({ time: raw, close: item.close, open: item.open, high: item.high, low: item.low });
            }
        });
        result.sort((a, b) => typeof a.time === 'number' ? a.time - b.time : (a.time < b.time ? -1 : 1));
        return result;
    }, [data]);

    const displayData = useMemo(() => {
        if (!currentPrice || chartData.length === 0) return chartData;
        const last = chartData[chartData.length - 1];
        return [...chartData.slice(0, -1), { ...last, close: currentPrice }];
    }, [chartData, currentPrice]);

    const isUp = displayData.length >= 2 ? displayData[displayData.length - 1].close >= displayData[0].close : true;
    const lineColor = isUp ? '#059669' : '#dc2626';
    const gradId = isUp ? 'priceGradUp' : 'priceGradDown';

    const PeriodButtons = () => (
        <div className="flex justify-end gap-1 mb-2">
            {CHART_PERIODS.map(p => (
                <button
                    key={p}
                    onClick={() => onPeriodChange?.(p)}
                    className="px-2 py-0.5 text-[10px] rounded font-bold transition-all"
                    style={selectedPeriod === p
                        ? { background: '#2563eb', color: '#ffffff', border: '1px solid transparent' }
                        : { background: 'transparent', color: '#64748b', border: '1px solid #e2e8f0' }
                    }
                >
                    {p}
                </button>
            ))}
        </div>
    );

    if (!data || data.length === 0) {
        return (
            <div className="w-full" style={{ height }}>
                <PeriodButtons />
                <div className="flex items-center justify-center text-xs" style={{ height: height - 32, color: '#94a3b8' }}>
                    No data available
                </div>
            </div>
        );
    }

    return (
        <div className="w-full">
            <PeriodButtons />
            <ResponsiveContainer width="100%" height={height}>
                <AreaChart data={displayData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                    <defs>
                        <linearGradient id="priceGradUp" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#059669" stopOpacity={0.12} />
                            <stop offset="95%" stopColor="#059669" stopOpacity={0} />
                        </linearGradient>
                        <linearGradient id="priceGradDown" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#dc2626" stopOpacity={0.12} />
                            <stop offset="95%" stopColor="#dc2626" stopOpacity={0} />
                        </linearGradient>
                    </defs>
                    <XAxis dataKey="time" tickFormatter={formatXTick} tick={{ fill: '#94a3b8', fontSize: 10 }} axisLine={false} tickLine={false} dy={6} minTickGap={50} />
                    <YAxis domain={['auto', 'auto']} tickFormatter={formatPrice} tick={{ fill: '#94a3b8', fontSize: 10 }} axisLine={false} tickLine={false} dx={-4} width={70} />
                    <Tooltip content={<CustomTooltip />} />
                    {currentPrice && (
                        <ReferenceLine y={currentPrice} stroke={lineColor} strokeDasharray="3 3" strokeOpacity={0.5} />
                    )}
                    <Area type="monotone" dataKey="close" stroke={lineColor} strokeWidth={2} fill={`url(#${gradId})`} dot={false} activeDot={{ r: 4, fill: lineColor, strokeWidth: 0 }} isAnimationActive={false} />
                </AreaChart>
            </ResponsiveContainer>
        </div>
    );
}
