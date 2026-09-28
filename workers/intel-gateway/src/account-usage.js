// =============================================================================
// CYBERDUDEBIVASH(R) SENTINEL APEX -- GET /api/account/usage (2026-09-26)
// -----------------------------------------------------------------------------
// The customer API console (api-key-manager.html) called /api/account/usage
// for its Keys and Usage tabs, but no such route existed (404), so every
// signed-in customer saw "Authentication required" however valid their key.
// usage-meter.js's getUsageSummary() already documented itself as "Used by:
// /api/account/usage" -- the route was simply never wired.
//
// The route (index.js) composes two existing, unchanged engines:
//   - readSwarmQuotaSnapshot(env, auth.key, auth.tier): the daily quota that
//     checkDailyQuota() actually enforces (RATE_LIMIT_KV, keyed by auth.key);
//   - getUsageSummary(env, auth.sub, date): usage-meter.js's per-customer
//     request/credit/endpoint counters (ANALYTICS_KV, keyed by auth.sub).
// This module only shapes their output. It is dependency-free so
// __tests__/account-usage.test.js can import it under plain `node --test`.
//
// Security: the caller's own credential is never echoed back (masked only);
// the response is per-caller and must not be cached (Cache-Control: no-store
// is set by the route).
// =============================================================================

// Key issuance and revocation are not self-service: paid keys are issued on
// purchase (Gumroad / Razorpay webhooks) and rotation or revocation by
// support. The console says so instead of offering buttons that would 404.
// free_key_endpoint is DEPRECATED (2026-09-28, null): the Free tier is keyless
// per commercial-contract.json and /api/keys/free answers 410. The field is
// kept so existing console clients read "no endpoint" rather than break.
export const KEY_MANAGEMENT = Object.freeze({
  self_service_create: false,
  self_service_revoke: false,
  free_key_endpoint: null,
  free_tier_keyless: true,
  support_contact: "mailto:support@cyberdudebivash.com",
});

export function maskCredential(raw, isJwt) {
  if (isJwt) return "session token (JWT)";
  const s = String(raw || "");
  if (s.length < 12) return "****";
  return `${s.slice(0, 8)}\u2026${s.slice(-4)}`;
}

export function buildAccountUsage(auth, quota, today) {
  const tier = auth && auth.tier ? auth.tier : "FREE";
  const q = quota || {};
  const t = today || null;
  return {
    tier,
    account: {
      customer_id: auth && auth.sub ? String(auth.sub) : null,
      credential: maskCredential(auth && auth.key, !!(auth && auth.jwt)),
      credential_type: auth && auth.jwt ? "jwt" : "api_key",
      subscription_status: (auth && auth.subscription_status) || null,
      expires_at: (auth && auth.expires_at) || (auth && auth.entitlement_expires_at) || null,
    },
    // The limit the gateway enforces: per UTC day, per credential.
    daily_quota: {
      available: q.available === true,
      limit: typeof q.limit === "number" ? q.limit : null,
      used: typeof q.used === "number" ? q.used : null,
      remaining: typeof q.remaining === "number" ? q.remaining : null,
      used_pct: typeof q.used === "number" && q.limit > 0 ? Math.min(100, Math.round((q.used / q.limit) * 1000) / 10) : null,
      exhausted: q.exhausted === true,
      date_utc: q.date_utc || null,
      reset_utc: q.reset_utc || null,
    },
    // usage-meter.js counters for today (null when none recorded yet).
    today: t ? {
      requests: typeof t.requests_count === "number" ? t.requests_count : 0,
      credits_consumed: typeof t.credits_consumed === "number" ? t.credits_consumed : 0,
      peak_hour: t.peak_hour ?? null,
      peak_count: typeof t.peak_count === "number" ? t.peak_count : 0,
      endpoint_usage: t.endpoint_usage && typeof t.endpoint_usage === "object" ? t.endpoint_usage : {},
    } : null,
    key_management: KEY_MANAGEMENT,
  };
}
