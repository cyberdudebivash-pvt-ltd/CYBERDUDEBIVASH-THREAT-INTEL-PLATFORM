/**
 * CYBERDUDEBIVASH® SENTINEL APEX — API Integration Layer v1.0
 * All backend calls. Handles errors gracefully. Never crashes UI.
 */
'use strict';

const APEX = (() => {
  // v184.6: Railway backend retired (orphaned, no live traffic behind it --
  // see index.html/script.js's own equivalent fix from 2026-08-20). This now
  // points at intel-gateway, the real production Cloudflare Worker gateway.
  const BASE = 'https://intel.cyberdudebivash.com';
  const TIMEOUT_MS = 12000;

  /** Fetch with timeout + structured error */
  async function apiFetch(path, opts = {}) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    try {
      const res = await fetch(BASE + path, { ...opts, signal: ctrl.signal });
      clearTimeout(timer);
      const ct = res.headers.get('content-type') || '';
      const data = ct.includes('json') ? await res.json() : await res.text();
      if (!res.ok) throw { status: res.status, data };
      return { ok: true, data, status: res.status };
    } catch (err) {
      clearTimeout(timer);
      if (err.name === 'AbortError')
        return { ok: false, error: 'Request timed out. Please try again.', status: 0 };
      if (err.status) return { ok: false, error: err.data?.detail || err.data || 'API error', status: err.status };
      return { ok: false, error: 'Network error — check your connection.', status: 0 };
    }
  }

  /**
   * GET /api/v1/onboard — pricing + quick-start guide
   * @deprecated Since 2026-08-21 (Railway retirement). No equivalent route
   * exists on intel-gateway (the real production Worker) and no caller of
   * this function was found anywhere in the repository. Retained, unused,
   * through 2026-11-21 (90 days) in case another page still embeds this
   * widget; remove after that date once confirmed no consumer remains.
   */
  async function onboard() {
    return apiFetch('/api/v1/onboard');
  }

  /**
   * POST /api/v1/subscribe — create checkout session
   * @deprecated Since 2026-08-20. This path targeted an orphaned backend with
   * no live production traffic behind it and is no longer called from
   * index.html (the pricing CTAs now link directly to /upgrade.html, the
   * existing production checkout page already wired to the real Razorpay
   * flow). Replacement: /upgrade.html?plan={pro|enterprise}. Retained,
   * unused, through 2026-11-20 (90 days) in case another page still embeds
   * this widget; remove after that date once confirmed no consumer remains.
   */
  async function subscribe(plan, provider = 'stripe', name = '', email = '') {
    return apiFetch('/api/v1/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tier: plan, payment_provider: provider, name, email }),
    });
  }

  /**
   * GET /api/v1/intel/latest.json — shared fetch for fetchIntel/fetchFeed.
   * v184.6: intel-gateway's real endpoint has no `limit`/`offset` query
   * params (unlike the retired Railway backend) -- it returns the full
   * tier-appropriate set; slice client-side instead.
   */
  async function _fetchIntelSlice(apiKey, start, end) {
    const headers = {};
    if (apiKey && apiKey !== 'anon') headers['X-API-Key'] = apiKey;
    const res = await apiFetch('/api/v1/intel/latest.json', { headers });
    if (res.ok && res.data && Array.isArray(res.data.items)) {
      res.data = { ...res.data, items: res.data.items.slice(start, end) };
    }
    return res;
  }

  /** GET /api/v1/intel/latest.json — fetch latest advisories, tier-gated server-side by the caller's key. */
  async function fetchIntel(apiKey, limit = 20) {
    return _fetchIntelSlice(apiKey, 0, limit);
  }

  /** GET /api/v1/intel/latest.json — paginated feed. */
  async function fetchFeed(apiKey, limit = 50, offset = 0) {
    return _fetchIntelSlice(apiKey, offset, offset + limit);
  }

  /** GET /api/v1/stats — platform stats */
  async function fetchStats(apiKey) {
    const headers = {};
    if (apiKey && apiKey !== 'anon') headers['X-API-Key'] = apiKey;
    return apiFetch('/api/v1/stats', { headers });
  }

  /**
   * GET /api/v1/tiers — public tier info
   * @deprecated Since 2026-08-21 (Railway retirement). No equivalent route
   * exists on intel-gateway and no caller of this function was found
   * anywhere in the repository. Retained, unused, through 2026-11-21 (90
   * days) in case another page still embeds this widget; remove after that
   * date once confirmed no consumer remains.
   */
  async function fetchTiers() {
    return apiFetch('/api/v1/tiers');
  }

  /** GET /api/health — liveness check (intel-gateway's real path, v184.6) */
  async function health() {
    return apiFetch('/api/health');
  }

  return { onboard, subscribe, fetchIntel, fetchFeed, fetchStats, fetchTiers, health };
})();

/* Make available globally */
if (typeof window !== 'undefined') window.APEX = APEX;
if (typeof module !== 'undefined') module.exports = APEX;
