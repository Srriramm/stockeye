import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, NavLink, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { BarChart3, MessageSquare, Briefcase, Activity, Bell, TrendingUp, Menu, X, LineChart, AlertTriangle, TrendingDown, Zap, Newspaper, Target, Flame, SlidersHorizontal, Grid3X3, LogOut, Shield } from 'lucide-react';
import StockEyeLogo from './components/StockEyeLogo';
import io from 'socket.io-client';
import axios from 'axios';
import { authAxios } from './utils/api';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';

import { AuthProvider, useAuth } from './context/AuthContext';
import LoginPage from './components/LoginPage';
import Dashboard from './components/Dashboard';
import Chatbot from './components/Chatbot';
import Portfolio from './components/PortfolioEnhanced';
import MarketMonitor from './components/MarketMonitor';
import Watchlist from './components/Watchlist';
import Forecast from './components/Forecast';
import Screener from './components/Screener';
import SectorHeatmap from './components/SectorHeatmap';
import OAuthConsent from './components/OAuthConsent';
import AdminDashboard from './components/AdminDashboard';
import { supabase } from './lib/supabase';
import wsManager from './utils/websocket';
import * as apiCache from './utils/apiCache';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

// autoConnect: false — we connect manually after getting the auth token
const socket = io(API_URL, { autoConnect: false, transports: ['websocket', 'polling'], reconnection: true, reconnectionDelay: 1000 });

/* ─── Shared loading spinner ────────────────────────────── */
function LoadingSpinner() {
  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: '#f8fafc',
    }}>
      <div style={{
        width: 36, height: 36,
        border: '3px solid #e2e8f0', borderTopColor: '#2563eb',
        borderRadius: '50%', animation: 'spin 0.8s linear infinite',
      }} />
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

/* ─── Access Gate — shown when user is not approved ─────── */
function AccessGatePage() {
  const { user, userStatus, signOut } = useAuth();
  const displayName = user?.user_metadata?.full_name || user?.email || 'there';

  const isRejected = userStatus === 'rejected';
  const isSuspended = userStatus === 'suspended';

  const handleSignOut = async () => {
    try { await signOut(); } catch (e) { console.error(e); }
  };

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: '#f8fafc', padding: '24px',
    }}>
      <div style={{
        maxWidth: 440, width: '100%', background: '#ffffff',
        borderRadius: 20, border: '1px solid #e2e8f0',
        boxShadow: '0 4px 24px rgba(0,0,0,0.07)', padding: '40px 36px',
        textAlign: 'center',
      }}>
        {/* Logo */}
        <div style={{ margin: '0 auto 20px', display: 'flex', justifyContent: 'center' }}>
          <StockEyeLogo size={64} bare={true} />
        </div>

        {isSuspended ? (
          <>
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              background: '#fef3c7', color: '#92400e', borderRadius: 8,
              padding: '6px 14px', fontSize: 13, fontWeight: 600, margin: '12px 0',
            }}>
              Account Suspended
            </div>
            <p style={{ color: '#64748b', fontSize: 14, lineHeight: 1.6, margin: '12px 0 0' }}>
              Hi {displayName}, your account has been suspended.<br />
              Please contact the administrator for assistance.
            </p>
          </>
        ) : (
          <>
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              background: '#fee2e2', color: '#991b1b', borderRadius: 8,
              padding: '6px 14px', fontSize: 13, fontWeight: 600, margin: '12px 0',
            }}>
              {isRejected ? 'Not Invited' : 'Access Restricted'}
            </div>
            <p style={{ color: '#64748b', fontSize: 14, lineHeight: 1.6, margin: '12px 0 0' }}>
              Hi {displayName}, you don't have access to the StockEye beta yet.
              <br /><br />
              This is an invite-only application. Please contact the administrator
              to request access for <strong style={{ color: '#0f172a' }}>{user?.email}</strong>.
            </p>
          </>
        )}

        <button
          onClick={handleSignOut}
          style={{
            marginTop: 28, width: '100%', padding: '11px 0',
            borderRadius: 10, border: 'none', cursor: 'pointer',
            background: '#f1f5f9', color: '#475569', fontSize: 14, fontWeight: 600,
          }}
          onMouseEnter={e => { e.currentTarget.style.background = '#e2e8f0'; }}
          onMouseLeave={e => { e.currentTarget.style.background = '#f1f5f9'; }}
        >
          Sign out
        </button>
      </div>
    </div>
  );
}

