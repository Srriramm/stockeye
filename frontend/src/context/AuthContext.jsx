import { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';
import { supabase } from '../lib/supabase';
import { authAxios } from '../utils/api';

const AuthContext = createContext(null);

const API_URL = process.env.REACT_APP_API_URL || '';

// sessionStorage keys — cleared on sign-out
const SK_STATUS = 'se_user_status';
const SK_ROLE   = 'se_user_role';

// localStorage key for trial start timestamp (survives page refresh)
const LS_TRIAL_SINCE = 'se_trial_since';
const TRIAL_DURATION_MS = 3 * 24 * 60 * 60 * 1000; // 3 days

function trialDaysLeft() {
    const since = parseInt(localStorage.getItem(LS_TRIAL_SINCE) || '0', 10);
    if (!since) return 0;
    const elapsed = Date.now() - since;
    return Math.max(0, Math.ceil((TRIAL_DURATION_MS - elapsed) / (24 * 60 * 60 * 1000)));
}

export function AuthProvider({ children }) {
    const [user, setUser]       = useState(null);
    const [session, setSession] = useState(null);
    const [loading, setLoading] = useState(true);
    const [isTrial, setIsTrial] = useState(false);
    const [trialDays, setTrialDays] = useState(3);

    // Seed from sessionStorage so there's no spinner flash on page reload
    const [userRole,   setUserRoleState]   = useState(() => sessionStorage.getItem(SK_ROLE)   || null);
    const [userStatus, setUserStatusState] = useState(() => sessionStorage.getItem(SK_STATUS) || null);

    // Wrappers that keep sessionStorage in sync
    const setUserRole = (v) => {
        setUserRoleState(v);
        if (v) sessionStorage.setItem(SK_ROLE, v);
        else    sessionStorage.removeItem(SK_ROLE);
    };
    const setUserStatus = (v) => {
        setUserStatusState(v);
        if (v) sessionStorage.setItem(SK_STATUS, v);
        else    sessionStorage.removeItem(SK_STATUS);
    };

    useEffect(() => {
        const fetchUserMeta = async (isBackground = false, directToken = null) => {
            try {
                let data;
                if (directToken) {
                    const res = await axios.get(`${API_URL}/api/auth/me`, {
                        headers: { Authorization: `Bearer ${directToken}` },
                        timeout: 30000,
                    });
                    data = res.data;
                } else {
                    const res = await authAxios.get(`${API_URL}/api/auth/me`);
                    data = res.data;
                }
                setUserRole(data.role);
                setUserStatus(data.status);
                if (data.is_trial) {
                    setIsTrial(true);
                    setTrialDays(trialDaysLeft());
                }
            } catch (err) {
                console.error('Failed to fetch user meta:', err);
                if (!isBackground) {
                    setUserRole('user');
                    setUserStatus('rejected');
                }
            }
        };

        const init = async () => {
            try {
                const { data: { session: s } } = await supabase.auth.getSession();
                setSession(s);
                setUser(s?.user ?? null);

                // Check trial expiry on every page load
                if (s?.user?.is_anonymous) {
                    const days = trialDaysLeft();
                    if (days <= 0) {
                        // Trial expired — sign out silently
                        await supabase.auth.signOut();
                        localStorage.removeItem(LS_TRIAL_SINCE);
                        setLoading(false);
                        return;
                    }
                    setIsTrial(true);
                    setTrialDays(days);
                }

                if (s) {
                    if (sessionStorage.getItem(SK_STATUS)) {
                        setLoading(false);
                        fetchUserMeta(true);
                    } else {
                        await fetchUserMeta(false);
                        setLoading(false);
                    }
                } else {
                    setLoading(false);
                }
            } catch {
                setLoading(false);
            }
        };
        init();

        const { data: { subscription } } = supabase.auth.onAuthStateChange(
            async (_event, s) => {
                setSession(s);
                setUser(s?.user ?? null);

                if (_event === 'SIGNED_OUT') {
                    setUserRole(null);
                    setUserStatus(null);
                    setIsTrial(false);
                    setLoading(false);
                    return;
                }

                if (_event === 'INITIAL_SESSION') {
                    setLoading(false);
                    return;
                }

                if (!s) {
                    setLoading(false);
                    return;
                }

                const isBackground = _event !== 'SIGNED_IN';
                await fetchUserMeta(isBackground, s.access_token);
                setLoading(false);
            }
        );

        return () => subscription.unsubscribe();
    }, []);

    const signInWithGoogle = async (redirectTo) => {
        const { error } = await supabase.auth.signInWithOAuth({
            provider: 'google',
            options: {
                redirectTo: window.location.origin + (redirectTo || '/dashboard'),
            },
        });
        if (error) throw error;
    };

    const signInAnonymously = async () => {
        const { error } = await supabase.auth.signInAnonymously();
        if (error) throw error;
        // Record trial start if not already set
        if (!localStorage.getItem(LS_TRIAL_SINCE)) {
            localStorage.setItem(LS_TRIAL_SINCE, String(Date.now()));
        }
        setIsTrial(true);
        setTrialDays(trialDaysLeft());
    };

    const signOut = async () => {
        const { error } = await supabase.auth.signOut();
        if (error) throw error;
        sessionStorage.removeItem(SK_STATUS);
        sessionStorage.removeItem(SK_ROLE);
        // Clear trial state only on explicit sign-out (not expiry)
        if (isTrial) localStorage.removeItem(LS_TRIAL_SINCE);
    };

    const getAccessToken = async () => {
        const { data: { session: s } } = await supabase.auth.getSession();
        return s?.access_token ?? null;
    };

    const value = {
        user,
        session,
        loading,
        userRole,
        userStatus,
        isTrial,
        trialDays,
        signInWithGoogle,
        signInAnonymously,
        signOut,
        getAccessToken,
        isAuthenticated: !!session,
    };

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
    return ctx;
}
