import React, { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import StockEyeLogo from './StockEyeLogo';

export default function LoginPage() {
    const { signInWithGoogle, isAuthenticated, loading } = useAuth();
    const navigate = useNavigate();
    const [searchParams] = useSearchParams();
    const redirectTo = searchParams.get('redirect') || '/dashboard';

    useEffect(() => {
        if (!loading && isAuthenticated) {
            navigate(redirectTo, { replace: true });
        }
    }, [loading, isAuthenticated, navigate, redirectTo]);

    const handleGoogleLogin = async () => {
        try {
            await signInWithGoogle(redirectTo);
        } catch (err) {
            console.error('Login failed:', err);
        }
    };

    if (loading) {
        return (
            <div style={styles.loadingContainer}>
                <div style={styles.spinner} />
            </div>
        );
    }

    return (
        <div style={styles.container}>
            {/* Animated background */}
            <div style={styles.bgGradient} />
            <div style={styles.bgOrb1} />
            <div style={styles.bgOrb2} />
            <div style={styles.bgOrb3} />

            {/* Login card */}
            <div style={styles.card}>
                {/* Logo & Brand */}
                <div style={styles.logoSection}>
                    <div style={styles.logoContainer}>
                        <StockEyeLogo size={64} />
                        <div style={styles.logoPulse} />
                    </div>
                    <h1 style={styles.brandName}>StockEye</h1>
                    <p style={styles.brandTagline}>AI-Powered Stock Intelligence</p>
                </div>

                {/* Divider */}
                <div style={styles.divider}>
                    <div style={styles.dividerLine} />
                    <span style={styles.dividerText}>sign in to continue</span>
                    <div style={styles.dividerLine} />
                </div>

                {/* Google Sign In Button */}
                <button onClick={handleGoogleLogin} style={styles.googleBtn}>
                    <svg width="20" height="20" viewBox="0 0 24 24" style={{ flexShrink: 0 }}>
                        <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
                        <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                        <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                        <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                    </svg>
                    <span>Continue with Google</span>
                </button>

                {/* Info text */}
                <p style={styles.infoText}>
                    Your portfolio, watchlists, and conversations are synced securely via Supabase.
                </p>

                {/* Features */}
                <div style={styles.features}>
                    {['Real-time Market Data', 'AI-Powered Analysis', 'Portfolio Tracking'].map((f, i) => (
                        <div key={i} style={styles.featureItem}>
                            <div style={styles.featureDot} />
                            <span>{f}</span>
                        </div>
                    ))}
                </div>
            </div>

            {/* Footer */}
            <p style={styles.footer}>
                © 2026 StockEye · Powered by Supabase & AI
            </p>

            <style>{`
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
        @keyframes float3 {
          0%, 100% { transform: translate(0, 0) scale(1); }
          50% { transform: translate(20px, 30px) scale(1.05); }
        }
        @keyframes pulse-ring {
          0% { transform: scale(1); opacity: 0.4; }
          100% { transform: scale(1.6); opacity: 0; }
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        @keyframes fadeInUp {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
        </div>
    );
}

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
    bgOrb3: {
        position: 'absolute',
        width: 200,
        height: 200,
        borderRadius: '50%',
        background: 'radial-gradient(circle, rgba(16,185,129,0.08), transparent 70%)',
        top: '60%',
        left: '20%',
        animation: 'float3 10s ease-in-out infinite',
    },
    card: {
        position: 'relative',
        zIndex: 10,
        width: '100%',
        maxWidth: 420,
        padding: '48px 40px',
        background: 'rgba(15, 23, 42, 0.8)',
        backdropFilter: 'blur(24px)',
        border: '1px solid rgba(148, 163, 184, 0.1)',
        borderRadius: 24,
        boxShadow: '0 24px 64px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.05) inset',
        animation: 'fadeInUp 0.6s ease-out',
    },
    logoSection: {
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        marginBottom: 32,
    },
    logoContainer: {
        position: 'relative',
        marginBottom: 16,
    },
    logoIconWrapper: {
        width: 64,
        height: 64,
        borderRadius: 20,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #2563eb, #7c3aed)',
        boxShadow: '0 8px 32px rgba(37,99,235,0.4)',
    },
    logoPulse: {
        position: 'absolute',
        inset: -4,
        borderRadius: 24,
        border: '2px solid rgba(37,99,235,0.3)',
        animation: 'pulse-ring 2s ease-out infinite',
    },
    brandName: {
        fontSize: 28,
        fontWeight: 800,
        letterSpacing: '-0.02em',
        background: 'linear-gradient(135deg, #ffffff, #94a3b8)',
        WebkitBackgroundClip: 'text',
        WebkitTextFillColor: 'transparent',
        margin: 0,
    },
    brandTagline: {
        fontSize: 13,
        color: '#64748b',
        marginTop: 4,
        letterSpacing: '0.02em',
    },
    divider: {
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        marginBottom: 28,
    },
    dividerLine: {
        flex: 1,
        height: 1,
        background: 'rgba(148,163,184,0.15)',
    },
    dividerText: {
        fontSize: 11,
        color: '#475569',
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
        fontWeight: 600,
    },
    googleBtn: {
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 12,
        padding: '14px 24px',
        background: '#ffffff',
        border: 'none',
        borderRadius: 14,
        fontSize: 15,
        fontWeight: 600,
        color: '#1f2937',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
        fontFamily: 'inherit',
    },
    infoText: {
        fontSize: 12,
        color: '#475569',
        textAlign: 'center',
        marginTop: 20,
        lineHeight: 1.5,
    },
    features: {
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        marginTop: 28,
        paddingTop: 24,
        borderTop: '1px solid rgba(148,163,184,0.1)',
    },
    featureItem: {
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        fontSize: 13,
        color: '#94a3b8',
    },
    featureDot: {
        width: 6,
        height: 6,
        borderRadius: '50%',
        background: 'linear-gradient(135deg, #2563eb, #7c3aed)',
        flexShrink: 0,
    },
    footer: {
        position: 'relative',
        zIndex: 10,
        marginTop: 32,
        fontSize: 11,
        color: '#334155',
        letterSpacing: '0.02em',
    },
    loadingContainer: {
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#050a18',
    },
    spinner: {
        width: 40,
        height: 40,
        border: '3px solid rgba(37,99,235,0.2)',
        borderTopColor: '#2563eb',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
    },
};
