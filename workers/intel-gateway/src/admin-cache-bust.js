// =============================================================================
// CYBERDUDEBIVASH(R) SENTINEL APEX -- Admin Cache-Bust (pure module)
//
// P0 fix history: scripts/bust_kv_cache.py (pipeline STAGE 3.7) has been
// POSTing to /api/admin/cache/bust[-prefix] with an "X-Admin-Secret" header
// carrying WORKER_ADMIN_SECRET since it was written. handleAdmin() (index.js)
// never had a route for these paths -- every call fell through to the
// ADMIN_SECRET/X-Admin-Key check (a different header, a different secret),
// so every cache-bust request 403'd regardless of WORKER_ADMIN_SECRET's
// value. Three consecutive secret rotations reproduced the identical
// failure because the secret was never the problem.
//
// Extracted into its own dependency-free file, same pattern as
// subscription-lifecycle.js/daily-quota.js, so it is unit-testable under
// plain `node --test` without pulling in index.js's full import chain
// (pricing.js -> pricing-data.json fails Node's native ESM loader outside
// the wrangler/esbuild bundler). Unlike those two, this module takes its
// few index.js collaborators (timingSafeEqual/auditLog/jsonResp) as
// parameters rather than owning its own copies or re-exporting index.js's
// -- those three are each used 4/28/230 times respectively elsewhere in
// index.js, so moving their canonical definitions would be a much larger
// blast radius than this fix needs; dependency injection gets the same
// testability with zero risk to any of those other call sites.
//
// index.js's handleAdmin() calls this unchanged for its two cache-bust
// paths -- this is a pure move of that branch's logic, not a rewrite.
// =============================================================================

// Canonical cache-key namespace this endpoint is scoped to, mirroring
// scripts/bust_kv_cache.py's CACHE_KEYS. SECURITY_HUB_KV also holds
// unrelated data (audit:* from auditLog(), fingerprint:* etc.) -- without
// this allowlist, an authenticated cache-bust call could be used to erase
// that data instead of just cache entries.
export const ALLOWED_EXACT_KEYS = new Set([
  "idx:reports", "idx:preview", "ai:index", "ai:analyze", "ai:respond", "ai:correlate",
]);
export const ALLOWED_PREFIXES = new Set([
  "darkweb:scan", "darkweb:status", "reports:premium", "reports:list", "checkout",
]);

/**
 * Handles POST /api/admin/cache/bust and /api/admin/cache/bust-prefix.
 * Caller (index.js) must have already confirmed `path` is one of those two
 * before invoking this -- it does not re-check the path itself.
 *
 * @param {Request} request
 * @param {{WORKER_ADMIN_SECRET?: string, SECURITY_HUB_KV: {delete: Function, list: Function}}} env
 * @param {{waitUntil: Function}} ctx
 * @param {string} path - "/api/admin/cache/bust" or "/api/admin/cache/bust-prefix"
 * @param {string} method
 * @param {{timingSafeEqual: Function, auditLog: Function, jsonResp: Function}} deps
 * @returns {Promise<Response>}
 */
export async function handleAdminCacheBust(request, env, ctx, path, method, { timingSafeEqual, auditLog, jsonResp }) {
  const cacheSecret = request.headers.get("X-Admin-Secret") || "";
  if (!env.WORKER_ADMIN_SECRET || !timingSafeEqual(cacheSecret, env.WORKER_ADMIN_SECRET)) {
    auditLog(ctx, env, { action: "admin_auth_failed", path, method });
    return jsonResp({ error: "Forbidden: invalid admin credentials" }, 403);
  }
  if (method !== "POST") {
    return jsonResp({ error: "Method not allowed", allowed: ["POST"] }, 405);
  }

  const qs = new URL(request.url).searchParams;
  try {
    if (path === "/api/admin/cache/bust") {
      const key = qs.get("key") || "";
      if (!key) return jsonResp({ error: "Missing 'key' query parameter" }, 400);
      if (!ALLOWED_EXACT_KEYS.has(key)) {
        return jsonResp({ error: "Unknown cache key", allowed: [...ALLOWED_EXACT_KEYS] }, 400);
      }
      await env.SECURITY_HUB_KV.delete(key);
      return jsonResp({ busted: key }, 200);
    }
    const prefix = qs.get("prefix") || "";
    if (!prefix) return jsonResp({ error: "Missing 'prefix' query parameter" }, 400);
    if (!ALLOWED_PREFIXES.has(prefix)) {
      return jsonResp({ error: "Unknown cache prefix", allowed: [...ALLOWED_PREFIXES] }, 400);
    }
    // KV list() returns at most 1,000 keys per call; loop on the cursor
    // until list_complete so a prefix with more entries than that is fully
    // busted, not silently left partially stale.
    let cursor;
    let deleted = 0;
    for (;;) {
      const listed = await env.SECURITY_HUB_KV.list({ prefix, cursor });
      await Promise.all(listed.keys.map((k) => env.SECURITY_HUB_KV.delete(k.name)));
      deleted += listed.keys.length;
      if (listed.list_complete) break;
      cursor = listed.cursor;
    }
    return jsonResp({ busted_prefix: prefix, count: deleted }, 200);
  } catch (e) {
    // Never return KV/provider exception text to the caller -- log
    // server-side only (visible via wrangler tail / Logpush).
    console.error(`[handleAdminCacheBust] KV operation failed: ${e && e.message ? e.message : e}`);
    return jsonResp({ error: "Cache bust failed" }, 500);
  }
}
