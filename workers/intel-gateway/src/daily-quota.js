// =============================================================================
// CYBERDUDEBIVASH(R) SENTINEL APEX -- Daily API Quota
//
// Extracted into its own dependency-free file, same pattern as
// subscription-lifecycle.js, specifically so it is unit-testable in CI
// under plain `node --test` without pulling in index.js's full import
// chain (pricing.js -> pricing-data.json fails Node's native ESM loader
// outside the wrangler/esbuild bundler -- see subscription-lifecycle.js's
// header comment for the full explanation).
//
// This is a genuinely additive layer on top of the existing per-minute
// checkRateLimit()/RATE_LIMITS already in index.js: that limiter enforces
// a per-minute burst cap; this one enforces a 24-hour rolling quota per
// API key (or per hashed IP for anonymous callers). Both are consulted on
// every request and both read/write the same RATE_LIMIT_KV binding --
// deliberately reusing index.js's already-resolved auth/tier
// (resolveAuth()) rather than re-deriving identity a second way, so there
// is exactly one place a caller's tier is decided and two independent
// counters against it, not two independent identity-resolution paths.
// =============================================================================

export const DAILY_QUOTA = { FREE: 50, PRO: 5000, ENTERPRISE: 50000, MSSP: 1000000 };

/**
 * SHA-256 hash of a client IP, hex-encoded and truncated to 32 chars.
 * RATE_LIMIT_KV never holds a raw IP at rest for anonymous callers.
 * @param {string} ip
 * @returns {Promise<string>}
 */
export async function hashClientIp(ip) {
  const data   = new TextEncoder().encode(ip || "");
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest)).map(b => b.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

/** UTC calendar day (YYYY-MM-DD) for `at`, defaulting to now. */
export function utcDayString(at = new Date()) {
  return at.toISOString().slice(0, 10);
}

/** Unix seconds of the next UTC midnight strictly after `at`. */
export function nextUtcMidnight(at = new Date()) {
  const day = utcDayString(at);
  return Math.floor(new Date(`${day}T00:00:00.000Z`).getTime() / 1000) + 86400;
}

/**
 * 24h rolling quota check + increment against RATE_LIMIT_KV.
 *
 * Not a second auth/tier resolution path: `auth` is whatever index.js's
 * resolveAuth() already produced for this request; this function only
 * meters against it.
 *
 * @param {{RATE_LIMIT_KV: {get: Function, put: Function}}} env
 * @param {{key?: string|null, tier?: string}} auth - from resolveAuth()
 * @param {string} ip - CF-Connecting-IP, already resolved by index.js
 * @returns {Promise<{allowed:boolean, tier:string, limit:number, remaining:number, reset:number, count:number}>}
 */
export async function checkDailyQuota(env, auth, ip) {
  const tier  = (auth && auth.tier) || "FREE";
  const limit = DAILY_QUOTA[tier] || DAILY_QUOTA.FREE;
  const now   = new Date();
  const day   = utcDayString(now);
  const reset = nextUtcMidnight(now);
  const identity = auth && auth.key ? auth.key : `ip:${await hashClientIp(ip)}`;
  const kvKey = `usage:${identity}:${day}`;

  try {
    const val   = await env.RATE_LIMIT_KV.get(kvKey);
    const count = val ? parseInt(val, 10) : 0;
    if (count >= limit) {
      return { allowed: false, tier, limit, remaining: 0, reset, count };
    }
    // 48h TTL per spec -- comfortably outlives the 24h window it counts,
    // so it never expires mid-day; the YYYY-MM-DD key naturally rolls over.
    await env.RATE_LIMIT_KV.put(kvKey, String(count + 1), { expirationTtl: 172800 });
    return { allowed: true, tier, limit, remaining: Math.max(limit - count - 1, 0), reset, count: count + 1 };
  } catch (_) {
    // Fail-open on a KV outage -- same posture as checkRateLimit() (index.js).
    return { allowed: true, tier, limit, remaining: limit, reset, count: 0 };
  }
}

/**
 * Builds the exact JSON body index.js returns on a 429 from checkDailyQuota().
 * Extracted as its own pure function (not inlined in index.js) so the exact
 * response schema is directly unit-testable without index.js's import chain.
 *
 * @param {{allowed:boolean, tier:string, limit:number, reset:number}} quota - a checkDailyQuota() result with allowed:false
 * @returns {{error:string, status:number, tier:string, message:string, upgrade_url:string, direct_checkout?: Record<string,string>}}
 */
export function buildQuotaExceededBody(quota) {
  const nextTier = quota.tier === "FREE" ? "PRO" : quota.tier === "PRO" ? "ENTERPRISE" : null;
  const message = nextTier
    ? `Daily request quota reached (${quota.limit}/${quota.limit}). Upgrade to Sentinel ${nextTier === "PRO" ? "Pro" : "Enterprise"} for ${DAILY_QUOTA[nextTier].toLocaleString()} requests/day, raw feeds, and STIX/TAXII streams.`
    : `Daily request quota reached (${quota.limit}/${quota.limit}). Contact enterprise@cyberdudebivash.com for a higher-throughput plan.`;
  const directCheckout = nextTier ? {
    [`${nextTier.toLowerCase()}_usd`]: `https://intel.cyberdudebivash.com/api/billing/checkout?tier=${nextTier.toLowerCase()}&currency=usd`,
    [`${nextTier.toLowerCase()}_inr`]: `https://intel.cyberdudebivash.com/api/billing/checkout?tier=${nextTier.toLowerCase()}&currency=inr`,
  } : undefined;

  return {
    error: "RATE_LIMIT_EXCEEDED",
    status: 429,
    tier: quota.tier,
    message,
    // .html suffix required -- this site has no clean-URL routing (no
    // Jekyll/_redirects config, .nojekyll at root); every other real
    // internal link on the site (88 of them) uses /pricing.html, zero use
    // bare /pricing, and premium-reports.js/revenue-enforcement.js's own
    // pricing links already agree on .html. Bare /pricing was a dead link.
    upgrade_url: "https://intel.cyberdudebivash.com/pricing.html?ref=api_429",
    ...(directCheckout ? { direct_checkout: directCheckout } : {}),
  };
}
