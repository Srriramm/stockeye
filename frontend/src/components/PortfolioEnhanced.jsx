import React, { useState, useEffect, useCallback } from 'react';
import {
  Plus, Trash2, RefreshCw, TrendingUp, TrendingDown, ArrowUpRight,
  ArrowDownRight, Search, X, BarChart3, PieChart as PieIcon, Activity
} from 'lucide-react';
import {
  PieChart, Pie, Cell, AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, BarChart, Bar
} from 'recharts';
import axios from 'axios';
import { toast } from 'react-toastify';
import wsManager from '../utils/websocket';

const COLORS = ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16'];

const lightTooltip = {
  contentStyle: { background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 10, padding: '8px 12px', boxShadow: '0 4px 16px rgba(0,0,0,0.08)' },
  labelStyle: { color: '#64748b', fontSize: 11 },
  itemStyle: { fontSize: 12, color: '#0f172a' },
};

export default function PortfolioEnhanced({ apiUrl, socket }) {
  const [portfolio, setPortfolio] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [portfolioHistory, setPortfolioHistory] = useState([]);
  const [realtimePrices, setRealtimePrices] = useState({});
  const [sortField, setSortField] = useState('pnl_percent');
  const [sortAsc, setSortAsc] = useState(false);

  useEffect(() => {
    axios.post(`${apiUrl}/api/monitor/service`, { action: 'start' }).catch(() => { });
  }, [apiUrl]);

  const fetchPortfolio = useCallback(async () => {
    try {
      const [portfolioRes, historyRes] = await Promise.allSettled([
        axios.get(`${apiUrl}/api/portfolio`),
        axios.get(`${apiUrl}/api/portfolio/history?days=30`),
      ]);
      if (portfolioRes.status === 'fulfilled') setPortfolio(portfolioRes.value.data);
      if (historyRes.status === 'fulfilled') setPortfolioHistory(historyRes.value.data.history || []);
    } catch { toast.error('Failed to load portfolio'); }
    finally { setLoading(false); }
  }, [apiUrl]);

  useEffect(() => {
    fetchPortfolio();
    const interval = setInterval(fetchPortfolio, 60000);
    return () => clearInterval(interval);
  }, [fetchPortfolio]);

  useEffect(() => {
    if (!portfolio?.holdings) return;
    const unsubscribers = portfolio.holdings.map(h =>
      wsManager.subscribe(h.ticker, (priceData) => {
        setRealtimePrices(prev => ({ ...prev, [h.ticker]: priceData }));
      })
    );
    return () => unsubscribers.forEach(u => u());
  }, [portfolio?.holdings]);

  const calcRealtimePortfolio = () => {
    if (!portfolio?.holdings) return portfolio;
    let totalValue = 0;
    const totalInvestment = portfolio.total_investment || 0;
    const updatedHoldings = portfolio.holdings.map(h => {
      const rt = realtimePrices[h.ticker];
      const currentPrice = rt?.current_price || h.current_price;
      const currentValue = h.quantity * currentPrice;
      const pnl = currentValue - h.investment;
      totalValue += currentValue;
      return { ...h, current_price: currentPrice, current_value: currentValue, pnl, pnl_percent: (pnl / h.investment) * 100, change: rt?.change || 0, change_percent: rt?.change_percent || 0 };
    });
    return { ...portfolio, holdings: updatedHoldings, total_value: totalValue, total_pnl: totalValue - totalInvestment, total_pnl_percent: ((totalValue - totalInvestment) / totalInvestment) * 100 };
  };

  const rt = calcRealtimePortfolio();
  const sectorData = Object.entries(rt?.holdings?.reduce((acc, h) => { const s = h.sector || 'Other'; acc[s] = (acc[s] || 0) + h.current_value; return acc; }, {}) || {}).map(([name, value]) => ({ name, value: Math.round(value) }));
  const sortedByPnL = [...(rt?.holdings || [])].sort((a, b) => b.pnl_percent - a.pnl_percent);
  const topGainers = sortedByPnL.filter(h => h.pnl >= 0).slice(0, 3);
  const topLosers = sortedByPnL.filter(h => h.pnl < 0).slice(-3).reverse();
  const sortedHoldings = [...(rt?.holdings || [])].sort((a, b) => ((a[sortField] || 0) - (b[sortField] || 0)) * (sortAsc ? 1 : -1));

  const fmt = (n) => {
    if (!n) return '₹0';
    if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`;
    if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)} L`;
    if (n >= 1e3) return `₹${(n / 1e3).toFixed(2)} K`;
    return `₹${n?.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
  };

  if (loading) {
    return <div className="p-8 flex items-center justify-center"><div className="text-sm animate-pulse" style={{ color: '#94a3b8' }}>Loading portfolio...</div></div>;
  }

  if (!rt || rt.num_holdings === 0) {
    return (
      <div className="p-8">
        <div className="rounded-2xl p-14 text-center" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-5" style={{ background: '#eff6ff' }}>
            <BarChart3 size={28} style={{ color: '#2563eb' }} />
          </div>
          <h3 className="text-xl font-bold mb-2" style={{ color: '#0f172a' }}>Your portfolio is empty</h3>
          <p className="text-sm mb-6" style={{ color: '#64748b' }}>Add stocks to track your investments and P&L</p>
          <button onClick={() => setShowAddModal(true)} className="px-6 py-3 rounded-xl text-sm font-semibold" style={{ background: '#2563eb', color: '#ffffff', boxShadow: '0 4px 12px rgba(37,99,235,0.25)' }}>
            Add Your First Stock
          </button>
        </div>
        {showAddModal && <AddStockModal apiUrl={apiUrl} onClose={() => setShowAddModal(false)} onSuccess={fetchPortfolio} />}
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: '#0f172a' }}>Portfolio</h1>
          <p className="text-sm mt-0.5" style={{ color: '#64748b' }}>Real-time investments tracker</p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={fetchPortfolio} className="p-2 rounded-xl transition-all" style={{ background: '#f8fafc', border: '1px solid #e2e8f0', color: '#64748b' }}
            onMouseEnter={e => { e.currentTarget.style.background = '#f1f5f9'; e.currentTarget.style.color = '#0f172a'; }}
            onMouseLeave={e => { e.currentTarget.style.background = '#f8fafc'; e.currentTarget.style.color = '#64748b'; }}>
            <RefreshCw size={16} />
          </button>
          <button onClick={() => setShowAddModal(true)} className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all" style={{ background: '#2563eb', color: '#ffffff', boxShadow: '0 2px 8px rgba(37,99,235,0.25)' }}
            onMouseEnter={e => { e.currentTarget.style.background = '#1d4ed8'; }}
            onMouseLeave={e => { e.currentTarget.style.background = '#2563eb'; }}>
            <Plus size={16} /> Add Stock
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { title: 'Current Value', value: fmt(rt.total_value), icon: <BarChart3 size={18} style={{ color: '#2563eb' }} />, bg: '#eff6ff', border: '#bfdbfe' },
          { title: 'Total Investment', value: fmt(rt.total_investment), icon: <TrendingUp size={18} style={{ color: '#8b5cf6' }} />, bg: '#f5f3ff', border: '#ddd6fe' },
          {
            title: 'Total P&L',
            value: `${rt.total_pnl >= 0 ? '+' : ''}${fmt(rt.total_pnl)}`,
            sub: `${rt.total_pnl >= 0 ? '+' : ''}${rt.total_pnl_percent?.toFixed(2)}%`,
            icon: rt.total_pnl >= 0 ? <ArrowUpRight size={18} style={{ color: '#059669' }} /> : <ArrowDownRight size={18} style={{ color: '#dc2626' }} />,
            bg: rt.total_pnl >= 0 ? '#f0fdf4' : '#fff1f2',
            border: rt.total_pnl >= 0 ? '#bbf7d0' : '#fecdd3',
            valColor: rt.total_pnl >= 0 ? '#065f46' : '#991b1b',
          },
          { title: 'Holdings', value: rt.num_holdings, icon: <PieIcon size={18} style={{ color: '#f59e0b' }} />, bg: '#fffbeb', border: '#fde68a' },
        ].map((c, i) => (
          <div key={i} className="rounded-xl p-5" style={{ background: c.bg, border: `1px solid ${c.border}` }}>
            <div className="flex items-start justify-between mb-2">
              <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: '#64748b' }}>{c.title}</span>
              {c.icon}
            </div>
            <div className="text-2xl font-bold font-mono-nums" style={{ color: c.valColor || '#0f172a' }}>{c.value}</div>
            {c.sub && <div className="text-xs mt-1 font-medium" style={{ color: c.valColor || '#64748b' }}>{c.sub}</div>}
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="rounded-xl p-6" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <h3 className="font-bold text-sm mb-4" style={{ color: '#0f172a' }}>Portfolio Performance</h3>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={portfolioHistory}>
              <defs>
                <linearGradient id="portGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#2563eb" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#2563eb" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} axisLine={false} tickLine={false} />
              <Tooltip {...lightTooltip} />
              <Area type="monotone" dataKey="total_value" stroke="#2563eb" strokeWidth={2} fill="url(#portGrad)" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="rounded-xl p-6" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
          <h3 className="font-bold text-sm mb-4" style={{ color: '#0f172a' }}>Sector Allocation</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={sectorData} cx="50%" cy="50%" labelLine={false} label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`} outerRadius={75} dataKey="value">
                {sectorData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
              </Pie>
              <Tooltip {...lightTooltip} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Top Gainers / Losers */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {[
          { title: 'Top Gainers', icon: <TrendingUp size={16} style={{ color: '#059669' }} />, data: topGainers, positive: true },
          { title: 'Top Losers', icon: <TrendingDown size={16} style={{ color: '#dc2626' }} />, data: topLosers, positive: false },
        ].map(({ title, icon, data, positive }) => (
          <div key={title} className="rounded-xl p-6" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
            <h3 className="font-bold text-sm mb-4 flex items-center gap-2" style={{ color: '#0f172a' }}>{icon}{title}</h3>
            <div className="space-y-3">
              {data.map(h => (
                <div key={h.ticker} className="flex items-center justify-between">
                  <div>
                    <div className="font-semibold text-sm" style={{ color: '#0f172a' }}>{h.ticker}</div>
                    <div className="text-xs" style={{ color: '#94a3b8' }}>{h.name}</div>
                  </div>
                  <div className="text-right">
                    <div className="font-semibold text-sm" style={{ color: positive ? '#059669' : '#dc2626' }}>
                      {positive ? '+' : ''}{h.pnl_percent?.toFixed(2)}%
                    </div>
                    <div className="text-xs" style={{ color: '#94a3b8' }}>{positive ? '+' : ''}{fmt(h.pnl)}</div>
                  </div>
                </div>
              ))}
              {data.length === 0 && <div className="text-center text-sm py-4" style={{ color: '#94a3b8' }}>No data</div>}
            </div>
          </div>
        ))}
      </div>

      {/* Holdings Table */}
      <div className="rounded-xl overflow-hidden" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
        <div className="px-6 py-4" style={{ borderBottom: '1px solid #f1f5f9', background: '#fcfcfd' }}>
          <h3 className="font-bold text-sm" style={{ color: '#0f172a' }}>Holdings ({rt.num_holdings})</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr style={{ background: '#f8fafc', borderBottom: '1px solid #f1f5f9' }}>
                {['Stock', 'Qty', 'Avg Price', 'LTP', 'Value', 'P&L', 'P&L %', ''].map((h, i) => (
                  <th
                    key={i}
                    className={`px-5 py-3 text-[10px] font-bold uppercase tracking-wider ${i > 0 && i < 7 ? 'text-right cursor-pointer' : 'text-left'}`}
                    style={{ color: '#94a3b8' }}
                    onClick={i > 0 && i < 7 ? () => { setSortField(['', 'quantity', 'buy_price', 'current_price', 'current_value', 'pnl', 'pnl_percent'][i]); setSortAsc(!sortAsc); } : undefined}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedHoldings.map(h => (
                <tr
                  key={h.id}
                  className="transition-colors"
                  style={{ borderBottom: '1px solid #f8fafc' }}
                  onMouseEnter={e => { e.currentTarget.style.background = '#f8fafc'; }}
                  onMouseLeave={e => { e.currentTarget.style.background = ''; }}
                >
                  <td className="px-5 py-4">
                    <div className="font-semibold text-sm" style={{ color: '#0f172a' }}>{h.ticker}</div>
                    <div className="text-xs" style={{ color: '#94a3b8' }}>{h.name}</div>
                  </td>
                  <td className="px-5 py-4 text-right text-sm" style={{ color: '#475569' }}>{h.quantity}</td>
                  <td className="px-5 py-4 text-right text-sm font-mono-nums" style={{ color: '#475569' }}>₹{h.buy_price?.toFixed(2)}</td>
                  <td className="px-5 py-4 text-right">
                    <div className="text-sm font-semibold font-mono-nums" style={{ color: '#0f172a' }}>₹{h.current_price?.toFixed(2)}</div>
                    <div className="text-[10px] font-bold" style={{ color: h.change_percent >= 0 ? '#059669' : '#dc2626' }}>
                      {h.change_percent >= 0 ? '+' : ''}{h.change_percent?.toFixed(2)}%
                    </div>
                  </td>
                  <td className="px-5 py-4 text-right text-sm font-semibold font-mono-nums" style={{ color: '#0f172a' }}>{fmt(h.current_value)}</td>
                  <td className="px-5 py-4 text-right text-sm font-semibold font-mono-nums" style={{ color: h.pnl >= 0 ? '#059669' : '#dc2626' }}>
                    {h.pnl >= 0 ? '+' : ''}{fmt(h.pnl)}
                  </td>
                  <td className="px-5 py-4 text-right text-sm font-bold font-mono-nums" style={{ color: h.pnl >= 0 ? '#059669' : '#dc2626' }}>
                    {h.pnl >= 0 ? '+' : ''}{h.pnl_percent?.toFixed(2)}%
                  </td>
                  <td className="px-5 py-4">
                    <button
                      onClick={() => removeStock(h.id, h.ticker, apiUrl, fetchPortfolio)}
                      className="p-1.5 rounded-lg transition-all opacity-40 hover:opacity-100"
                      style={{ color: '#dc2626' }}
                      onMouseEnter={e => { e.currentTarget.style.background = '#fee2e2'; }}
                      onMouseLeave={e => { e.currentTarget.style.background = ''; }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {showAddModal && <AddStockModal apiUrl={apiUrl} onClose={() => setShowAddModal(false)} onSuccess={fetchPortfolio} />}
    </div>
  );
}

function AddStockModal({ apiUrl, onClose, onSuccess }) {
  const [formData, setFormData] = useState({ ticker: '', name: '', quantity: '', buy_price: '', purchase_date: new Date().toISOString().split('T')[0], sector: '' });
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (searchQuery.length < 1) { setSearchResults([]); return; }
    const timer = setTimeout(async () => {
      try {
        const res = await axios.get(`${apiUrl}/api/stocks/search?q=${searchQuery}`);
        setSearchResults(res.data.results || []);
      } catch { }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery, apiUrl]);

  const selectStock = (stock) => {
    setFormData(prev => ({ ...prev, ticker: stock.ticker, name: stock.name, sector: stock.sector || '' }));
    setSearchQuery(stock.ticker);
    setSearchResults([]);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await axios.post(`${apiUrl}/api/portfolio/add`, { ...formData, quantity: parseFloat(formData.quantity), buy_price: parseFloat(formData.buy_price) });
      toast.success('Stock added to portfolio');
      onSuccess();
      onClose();
    } catch (err) { toast.error(err.response?.data?.error || 'Failed to add stock'); }
    finally { setLoading(false); }
  };

  const inputStyle = { background: '#f8fafc', border: '1px solid #e2e8f0', color: '#0f172a', borderRadius: 10, padding: '10px 14px', fontSize: 14, width: '100%' };
  const labelStyle = { display: 'block', fontSize: 11, fontWeight: 600, color: '#64748b', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' };

  return (
    <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: 'rgba(15,23,42,0.4)', backdropFilter: 'blur(4px)' }}>
      <div className="w-full max-w-md rounded-2xl p-6 fade-in" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 20px 60px rgba(0,0,0,0.15)' }}>
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-base font-bold" style={{ color: '#0f172a' }}>Add Stock to Portfolio</h3>
          <button onClick={onClose} style={{ color: '#94a3b8' }}><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="relative">
            <label style={labelStyle}>Search Stock</label>
            <input type="text" value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder="Search by name or ticker..." style={inputStyle} />
            {searchResults.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-1 rounded-xl overflow-hidden z-10" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 8px 24px rgba(0,0,0,0.1)' }}>
                {searchResults.map(stock => (
                  <button key={stock.ticker} type="button" onClick={() => selectStock(stock)} className="w-full p-3 text-left transition-colors"
                    onMouseEnter={e => { e.currentTarget.style.background = '#f8fafc'; }}
                    onMouseLeave={e => { e.currentTarget.style.background = ''; }}>
                    <div className="font-semibold text-sm" style={{ color: '#0f172a' }}>{stock.ticker}</div>
                    <div className="text-xs" style={{ color: '#94a3b8' }}>{stock.name}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div><label style={labelStyle}>Quantity</label><input type="number" value={formData.quantity} onChange={e => setFormData({ ...formData, quantity: e.target.value })} placeholder="0" step="0.01" required style={inputStyle} /></div>
          <div><label style={labelStyle}>Buy Price (₹)</label><input type="number" value={formData.buy_price} onChange={e => setFormData({ ...formData, buy_price: e.target.value })} placeholder="0.00" step="0.01" required style={inputStyle} /></div>
          <div><label style={labelStyle}>Purchase Date</label><input type="date" value={formData.purchase_date} onChange={e => setFormData({ ...formData, purchase_date: e.target.value })} style={inputStyle} /></div>
          <div className="flex gap-3 pt-2">
            <button type="button" onClick={onClose} className="flex-1 py-2.5 rounded-xl text-sm font-medium transition-all" style={{ background: '#f8fafc', border: '1px solid #e2e8f0', color: '#475569' }}>Cancel</button>
            <button type="submit" disabled={loading || !formData.ticker || !formData.quantity || !formData.buy_price} className="flex-1 py-2.5 rounded-xl text-sm font-semibold transition-all" style={{ background: '#2563eb', color: '#ffffff', boxShadow: '0 2px 8px rgba(37,99,235,0.25)', opacity: loading || !formData.ticker ? 0.6 : 1 }}>
              {loading ? 'Adding...' : 'Add Stock'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

async function removeStock(id, ticker, apiUrl, onSuccess) {
  if (!window.confirm(`Remove ${ticker} from portfolio?`)) return;
  try {
    await axios.delete(`${apiUrl}/api/portfolio/${id}`);
    toast.success(`${ticker} removed from portfolio`);
    onSuccess();
  } catch { toast.error('Failed to remove stock'); }
}
