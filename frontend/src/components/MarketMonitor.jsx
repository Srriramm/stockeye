import React, { useState, useEffect, useCallback } from 'react';
import { Activity, Eye, Bell, Search, RefreshCw, Trash2, ArrowUpRight, ArrowDownRight, Target, TrendingUp, X, Newspaper, ChevronDown, ChevronUp } from 'lucide-react';
import { LineChart, Line, ResponsiveContainer } from 'recharts';
import axios from 'axios';
import { authAxios } from '../utils/api';
import { toast } from 'react-toastify';

export default function MarketMonitor({ apiUrl, socket, alerts: globalAlerts }) {
  const [monitoredStocks, setMonitoredStocks] = useState([]);
  const [alerts, setAlerts] = useState(globalAlerts || []);
  const [loading, setLoading] = useState(true);
  const [addTicker, setAddTicker] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [showAddPriceAlert, setShowAddPriceAlert] = useState(false);
  const [priceAlertForm, setPriceAlertForm] = useState({ ticker: '', target_price: '', direction: 'above' });
  const [news, setNews] = useState([]);
  const [stockHistories, setStockHistories] = useState({});
  const [stockSignals, setStockSignals] = useState({});   // { TICKER: { signal, score, rsi, ... } }
  const [stockNews, setStockNews] = useState({});          // { TICKER: [articles] }
  const [expandedStock, setExpandedStock] = useState(null); // ticker whose news panel is open
  const [newsLoading, setNewsLoading] = useState({});       // { TICKER: bool }

  const fetchMonitoredStocks = useCallback(async () => {
    try {
      const [stocksRes, alertsRes, newsRes] = await Promise.allSettled([
        authAxios.get(`${apiUrl}/api/monitor/stocks`),
        authAxios.get(`${apiUrl}/api/alerts?hours=24&limit=50`),
        axios.get(`${apiUrl}/api/news/market`),
      ]);
      if (stocksRes.status === 'fulfilled') {
        const stocks = stocksRes.value.data.stocks || [];
        setMonitoredStocks(stocks);

        // Fetch chart histories (first 10 stocks)
        for (const stock of stocks.slice(0, 10)) {
          try {
            const histRes = await axios.get(`${apiUrl}/api/stocks/${stock.ticker}/history?period=5d&interval=1h`);
            setStockHistories(prev => ({ ...prev, [stock.ticker]: histRes.data.data || [] }));
          } catch { }
        }

        // Fetch quick signals in parallel for all monitored stocks
        const signalResults = await Promise.allSettled(
          stocks.map(s => axios.get(`${apiUrl}/api/stocks/${s.ticker}/quick-signal`))
        );
        const signals = {};
        signalResults.forEach((res, i) => {
          if (res.status === 'fulfilled') {
            signals[stocks[i].ticker] = res.value.data;
          }
        });
        setStockSignals(prev => ({ ...prev, ...signals }));
      }
      if (alertsRes.status === 'fulfilled') setAlerts(alertsRes.value.data.alerts || []);
      if (newsRes.status === 'fulfilled') setNews(newsRes.value.data.news || []);
    } catch (err) {
      toast.error('Failed to load monitoring data');
    } finally { setLoading(false); }
  }, [apiUrl]);

  useEffect(() => {
    fetchMonitoredStocks();
    const interval = setInterval(fetchMonitoredStocks, 60000);
    return () => clearInterval(interval);
  }, [fetchMonitoredStocks]);

  useEffect(() => {
    if (!socket) return;
    const handleAlert = (alert) => setAlerts(prev => [alert, ...prev].slice(0, 50));
    socket.on('new_alert', handleAlert);
    return () => socket.off('new_alert', handleAlert);
  }, [socket]);

  const searchStocks = async (query) => {
    if (query.length < 1) { setSearchResults([]); return; }
    try {
      const res = await axios.get(`${apiUrl}/api/stocks/search?q=${encodeURIComponent(query)}`);
      setSearchResults(res.data.results || []);
    } catch { }
  };

  const startMonitoring = async (ticker) => {
    try {
      await authAxios.post(`${apiUrl}/api/monitor/start`, { ticker });
      setAddTicker(''); setSearchResults([]);
      toast.success(`Started monitoring ${ticker}`);
      fetchMonitoredStocks();
    } catch { toast.error('Failed to start monitoring'); }
  };

  const stopMonitoring = async (ticker) => {
    try {
      await authAxios.post(`${apiUrl}/api/monitor/stop`, { ticker });
      if (expandedStock === ticker) setExpandedStock(null);
      toast.success(`Stopped monitoring ${ticker}`);
      fetchMonitoredStocks();
    } catch { toast.error('Failed to stop monitoring'); }
  };

  const toggleStockNews = async (ticker) => {
    if (expandedStock === ticker) {
      setExpandedStock(null);
      return;
    }
    setExpandedStock(ticker);
    if (stockNews[ticker]) return; // already fetched
    setNewsLoading(prev => ({ ...prev, [ticker]: true }));
    try {
      const res = await axios.get(`${apiUrl}/api/news/${ticker}`);
      setStockNews(prev => ({ ...prev, [ticker]: res.data?.news || [] }));
    } catch {
      setStockNews(prev => ({ ...prev, [ticker]: [] }));
    } finally {
      setNewsLoading(prev => ({ ...prev, [ticker]: false }));
    }
  };

  const addPriceAlert = async (e) => {
    e.preventDefault();
    if (!priceAlertForm.ticker || !priceAlertForm.target_price) return;
    if (!/^[A-Z]{2,10}$/i.test(priceAlertForm.ticker.trim())) { toast.error('Invalid ticker format'); return; }
    const targetPrice = parseFloat(priceAlertForm.target_price);
    if (isNaN(targetPrice) || targetPrice <= 0) { toast.error('Target price must be positive'); return; }
    try {
      await authAxios.post(`${apiUrl}/api/alerts/price`, { ticker: priceAlertForm.ticker, target_price: targetPrice, direction: priceAlertForm.direction });
      setShowAddPriceAlert(false);
      setPriceAlertForm({ ticker: '', target_price: '', direction: 'above' });
      toast.success('Price alert set!');
    } catch (err) { toast.error(err.response?.data?.error || 'Failed to set price alert'); }
  };

  const severityStyle = (severity) => {
    if (severity === 'critical') return { bg: '#fff1f2', text: '#991b1b', border: '#fecdd3', dotColor: '#ef4444' };
    if (severity === 'warning') return { bg: '#fffbeb', text: '#92400e', border: '#fde68a', dotColor: '#f59e0b' };
    return { bg: '#eff6ff', text: '#1e40af', border: '#bfdbfe', dotColor: '#2563eb' };
  };

  const signalStyle = (signal) => {
    if (signal === 'BUY') return { bg: '#f0fdf4', text: '#15803d', border: '#bbf7d0' };
    if (signal === 'SELL') return { bg: '#fff1f2', text: '#991b1b', border: '#fecdd3' };
    return { bg: '#f8fafc', text: '#475569', border: '#e2e8f0' };
  };

  const inputStyle = { background: '#f8fafc', border: '1px solid #e2e8f0', color: '#0f172a', borderRadius: 10, padding: '10px 14px', fontSize: 14, width: '100%' };

  return (
    <div className="p-6 space-y-6 fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: '#0f172a' }}>Market Monitor</h1>
          <p className="text-sm mt-0.5" style={{ color: '#64748b' }}>Real-time stock monitoring and alerts</p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={() => setShowAddPriceAlert(true)} className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium transition-all" style={{ background: '#f8fafc', border: '1px solid #e2e8f0', color: '#475569' }}
            onMouseEnter={e => { e.currentTarget.style.background = '#eff6ff'; e.currentTarget.style.color = '#1d4ed8'; }}
            onMouseLeave={e => { e.currentTarget.style.background = '#f8fafc'; e.currentTarget.style.color = '#475569'; }}>
            <Target size={14} /> Price Alert
          </button>
          <button onClick={fetchMonitoredStocks} className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium transition-all" style={{ background: '#f8fafc', border: '1px solid #e2e8f0', color: '#475569' }}
            onMouseEnter={e => { e.currentTarget.style.background = '#f1f5f9'; e.currentTarget.style.color = '#0f172a'; }}
            onMouseLeave={e => { e.currentTarget.style.background = '#f8fafc'; e.currentTarget.style.color = '#475569'; }}>
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {/* Search to Monitor */}
      <div className="rounded-xl p-4" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
        <div className="relative max-w-md">
          <div className="relative flex items-center gap-3">
            <div className="relative flex-1">
              <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: '#94a3b8' }} />
              <input
                type="text"
                value={addTicker}
                onChange={(e) => { setAddTicker(e.target.value); searchStocks(e.target.value); }}
                placeholder="Search stock to monitor..."
                className="w-full text-sm pl-9 pr-4 py-2.5 rounded-xl transition-all"
                style={{ background: '#f8fafc', border: '1px solid #e2e8f0', color: '#0f172a' }}
                onFocus={e => { e.target.style.borderColor = '#2563eb'; e.target.style.boxShadow = '0 0 0 3px rgba(37,99,235,0.1)'; }}
                onBlur={e => { e.target.style.borderColor = '#e2e8f0'; e.target.style.boxShadow = ''; }}
              />
            </div>
          </div>
          {searchResults.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-1 rounded-xl overflow-hidden z-10" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 8px 24px rgba(0,0,0,0.1)' }}>
              {searchResults.map((stock, i) => (
                <button key={i} onClick={() => startMonitoring(stock.ticker)} className="w-full flex justify-between items-center px-4 py-3 text-left transition-colors border-b last:border-0"
                  style={{ borderColor: '#f8fafc' }}
                  onMouseEnter={e => { e.currentTarget.style.background = '#f8fafc'; }}
                  onMouseLeave={e => { e.currentTarget.style.background = ''; }}>
                  <div>
                    <div className="text-sm font-semibold" style={{ color: '#0f172a' }}>{stock.ticker}</div>
                    <div className="text-xs" style={{ color: '#94a3b8' }}>{stock.name}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs" style={{ color: '#94a3b8' }}>{stock.sector}</span>
                    <Eye size={13} style={{ color: '#2563eb' }} />
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Monitored Stocks */}
        <div className="lg:col-span-2 space-y-4">
          <h3 className="text-base font-bold flex items-center gap-2" style={{ color: '#0f172a' }}>
            <Eye size={16} style={{ color: '#2563eb' }} /> Active Monitors ({monitoredStocks.length})
          </h3>
          {loading ? (
            <div className="rounded-xl p-12 text-center text-sm" style={{ background: '#ffffff', border: '1px solid #e2e8f0', color: '#94a3b8' }}>Loading monitored stocks...</div>
          ) : monitoredStocks.length === 0 ? (
            <div className="rounded-xl p-14 text-center" style={{ background: '#ffffff', border: '1px solid #e2e8f0' }}>
              <Eye size={36} className="mx-auto mb-3" style={{ color: '#cbd5e1' }} />
              <p className="text-sm mb-1" style={{ color: '#64748b' }}>No stocks being monitored</p>
              <p className="text-xs" style={{ color: '#94a3b8' }}>Search above to start monitoring</p>
            </div>
          ) : (
            <div className="space-y-4">
              {monitoredStocks.map((stock) => {
                const sig = stockSignals[stock.ticker];
                const ss = signalStyle(sig?.signal);
                const isExpanded = expandedStock === stock.ticker;
                const articles = stockNews[stock.ticker] || [];
                const loadingNews = newsLoading[stock.ticker];

                return (
                  <div key={stock.ticker} className="rounded-xl overflow-hidden transition-all" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.06)' }}>
                    {/* Stock card row */}
                    <div className="p-5">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3">
                          <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: stock.change_percent >= 0 ? '#f0fdf4' : '#fff1f2' }}>
                            <Activity size={16} style={{ color: stock.change_percent >= 0 ? '#059669' : '#dc2626' }} />
                          </div>
                          <div>
                            <div className="font-bold text-sm" style={{ color: '#0f172a' }}>{stock.ticker}</div>
                            <div className="text-xs" style={{ color: '#94a3b8' }}>{stock.name?.substring(0, 24)}</div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {/* Signal badge */}
                          {sig && (
                            <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold" style={{ background: ss.bg, color: ss.text, border: `1px solid ${ss.border}` }}>
                              {sig.signal}
                            </span>
                          )}
                          <button onClick={() => stopMonitoring(stock.ticker)} className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium transition-all" title="Remove from monitor"
                            style={{ background: '#fff1f2', color: '#dc2626', border: '1px solid #fecdd3' }}
                            onMouseEnter={e => { e.currentTarget.style.background = '#fee2e2'; e.currentTarget.style.borderColor = '#fca5a5'; }}
                            onMouseLeave={e => { e.currentTarget.style.background = '#fff1f2'; e.currentTarget.style.borderColor = '#fecdd3'; }}>
                            <Trash2 size={11} /> Remove
                          </button>
                        </div>
                      </div>

                      <div className="flex items-end justify-between mb-3">
                        <div>
                          <div className="text-xl font-bold font-mono-nums" style={{ color: '#0f172a' }}>₹{stock.current_price?.toLocaleString('en-IN')}</div>
                          <div className="flex items-center gap-1 text-xs font-bold mt-0.5" style={{ color: stock.change_percent >= 0 ? '#059669' : '#dc2626' }}>
                            {stock.change_percent >= 0 ? <ArrowUpRight size={11} /> : <ArrowDownRight size={11} />}
                            {stock.change_percent >= 0 ? '+' : ''}{stock.change_percent?.toFixed(2)}%
                          </div>
                        </div>
                        <div className="text-right">
                          {sig && (
                            <div className="text-[10px] font-mono" style={{ color: '#94a3b8' }}>
                              RSI {sig.rsi} · Score {sig.score}
                            </div>
                          )}
                          <div className="text-[10px] mt-0.5" style={{ color: '#94a3b8' }}>Base: ₹{stock.price_baseline?.toLocaleString('en-IN')}</div>
                        </div>
                      </div>

                      {stockHistories[stock.ticker]?.length > 0 && (
                        <ResponsiveContainer width="100%" height={48}>
                          <LineChart data={stockHistories[stock.ticker].slice(-48)}>
                            <Line type="monotone" dataKey="close" dot={false} stroke={stock.change_percent >= 0 ? '#059669' : '#dc2626'} strokeWidth={1.5} />
                          </LineChart>
                        </ResponsiveContainer>
                      )}

                      <div className="flex items-center justify-between mt-3">
                        <div className="flex items-center gap-2">
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold" style={{
                            background: stock.change_percent >= 0 ? '#f0fdf4' : '#fff1f2',
                            color: stock.change_percent >= 0 ? '#059669' : '#dc2626',
                          }}>
                            {stock.change_percent >= 0 ? '▲ Bullish' : '▼ Bearish'}
                          </span>
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold" style={{ background: '#eff6ff', color: '#1e40af' }}>
                            Monitoring
                          </span>
                          {sig && (
                            <span className="text-[10px]" style={{ color: '#94a3b8' }}>
                              {sig.positive_news}↑ {sig.negative_news}↓ news
                            </span>
                          )}
                        </div>
                        {/* Toggle news button */}
                        <button
                          onClick={() => toggleStockNews(stock.ticker)}
                          className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium transition-all"
                          style={{ background: isExpanded ? '#eff6ff' : '#f8fafc', color: isExpanded ? '#1d4ed8' : '#64748b', border: `1px solid ${isExpanded ? '#bfdbfe' : '#e2e8f0'}` }}
                        >
                          <Newspaper size={11} />
                          News
                          {isExpanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
                        </button>
                      </div>
                    </div>

                    {/* Expandable news panel */}
                    {isExpanded && (
                      <div style={{ borderTop: '1px solid #f1f5f9', background: '#f8fafc' }}>
                        <div className="px-5 py-3 flex items-center justify-between">
                          <span className="text-xs font-semibold" style={{ color: '#64748b' }}>
                            Latest news for {stock.ticker}
                          </span>
                          {sig && (
                            <span className="text-[10px]" style={{ color: '#94a3b8' }}>
                              {sig.positive_news} positive · {sig.negative_news} negative · {sig.neutral_news} neutral
                            </span>
                          )}
                        </div>
                        {loadingNews ? (
                          <div className="px-5 pb-4 text-xs" style={{ color: '#94a3b8' }}>Loading news...</div>
                        ) : articles.length === 0 ? (
                          <div className="px-5 pb-4 text-xs" style={{ color: '#94a3b8' }}>No recent news found.</div>
                        ) : (
                          <div className="divide-y" style={{ borderColor: '#e2e8f0' }}>
                            {articles.slice(0, 6).map((article, i) => (
                              <a key={i} href={article.url} target="_blank" rel="noopener noreferrer"
                                className="flex items-start gap-3 px-5 py-3 transition-colors"
                                style={{ textDecoration: 'none' }}
                                onMouseEnter={e => { e.currentTarget.style.background = '#ffffff'; }}
                                onMouseLeave={e => { e.currentTarget.style.background = ''; }}>
                                <span className="w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0" style={{
                                  background: article.sentiment === 'positive' ? '#10b981' : article.sentiment === 'negative' ? '#ef4444' : '#f59e0b'
                                }} />
                                <div className="flex-1 min-w-0">
                                  <p className="text-xs leading-snug" style={{ color: '#334155' }}>{article.title}</p>
                                  <div className="flex items-center gap-2 mt-1">
                                    <span className="text-[10px]" style={{ color: '#94a3b8' }}>{article.source}</span>
                                    {article.published_at && (
                                      <span className="text-[10px]" style={{ color: '#cbd5e1' }}>
                                        {new Date(article.published_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                                      </span>
                                    )}
                                    <span className="text-[10px] px-1.5 py-0.5 rounded" style={{
                                      background: article.sentiment === 'positive' ? '#f0fdf4' : article.sentiment === 'negative' ? '#fff1f2' : '#fffbeb',
                                      color: article.sentiment === 'positive' ? '#15803d' : article.sentiment === 'negative' ? '#991b1b' : '#92400e',
                                    }}>
                                      {article.sentiment}
                                    </span>
                                  </div>
                                </div>
                              </a>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Alerts + News */}
        <div className="space-y-5">
          {/* Alerts */}
          <div>
            <h3 className="text-base font-bold mb-3 flex items-center gap-2" style={{ color: '#0f172a' }}>
              <Bell size={16} style={{ color: '#f59e0b' }} /> Live Alerts
            </h3>
            <div className="rounded-xl overflow-hidden max-h-72 overflow-y-auto custom-scrollbar" style={{ background: '#ffffff', border: '1px solid #e2e8f0' }}>
              {alerts.length === 0 ? (
                <div className="p-8 text-center text-sm" style={{ color: '#94a3b8' }}>No alerts yet.</div>
              ) : (
                alerts.map((alert, i) => {
                  const s = severityStyle(alert.severity);
                  return (
                    <div key={i} className="p-3.5 border-b last:border-0" style={{ borderColor: '#f8fafc', borderLeft: `3px solid ${s.dotColor}` }}>
                      <div className="flex items-start gap-2">
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded" style={{ background: '#f1f5f9', color: '#475569' }}>{alert.ticker}</span>
                            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded" style={{ background: s.bg, color: s.text }}>{alert.alert_type || alert.type}</span>
                          </div>
                          <p className="text-xs break-words" style={{ color: '#475569' }}>{alert.message}</p>
                          <p className="text-[10px] mt-1 font-mono" style={{ color: '#94a3b8' }}>
                            {new Date(alert.created_at || alert.timestamp).toLocaleString('en-IN', { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' })}
                          </p>
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Market News */}
          <div>
            <h3 className="text-base font-bold mb-3" style={{ color: '#0f172a' }}>Market News</h3>
            <div className="rounded-xl overflow-hidden max-h-80 overflow-y-auto custom-scrollbar" style={{ background: '#ffffff', border: '1px solid #e2e8f0' }}>
              {news.length === 0 ? (
                <div className="p-8 text-center text-sm" style={{ color: '#94a3b8' }}>Loading news...</div>
              ) : (
                news.slice(0, 10).map((article, i) => (
                  <a key={i} href={article.url} target="_blank" rel="noopener noreferrer"
                    className="block p-3.5 border-b last:border-0 transition-colors"
                    style={{ borderColor: '#f8fafc' }}
                    onMouseEnter={e => { e.currentTarget.style.background = '#f8fafc'; }}
                    onMouseLeave={e => { e.currentTarget.style.background = ''; }}>
                    <div className="flex items-start gap-2">
                      <span className="w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0" style={{ background: article.sentiment === 'positive' ? '#10b981' : article.sentiment === 'negative' ? '#ef4444' : '#f59e0b' }} />
                      <div>
                        <p className="text-xs leading-snug" style={{ color: '#334155' }}>{article.title?.substring(0, 100)}</p>
                        <span className="text-[10px] mt-1 block" style={{ color: '#94a3b8' }}>{article.source}</span>
                      </div>
                    </div>
                  </a>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Price Alert Modal */}
      {showAddPriceAlert && (
        <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: 'rgba(15,23,42,0.4)', backdropFilter: 'blur(4px)' }}>
          <div className="w-full max-w-sm rounded-2xl p-6 fade-in" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 20px 60px rgba(0,0,0,0.15)' }}>
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-base font-bold" style={{ color: '#0f172a' }}>Set Price Alert</h3>
              <button onClick={() => setShowAddPriceAlert(false)} style={{ color: '#94a3b8' }}><X size={18} /></button>
            </div>
            <form onSubmit={addPriceAlert} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold mb-1.5 uppercase tracking-wide" style={{ color: '#64748b' }}>Ticker</label>
                <input type="text" value={priceAlertForm.ticker}
                  onChange={e => setPriceAlertForm(prev => ({ ...prev, ticker: e.target.value.toUpperCase() }))}
                  style={inputStyle} placeholder="e.g., RELIANCE" required />
              </div>
              <div>
                <label className="block text-xs font-semibold mb-1.5 uppercase tracking-wide" style={{ color: '#64748b' }}>Target Price (₹)</label>
                <input type="number" step="0.01" value={priceAlertForm.target_price}
                  onChange={e => setPriceAlertForm(prev => ({ ...prev, target_price: e.target.value }))}
                  style={inputStyle} placeholder="e.g., 2500" required />
              </div>
              <div>
                <label className="block text-xs font-semibold mb-1.5 uppercase tracking-wide" style={{ color: '#64748b' }}>Alert condition</label>
                <select value={priceAlertForm.direction}
                  onChange={e => setPriceAlertForm(prev => ({ ...prev, direction: e.target.value }))}
                  style={inputStyle}>
                  <option value="above">Price goes Above target</option>
                  <option value="below">Price falls Below target</option>
                </select>
              </div>
              <button type="submit" className="w-full py-3 rounded-xl text-sm font-semibold" style={{ background: '#2563eb', color: '#ffffff', boxShadow: '0 2px 8px rgba(37,99,235,0.25)' }}>
                Set Alert
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
