import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';
import { supabase } from '../lib/supabase';
import { authAxios } from '../utils/api';

const AuthContext = createContext(null);

const API_URL = process.env.REACT_APP_API_URL || '';

// sessionStorage keys — cleared on sign-out
const SK_STATUS = 'se_user_status';
const SK_ROLE   = 'se_user_role';

export function AuthProvider({ children }) {
    const [user, setUser]       = useState(null);
    const [session, setSession] = useState(null);
    const [loading, setLoading] = useState(true);

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
        // directToken: when provided (from onAuthStateChange), bypasses the authAxios
        // interceptor which calls supabase.auth.getSession() and can deadlock on
        // Supabase's internal refresh lock (_recoverAndRefresh holds the lock while
        // onAuthStateChange is firing, causing getSession() to wait → 8 s timeout →
        // request sent without auth header → 401 → status set to 'rejected').
        const fetchUserMeta = async (isBackground = false, directToken = null) => {
            try {
                let data;
                if (directToken) {
                    // Bypass the interceptor entirely — token is already in hand
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
            } catch (err) {
                console.error('Failed to fetch user meta:', err);
                // On background refresh, keep cached values — don't reject on network hiccup
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
                if (s) {
                    // If we already have a cached status, unblock the UI immediately
                    // and refresh in the background
                    if (sessionStorage.getItem(SK_STATUS)) {
                        setLoading(false);
                        fetchUserMeta(true);   // background refresh — don't clear on error
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
                if (s) {
                    // Pass the token directly — avoids calling getSession() inside
                    // the auth callback which deadlocks on Supabase's refresh lock
                    await fetchUserMeta(false, s.access_token);
                } else if (_event === 'SIGNED_OUT') {
                    // Only clear cached status on explicit sign-out, not on
                    // transient null-session events during token refresh
                    setUserRole(null);
                    setUserStatus(null);
                }
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

    const signOut = async () => {
        const { error } = await supabase.auth.signOut();
        if (error) throw error;
        // Clear cached status on explicit sign-out
        sessionStorage.removeItem(SK_STATUS);
        sessionStorage.removeItem(SK_ROLE);
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
        signInWithGoogle,
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