/* ─── Protected Route wrapper ───────────────────────────── */
function ProtectedRoute({ children }) {
  const { isAuthenticated, userStatus, loading } = useAuth();
  const location = useLocation();

  if (loading) return <LoadingSpinner />;
  if (!isAuthenticated) return <Navigate to="/login" state={{ from: location }} replace />;
  if (userStatus === 'approved') return children;
  return <AccessGatePage />;
}

/* ─── Admin Route wrapper ────────────────────────────────── */
function AdminRoute({ children }) {
  const { userRole } = useAuth();
  if (userRole !== 'admin') return <Navigate to="/dashboard" replace />;
  return children;
}

/* ─── Main App (authenticated shell) ─────────────────────── */
function AppShell() {
  const { user, userRole, signOut } = useAuth();
  const [alerts, setAlerts] = useState([]);
  const [unreadAlerts, setUnreadAlerts] = useState(0);
  const [indices, setIndices] = useState({});
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [connected, setConnected] = useState(false);
  const [showAlertPanel, setShowAlertPanel] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);

  const [movers, setMovers] = useState(apiCache.get('movers') || null);
  const [marketNews, setMarketNews] = useState(apiCache.get('marketNews') || null);

  useEffect(() => {
    socket.on('connect', () => setConnected(true));
    socket.on('disconnect', () => setConnected(false));
    socket.on('new_alert', (alert) => {
      setAlerts(prev => [alert, ...prev].slice(0, 50));
      setUnreadAlerts(prev => prev + 1);
    });

    // Connect sockets with the Supabase access token so the server can auth the WS handshake
    supabase.auth.getSession().then(({ data: { session } }) => {
      const token = session?.access_token;
      if (token) {
        socket.io.opts.query = { token };
        wsManager.connect(API_URL, token);
      }
      socket.connect();
    });

    return () => {
      socket.off('connect');
      socket.off('disconnect');
      socket.off('new_alert');
      wsManager.disconnect();
    };
  }, []);

  useEffect(() => {
    const fetchGlobal = async () => {
      try {
        const [alertsRes, indicesRes] = await Promise.all([
          authAxios.get(`${API_URL}/api/alerts?hours=24`),
          axios.get(`${API_URL}/api/market/overview`),
        ]);
        setAlerts(alertsRes.data.alerts || []);
        setIndices(indicesRes.data.indices || {});
      } catch (err) {
        console.log('Backend not connected yet');
      }
    };
    fetchGlobal();
    const interval = setInterval(fetchGlobal, 60000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const fetchMoversAndNews = async () => {
      try {
        const [moversRes, newsRes] = await Promise.allSettled([
          axios.get(`${API_URL}/api/market/movers`),
          axios.get(`${API_URL}/api/news/market`),
        ]);
        if (moversRes.status === 'fulfilled') {
          const data = moversRes.value.data;
          setMovers(data);
          apiCache.set('movers', data, 60_000);
        }
        if (newsRes.status === 'fulfilled') {
          const data = newsRes.value.data;
          setMarketNews(data);
          apiCache.set('marketNews', data, 60_000);
        }
      } catch (err) {
        console.log('Movers/news fetch error:', err.message);
      }
    };
    if (!apiCache.get('movers') || !apiCache.get('marketNews')) fetchMoversAndNews();
    const interval = setInterval(fetchMoversAndNews, 60_000);
    return () => clearInterval(interval);
  }, []);

  const handleSignOut = async () => {
    try {
      await signOut();
    } catch (err) {
      console.error('Sign out error:', err);
    }
  };

  const navItems = [
    { to: '/dashboard', icon: BarChart3, label: 'Dashboard' },
    { to: '/forecast', icon: LineChart, label: 'Forecast' },
    { to: '/screener', icon: SlidersHorizontal, label: 'Screener' },
    { to: '/heatmap', icon: Grid3X3, label: 'Heatmap' },
    { to: '/watchlist', icon: TrendingUp, label: 'Watchlist' },
    { to: '/portfolio', icon: Briefcase, label: 'Portfolio' },
    { to: '/chat', icon: MessageSquare, label: 'AI Advisor' },
    { to: '/monitor', icon: Activity, label: 'Monitor' },
    ...(userRole === 'admin' ? [{ to: '/admin', icon: Shield, label: 'Admin' }] : []),
  ];

  // User avatar: use Google profile pic or initials
  const avatarUrl = user?.user_metadata?.avatar_url;
  const displayName = user?.user_metadata?.full_name || user?.email || 'User';
  const initials = displayName.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase();

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: '#f8fafc' }}>

      {/* ─── Sidebar ─────────────────────────────────────────── */}
      <aside
        className={`${sidebarOpen ? 'w-60' : 'w-[70px]'} relative z-30 flex flex-col transition-all duration-300 ease-out flex-shrink-0`}
        style={{ background: '#ffffff', borderRight: '1px solid #e2e8f0', boxShadow: '1px 0 0 #f1f5f9' }}
      >
        {/* Brand */}
        <div className="h-16 flex items-center justify-between px-4 flex-shrink-0" style={{ borderBottom: '1px solid #f1f5f9' }}>
          {sidebarOpen ? (
            <div className="flex items-center gap-3 fade-in">
              <div className="relative">
                <StockEyeLogo size={32} bare={true} />
                <div
                  className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-white"
                  style={{ background: connected ? '#10b981' : '#ef4444' }}
                />
              </div>
              <div>
                <span className="text-[10px] font-semibold tracking-wider uppercase" style={{ color: '#2563eb' }}>Pro Console</span>
              </div>
            </div>
          ) : (
            <div className="w-full flex justify-center">
              <StockEyeLogo size={32} bare={true} iconOnly={true} />
            </div>
          )}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className={`w-6 h-6 rounded-full flex items-center justify-center transition-colors ${!sidebarOpen ? 'hidden' : ''}`}
            style={{ color: '#94a3b8', background: '#f8fafc', border: '1px solid #e2e8f0' }}
            onMouseEnter={e => { e.currentTarget.style.color = '#0f172a'; }}
            onMouseLeave={e => { e.currentTarget.style.color = '#94a3b8'; }}
          >
            <X size={11} />
          </button>
          {!sidebarOpen && (
            <button
              onClick={() => setSidebarOpen(true)}
              className="absolute -right-3 top-5 w-6 h-6 rounded-full flex items-center justify-center transition-colors z-10"
              style={{ color: '#64748b', background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }}
            >
              <Menu size={11} />
            </button>
          )}
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 px-3 space-y-0.5 overflow-y-auto custom-scrollbar">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `group flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-150 ${isActive ? 'active-nav' : 'inactive-nav'}`
              }
              style={({ isActive }) => isActive
                ? { background: '#eff6ff', color: '#1d4ed8' }
                : { color: '#64748b' }
              }
              onMouseEnter={e => { if (!e.currentTarget.classList.contains('active-nav')) { e.currentTarget.style.background = '#f8fafc'; e.currentTarget.style.color = '#0f172a'; } }}
              onMouseLeave={e => { if (!e.currentTarget.style.color?.includes('1d4ed8')) { e.currentTarget.style.background = ''; e.currentTarget.style.color = '#64748b'; } }}
            >
              {({ isActive }) => (
                <>
                  <Icon
                    size={18}
                    strokeWidth={isActive ? 2.5 : 1.75}
                    style={{ color: isActive ? '#2563eb' : 'inherit', flexShrink: 0 }}
                  />
                  {sidebarOpen && (
                    <span
                      className="font-medium text-sm whitespace-nowrap transition-all duration-200 opacity-100"
                      style={{ color: 'inherit' }}
                    >
                      {label}
                    </span>
                  )}
                  {isActive && !sidebarOpen && (
                    <div
                      className="absolute left-0 top-2 bottom-2 w-1 rounded-r"
                      style={{ background: '#2563eb' }}
                    />
                  )}
                </>
              )}
            </NavLink>
          ))}
        </nav>

        {/* User section in sidebar footer */}
        <div className="p-3 flex-shrink-0" style={{ borderTop: '1px solid #f1f5f9' }}>
          <div className="relative">
            <button
              onClick={() => setShowUserMenu(!showUserMenu)}
              className="w-full flex items-center gap-2.5 px-2 py-2 rounded-xl transition-colors"
              style={{ background: showUserMenu ? '#f1f5f9' : 'transparent' }}
              onMouseEnter={e => { e.currentTarget.style.background = '#f1f5f9'; }}
              onMouseLeave={e => { if (!showUserMenu) e.currentTarget.style.background = 'transparent'; }}
            >
              {avatarUrl ? (
                <img
                  src={avatarUrl}
                  alt=""
                  className="w-8 h-8 rounded-full flex-shrink-0"
                  style={{ border: '2px solid #e2e8f0' }}
                  referrerPolicy="no-referrer"
                />
              ) : (
                <div
                  className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold"
                  style={{ background: 'linear-gradient(135deg, #2563eb, #7c3aed)', color: '#fff' }}
                >
                  {initials}
                </div>
              )}
              {sidebarOpen && (
                <div className="flex-1 min-w-0 text-left">
                  <div className="text-xs font-semibold truncate" style={{ color: '#0f172a' }}>{displayName}</div>
                  <div className="text-[10px] truncate" style={{ color: '#94a3b8' }}>{user?.email}</div>
                </div>
              )}
            </button>

            {/* User dropdown */}
            {showUserMenu && (
              <div
                className="absolute bottom-full left-0 w-full mb-1 rounded-xl overflow-hidden z-50"
                style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 4px 16px rgba(0,0,0,0.1)' }}
              >
                <button
                  onClick={handleSignOut}
                  className="w-full flex items-center gap-2 px-4 py-3 text-xs font-medium transition-colors"
                  style={{ color: '#ef4444' }}
                  onMouseEnter={e => { e.currentTarget.style.background = '#fef2f2'; }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
                >
                  <LogOut size={14} />
                  Sign Out
                </button>
              </div>
            )}
          </div>
        </div>
      </aside>

      {/* ─── Main content ───────────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0 relative" style={{ background: '#f8fafc' }}>

        {/* Top bar */}
        <header
          className="h-14 flex items-center justify-between px-6 flex-shrink-0 z-10"
          style={{ background: '#ffffff', borderBottom: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}
        >
          {/* Market ticker */}
          <div className="flex items-center gap-6 overflow-hidden flex-1 mr-6">
            {Object.entries(indices).length > 0 ? (
              Object.entries(indices).map(([name, data]) => (
                <div key={name} className="flex items-center gap-2.5 text-xs flex-shrink-0">
                  <span className="font-semibold" style={{ color: '#64748b' }}>{name}</span>
                  <span className="font-mono font-semibold" style={{ color: '#0f172a' }}>
                    {data.value?.toLocaleString('en-IN')}
                  </span>
                  <span
                    className="font-mono font-bold px-1.5 py-0.5 rounded text-[11px]"
                    style={{
                      background: data.change_percent >= 0 ? '#d1fae5' : '#fee2e2',
                      color: data.change_percent >= 0 ? '#065f46' : '#991b1b',
                    }}
                  >
                    {data.change_percent >= 0 ? '+' : ''}{data.change_percent?.toFixed(2)}%
                  </span>
                </div>
              ))
            ) : (
              <div className="flex items-center gap-2 text-xs animate-pulse" style={{ color: '#94a3b8' }}>
                <Activity size={12} /> Initializing Market Feed...
              </div>
            )}
          </div>

          {/* Notifications bell */}
          <div className="relative">
            <button
              onClick={() => { setShowAlertPanel(!showAlertPanel); setUnreadAlerts(0); }}
              className="relative w-9 h-9 rounded-xl flex items-center justify-center transition-all"
              style={{ color: '#64748b', background: showAlertPanel ? '#eff6ff' : 'transparent' }}
              onMouseEnter={e => { e.currentTarget.style.background = '#f1f5f9'; e.currentTarget.style.color = '#0f172a'; }}
              onMouseLeave={e => { e.currentTarget.style.background = showAlertPanel ? '#eff6ff' : 'transparent'; e.currentTarget.style.color = showAlertPanel ? '#2563eb' : '#64748b'; }}
            >
              <Bell size={18} />
              {unreadAlerts > 0 && (
                <span
                  className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full border-2 border-white"
                  style={{ background: '#ef4444' }}
                />
              )}
            </button>

            {showAlertPanel && (
              <div
                className="absolute top-12 right-0 w-96 rounded-2xl z-50 overflow-hidden fade-in"
                style={{ background: '#ffffff', border: '1px solid #e2e8f0', boxShadow: '0 8px 32px rgba(0,0,0,0.12)' }}
              >
                <div className="flex items-center justify-between px-4 py-3" style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <span className="text-xs font-bold uppercase tracking-wider" style={{ color: '#0f172a' }}>Notifications</span>
                  <button onClick={() => setShowAlertPanel(false)} style={{ color: '#94a3b8' }}><X size={14} /></button>
                </div>
                <div className="max-h-80 overflow-y-auto custom-scrollbar">
                  {alerts.length === 0 ? (
                    <div className="py-8 text-center text-xs" style={{ color: '#94a3b8' }}>All systems nominal</div>
                  ) : (
                    alerts.map((alert, i) => <AlertCard key={i} alert={alert} onClose={() => setShowAlertPanel(false)} />)
                  )}
                </div>
              </div>
            )}
          </div>
        </header>

        {/* Page content */}
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          <Routes>
            <Route path="/dashboard" element={<Dashboard indices={indices} alerts={alerts} apiUrl={API_URL} movers={movers} marketNews={marketNews} />} />
            <Route path="/forecast" element={<Forecast apiUrl={API_URL} />} />
            <Route path="/screener" element={<ScreenerPage apiUrl={API_URL} />} />
            <Route path="/heatmap" element={<HeatmapPage />} />
            <Route path="/watchlist" element={<Watchlist apiUrl={API_URL} />} />
            <Route path="/portfolio" element={<Portfolio apiUrl={API_URL} socket={socket} />} />
            <Route path="/chat" element={<Chatbot apiUrl={API_URL} socket={socket} />} />
            <Route path="/monitor" element={<MarketMonitor apiUrl={API_URL} socket={socket} alerts={alerts} />} />
            <Route path="/admin" element={
              <AdminRoute><AdminDashboard apiUrl={API_URL} /></AdminRoute>
            } />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </div>
      </main>

      {/* Click-away for user menu */}
      {showUserMenu && (
        <div className="fixed inset-0 z-20" onClick={() => setShowUserMenu(false)} />
      )}
    </div>
  );
}

