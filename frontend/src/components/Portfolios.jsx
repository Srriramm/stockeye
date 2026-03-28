import React, { useState, useEffect } from 'react';
import { authAxios } from '../utils/api';
import {
  Briefcase, Plus, Trash2, RefreshCw, AlertTriangle, CheckCircle,
} from 'lucide-react';

const API_URL = process.env.REACT_APP_API_URL || '';

const PALETTE = [
  '#2563eb', '#7c3aed', '#059669', '#dc2626', '#f59e0b',
  '#0891b2', '#db2777', '#65a30d', '#ea580c', '#6366f1',
];

function fmtINR(n) {
  if (n == null) return '—';
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(n);
}

export default function Portfolios({ onSelect, selectedId }) {
  const [portfolios, setPortfolios] = useState([]);
  const [loading,    setLoading]    = useState(false);
  const [creating,   setCreating]   = useState(false);
  const [error,      setError]      = useState('');
  const [success,    setSuccess]    = useState('');
  const [showForm,   setShowForm]   = useState(false);
  const [form, setForm] = useState({ name: '', description: '', starting_balance: 100000, color: '#2563eb' });

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await authAxios.get(`${API_URL}/api/portfolios`);
      setPortfolios(data.portfolios || []);
    } catch (e) {
      setError('Failed to load portfolios');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.name.trim()) return;
    setCreating(true);
    setError('');
    try {
      await authAxios.post(`${API_URL}/api/portfolios`, form);
      setSuccess(`Portfolio "${form.name}" created`);
      setForm({ name: '', description: '', starting_balance: 100000, color: '#2563eb' });
      setShowForm(false);
      await load();
      setTimeout(() => setSuccess(''), 3000);
    } catch (e) {
      setError(e.response?.data?.error || 'Failed to create portfolio');
    } finally {
      setCreating(false);
    }
  };

  const remove = async (id, name) => {
    if (!window.confirm(`Delete portfolio "${name}"? This cannot be undone.`)) return;
    try {
      await authAxios.delete(`${API_URL}/api/portfolios/${id}`);
      setPortfolios(prev => prev.filter(p => p.id !== id));
    } catch (e) {
      setError(e.response?.data?.error || 'Failed to delete');
    }
  };

  return (
    <div style={{
      background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 16,
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        padding: '14px 18px', borderBottom: '1px solid #f1f5f9',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Briefcase size={16} style={{ color: '#2563eb' }} />
          <span style={{ fontWeight: 700, fontSize: 14, color: '#0f172a' }}>Portfolios</span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={load}
            disabled={loading}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', padding: 4 }}
          >
            <RefreshCw size={13} style={{ animation: loading ? 'spin 0.8s linear infinite' : 'none' }} />
          </button>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
          <button
            onClick={() => setShowForm(!showForm)}
            style={{
              display: 'flex', alignItems: 'center', gap: 5,
              background: '#2563eb', color: '#fff', border: 'none', borderRadius: 8,
              padding: '5px 12px', fontSize: 12, fontWeight: 700, cursor: 'pointer',
            }}
          >
            <Plus size={12} /> New
          </button>
        </div>
      </div>

      {/* Feedback */}
      {error && (
        <div style={{ padding: '10px 18px', background: '#fef2f2', color: '#dc2626', fontSize: 12, display: 'flex', gap: 6, alignItems: 'center' }}>
          <AlertTriangle size={12} />{error}
        </div>
      )}
      {success && (
        <div style={{ padding: '10px 18px', background: '#d1fae5', color: '#065f46', fontSize: 12, display: 'flex', gap: 6, alignItems: 'center' }}>
          <CheckCircle size={12} />{success}
        </div>
      )}

      {/* Create form */}
      {showForm && (
        <div style={{
          padding: '16px 18px', borderBottom: '1px solid #f1f5f9',
          background: '#f8fafc', display: 'flex', flexDirection: 'column', gap: 10,
        }}>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <input
              placeholder="Portfolio name *"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              style={{
                flex: '1 1 180px', padding: '7px 10px', borderRadius: 8, fontSize: 13,
                border: '1px solid #e2e8f0', outline: 'none', background: '#fff',
              }}
            />
            <input
              placeholder="Description (optional)"
              value={form.description}
              onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              style={{
                flex: '2 1 200px', padding: '7px 10px', borderRadius: 8, fontSize: 13,
                border: '1px solid #e2e8f0', outline: 'none', background: '#fff',
              }}
            />
            <select
              value={form.starting_balance}
              onChange={e => setForm(f => ({ ...f, starting_balance: Number(e.target.value) }))}
              style={{ padding: '7px 10px', borderRadius: 8, fontSize: 13, border: '1px solid #e2e8f0', background: '#fff' }}
            >
              <option value={50000}>₹50,000</option>
              <option value={100000}>₹1,00,000</option>
              <option value={500000}>₹5,00,000</option>
              <option value={1000000}>₹10,00,000</option>
            </select>
          </div>

          {/* Color picker */}
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span style={{ fontSize: 11, color: '#64748b', fontWeight: 600 }}>Color:</span>
            {PALETTE.map(c => (
              <button
                key={c}
                onClick={() => setForm(f => ({ ...f, color: c }))}
                style={{
                  width: 18, height: 18, borderRadius: '50%', background: c, border: 'none', cursor: 'pointer',
                  outline: form.color === c ? `2px solid ${c}` : 'none',
                  outlineOffset: 2,
                }}
              />
            ))}
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={create}
              disabled={creating || !form.name.trim()}
              style={{
                padding: '7px 18px', borderRadius: 8, border: 'none', cursor: 'pointer',
                background: creating || !form.name.trim() ? '#e2e8f0' : '#2563eb',
                color: creating || !form.name.trim() ? '#94a3b8' : '#fff',
                fontSize: 13, fontWeight: 700,
              }}
            >
              {creating ? 'Creating…' : 'Create'}
            </button>
            <button
              onClick={() => setShowForm(false)}
              style={{ padding: '7px 18px', borderRadius: 8, border: '1px solid #e2e8f0', background: '#fff', fontSize: 13, cursor: 'pointer', color: '#64748b' }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Portfolio list */}
      <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {loading && portfolios.length === 0 && (
          <div style={{ padding: '20px', textAlign: 'center', color: '#94a3b8', fontSize: 13 }}>Loading…</div>
        )}
        {portfolios.map(p => {
          const isSelected = (selectedId || 'default') === p.id;
          const pnl = p.total_value != null && p.starting_balance
            ? p.total_value - p.starting_balance : null;
          return (
            <div
              key={p.id}
              onClick={() => onSelect && onSelect(p.id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '12px 14px', borderRadius: 12, cursor: onSelect ? 'pointer' : 'default',
                border: `1px solid ${isSelected ? p.color + '50' : '#f1f5f9'}`,
                background: isSelected ? p.color + '08' : '#f8fafc',
                transition: 'all 0.15s',
              }}
            >
              {/* Color strip */}
              <div style={{ width: 4, height: 36, borderRadius: 2, background: p.color, flexShrink: 0 }} />

              {/* Info */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontWeight: 700, fontSize: 13, color: '#0f172a' }}>{p.name}</span>
                  {p.is_default && (
                    <span style={{
                      fontSize: 9, fontWeight: 700, padding: '1px 5px', borderRadius: 4,
                      background: '#eff6ff', color: '#2563eb', textTransform: 'uppercase',
                    }}>Default</span>
                  )}
                </div>
                {p.description && (
                  <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 1 }}>{p.description}</div>
                )}
              </div>

              {/* Balance */}
              <div style={{ textAlign: 'right', flexShrink: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 700, fontFamily: 'monospace', color: '#0f172a' }}>
                  {p.total_value != null ? fmtINR(p.total_value) : fmtINR(p.starting_balance)}
                </div>
                {pnl != null && (
                  <div style={{ fontSize: 11, fontFamily: 'monospace', color: pnl >= 0 ? '#059669' : '#dc2626' }}>
                    {pnl >= 0 ? '+' : ''}{fmtINR(pnl)}
                  </div>
                )}
              </div>

              {/* Delete (non-default only) */}
              {!p.is_default && (
                <button
                  onClick={e => { e.stopPropagation(); remove(p.id, p.name); }}
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: '#cbd5e1', padding: 4, borderRadius: 6,
                    flexShrink: 0,
                  }}
                  onMouseEnter={e => { e.currentTarget.style.color = '#ef4444'; }}
                  onMouseLeave={e => { e.currentTarget.style.color = '#cbd5e1'; }}
                >
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
