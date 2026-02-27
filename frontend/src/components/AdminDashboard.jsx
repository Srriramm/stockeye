import React, { useState, useEffect, useCallback } from 'react';
import {
  Users, Mail, Activity, Shield, Check, X, Ban,
  RefreshCw, Pencil, Trash2, UserCheck, UserX, ChevronDown,
  Plus, AlertCircle,
} from 'lucide-react';
import { authAxios } from '../utils/api';

const STATUS_BADGE = {
  approved:  { bg: '#d1fae5', color: '#065f46', label: 'Approved' },
  rejected:  { bg: '#fee2e2', color: '#991b1b', label: 'Rejected' },
  suspended: { bg: '#fef3c7', color: '#92400e', label: 'Suspended' },
};

const ROLE_BADGE = {
  admin: { bg: '#ede9fe', color: '#5b21b6', label: 'Admin' },
  user:  { bg: '#f1f5f9', color: '#475569', label: 'User' },
};

function Badge({ map, value }) {
  const cfg = map[value] || { bg: '#f1f5f9', color: '#64748b', label: value };
  return (
    <span style={{
      background: cfg.bg, color: cfg.color,
      padding: '2px 10px', borderRadius: 6, fontSize: 11, fontWeight: 600,
    }}>
      {cfg.label}
    </span>
  );
}

function StatCard({ label, value, color }) {
  return (
    <div style={{
      background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: 14,
      padding: '18px 22px', flex: 1, minWidth: 120,
    }}>
      <div style={{ fontSize: 26, fontWeight: 800, color: color || '#0f172a', lineHeight: 1 }}>
        {value ?? '—'}
      </div>
      <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{label}</div>
    </div>
  );
}

function Avatar({ name, avatarUrl }) {
  const initials = (name || '?').split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();
  if (avatarUrl) {
    return (
      <img src={avatarUrl} alt="" referrerPolicy="no-referrer"
        style={{ width: 32, height: 32, borderRadius: '50%', border: '2px solid #e2e8f0', flexShrink: 0 }} />
    );
  }
  return (
    <div style={{
      width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
      background: 'linear-gradient(135deg, #2563eb, #7c3aed)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 11, fontWeight: 700, color: '#fff',
    }}>
      {initials}
    </div>
  );
}

function ActionBtn({ label, color, bg, hoverBg, onClick, icon: Icon, disabled }) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 4,
        padding: '4px 10px', borderRadius: 6, border: 'none', cursor: disabled ? 'not-allowed' : 'pointer',
        fontSize: 11, fontWeight: 600, color,
        background: hovered ? hoverBg : bg,
        opacity: disabled ? 0.4 : 1, transition: 'background 0.15s',
      }}
    >
      {Icon && <Icon size={12} />} {label}
    </button>
  );
}

// ─── Users Tab ─────────────────────────────────────────────────