// Wrapper provides useNavigate hook to Screener, enabling "Analyse →" to deep-link into Forecast.
function ScreenerPage({ apiUrl }) {
  const navigate = useNavigate();
  return (
    <Screener
      apiUrl={apiUrl}
      onNavigateToForecast={(ticker) => navigate(`/forecast?ticker=${ticker}`)}
    />
  );
}

// Wrapper provides useNavigate hook to SectorHeatmap.
function HeatmapPage() {
  const navigate = useNavigate();
  return (
    <SectorHeatmap
      onNavigateToForecast={(ticker) => navigate(`/forecast?ticker=${ticker}`)}
    />
  );
}

const ALERT_CONFIG = {
  price_movement: { icon: TrendingUp, border: '#3b82f6', iconBg: '#dbeafe', iconColor: '#1d4ed8' },
  volume_spike: { icon: Zap, border: '#f59e0b', iconBg: '#fef3c7', iconColor: '#92400e' },
  technical: { icon: BarChart3, border: '#8b5cf6', iconBg: '#ede9fe', iconColor: '#5b21b6' },
  pattern: { icon: BarChart3, border: '#6366f1', iconBg: '#e0e7ff', iconColor: '#3730a3' },
  news: { icon: Newspaper, border: '#94a3b8', iconBg: '#f1f5f9', iconColor: '#475569' },
  price_alert: { icon: Target, border: '#10b981', iconBg: '#d1fae5', iconColor: '#065f46' },
  signal: { icon: TrendingUp, border: '#10b981', iconBg: '#d1fae5', iconColor: '#065f46' },
  booming: { icon: Flame, border: '#f97316', iconBg: '#ffedd5', iconColor: '#9a3412' },
};

