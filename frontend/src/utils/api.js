/**
 * api.js — Authenticated axios helper.
 *
 * Usage:
 *   import { getAuthHeaders, authAxios } from '../utils/api';
 *
 *   // One-off request with auth headers:
 *   const res = await authAxios.get(`${apiUrl}/api/portfolio`);
 *
 *   // Manual header injection (if needed):
 *   const headers = await getAuthHeaders();
 *   const res = await axios.get(url, { headers });
 */

import axios from 'axios';
import { supabase } from '../lib/supabase';

/**
 * Returns an Authorization header object with the current Supabase access token.
 * Throws if no session is active.
 */
export async function getAuthHeaders() {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session?.access_token) {
        throw new Error('No active session — user is not authenticated');
    }
    return { Authorization: `Bearer ${session.access_token}` };
}

/**
 * Axios instance with a request interceptor that auto-attaches the Bearer token.
 * Use this instead of bare `axios` for any authenticated backend call.
 */
export const authAxios = axios.create({ timeout: 8000 });

authAxios.interceptors.request.use(async (config) => {
    const headers = await getAuthHeaders();
    config.headers = { ...config.headers, ...headers };
    return config;
});
