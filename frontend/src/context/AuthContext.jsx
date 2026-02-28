import React, { createContext, useContext, useState, useEffect } from 'react';
import { supabase } from '../lib/supabase';
import { authAxios } from '../utils/api';

const AuthContext = createContext(null);

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

export function AuthProvider({ children }) {
    const [user, setUser] = useState(null);
    const [session, setSession] = useState(null);
    const [loading, setLoading] = useState(true);
    const [userRole, setUserRole] = useState(null);    // 'user' | 'admin'
    const [userStatus, setUserStatus] = useState(null); // 'approved' | 'rejected' | 'suspended'

    useEffect(() => {
        const fetchUserMeta = async () => {
            try {
                const { data } = await authAxios.get(`${API_URL}/api/auth/me`);
                setUserRole(data.role);
                setUserStatus(data.status);
            } catch (err) {
                console.error('Failed to fetch user meta:', err);
                setUserRole('user');
                setUserStatus('rejected');   // treat backend error as rejected — avoids infinite spinner
            }
        };

        // Get initial session, then fetch user meta
        const init = async () => {
            const { data: { session: s } } = await supabase.auth.getSession();
            setSession(s);
            setUser(s?.user ?? null);
            if (s) {
                await fetchUserMeta();
            }
            setLoading(false);
        };
        init();

        // Listen for auth changes (login, logout, token refresh)
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