function AlertCard({ alert, onClose }) {
  const navigate = useNavigate();
  const isSell = alert.message?.includes('SELL') || alert.message?.includes('sell');
  let type = alert.type || 'price_movement';
  if (type === 'signal' && isSell) type = '_sell';

  const cfg = ALERT_CONFIG[type] || {
    icon: isSell ? TrendingDown : AlertTriangle,
    border: isSell ? '#ef4444' : '#3b82f6',
    iconBg: isSell ? '#fee2e2' : '#dbeafe',
    iconColor: isSell ? '#991b1b' : '#1d4ed8',
  };
  const Icon = cfg.icon;

  const handleAnalyze = () => {
    if (alert.ticker) { onClose(); navigate(`/forecast?ticker=${alert.ticker}`); }
  };

  return (
    <div
      className="px-4 py-3 transition-colors"
      style={{ borderBottom: '1px solid #f8fafc', borderLeft: `3px solid ${cfg.border}` }}
      onMouseEnter={e => { e.currentTarget.style.background = '#f8fafc'; }}
      onMouseLeave={e => { e.currentTarget.style.background = ''; }}
    >
      <div className="flex items-start gap-3">
        <div className="w-6 h-6 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5" style={{ background: cfg.iconBg }}>
          <Icon size={12} style={{ color: cfg.iconColor }} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs leading-snug" style={{ color: '#334155' }}>{alert.message}</p>
          <div className="flex items-center justify-between mt-1.5">
            <span className="text-[10px] font-mono" style={{ color: '#94a3b8' }}>
              {alert.timestamp ? new Date(alert.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' }) : ''}
            </span>
            {alert.ticker && (
              <button onClick={handleAnalyze} className="text-[10px] font-semibold transition-colors" style={{ color: '#2563eb' }}>
                → Analyze
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── Root App — wraps everything in AuthProvider + Router ──── */
function App() {
  return (
    <Router>
      <AuthProvider>
        <ToastContainer
          position="bottom-right"
          autoClose={4000}
          hideProgressBar={false}
          newestOnTop={true}
          closeOnClick
          rtl={false}
          pauseOnFocusLoss
          draggable
          pauseOnHover
          theme="light"
        />
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/oauth/consent" element={
            <ProtectedRoute>
              <OAuthConsent />
            </ProtectedRoute>
          } />
          <Route path="/*" element={
            <ProtectedRoute>
              <AppShell />
            </ProtectedRoute>
          } />
        </Routes>
      </AuthProvider>
    </Router>
  );
}

export default App;
