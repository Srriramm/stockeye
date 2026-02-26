import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { supabase } from '../lib/supabase';
import { Eye, Shield, CheckCircle, XCircle, Loader2, Globe, Key, User, Mail } from 'lucide-react';

/**
 * OAuthConsent — Supabase OAuth 2.1 Authorization Consent Page.
 *
 * When a third-party app initiates OAuth, Supabase Auth redirects users here
 * with an `authorization_id` query parameter. This component:
 * 1. Extracts the authorization_id
 * 2. Fetches authorization details (client name, scopes, redirect_uri)
 * 3. Displays a consent screen
 * 4. Handles approve/deny via Supabase JS SDK
 */

const SCOPE_LABELS = {
    openid: { label: 'OpenID Connect', desc: 'Verify your identity', icon: Key },
    email: { label: 'Email Address', desc: 'View your email address', icon: Mail },
    profile: { label: 'Profile Info', desc: 'View your name and avatar', icon: User },
};

export default function OAuthConsent() {
    const [searchParams] = useSearchParams();
    const navigate = useNavigate();
    const { user, isAuthenticated, loading: authLoading } = useAuth();

    const [authDetails, setAuthDetails] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [submitting, setSubmitting] = useState(null); // 'approve' | 'deny' | null

    const authorizationId = searchParams.get('authorization_id');

    // Redirect to login if not authenticated, preserving authorization_id
    useEffect(() => {
        if (!authLoading && !isAuthenticated) {
            navigate(`/login?redirect=/oauth/consent?authorization_id=${authorizationId}`, { replace: true });
        }
    }, [authLoading, isAuthenticated, navigate, authorizationId]);

    // Fetch authorization details
    useEffect(() => {
        if (!authorizationId || !isAuthenticated) return;

        const fetchDetails = async () => {
            try {
                setLoading(true);
                const { data, error: fetchError } = await supabase.auth.oauth.getAuthorizationDetails(authorizationId);
                if (fetchError) throw fetchError;
                setAuthDetails(data);
            } catch (err) {
                setError(err.message || 'Failed to load authorization details');
            } finally {
                setLoading(false);
            }
        };

        fetchDetails();
    }, [authorizationId, isAuthenticated]);

    const handleApprove = async () => {
        try {
            setSubmitting('approve');
            const { data, error: approveError } = await supabase.auth.oauth.approveAuthorization(authorizationId);
            if (approveError) throw approveError;
            // Redirect back to the client with authorization code
            window.location.href = data.redirect_to;
        } catch (err) {
            setError(err.message || 'Failed to approve authorization');
            setSubmitting(null);
        }
    };

    const handleDeny = async () => {
        try {
            setSubmitting('deny');
            const { data, error: denyError } = await supabase.auth.oauth.denyAuthorization(authorizationId);
            if (denyError) throw denyError;
            // Redirect back to the client with error
            window.location.href = data.redirect_to;
        } catch (err) {
            setError(err.message || 'Failed to deny authorization');
            setSubmitting(null);
        }
    };

    // Parse scopes from the auth details
    const scopes = authDetails?.scope?.trim()
        ? authDetails.scope.split(' ').filter(Boolean)
        : [];

    // ─── Missing authorization_id ───────────────────────────────
    if (!authorizationId) {
        return (
            <div style={styles.container}>
                <div style={styles.bgGradient} />
                <div style={styles.card}>
                    <div style={styles.errorIcon}>
                        <XCircle size={32} color="#ef4444" />
                    </div>
                    <h2 style={styles.errorTitle}>Invalid Request</h2>
                    <p style={styles.errorText}>Missing <code>authorization_id</code> parameter.</p>
                </div>
            </div>
        );
    }

    // ─── Loading state ──────────────────────────────────────────
    if (loading || authLoading) {
        return (
            <div style={styles.container}>
                <div style={styles.bgGradient} />
                <div style={styles.card}>
                    <div style={styles.loadingWrapper}>
                        <div style={styles.spinner} />
                        <p style={styles.loadingText}>Loading authorization details...</p>
                    </div>
                </div>
                <style>{animations}</style>
            </div>
        );
    }

    // ─── Error state ────────────────────────────────────────────
    if (error) {
        return (
            <div style={styles.container}>
                <div style={styles.bgGradient} />
                <div style={styles.card}>
                    <div style={styles.errorIcon}>
                        <XCircle size={32} color="#ef4444" />
                    </div>
                    <h2 style={styles.errorTitle}>Authorization Error</h2>
                    <p style={styles.errorText}>{error}</p>
                    <button
                        onClick={() => navigate('/dashboard')}
                        style={styles.backBtn}
                    >
                        Return to Dashboard
                    </button>
                </div>
            </div>
        );
    }

    // ─── Consent Screen ─────────────────────────────────────────
    return (
        <div style={styles.container}>
            <div style={styles.bgGradient} />
            <div style={styles.bgOrb1} />
            <div style={styles.bgOrb2} />

            <div style={styles.card}>
                {/* Header — StockEye branding */}
                <div style={styles.header}>
                    <div style={styles.logoIconWrapper}>
                        <Eye size={20} color="#ffffff" strokeWidth={2.5} />
                    </div>
                    <span style={styles.logoText}>StockEye</span>
                </div>

                {/* Authorization prompt */}
                <div style={styles.shieldSection}>
                    <div style={styles.shieldIcon}>
                        <Shield size={24} color="#2563eb" />
                    </div>
                    <h1 style={styles.title}>Authorization Request</h1>
                    <p style={styles.subtitle}>
                        <strong style={{ color: '#e2e8f0' }}>{authDetails?.client?.name || 'An application'}</strong>
                        {' '}wants to access your StockEye account
                    </p>
                </div>

                {/* Signed in as */}
                <div style={styles.userBadge}>
                    <div style={styles.userAvatar}>
                        {user?.user_metadata?.avatar_url ? (
                            <img
                                src={user.user_metadata.avatar_url}
                                alt=""
                                style={styles.avatarImg}
                                referrerPolicy="no-referrer"
                            />
                        ) : (
                            <User size={14} color="#94a3b8" />
                        )}
                    </div>
                    <div>
                        <div style={styles.userName}>{user?.user_metadata?.full_name || user?.email}</div>
                        <div style={styles.userEmail}>{user?.email}</div>
                    </div>
                </div>

                {/* Scopes / Permissions */}
                {scopes.length > 0 && (
                    <div style={styles.scopesSection}>
                        <div style={styles.scopesHeader}>
                            <Key size={14} color="#64748b" />
                            <span style={styles.scopesTitle}>Requested Permissions</span>
                        </div>
                        <div style={styles.scopesList}>
                            {scopes.map((scope) => {
                                const info = SCOPE_LABELS[scope] || {
                                    label: scope,
                                    desc: `Access to ${scope}`,
                                    icon: Globe,
                                };
                                const ScopeIcon = info.icon;
                                return (
                                    <div key={scope} style={styles.scopeItem}>
                                        <div style={styles.scopeIconWrapper}>
                                            <ScopeIcon size={14} color="#2563eb" />
                                        </div>
                                        <div>
                                            <div style={styles.scopeLabel}>{info.label}</div>
                                            <div style={styles.scopeDesc}>{info.desc}</div>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}

                {/* Redirect URI info */}
                {authDetails?.redirect_uri && (
                    <div style={styles.redirectInfo}>
                        <Globe size={12} color="#475569" />
                        <span style={styles.redirectText}>
                            Redirects to: <code style={styles.redirectCode}>{authDetails.redirect_uri}</code>
                        </span>
                    </div>
                )}

                {/* Action buttons */}
                <div style={styles.actions}>
                    <button
                        onClick={handleApprove}
                        disabled={!!submitting}
                        style={{
                            ...styles.approveBtn,
                            opacity: submitting ? 0.7 : 1,
                            cursor: submitting ? 'not-allowed' : 'pointer',
                        }}
                    >
                        {submitting === 'approve' ? (
                            <>
                                <div style={styles.btnSpinner} />
                                Authorizing...
                            </>
                        ) : (
                            <>
                                <CheckCircle size={16} />
                                Authorize
                            </>
                        )}
                    </button>
                    <button
                        onClick={handleDeny}
                        disabled={!!submitting}
                        style={{
                            ...styles.denyBtn,
                            opacity: submitting ? 0.7 : 1,
                            cursor: submitting ? 'not-allowed' : 'pointer',
                        }}
                    >
                        {submitting === 'deny' ? (
                            <>
                                <div style={styles.btnSpinner} />
                                Denying...
                            </>
                        ) : (
                            <>
                                <XCircle size={16} />
                                Deny
                            </>
                        )}
                    </button>
                </div>

                {/* Footer */}
                <p style={styles.footer}>
                    By authorizing, you allow this application to access the listed permissions on your behalf.
                </p>
            </div>

            <style>{animations}</style>
        </div>
    );
}

// ─── Animations ─────────────────────────────────────────────────
const animations = `
  @keyframes float1 {
    0%, 100% { transform: translate(0, 0) scale(1); }
    33% { transform: translate(30px, -50px) scale(1.05); }
    66% { transform: translate(-20px, 20px) scale(0.95); }
  }
  @keyframes float2 {
    0%, 100% { transform: translate(0, 0) scale(1); }
    33% { transform: translate(-40px, 30px) scale(1.1); }
    66% { transform: translate(25px, -40px) scale(0.9); }
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }
  @keyframes fadeInUp {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
  }
`;

// ─── Styles ─────────────────────────────────────────────────────
const styles = {
    container: {
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        position: 'relative',
        overflow: 'hidden',
        background: '#050a18',
        fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    },
    bgGradient: {
        position: 'absolute',
        inset: 0,
        background: 'radial-gradient(ellipse at 30% 20%, rgba(37,99,235,0.15), transparent 50%), radial-gradient(ellipse at 70% 80%, rgba(124,58,237,0.1), transparent 50%)',
    },
    bgOrb1: {
        position: 'absolute',
        width: 400,
        height: 400,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(37,99,235,0.12), transparent 70%)',
        top: '-10%',
        left: '-5%',
        animation: 'float1 12s ease-in-out infinite',
    },
    bgOrb2: {
        position: 'absolute',
        width: 350,
        height: 350,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(124,58,237,0.1), transparent 70%)',
        bottom: '-5%',
        right: '-5%',
        animation: 'float2 15s ease-in-out infinite',
    },
    card: {
        position: 'relative',
        zIndex: 10,
        width: '100%',
        maxWidth: 460,
        padding: '40px 36px',
        background: 'rgba(15, 23, 42, 0.85)',
        backdropFilter: 'blur(24px)',
        border: '1px solid rgba(148, 163, 184, 0.1)',
        borderRadius: 24,
        boxShadow: '0 24px 64px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.05) inset',
        animation: 'fadeInUp 0.6s ease-out',
    },
    header: {
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        marginBottom: 28,
    },
    logoIconWrapper: {
        width: 36,
        height: 36,
        borderRadius: 12,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #2563eb, #7c3aed)',
        boxShadow: '0 4px 16px rgba(37,99,235,0.35)',
    },
    logoText: {
        fontSize: 18,
        fontWeight: 800,
        background: 'linear-gradient(135deg, #ffffff, #94a3b8)',
        WebkitBackgroundClip: 'text',
        WebkitTextFillColor: 'transparent',
    },
    shieldSection: {
        textAlign: 'center',
        marginBottom: 24,
    },
    shieldIcon: {
        width: 48,
        height: 48,
        borderRadius: 16,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(37,99,235,0.1)',
        border: '1px solid rgba(37,99,235,0.2)',
        marginBottom: 16,
    },
    title: {
        fontSize: 20,
        fontWeight: 700,
        color: '#f1f5f9',
        margin: '0 0 8px',
    },
    subtitle: {
        fontSize: 14,
        color: '#94a3b8',
        lineHeight: 1.5,
        margin: 0,
    },
    userBadge: {
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '12px 16px',
        background: 'rgba(30, 41, 59, 0.6)',
        borderRadius: 14,
        border: '1px solid rgba(148,163,184,0.1)',
        marginBottom: 20,
    },
    userAvatar: {
        width: 36,
        height: 36,
        borderRadius: '50%',
        overflow: 'hidden',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(148,163,184,0.1)',
        flexShrink: 0,
    },
    avatarImg: {
        width: '100%',
        height: '100%',
        objectFit: 'cover',
        borderRadius: '50%',
    },
    userName: {
        fontSize: 13,
        fontWeight: 600,
        color: '#e2e8f0',
    },
    userEmail: {
        fontSize: 11,
        color: '#64748b',
        marginTop: 2,
    },
    scopesSection: {
        marginBottom: 20,
    },
    scopesHeader: {
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        marginBottom: 12,
    },
    scopesTitle: {
        fontSize: 12,
        fontWeight: 600,
        color: '#94a3b8',
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
    },
    scopesList: {
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
    },
    scopeItem: {
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '10px 14px',
        background: 'rgba(30, 41, 59, 0.5)',
        borderRadius: 12,
        border: '1px solid rgba(148,163,184,0.08)',
    },
    scopeIconWrapper: {
        width: 32,
        height: 32,
        borderRadius: 10,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(37,99,235,0.1)',
        flexShrink: 0,
    },
    scopeLabel: {
        fontSize: 13,
        fontWeight: 600,
        color: '#e2e8f0',
    },
    scopeDesc: {
        fontSize: 11,
        color: '#64748b',
        marginTop: 2,
    },
    redirectInfo: {
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 12px',
        background: 'rgba(30, 41, 59, 0.4)',
        borderRadius: 10,
        marginBottom: 24,
    },
    redirectText: {
        fontSize: 11,
        color: '#475569',
    },
    redirectCode: {
        color: '#64748b',
        fontFamily: 'monospace',
        fontSize: 10,
    },
    actions: {
        display: 'flex',
        gap: 12,
        marginBottom: 16,
    },
    approveBtn: {
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        padding: '14px 20px',
        background: 'linear-gradient(135deg, #2563eb, #1d4ed8)',
        border: 'none',
        borderRadius: 14,
        fontSize: 14,
        fontWeight: 600,
        color: '#ffffff',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        boxShadow: '0 4px 16px rgba(37,99,235,0.3)',
        fontFamily: 'inherit',
    },
    denyBtn: {
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        padding: '14px 20px',
        background: 'rgba(30, 41, 59, 0.6)',
        border: '1px solid rgba(148,163,184,0.15)',
        borderRadius: 14,
        fontSize: 14,
        fontWeight: 600,
        color: '#94a3b8',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        fontFamily: 'inherit',
    },
    footer: {
        fontSize: 11,
        color: '#475569',
        textAlign: 'center',
        lineHeight: 1.5,
        margin: 0,
    },
    // Error / Loading states
    errorIcon: {
        textAlign: 'center',
        marginBottom: 16,
    },
    errorTitle: {
        fontSize: 18,
        fontWeight: 700,
        color: '#f1f5f9',
        textAlign: 'center',
        marginBottom: 8,
    },
    errorText: {
        fontSize: 13,
        color: '#94a3b8',
        textAlign: 'center',
        lineHeight: 1.5,
    },
    backBtn: {
        display: 'block',
        width: '100%',
        marginTop: 20,
        padding: '12px 20px',
        background: 'rgba(37,99,235,0.1)',
        border: '1px solid rgba(37,99,235,0.2)',
        borderRadius: 12,
        fontSize: 13,
        fontWeight: 600,
        color: '#2563eb',
        cursor: 'pointer',
        textAlign: 'center',
        fontFamily: 'inherit',
    },
    loadingWrapper: {
        textAlign: 'center',
        padding: '20px 0',
    },
    spinner: {
        width: 40,
        height: 40,
        border: '3px solid rgba(37,99,235,0.2)',
        borderTopColor: '#2563eb',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
        margin: '0 auto 16px',
    },
    loadingText: {
        fontSize: 13,
        color: '#94a3b8',
    },
    btnSpinner: {
        width: 16,
        height: 16,
        border: '2px solid rgba(255,255,255,0.3)',
        borderTopColor: '#ffffff',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
    },
};
