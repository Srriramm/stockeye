import React, { createContext, useContext, useState, useEffect } from 'react';
import { supabase } from '../lib/supabase';
import { authAxios } from '../utils/api';

const AuthContext = createContext(null);

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

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
        const fetchUserMeta = async () => {
            try {
                const { data } = await authAxios.get(`${API_URL}/api/auth/me`);
                setUserRole(data.role);
                setUserStatus(data.status);
            } catch (err) {
                console.error('Failed to fetch user meta:', err);
                setUserRole('user');
                setUserStatus('rejected');
            }
        };

        const init = async () => {
            const { data: { session: s } } = await supabase.auth.getSession();
            setSession(s);
            setUser(s?.user ?? null);
            if (s) {
                // If we already have a cached status, unblock the UI immediately
                // and refresh in the background
                if (sessionStorage.getItem(SK_STATUS)) {
                    setLoading(false);
                    fetchUserMeta();   // background refresh — no await
                } else {
                    await fetchUserMeta();
                    setLoading(false);
                }
            } else {
                setLoading(false);
            }
        };
        init();

        const { data: { subscription } } = supabase.auth.onAuthStateChange(
            async (_event, s) => {
                setSession(s);
                setUser(s?.user ?? null);
                if (s) {
                    await fetchUserMeta();
                } else {
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