function UsersTab({ apiUrl }) {
  const [users, setUsers] = useState([]);
  const [filter, setFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [editingNotes, setEditingNotes] = useState(null); // user_id
  const [notesText, setNotesText] = useState('');
  const [toast, setToast] = useState(null);

  const showToast = (msg, ok = true) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await authAxios.get(
        `${apiUrl}/api/admin/users?status=${filter}&limit=100`
      );
      setUsers(data);
    } catch (e) {
      showToast('Failed to load users', false);
    } finally {
      setLoading(false);
    }
  }, [apiUrl, filter]);

  useEffect(() => { load(); }, [load]);

  const changeStatus = async (uid, status) => {
    try {
      await authAxios.patch(`${apiUrl}/api/admin/users/${uid}/status`, { status });
      showToast(`User ${status}`);
      load();
    } catch (e) {
      showToast('Action failed', false);
    }
  };

  const saveNotes = async (uid) => {
    try {
      await authAxios.patch(`${apiUrl}/api/admin/users/${uid}/notes`, { notes: notesText });
      showToast('Notes saved');
      setEditingNotes(null);
      setUsers(prev => prev.map(u => u.user_id === uid ? { ...u, notes: notesText } : u));
    } catch (e) {
      showToast('Failed to save notes', false);
    }
  };

  const FILTERS = ['all', 'approved', 'rejected', 'suspended'];

  return (
    <div>
      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 1000,
          background: toast.ok ? '#064e3b' : '#7f1d1d',
          color: '#fff', padding: '10px 18px', borderRadius: 10,
          fontSize: 13, fontWeight: 600, boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
        }}>
          {toast.msg}
        </div>
      )}

      {/* Filter tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 16 }}>
        {FILTERS.map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              padding: '6px 14px', borderRadius: 8, border: 'none', cursor: 'pointer',
              fontSize: 12, fontWeight: 600, textTransform: 'capitalize',
              background: filter === f ? '#2563eb' : '#f1f5f9',
              color: filter === f ? '#fff' : '#475569',
            }}
          >
            {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
        <button
          onClick={load}
          style={{
            marginLeft: 'auto', padding: '6px 12px', borderRadius: 8,
            border: 'none', cursor: 'pointer', background: '#f1f5f9', color: '#475569',
            display: 'flex', alignItems: 'center', gap: 4, fontSize: 12,
          }}
        >
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      {/* Table */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px 0', color: '#94a3b8', fontSize: 13 }}>
          Loading users…
        </div>
      ) : users.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px 0', color: '#94a3b8', fontSize: 13 }}>
          No users found
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #e2e8f0' }}>
                {['User', 'Email', 'Role', 'Status', 'Joined', 'Last seen', 'Actions'].map(h => (
                  <th key={h} style={{
                    padding: '8px 12px', textAlign: 'left', fontSize: 11,
                    fontWeight: 700, color: '#64748b', textTransform: 'uppercase',
                    letterSpacing: '0.04em', whiteSpace: 'nowrap',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <React.Fragment key={u.user_id}>
                  <tr
                    style={{
                      borderBottom: '1px solid #f1f5f9',
                      opacity: u.status === 'suspended' ? 0.6 : 1,
                    }}
                    onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                    onMouseLeave={e => e.currentTarget.style.background = ''}
                  >
                    {/* User */}
                    <td style={{ padding: '10px 12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Avatar name={u.full_name || u.email} avatarUrl={u.avatar_url} />
                        <div>
                          <div style={{ fontWeight: 600, color: '#0f172a', fontSize: 13 }}>
                            {u.full_name || '—'}
                          </div>
                          {u.notes && (
                            <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 1 }}>
                              📝 {u.notes.slice(0, 40)}{u.notes.length > 40 ? '…' : ''}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                    {/* Email */}
                    <td style={{ padding: '10px 12px', color: '#475569', whiteSpace: 'nowrap' }}>
                      {u.email}
                    </td>
                    {/* Role */}
                    <td style={{ padding: '10px 12px' }}>
                      <Badge map={ROLE_BADGE} value={u.role} />
                    </td>
                    {/* Status */}
                    <td style={{ padding: '10px 12px' }}>
                      <Badge map={STATUS_BADGE} value={u.status} />
                    </td>
                    {/* Joined */}
                    <td style={{ padding: '10px 12px', color: '#94a3b8', fontSize: 12, whiteSpace: 'nowrap' }}>
                      {u.created_at ? new Date(u.created_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: '2-digit' }) : '—'}
                    </td>
                    {/* Last seen */}
                    <td style={{ padding: '10px 12px', color: '#94a3b8', fontSize: 12, whiteSpace: 'nowrap' }}>
                      {u.last_seen_at ? new Date(u.last_seen_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' }) : '—'}
                    </td>
                    {/* Actions */}
                    <td style={{ padding: '10px 12px' }}>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {u.status !== 'approved' && (
                          <ActionBtn
                            label="Approve" icon={UserCheck}
                            color="#065f46" bg="#d1fae5" hoverBg="#a7f3d0"
                            onClick={() => changeStatus(u.user_id, 'approved')}
                          />
                        )}
                        {u.status !== 'rejected' && (
                          <ActionBtn
                            label="Reject" icon={UserX}
                            color="#991b1b" bg="#fee2e2" hoverBg="#fecaca"
                            onClick={() => changeStatus(u.user_id, 'rejected')}
                          />
                        )}
                        {u.status !== 'suspended' && (
                          <ActionBtn
                            label="Suspend" icon={Ban}
                            color="#92400e" bg="#fef3c7" hoverBg="#fde68a"
                            onClick={() => changeStatus(u.user_id, 'suspended')}
                          />
                        )}
                        <ActionBtn
                          label="" icon={Pencil}
                          color="#475569" bg="#f1f5f9" hoverBg="#e2e8f0"
                          onClick={() => {
                            if (editingNotes === u.user_id) {
                              setEditingNotes(null);
                            } else {
                              setEditingNotes(u.user_id);
                              setNotesText(u.notes || '');
                            }
                          }}
                        />
                      </div>
                    </td>
                  </tr>
                  {/* Inline notes editor */}
                  {editingNotes === u.user_id && (
                    <tr style={{ background: '#f8fafc' }}>
                      <td colSpan={7} style={{ padding: '8px 12px 12px 60px' }}>
                        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                          <textarea
                            value={notesText}
                            onChange={e => setNotesText(e.target.value)}
                            placeholder="Add notes about this user…"
                            rows={2}
                            style={{
                              flex: 1, borderRadius: 8, border: '1px solid #e2e8f0',
                              padding: '8px 12px', fontSize: 12, resize: 'vertical',
                              fontFamily: 'inherit', outline: 'none',
                            }}
                          />
                          <ActionBtn
                            label="Save" icon={Check}
                            color="#065f46" bg="#d1fae5" hoverBg="#a7f3d0"
                            onClick={() => saveNotes(u.user_id)}
                          />
                          <ActionBtn
                            label="Cancel" icon={X}
                            color="#475569" bg="#f1f5f9" hoverBg="#e2e8f0"
                            onClick={() => setEditingNotes(null)}
                          />
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Invitations Tab ────────────────────────────────────────────

function InvitesTab({ apiUrl }) {
  const [invites, setInvites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newEmail, setNewEmail] = useState('');
  const [newNotes, setNewNotes] = useState('');
  const [adding, setAdding] = useState(false);
  const [toast, setToast] = useState(null);

  const showToast = (msg, ok = true) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3000);
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await authAxios.get(`${apiUrl}/api/admin/invites`);
      setInvites(data);
    } catch (e) {
      showToast('Failed to load invites', false);
    } finally {
      setLoading(false);
    }
  }, [apiUrl]);

  useEffect(() => { load(); }, [load]);

  const addInvite = async () => {
    const email = newEmail.trim();
    if (!email || !email.includes('@')) {
      showToast('Enter a valid email', false);
      return;
    }
    setAdding(true);
    try {
      const { data } = await authAxios.post(`${apiUrl}/api/admin/invites`, {
        email, notes: newNotes.trim(),
      });
      showToast(
        data.auto_approved > 0
          ? `Invite added & ${data.auto_approved} user(s) auto-approved`
          : 'Invite added'
      );
      setNewEmail('');
      setNewNotes('');
      load();
    } catch (e) {
      showToast('Failed to add invite', false);
    } finally {
      setAdding(false);
    }
  };

  const removeInvite = async (email) => {
    try {
      await authAxios.delete(`${apiUrl}/api/admin/invites/${encodeURIComponent(email)}`);
      showToast('Invite removed');
      load();
    } catch (e) {
      showToast('Failed to remove invite', false);
    }
  };

  return (
    <div>
      {toast && (
        <div style={{
          position: 'fixed', bottom: 24, right: 24, zIndex: 1000,
          background: toast.ok ? '#064e3b' : '#7f1d1d',
          color: '#fff', padding: '10px 18px', borderRadius: 10,
          fontSize: 13, fontWeight: 600, boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
        }}>
          {toast.msg}
        </div>
      )}

      {/* Add invite form */}
      <div style={{
        background: '#f8fafc', borderRadius: 12, padding: '16px 18px',
        marginBottom: 20, border: '1px solid #e2e8f0',
      }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: '#0f172a', marginBottom: 10 }}>
          Add Email Invite
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          <input
            type="email"
            value={newEmail}
            onChange={e => setNewEmail(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && addInvite()}
            placeholder="user@example.com"
            style={{
              flex: '2 1 200px', padding: '8px 12px', borderRadius: 8,
              border: '1px solid #e2e8f0', fontSize: 13, outline: 'none',
              fontFamily: 'inherit',
            }}
          />
          <input
            type="text"
            value={newNotes}
            onChange={e => setNewNotes(e.target.value)}
            placeholder="Notes (optional)"
            style={{
              flex: '3 1 200px', padding: '8px 12px', borderRadius: 8,
              border: '1px solid #e2e8f0', fontSize: 13, outline: 'none',
              fontFamily: 'inherit',
            }}
          />
          <button
            onClick={addInvite}
            disabled={adding}
            style={{
              padding: '8px 18px', borderRadius: 8, border: 'none', cursor: 'pointer',
              background: '#2563eb', color: '#fff', fontSize: 13, fontWeight: 600,
              display: 'flex', alignItems: 'center', gap: 6,
              opacity: adding ? 0.6 : 1,
            }}
          >
            <Plus size={14} /> Add Invite
          </button>
        </div>
        <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 8 }}>
          Adding an email here auto-approves any existing user with that email.
        </div>
      </div>

      {/* Invite list */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '32px 0', color: '#94a3b8', fontSize: 13 }}>
          Loading…
        </div>
      ) : invites.length === 0 ? (
        <div style={{
          textAlign: 'center', padding: '40px 0', color: '#94a3b8',
          fontSize: 13, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8,
        }}>
          <AlertCircle size={24} style={{ color: '#cbd5e1' }} />
          No invites yet — add emails above to allow users in.
        </div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: '1px solid #e2e8f0' }}>
              {['Email', 'Notes', 'Added by', 'Date', ''].map(h => (
                <th key={h} style={{
                  padding: '8px 12px', textAlign: 'left', fontSize: 11,
                  fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.04em',
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {invites.map(inv => (
              <tr key={inv.id}
                style={{ borderBottom: '1px solid #f1f5f9' }}
                onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                onMouseLeave={e => e.currentTarget.style.background = ''}
              >
                <td style={{ padding: '10px 12px', fontWeight: 600, color: '#0f172a' }}>
                  {inv.email}
                </td>
                <td style={{ padding: '10px 12px', color: '#64748b' }}>
                  {inv.notes || '—'}
                </td>
                <td style={{ padding: '10px 12px', color: '#64748b' }}>
                  {inv.added_by_email || '—'}
                </td>
                <td style={{ padding: '10px 12px', color: '#94a3b8', fontSize: 12, whiteSpace: 'nowrap' }}>
                  {inv.created_at ? new Date(inv.created_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: '2-digit' }) : '—'}
                </td>
                <td style={{ padding: '10px 12px' }}>
                  <ActionBtn
                    label="Remove" icon={Trash2}
                    color="#991b1b" bg="#fee2e2" hoverBg="#fecaca"
                    onClick={() => removeInvite(inv.email)}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ─── Audit Log Tab ──────────────────────────────────────────────

function AuditTab({ apiUrl }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [offset, setOffset] = useState(0);
  const LIMIT = 50;

  const load = useCallback(async (off = 0) => {
    setLoading(true);
    try {
      const { data } = await authAxios.get(
        `${apiUrl}/api/admin/audit?limit=${LIMIT}&offset=${off}`
      );
      setLogs(off === 0 ? data : prev => [...prev, ...data]);
      setOffset(off + data.length);
    } catch (e) {
      console.error('Audit load error:', e);
    } finally {
      setLoading(false);
    }
  }, [apiUrl]);

  useEffect(() => { load(0); }, [load]);

  return (
    <div>
      {loading && logs.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px 0', color: '#94a3b8', fontSize: 13 }}>
          Loading…
        </div>
      ) : logs.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px 0', color: '#94a3b8', fontSize: 13 }}>
          No audit events yet
        </div>
      ) : (
        <>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #e2e8f0' }}>
                {['Time', 'User', 'Event', 'IP', 'Details'].map(h => (
                  <th key={h} style={{
                    padding: '8px 12px', textAlign: 'left', fontSize: 11,
                    fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.04em',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {logs.map((log, i) => (
                <tr key={i}
                  style={{ borderBottom: '1px solid #f1f5f9' }}
                  onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                  onMouseLeave={e => e.currentTarget.style.background = ''}
                >
                  <td style={{ padding: '8px 12px', color: '#94a3b8', whiteSpace: 'nowrap' }}>
                    {log.created_at
                      ? new Date(log.created_at).toLocaleString('en-IN', {
                          day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
                        })
                      : '—'}
                  </td>
                  <td style={{ padding: '8px 12px', color: '#475569' }}>
                    {log.user_email || log.user_id?.slice(0, 8) || '—'}
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    <code style={{
                      background: '#f1f5f9', color: '#334155',
                      padding: '2px 6px', borderRadius: 4, fontSize: 11,
                    }}>
                      {log.event_type}
                    </code>
                  </td>
                  <td style={{ padding: '8px 12px', color: '#94a3b8', fontFamily: 'monospace', fontSize: 11 }}>
                    {log.ip_address || '—'}
                  </td>
                  <td style={{ padding: '8px 12px', color: '#64748b', maxWidth: 200 }}>
                    {log.details && Object.keys(log.details).length > 0
                      ? Object.entries(log.details)
                          .map(([k, v]) => `${k}: ${v}`)
                          .join(', ')
                          .slice(0, 80)
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ marginTop: 16, textAlign: 'center' }}>
            <button
              onClick={() => load(offset)}
              disabled={loading}
              style={{
                padding: '8px 20px', borderRadius: 8, border: '1px solid #e2e8f0',
                background: '#fff', color: '#475569', fontSize: 13, cursor: 'pointer',
                display: 'inline-flex', alignItems: 'center', gap: 6,
                opacity: loading ? 0.5 : 1,
              }}
            >
              <ChevronDown size={14} /> Load more
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ─── Main AdminDashboard ────────────────────────────────────────

const TABS = [
  { id: 'users',   label: 'Users',       icon: Users },
  { id: 'invites', label: 'Invitations', icon: Mail },
  { id: 'audit',   label: 'Audit Log',   icon: Activity },
];

export default function AdminDashboard({ apiUrl }) {
  const [activeTab, setActiveTab] = useState('users');
  const [stats, setStats] = useState(null);

  useEffect(() => {
    authAxios.get(`${apiUrl}/api/admin/stats`)
      .then(({ data }) => setStats(data))
      .catch(() => {});
  }, [apiUrl]);

  return (
    <div style={{ padding: '24px 28px', maxWidth: 1100, margin: '0 auto' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
        <div style={{
          width: 36, height: 36, borderRadius: 10,
          background: 'linear-gradient(135deg, #2563eb, #3b82f6)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Shield size={18} style={{ color: '#fff' }} />
        </div>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 800, color: '#0f172a', margin: 0 }}>
            Admin Dashboard
          </h1>
          <div style={{ fontSize: 12, color: '#64748b' }}>Manage beta access and users</div>
        </div>
      </div>

      {/* Stats cards */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
        <StatCard label="Total users"  value={stats?.total}     color="#0f172a" />
        <StatCard label="Approved"     value={stats?.approved}  color="#065f46" />
        <StatCard label="Rejected"     value={stats?.rejected}  color="#991b1b" />
        <StatCard label="Suspended"    value={stats?.suspended} color="#92400e" />
      </div>

      {/* Card with tabs */}
      <div style={{
        background: '#ffffff', border: '1px solid #e2e8f0',
        borderRadius: 16, overflow: 'hidden',
      }}>
        {/* Tab bar */}
        <div style={{
          display: 'flex', borderBottom: '1px solid #e2e8f0',
          background: '#f8fafc', padding: '0 20px',
        }}>
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '12px 16px', border: 'none', cursor: 'pointer',
                background: 'transparent', fontSize: 13, fontWeight: 600,
                color: activeTab === id ? '#2563eb' : '#64748b',
                borderBottom: activeTab === id ? '2px solid #2563eb' : '2px solid transparent',
                marginBottom: -1, transition: 'color 0.15s',
              }}
            >
              <Icon size={15} /> {label}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div style={{ padding: '20px 20px' }}>
          {activeTab === 'users'   && <UsersTab   apiUrl={apiUrl} />}
          {activeTab === 'invites' && <InvitesTab apiUrl={apiUrl} />}
          {activeTab === 'audit'   && <AuditTab   apiUrl={apiUrl} />}
        </div>
      </div>
    </div>
  );
}
