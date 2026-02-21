/**
 * apiCache.js — Simple in-memory TTL cache.
 * Prevents redundant API calls when navigating between pages.
 *
 * Usage:
 *   import * as cache from './utils/apiCache';
 *   const cached = cache.get('movers');
 *   if (!cached) { ... fetch ... cache.set('movers', data); }
 */

const _store = {};

/**
 * Store a value with a time-to-live.
 * @param {string} key
 * @param {*}      value
 * @param {number} ttlMs  Default 60 000 ms (60 s)
 */
export function set(key, value, ttlMs = 60_000) {
    _store[key] = { value, expiresAt: Date.now() + ttlMs };
}

/**
 * Return a cached value, or null if missing / expired.
 * @param {string} key
 */
export function get(key) {
    const entry = _store[key];
    if (!entry) return null;
    if (Date.now() > entry.expiresAt) {
        delete _store[key];
        return null;
    }
    return entry.value;
}

/** Force-remove a cache entry (e.g. after a manual refresh). */
export function invalidate(key) {
    delete _store[key];
}
