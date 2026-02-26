import axios from 'axios';
import { supabase } from './supabase';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

const api = axios.create({
    baseURL: API_URL,
});

// Attach Bearer token to every request
api.interceptors.request.use(async (config) => {
    try {
        const { data: { session } } = await supabase.auth.getSession();
        if (session?.access_token) {
            config.headers.Authorization = `Bearer ${session.access_token}`;
        }
    } catch (err) {
        // If session fetch fails, proceed without token
        console.warn('Failed to attach auth token:', err.message);
    }
    return config;
});

// Handle 401 responses — redirect to login
api.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401) {
            // Clear the session and redirect to login
            supabase.auth.signOut();
            window.location.href = '/login';
        }
        return Promise.reject(error);
    }
);

export default api;
export { API_URL };
