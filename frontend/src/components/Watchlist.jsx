import React, { useState, useEffect } from 'react';
import {
  Plus, Search, Trash2, MoreVertical, TrendingUp, TrendingDown, X,
} from 'lucide-react';
import axios from 'axios';
import { toast } from 'react-toastify';
import wsManager from '../utils/websocket';

export default function Watchlist({ apiUrl }) {
  const [watchlists, setWatchlists] = useState([]);
  const [activeWatchlist, setActiveWatchlist] = useState(null);
  const [watchlistItems, setWatchlistItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [priceData, setPriceData] = useState({});

  useEffect(() => { fetchWatchlists(); }, []);

  useEffect(() => {
    if (activeWatchlist) fetchWatchlistItems(activeWatchlist.id);
  }, [activeWatchlist]);

  useEffect(() => {
    const unsubscribers = watchlistItems.map(item =>
      wsManager.subscribe(item.ticker, (data) => {
        setPriceData(prev => ({ ...prev, [item.ticker]: data }));
      })
    );
    return () => unsubscribers.forEach(u => u());
  }, [watchlistItems]);

  const fetchWatchlists = async () => {
    try {
      const res = await axios.get(`${apiUrl}/api/watchlists`);
      const lists = res.data.watchlists || [];
      setWatchlists(lists);
      if (!activeWatchlist && lists.length > 0) setActiveWatchlist(lists[0]);
    } catch { toast.error('Failed to load watchlists'); }
    finally { setLoading(false); }
  };

  const fetchWatchlistItems = async (id) => {
    try {
      const res = await axios.get(`${apiUrl}/api/watchlists/${id}`);
      setWatchlistItems(res.data.items || []);
    } catch { toast.error('Failed to load watchlist items'); }
  };

  const createWatchlist = async (name, color = '#2563eb') => {
    try {
      await axios.post(`${apiUrl}/api/watchlists`, { name, color });
      toast.success('Watchlist created');
      fetchWatchlists();
      setShowCreateModal(false);
    } catch { toast.error('Failed to create watchlist'); }
  };

  const deleteWatchlist = async (id) => {
    if (!window.confirm('Delete this watchlist?')) return;
    try {
      await axios.delete(`${apiUrl}/api/watchlists/${id}`);
      toast.success('Watchlist deleted');
      fetchWatchlists();
      if (activeWatchlist?.id === id) setActiveWatchlist(null);
    } catch { toast.error('Failed to delete watchlist'); }
  };

  const addStockToWatchlist = async (ticker, name = '') => {
    if (!activeWatchlist) return;
    try {
      await axios.post(`${apiUrl}/api/watchlists/${activeWatchlist.id}/items`, { ticker: ticker.toUpperCase(), name });
      toast.success(`${ticker} added to watchlist`);
      fetchWatchlistItems(activeWatchlist.id);
      setShowAddModal(false);
      setSearchQuery('');
    } catch (err) {
      if (err.response?.status === 409) toast.error('Stock already in watchlist');
      else toast.error('Failed to add stock');
    }
  };

  const removeStock = async (ticker) => {
    if (!activeWatchlist) return;
    try {
      await axios.delete(`${apiUrl}/api/watchlists/${activeWatchlist.id}/items/${ticker}`);
      toast.success(`${ticker} removed`);
      fetchWatchlistItems(activeWatchlist.id);
    } catch { toast.error('Failed to remove stock'); }
  };

  const filteredItems = watchlistItems.filter(item =>
    item.ticker.toLowerCase().includes(searchQuery.toLowerCase()) ||
    item.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center">
        <div className="text-sm animate-pulse" style={{ color: '#94a3b8' }}>Loading watchlists...</div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col" style={{ background: '#f8fafc' }}>
      {/* Header */}
      <div className="px-6 py-5" style={{ background: '#ffffff', borderBottom: '1px solid #e2e8f0' }}>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-bold" style={{ color: '#0f172a' }}>Watchlists</h1>
            <p className="text-sm mt-0.5" style={{ color: '#64748b' }}>Track your favourite stocks</p>
          </div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold transition-all"
            style={{ background: '#2563eb', color: '#ffffff', boxShadow: '0 2px 8px rgba(37,99,235,0.25)' }}
            onMouseEnter={e => { e.currentTarget.style.background = '#1d4ed8'; }}
            onMouseLeave={e => { e.currentTarget.style.background = '#2563eb'; }}
          >
            <Plus size={15} />
            New List
          </button>
        </div>

        {/* Tabs */}
        <div className="flex items-center gap-2 overflow-x-auto custom-scrollbar pb-1">
          {watchlists.map(wl => (
            <button
              key={wl.id}
              onClick={() => setActiveWatchlist(wl)}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition-all flex-shrink-0"
              style={activeWatchlist?.id === wl.id
                ? { background: '#eff6ff', color: '#1d4ed8', border: '1px solid #bfdbfe' }
                : { background: 'transparent', color: '#64748b', border: '1px solid transparent' }
              }
              onMouseEnter={e => { if (activeWatchlist?.id !== wl.id) { e.currentTarget.style.background = '#f8fafc'; e.currentTarget.style.color = '#0f172a'; } }}
              onMouseLeave={e => { if (activeWatchlist?.id !== wl.id) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = '#64748b'; } }}
            >
              <span className="w-2 h-2 rounded-full" style={{ background: wl.color }} />
              {wl.name}
              <span className="text-[10px] font-normal opacity-60">({wl.item_count})</span>
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      {activeWatchlist ? (
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Toolbar */}
          <div className="px-6 py-3 flex items-center justify-between gap-3" style={{ background: '#ffffff', borderBottom: '1px solid #f1f5f9' }}>
            <div className="relative flex-1 max-w-sm">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2" size={15} style={{ color: '#94a3b8' }} />
              <input
                type="text"
                placeholder="Search stocks..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-4 py-2 text-sm rounded-lg transition-all"
                style={{ background: '#f8fafc', border: '1px solid #e2e8f0', color: '#0f172a' }}
                onFocus={e => { e.target.style.borderColor = '#2563eb'; e.target.style.boxShadow = '0 0 0 3px rgba(37,99,235,0.1)'; }}
                onBlur={e => { e.target.style.borderColor = '#e2e8f0'; e.target.style.boxShadow = ''; }}
              />
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setShowAddModal(true)}
                className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all"
                style={{ background: '#f8fafc', border: '1px solid #e2e8f0', color: '#475569' }}
                onMouseEnter={e => { e.currentTarget.style.background = '#eff6ff'; e.currentTarget.style.borderColor = '#bfdbfe'; e.currentTarget.style.color = '#1d4ed8'; }}
                onMouseLeave={e => { e.currentTarget.style.background = '#f8fafc'; e.currentTarget.style.borderColor = '#e2e8f0'; e.currentTarget.style.color = '#475569'; }}
              >
                <Plus size={14} /> Add Stock
              </button>
              <button
                onClick={() => deleteWatchlist(activeWatchlist.id)}
                className="p-2 rounded-lg transition-all"
                style={{ color: '#94a3b8', background: '#f8fafc', border: '1px solid #e2e8f0' }}
                onMouseEnter={e => { e.currentTarget.style.color = '#dc2626'; e.currentTarget.style.background = '#fee2e2'; e.currentTarget.style.borderColor = '#fca5a5'; }}
                onMouseLeave={e => { e.currentTarget.style.color = '#94a3b8'; e.currentTarget.style.background = '#f8fafc'; e.currentTarget.style.borderColor = '#e2e8f0'; }}
              >
                <Trash2 size={15} />
              </button>
            </div>
          </div>

          {/* Stock List */}
          <div className="flex-1 overflow-y-auto custom-scrollbar">
            {/* Table header */}
            <div
              className="grid px-6 py-2.5"
              style={{ gridTemplateColumns: '1fr auto auto auto', borderBottom: '1px solid #f1f5f9', background: '#fcfcfd' }}
            >
              <span className="text-[10px] font-bold uppercase tracking-wider" style={{ color: '#94a3b8' }}>Stock</span>
              <span className="text-[10px] font-bold uppercase tracking-wider text-right pr-8" style={{ color: '#94a3b8' }}>Price</span>
              <span className="text-[10px] font-bold uppercase tracking-wider text-right pr-8" style={{ color: '#94a3b8' }}>Change</span>
              <span></span>
            </div>

            {filteredItems.length === 0 ? (
              <div className="py-16 text-center">
                <p className="text-sm mb-2" style={{ color: '#94a3b8' }}>No stocks in this watchlist</p>
                <button
                  onClick={() => setShowAddModal(true)}
                  className="text-sm font-semibold transition-colors"
                  style={{ color: '#2563eb' }}
                >
                  Add your first stock →
                </button>
              </div>
            ) : (
              filteredItems.map(item => (
                <WatchlistRow
                  key={item.ticker}
                  item={item}
                  priceData={priceData[item.ticker]}
                  onRemove={() => removeStock(item.ticker)}
                />
              ))
            )}
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <p className="text-sm mb-4" style={{ color: '#94a3b8' }}>No watchlist selected</p>
            <button
              onClick={() => setShowCreateModal(true)}
              className="px-4 py-2.5 rounded-xl text-sm font-semibold"
              style={{ background: '#2563eb', color: '#ffffff', boxShadow: '0 2px 8px rgba(37,99,235,0.25)' }}
            >
              Create your first watchlist
            </button>
          </div>
        </div>
      )}

      {/* Modals */}
      {showCreateModal && <CreateWatchlistModal onClose={() => setShowCreateModal(false)} onCreate={createWatchlist} />}
      {showAddModal && <AddStockModal apiUrl={apiUrl} onClose={() => setShowAddModal(false)} onAdd={addStockToWatchlist} />}
    </div>
  );
}

function WatchlistRow({ item, priceData, onRemove }) {
  const [showMenu, setShowMenu] = useState(false);

  if (!priceData) {
    return (
      <div className="grid px-6 py-3.5 animate-pulse" style={{ gridTemplateColumns: '1fr auto auto auto', borderBottom: '1px solid #f8fafc' }}>
        <div className="h-4 rounded" style={{ background: '#f1f5f9', width: 80 }} />
        <div className="h-4 rounded mr-8" style={{ background: '#f1f5f9', width: 60 }} />
        <div className="h-4 rounded mr-8" style={{ background: '#f1f5f9', width: 50 }} />
        <div style={{ width: 32 }} />
      </div>
    );
  }

  const { current_price, change, change_percent } = priceData;
  const isPositive = change >= 0;

  return (
    <div
      className="grid px-6 py-3.5 group transition-colors"
      style={{ gridTemplateColumns: '1fr auto auto auto', borderBottom: '1px solid #f8fafc' }}
      onMouseEnter={e => { e.currentTarget.style.background = '#f8fafc'; }}
      onMouseLeave={e => { e.currentTarget.style.background = ''; }}
    >
      <div className="flex-1 min-w-0">
        <div className="font-semibold text-sm" style={{ color: '#0f172a' }}>{item.ticker}</div>
        <div className="text-xs mt-0.5 truncate" style={{ color: '#94a3b8' }}>{item.name}</div>
      </div>
      <div className="text-right pr-8">
        <div className="text-sm font-bold font-mono-nums" style={{ color: '#0f172a' }}>
          ₹{current_price?.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
        </div>
      </div>
      <div className="text-right pr-8">
        <div
          className="text-xs font-bold flex items-center justify-end gap-1"
          style={{ color: isPositive ? '#059669' : '#dc2626' }}
        >
          {isPositive ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
          {isPositive ? '+' : ''}{change?.toFixed(2)} ({isPositive ? '+' : ''}{change_percent?.toFixed(2)}%)
        </div>
      </div>
      <div className="relative flex items-center">
        <button
          onClick={() => setShowMenu(!showMenu)}
          className="w-7 h-7 rounded-lg flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all"
          style={{ color: '#94a3b8' }}
          onMouseEnter={e => { e.currentTarget.style.background = '#f1f5f9'; e.currentTarget.style.color = '#475569'; }}
          onMouseLeave={e => { e.currentTarget.style.background = ''; e.currentTarget.style.color = '#94a3b8'; }}
        >
          <MoreVertical size={14} />
        </button>
        {showMenu && (
          <div
            className="absolute right-0 top-full mt-1 w-36 rounded-xl overflow-hidden z-10"
            style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 8px 24px rgba(0,0,0,0.1)' }}
          >
            <button
              onClick={() => { onRemove(); setShowMenu(false); }}
              className="w-full px-4 py-2.5 text-left text-sm transition-colors"
              style={{ color: '#dc2626' }}
              onMouseEnter={e => { e.currentTarget.style.background = '#fff1f2'; }}
              onMouseLeave={e => { e.currentTarget.style.background = ''; }}
            >
              Remove
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function CreateWatchlistModal({ onClose, onCreate }) {
  const [name, setName] = useState('');
  const [color, setColor] = useState('#2563eb');
  const colors = ['#2563eb', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];

  return (
    <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: 'rgba(15,23,42,0.4)', backdropFilter: 'blur(4px)' }}>
      <div className="w-full max-w-sm rounded-2xl p-6 fade-in" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 20px 60px rgba(0,0,0,0.15)' }}>
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-base font-bold" style={{ color: '#0f172a' }}>Create Watchlist</h3>
          <button onClick={onClose} style={{ color: '#94a3b8' }} onMouseEnter={e => e.currentTarget.style.color = '#0f172a'} onMouseLeave={e => e.currentTarget.style.color = '#94a3b8'}>
            <X size={18} />
          </button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="block text-xs font-semibold mb-1.5 uppercase tracking-wide" style={{ color: '#64748b' }}>Name</label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="My Watchlist"
              className="w-full px-3.5 py-2.5 text-sm rounded-xl"
              style={{ background: '#f8fafc', border: '1px solid #e2e8f0', color: '#0f172a' }}
              onFocus={e => { e.target.style.borderColor = '#2563eb'; e.target.style.boxShadow = '0 0 0 3px rgba(37,99,235,0.1)'; }}
              onBlur={e => { e.target.style.borderColor = '#e2e8f0'; e.target.style.boxShadow = ''; }}
              autoFocus
            />
          </div>
          <div>
            <label className="block text-xs font-semibold mb-2 uppercase tracking-wide" style={{ color: '#64748b' }}>Color</label>
            <div className="flex gap-2">
              {colors.map(c => (
                <button
                  key={c}
                  onClick={() => setColor(c)}
                  className="w-7 h-7 rounded-lg transition-all"
                  style={{ background: c, outline: color === c ? `3px solid ${c}` : 'none', outlineOffset: 2 }}
                />
              ))}
            </div>
          </div>
          <div className="flex gap-3 pt-1">
            <button
              onClick={onClose}
              className="flex-1 py-2.5 rounded-xl text-sm font-medium transition-all"
              style={{ background: '#f8fafc', border: '1px solid #e2e8f0', color: '#475569' }}
              onMouseEnter={e => { e.currentTarget.style.background = '#f1f5f9'; }}
              onMouseLeave={e => { e.currentTarget.style.background = '#f8fafc'; }}
            >
              Cancel
            </button>
            <button
              onClick={() => onCreate(name, color)}
              disabled={!name}
              className="flex-1 py-2.5 rounded-xl text-sm font-semibold transition-all"
              style={{ background: '#2563eb', color: '#ffffff', boxShadow: '0 2px 8px rgba(37,99,235,0.25)', opacity: name ? 1 : 0.5 }}
              onMouseEnter={e => { if (name) e.currentTarget.style.background = '#1d4ed8'; }}
              onMouseLeave={e => { e.currentTarget.style.background = '#2563eb'; }}
            >
              Create
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function AddStockModal({ apiUrl, onClose, onAdd }) {
  const [search, setSearch] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (search.length < 1) { setResults([]); return; }
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await axios.get(`${apiUrl}/api/stocks/search?q=${search}`);
        setResults(res.data.results || []);
      } catch { } finally { setLoading(false); }
    }, 300);
    return () => clearTimeout(timer);
  }, [search, apiUrl]);

  return (
    <div className="fixed inset-0 flex items-center justify-center z-50" style={{ background: 'rgba(15,23,42,0.4)', backdropFilter: 'blur(4px)' }}>
      <div className="w-full max-w-md rounded-2xl p-6 fade-in" style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 20px 60px rgba(0,0,0,0.15)' }}>
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-base font-bold" style={{ color: '#0f172a' }}>Add Stock to Watchlist</h3>
          <button onClick={onClose} style={{ color: '#94a3b8' }}><X size={18} /></button>
        </div>
        <div className="relative mb-4">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2" size={15} style={{ color: '#94a3b8' }} />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search stocks (e.g., RELIANCE, TCS)"
            className="w-full pl-9 pr-4 py-2.5 text-sm rounded-xl"
            style={{ background: '#f8fafc', border: '1px solid #e2e8f0', color: '#0f172a' }}
            onFocus={e => { e.target.style.borderColor = '#2563eb'; e.target.style.boxShadow = '0 0 0 3px rgba(37,99,235,0.1)'; }}
            onBlur={e => { e.target.style.borderColor = '#e2e8f0'; e.target.style.boxShadow = ''; }}
            autoFocus
          />
        </div>
        <div className="max-h-72 overflow-y-auto custom-scrollbar rounded-xl" style={{ border: '1px solid #f1f5f9' }}>
          {loading ? (
            <div className="py-8 text-center text-sm" style={{ color: '#94a3b8' }}>Searching...</div>
          ) : results.length === 0 && search ? (
            <div className="py-8 text-center text-sm" style={{ color: '#94a3b8' }}>No stocks found</div>
          ) : (
            results.map(stock => (
              <button
                key={stock.ticker}
                onClick={() => onAdd(stock.ticker, stock.name)}
                className="w-full p-3.5 text-left transition-colors border-b last:border-0"
                style={{ borderColor: '#f8fafc' }}
                onMouseEnter={e => { e.currentTarget.style.background = '#eff6ff'; }}
                onMouseLeave={e => { e.currentTarget.style.background = ''; }}
              >
                <div className="font-semibold text-sm" style={{ color: '#0f172a' }}>{stock.ticker}</div>
                <div className="text-xs mt-0.5" style={{ color: '#94a3b8' }}>{stock.name}</div>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
