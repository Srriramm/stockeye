import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, BarChart3, ArrowUpRight, ArrowDownRight, RefreshCw, Newspaper, PieChart as PieIcon, Activity } from 'lucide-react';
import { PieChart, Pie, Cell, AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';
import { authAxios } from '../utils/api';

const SECTOR_COLORS = ['#2563eb', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#06b6d4', '#ec4899', '#84cc16'];

const lightTooltip = {
  contentStyle: {
    background: '#ffffff',
    border: '1px solid #e2e8f0',
    borderRadius: '10px',
    padding: '8px 12px',
    boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
  },
  labelStyle: { color: '#64748b', fontSize: 11, marginBottom: 4 },
  itemStyle: { fontSize: 12, color: '#0f172a' },
  cursor: { fill: 'rgba(37,99,235,0.05)' },
};

export default function Dashboard({ indices, alerts, apiUrl, movers: propMovers, marketNews }) {
  const [portfolio, setPortfolio] = useState(null);
  const movers = propMovers || { gainers: [], losers: [] };
  const news = marketNews?.news || [];
  const [loading, setLoading] = useState(true);
  const [portfolioHistory, setPortfolioHistory] = useState([]);
  const [histDays, setHistDays] = useState(30);

  const HIST_PERIODS = [
    { label: '7D', days: 7 },
    { label: '14D', days: 14 },
    { label: '30D', days: 30 },
    { label: '90D', days: 90 },
  ];

  useEffect(() => {
    fetchDashboardData();
    fetchPortfolioHistory(30);
    const interval = setInterval(fetchDashboardData, 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => { fetchPortfolioHistory(histDays); }, [histDays]);

  const fetchDashboardData = async () => {
    try {
      const portfolioRes = await authAxios.get(`${apiUrl}/api/portfolio`);
      setPortfolio(portfolioRes.data);
    } catch (err) {
      console.log('Portfolio fetch error');
    } finally {
      setLoading(false);
    }
  };

  const fetchPortfolioHistory = async (days) => {
    try {
      const historyRes = await authAxios.get(`${apiUrl}/api/portfolio/history?days=${days}`);
      setPortfolioHistory(historyRes.data.history || []);
    } catch (err) {
      console.log('History fetch error');
    }
  };

  const fmt = (n) => {
    if (!n && n !== 0) return '—';
    if (Math.abs(n) >= 1e7) return `₹${(n / 1e7).toFixed(2)}Cr`;
    if (Math.abs(n) >= 1e5) return `₹${(n / 1e5).toFixed(2)}L`;
    return `₹${Number(n).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
  };

  const sectorData = portfolio?.holdings ? Object.entries(
    portfolio.holdings.reduce((acc, h) => {
      const s = h.sector || 'Other';
      acc[s] = (acc[s] || 0) + h.current_value;
      return acc;
    }, {})
  ).map(([name, value]) => ({ name, value: Math.round(value) })) : [];

  const pnlData = portfolio?.holdings?.map(h => ({
    name: h.ticker,
    pnl: Math.round(h.pnl || 0),
    fill: (h.pnl || 0) >= 0 ? '#10b981' : '#ef4444',
  })) || [];

  return (
    <div className="p-6 space-y-6 fade-in max-w-[1600px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight" style={{ color: '#0f172a' }}>Market Overview</h1>
          <p className="text-sm mt-1" style={{ color: '#64748b' }}>Real-time surveillance & portfolio analytics</p>
        </div>
        <button
          onClick={fetchDashboardData}
          className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium transition-all"
          style={{ background: '#ffffff', border: '1px solid #e2e8f0', color: '#475569', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}
          onMouseEnter={e => { e.currentTarget.style.background = '#f1f5f9'; e.currentTarget.style.color = '#0f172a'; }}
          onMouseLeave={e => { e.currentTarget.style.background = '#ffffff'; e.currentTarget.style.color = '#475569'; }}
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Portfolio Summary */}
      {portfolio && portfolio.num_holdings > 0 && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="Net Worth" value={fmt(portfolio.total_value)} icon={Activity} color="blue" />
          <StatCard label="Invested Capital" value={fmt(portfolio.total_investment)} icon={BarChart3} color="indigo" />
          <StatCard
            label="Total P&L"
            value={`${portfolio.total_pnl >= 0 ? '+' : ''}${fmt(portfolio.total_pnl)}`}
            sub={`${portfolio.total_pnl >= 0 ? '+' : ''}${portfolio.total_pnl_percent?.toFixed(2)}%`}
            icon={portfolio.total_pnl >= 0 ? TrendingUp : TrendingDown}
            color={portfolio.total_pnl >= 0 ? 'green' : 'red'}
          />
          <StatCard label="Holdings" value={portfolio.num_holdings} sub="Active positions" icon={PieIcon} color="violet" />
        </div>
      )}

      {/* Market Index Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Object.entries(indices).map(([name, data]) => (
          <div
            key={name}
            className="rounded-xl p-5 relative overflow-hidden group transition-all duration-200"
            style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}
            onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.1)'; e.currentTarget.style.transform = 'translateY(-2px)'; }}
            onMouseLeave={e => { e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.06)'; e.currentTarget.style.transform = ''; }}
          >
            <div className="absolute top-3 right-3 opacity-8">
              {data.change_percent >= 0
                ? <TrendingUp size={32} style={{ color: '#10b981', opacity: 0.1 }} />
                : <TrendingDown size={32} style={{ color: '#ef4444', opacity: 0.1 }} />}
            </div>
            <div className="text-xs font-bold uppercase tracking-wider mb-2" style={{ color: '#94a3b8' }}>{name}</div>
            <div className="text-2xl font-bold font-mono-nums tracking-tight" style={{ color: '#0f172a' }}>
              {data.value?.toLocaleString('en-IN')}
            </div>
            <div className="flex items-center gap-2 mt-2">
              <span
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-xs font-bold"
                style={{
                  background: data.change_percent >= 0 ? '#d1fae5' : '#fee2e2',
                  color: data.change_percent >= 0 ? '#065f46' : '#991b1b',
                }}
              >
                {data.change_percent >= 0 ? <ArrowUpRight size={11} /> : <ArrowDownRight size={11} />}
                {data.change_percent >= 0 ? '+' : ''}{data.change_percent?.toFixed(2)}%
              </span>
              <span className="text-xs font-mono-nums" style={{ color: '#94a3b8' }}>
                {data.change >= 0 ? '+' : ''}{data.change?.toFixed(2)}
              </span>
            </div>
          </div>
        ))}
        {Object.keys(indices).length === 0 && (
          <div className="col-span-4 flex items-center justify-center py-12 rounded-xl text-sm gap-2" style={{ background: '#ffffff', border: '1px solid #e2e8f0', color: '#94a3b8' }}>
            <RefreshCw size={16} className="animate-spin" /> Establishing feed connection...
          </div>
        )}
      </div>

      {/* Charts Row */}
      {(sectorData.length > 0 || pnlData.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {sectorData.length > 0 && (
            <div className="rounded-xl p-6" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
              <h3 className="font-semibold text-sm mb-5 flex items-center gap-2" style={{ color: '#0f172a' }}>
                <PieIcon size={15} style={{ color: '#2563eb' }} /> Sector Allocation
              </h3>
              <div className="flex flex-col md:flex-row items-center gap-6">
                <ResponsiveContainer width="100%" height={200} className="flex-1">
                  <PieChart>
                    <Pie data={sectorData} cx="50%" cy="50%" innerRadius={55} outerRadius={80} cornerRadius={4} paddingAngle={4} dataKey="value" stroke="none">
                      {sectorData.map((_, i) => <Cell key={i} fill={SECTOR_COLORS[i % SECTOR_COLORS.length]} />)}
                    </Pie>
                    <Tooltip formatter={(v) => fmt(v)} {...lightTooltip} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="w-full md:w-44 space-y-2">
                  {sectorData.map((s, i) => (
                    <div key={i} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2" style={{ color: '#64748b' }}>
                        <span className="w-2 h-2 rounded-full" style={{ background: SECTOR_COLORS[i % SECTOR_COLORS.length] }} />
                        {s.name}
                      </div>
                      <span className="font-mono-nums font-medium" style={{ color: '#0f172a' }}>{fmt(s.value)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
          {pnlData.length > 0 && (
            <div className="rounded-xl p-6" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
              <h3 className="font-semibold text-sm mb-5 flex items-center gap-2" style={{ color: '#0f172a' }}>
                <BarChart3 size={15} style={{ color: '#10b981' }} /> P&L Distribution
              </h3>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={pnlData} barSize={22}>
                  <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 10 }} axisLine={false} tickLine={false} dy={8} />
                  <YAxis hide />
                  <Tooltip {...lightTooltip} formatter={(v) => [`₹${v.toLocaleString('en-IN')}`, 'P&L']} />
                  <Bar dataKey="pnl" radius={[4, 4, 4, 4]} minPointSize={4}>
                    {pnlData.map((entry, i) => <Cell key={i} fill={entry.fill} fillOpacity={0.85} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {/* Portfolio History */}
      {portfolioHistory.length > 0 && portfolio && portfolio.num_holdings > 0 && (
        <div className="rounded-xl p-6" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <div className="flex items-center justify-between mb-5">
            <h3 className="font-semibold text-sm flex items-center gap-2" style={{ color: '#0f172a' }}>
              <Activity size={15} style={{ color: '#6366f1' }} /> Portfolio Performance
            </h3>
            <div className="flex gap-1 p-1 rounded-lg" style={{ background: '#f8fafc', border: '1px solid #e2e8f0' }}>
              {HIST_PERIODS.map(({ label, days }) => (
                <button
                  key={days}
                  onClick={() => setHistDays(days)}
                  className="px-2.5 py-1 text-[10px] rounded-md font-bold transition-all"
                  style={histDays === days
                    ? { background: '#2563eb', color: '#ffffff' }
                    : { color: '#64748b' }
                  }
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={portfolioHistory}>
              <defs>
                <linearGradient id="histGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#2563eb" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#2563eb" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="snapshot_date" tick={{ fill: '#94a3b8', fontSize: 10 }} axisLine={false} tickLine={false} dy={8} minTickGap={30} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} tickFormatter={v => fmt(v)} axisLine={false} tickLine={false} dx={-8} />
              <Tooltip formatter={(v) => [fmt(v), 'Value']} {...lightTooltip} />
              <Area type="monotone" dataKey="total_value" stroke="#2563eb" strokeWidth={2} fill="url(#histGrad)" dot={false} activeDot={{ r: 4, fill: '#2563eb', strokeWidth: 0 }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Gainers / Losers / News */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Gainers */}
        <div className="rounded-xl p-5" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <h3 className="text-xs font-bold uppercase tracking-wider mb-4 flex items-center gap-2" style={{ color: '#94a3b8' }}>
            <TrendingUp size={13} style={{ color: '#10b981' }} /> Top Gainers
          </h3>
          <div className="space-y-0.5">
            {movers.gainers?.slice(0, 5).map((s, i) => (
              <MoverRow key={i} ticker={s.ticker} price={s.current_price} change={s.change_percent} positive />
            ))}
            {(!movers.gainers || movers.gainers.length === 0) && <EmptyRow text="Loading market data..." />}
          </div>
        </div>

        {/* Losers */}
        <div className="rounded-xl p-5" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <h3 className="text-xs font-bold uppercase tracking-wider mb-4 flex items-center gap-2" style={{ color: '#94a3b8' }}>
            <TrendingDown size={13} style={{ color: '#ef4444' }} /> Top Losers
          </h3>
          <div className="space-y-0.5">
            {movers.losers?.slice(0, 5).map((s, i) => (
              <MoverRow key={i} ticker={s.ticker} price={s.current_price} change={s.change_percent} positive={false} />
            ))}
            {(!movers.losers || movers.losers.length === 0) && <EmptyRow text="Loading market data..." />}
          </div>
        </div>

        {/* News */}
        <div className="rounded-xl overflow-hidden" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <div className="px-5 py-4" style={{ borderBottom: '1px solid #f1f5f9' }}>
            <h3 className="text-xs font-bold uppercase tracking-wider flex items-center gap-2" style={{ color: '#94a3b8' }}>
              <Newspaper size={13} style={{ color: '#2563eb' }} /> Market Intelligence
            </h3>
          </div>
          <div className="overflow-y-auto custom-scrollbar max-h-[300px]">
            {news.length > 0 ? (
              news.slice(0, 6).map((n, i) => (
                <a key={i} href={n.link} target="_blank" rel="noopener noreferrer"
                  className="block px-5 py-3.5 group transition-colors"
                  style={{ borderBottom: '1px solid #f8fafc' }}
                  onMouseEnter={e => { e.currentTarget.style.background = '#f8fafc'; }}
                  onMouseLeave={e => { e.currentTarget.style.background = ''; }}
                >
                  <div className="flex items-start gap-3">
                    <span
                      className="w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0"
                      style={{ background: n.sentiment === 'positive' ? '#10b981' : n.sentiment === 'negative' ? '#ef4444' : '#f59e0b' }}
                    />
                    <div>
                      <p className="text-xs leading-relaxed line-clamp-2 font-medium transition-colors"
                        style={{ color: '#334155' }}
                        onMouseEnter={e => { e.currentTarget.style.color = '#2563eb'; }}
                        onMouseLeave={e => { e.currentTarget.style.color = '#334155'; }}
                      >
                        {n.title}
                      </p>
                      <span className="text-[10px] mt-1 block" style={{ color: '#94a3b8' }}>{n.publisher} · {n.time_ago}</span>
                    </div>
                  </div>
                </a>
              ))
            ) : (
              <EmptyRow text="Aggregating news feeds..." />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, icon: Icon, color }) {
  const palette = {
    blue: { bg: '#eff6ff', border: '#bfdbfe', iconBg: '#dbeafe', iconColor: '#1d4ed8', valColor: '#1e40af' },
    indigo: { bg: '#eef2ff', border: '#c7d2fe', iconBg: '#e0e7ff', iconColor: '#3730a3', valColor: '#312e81' },
    green: { bg: '#f0fdf4', border: '#bbf7d0', iconBg: '#d1fae5', iconColor: '#059669', valColor: '#065f46' },
    red: { bg: '#fff1f2', border: '#fecdd3', iconBg: '#fee2e2', iconColor: '#dc2626', valColor: '#991b1b' },
    violet: { bg: '#f5f3ff', border: '#ddd6fe', iconBg: '#ede9fe', iconColor: '#7c3aed', valColor: '#5b21b6' },
  };
  const p = palette[color] || palette.blue;

  return (
    <div
      className="rounded-xl p-5 transition-all duration-200"
      style={{ background: p.bg, border: `1px solid ${p.border}`, boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="text-xs font-semibold uppercase tracking-wider" style={{ color: p.iconColor, opacity: 0.7 }}>{label}</div>
        <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: p.iconBg }}>
          <Icon size={16} style={{ color: p.iconColor }} />
        </div>
      </div>
      <div className="text-2xl font-bold font-mono-nums tracking-tight" style={{ color: p.valColor }}>{value}</div>
      {sub && (
        <div className="text-xs font-medium mt-1.5 inline-block px-2 py-0.5 rounded-full" style={{ background: p.iconBg, color: p.iconColor }}>
          {sub}
        </div>
      )}
    </div>
  );
}

function MoverRow({ ticker, price, change, positive }) {
  return (
    <div
      className="flex items-center justify-between py-2.5 px-3 rounded-lg cursor-pointer transition-colors"
      onMouseEnter={e => { e.currentTarget.style.background = '#f8fafc'; }}
      onMouseLeave={e => { e.currentTarget.style.background = ''; }}
    >
      <span className="text-sm font-bold" style={{ color: '#0f172a' }}>{ticker}</span>
      <div className="text-right">
        <div className="text-sm font-mono-nums" style={{ color: '#334155' }}>₹{price?.toLocaleString('en-IN')}</div>
        <div className="text-xs font-bold" style={{ color: positive ? '#059669' : '#dc2626' }}>
          {positive ? '+' : ''}{change?.toFixed(2)}%
        </div>
      </div>
    </div>
  );
}

function EmptyRow({ text }) {
  return <div className="py-6 text-center text-xs italic" style={{ color: '#94a3b8' }}>{text}</div>;
}
