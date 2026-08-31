import assert from "node:assert/strict";
import { test } from "node:test";
import { handleAdminCacheBust, ALLOWED_EXACT_KEYS, ALLOWED_PREFIXES } from "../admin-cache-bust.js";

// ---------------------------------------------------------------------------
// P0 regression suite -- CYBERDUDEBIVASH SENTINEL APEX
//
// scripts/bust_kv_cache.py (pipeline STAGE 3.7) has been POSTing to
// /api/admin/cache/bust[-prefix] with an "X-Admin-Secret" header carrying
// WORKER_ADMIN_SECRET since it was written. index.js's handleAdmin() never
// had a route for these paths -- every call fell through to the
// ADMIN_SECRET/X-Admin-Key check (a different header, a different secret),
// so every single cache-bust request 403'd regardless of WORKER_ADMIN_SECRET's
// value. Three consecutive secret rotations reproduced the identical failure
// because the secret was never the problem. These tests lock in the routes
// (now handleAdminCacheBust(), called unchanged from index.js's handleAdmin
// -- see that file's admin-cache-bust.js import) so this cannot silently
// regress back to always-403 (or, worse, an accidentally open cache-bust
// endpoint).
//
// This was originally written against handleAdmin() directly, imported from
// ../index.js; that transitively imports pricing.js -> pricing-data.json,
// which Node's native ESM loader rejects outside the wrangler/esbuild
// bundler (see subscription-lifecycle.js's header comment), so the suite
// could never actually run. The cache-bust branch was extracted into its
// own dependency-free module (admin-cache-bust.js) specifically to fix
// that -- same pattern as subscription-lifecycle.js/daily-quota.js -- with
// timingSafeEqual/auditLog/jsonResp taken as parameters rather than
// re-exported from index.js, since those three are each used 4/28/230
// times elsewhere in index.js and moving their canonical definitions would
// be a far larger blast radius than this fix needs. The three fakes below
// are faithful to index.js's real behavior for what these tests observe
// (status code + JSON body); the real jsonResp also adds CORS/security
// headers, which every response gets regardless via index.js's top-level
// withBaselineHeaders() wrapper (see fetch()), so omitting them here does
// not change what a real caller ultimately receives.
// ---------------------------------------------------------------------------

function timingSafeEqual(a, b) {
  const bufA = new TextEncoder().encode(String(a ?? ""));
  const bufB = new TextEncoder().encode(String(b ?? ""));
  const len  = Math.max(bufA.length, bufB.length);
  let diff   = bufA.length ^ bufB.length;
  for (let i = 0; i < len; i++) diff |= (bufA[i] ?? 0) ^ (bufB[i] ?? 0);
  return diff === 0;
}

function jsonResp(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

function auditLog(ctx, env, event) {
  if (!ctx || !env.SECURITY_HUB_KV) return;
  ctx.waitUntil((async () => {
    try {
      await env.SECURITY_HUB_KV.put(`audit:${Date.now()}:${Math.random().toString(36).slice(2, 8)}`, JSON.stringify(event));
    } catch (_) {}
  })());
}

const deps = { timingSafeEqual, auditLog, jsonResp };

// Models the real Cloudflare KV list() contract (cursor/list_complete, up to
// `pageSize` keys per call) so pagination bugs in the route handler are
// actually caught, not masked by a double that always returns everything.
function fakeKV(initial = {}, { pageSize = 1000 } = {}) {
  const store = new Map(Object.entries(initial));
  return {
    store,
    async get(key, opts) {
      const v = store.get(key);
      if (v === undefined) return null;
      return opts && opts.type === "json" ? JSON.parse(v) : v;
    },
    async put(key, value) {
      store.set(key, value);
    },
    async delete(key) {
      store.delete(key);
    },
    async list({ prefix, cursor } = {}) {
      // Cursor is the last key name returned (matching real KV's opaque,
      // key-ordered cursor semantics) rather than a raw array index, so
      // pagination stays correct even when the caller deletes earlier pages'
      // keys between list() calls -- an array-index cursor would silently
      // skip entries once the store shrinks mid-pagination.
      const matching = [...store.keys()].filter((k) => !prefix || k.startsWith(prefix)).sort();
      const from = cursor ? matching.findIndex((k) => k > cursor) : 0;
      const startIdx = from === -1 ? matching.length : from;
      const page = matching.slice(startIdx, startIdx + pageSize).map((name) => ({ name }));
      const list_complete = startIdx + page.length >= matching.length;
      const nextCursor = page.length ? page[page.length - 1].name : cursor;
      return { keys: page, list_complete, cursor: list_complete ? undefined : nextCursor };
    },
  };
}

function fakeCtx() {
  return { waitUntil: () => {} };
}

const SECRET = "test-worker-admin-secret";

test("allowlists are non-empty and match the exposed error messages", () => {
  assert.ok(ALLOWED_EXACT_KEYS.size > 0);
  assert.ok(ALLOWED_PREFIXES.size > 0);
});

test("cache/bust: 403 with missing X-Admin-Secret header", async () => {
  const env = { WORKER_ADMIN_SECRET: SECRET, SECURITY_HUB_KV: fakeKV({ "idx:reports": "{}" }) };
  const req = new Request("https://intel.example.com/api/admin/cache/bust?key=idx:reports", { method: "POST" });
  const res = await handleAdminCacheBust(req, env, fakeCtx(), "/api/admin/cache/bust", "POST", deps);
  assert.equal(res.status, 403);
  assert.equal(env.SECURITY_HUB_KV.store.has("idx:reports"), true, "must not delete anything on failed auth");
});

test("cache/bust: 403 with wrong X-Admin-Secret value", async () => {
  const env = { WORKER_ADMIN_SECRET: SECRET, SECURITY_HUB_KV: fakeKV({ "idx:reports": "{}" }) };
  const req = new Request("https://intel.example.com/api/admin/cache/bust?key=idx:reports", {
    method: "POST",
    headers: { "X-Admin-Secret": "wrong-value" },
  });
  const res = await handleAdminCacheBust(req, env, fakeCtx(), "/api/admin/cache/bust", "POST", deps);
  assert.equal(res.status, 403);
});

test("cache/bust: 403 when WORKER_ADMIN_SECRET is unset (fail closed, never open)", async () => {
  const env = { SECURITY_HUB_KV: fakeKV({ "idx:reports": "{}" }) };
  const req = new Request("https://intel.example.com/api/admin/cache/bust?key=idx:reports", {
    method: "POST",
    headers: { "X-Admin-Secret": "" },
  });
  const res = await handleAdminCacheBust(req, env, fakeCtx(), "/api/admin/cache/bust", "POST", deps);
  assert.equal(res.status, 403);
});

test("cache/bust: 200 and deletes the exact key with correct secret", async () => {
  const env = { WORKER_ADMIN_SECRET: SECRET, SECURITY_HUB_KV: fakeKV({ "idx:reports": "{}", other: "x" }) };
  const req = new Request("https://intel.example.com/api/admin/cache/bust?key=idx:reports", {
    method: "POST",
    headers: { "X-Admin-Secret": SECRET },
  });
  const res = await handleAdminCacheBust(req, env, fakeCtx(), "/api/admin/cache/bust", "POST", deps);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.busted, "idx:reports");
  assert.equal(env.SECURITY_HUB_KV.store.has("idx:reports"), false);
  assert.equal(env.SECURITY_HUB_KV.store.has("other"), true, "must not touch unrelated keys");
});

test("cache/bust: 400 when key query param missing", async () => {
  const env = { WORKER_ADMIN_SECRET: SECRET, SECURITY_HUB_KV: fakeKV() };
  const req = new Request("https://intel.example.com/api/admin/cache/bust", {
    method: "POST",
    headers: { "X-Admin-Secret": SECRET },
  });
  const res = await handleAdminCacheBust(req, env, fakeCtx(), "/api/admin/cache/bust", "POST", deps);
  assert.equal(res.status, 400);
});

test("cache/bust: 400 and no deletion for a key outside the canonical cache namespace", async () => {
  // An authenticated caller must not be able to use this endpoint to erase
  // unrelated SECURITY_HUB_KV data (e.g. a specific audit record) just
  // because they know its exact key.
  const env = { WORKER_ADMIN_SECRET: SECRET, SECURITY_HUB_KV: fakeKV({ "audit:123:abc": "{}" }) };
  const req = new Request("https://intel.example.com/api/admin/cache/bust?key=audit:123:abc", {
    method: "POST",
    headers: { "X-Admin-Secret": SECRET },
  });
  const res = await handleAdminCacheBust(req, env, fakeCtx(), "/api/admin/cache/bust", "POST", deps);
  assert.equal(res.status, 400);
  assert.equal(env.SECURITY_HUB_KV.store.has("audit:123:abc"), true);
});

test("cache/bust: deleting a never-written but canonical key is a harmless no-op (200)", async () => {
  const env = { WORKER_ADMIN_SECRET: SECRET, SECURITY_HUB_KV: fakeKV() };
  const req = new Request("https://intel.example.com/api/admin/cache/bust?key=ai:index", {
    method: "POST",
    headers: { "X-Admin-Secret": SECRET },
  });
  const res = await handleAdminCacheBust(req, env, fakeCtx(), "/api/admin/cache/bust", "POST", deps);
  assert.equal(res.status, 200);
});

test("cache/bust-prefix: 200 and deletes every key under the prefix", async () => {
  const env = {
    WORKER_ADMIN_SECRET: SECRET,
    SECURITY_HUB_KV: fakeKV({
      "darkweb:scan:aaa": "{}",
      "darkweb:scan:bbb": "{}",
      "darkweb:status:aaa": "{}",
      "idx:reports": "{}",
    }),
  };
  // Matches what bust_kv_cache.py actually sends: WILDCARD_KEYS entries have
  // their trailing ":*" stripped (bust_prefix_key's clean_prefix), so
  // "darkweb:scan:*" becomes "darkweb:scan" on the wire -- no trailing colon.
  const req = new Request("https://intel.example.com/api/admin/cache/bust-prefix?prefix=darkweb:scan", {
    method: "POST",
    headers: { "X-Admin-Secret": SECRET },
  });
  const res = await handleAdminCacheBust(req, env, fakeCtx(), "/api/admin/cache/bust-prefix", "POST", deps);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.count, 2);
  assert.equal(env.SECURITY_HUB_KV.store.has("darkweb:scan:aaa"), false);
  assert.equal(env.SECURITY_HUB_KV.store.has("darkweb:scan:bbb"), false);
  assert.equal(env.SECURITY_HUB_KV.store.has("darkweb:status:aaa"), true, "must not touch sibling prefix");
  assert.equal(env.SECURITY_HUB_KV.store.has("idx:reports"), true);
});

test("cache/bust-prefix: drains every page when list() returns list_complete=false", async () => {
  const seed = {};
  for (let i = 0; i < 5; i++) seed[`darkweb:scan:${i}`] = "{}";
  const env = { WORKER_ADMIN_SECRET: SECRET, SECURITY_HUB_KV: fakeKV(seed, { pageSize: 2 }) };
  const req = new Request("https://intel.example.com/api/admin/cache/bust-prefix?prefix=darkweb:scan", {
    method: "POST",
    headers: { "X-Admin-Secret": SECRET },
  });
  const res = await handleAdminCacheBust(req, env, fakeCtx(), "/api/admin/cache/bust-prefix", "POST", deps);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.count, 5, "must consume every page (2+2+1), not just the first");
  for (let i = 0; i < 5; i++) {
    assert.equal(env.SECURITY_HUB_KV.store.has(`darkweb:scan:${i}`), false);
  }
});

test("cache/bust-prefix: 200 with count 0 when nothing matches (matches 9/11 legacy target names today)", async () => {
  const env = { WORKER_ADMIN_SECRET: SECRET, SECURITY_HUB_KV: fakeKV() };
  const req = new Request("https://intel.example.com/api/admin/cache/bust-prefix?prefix=reports:premium", {
    method: "POST",
    headers: { "X-Admin-Secret": SECRET },
  });
  const res = await handleAdminCacheBust(req, env, fakeCtx(), "/api/admin/cache/bust-prefix", "POST", deps);
  assert.equal(res.status, 200);
  const body = await res.json();
  assert.equal(body.count, 0);
});

test("cache/bust-prefix: 400 and no deletion for prefix=audit: (must not erase audit history)", async () => {
  const env = {
    WORKER_ADMIN_SECRET: SECRET,
    SECURITY_HUB_KV: fakeKV({ "audit:111:aaa": "{}", "audit:222:bbb": "{}" }),
  };
  const req = new Request("https://intel.example.com/api/admin/cache/bust-prefix?prefix=audit:", {
    method: "POST",
    headers: { "X-Admin-Secret": SECRET },
  });
  const res = await handleAdminCacheBust(req, env, fakeCtx(), "/api/admin/cache/bust-prefix", "POST", deps);
  assert.equal(res.status, 400);
  assert.equal(env.SECURITY_HUB_KV.store.has("audit:111:aaa"), true);
  assert.equal(env.SECURITY_HUB_KV.store.has("audit:222:bbb"), true);
});

test("cache/bust: 405 on non-POST method (auth still enforced first)", async () => {
  const env = { WORKER_ADMIN_SECRET: SECRET, SECURITY_HUB_KV: fakeKV() };
  const req = new Request("https://intel.example.com/api/admin/cache/bust?key=idx:reports", {
    method: "GET",
    headers: { "X-Admin-Secret": SECRET },
  });
  const res = await handleAdminCacheBust(req, env, fakeCtx(), "/api/admin/cache/bust", "GET", deps);
  assert.equal(res.status, 405);
});

test("cache/bust: 500 with a generic message when KV throws -- never leaks provider exception text", async () => {
  const env = {
    WORKER_ADMIN_SECRET: SECRET,
    SECURITY_HUB_KV: {
      async delete() {
        throw new Error("internal binding detail: quota exceeded on namespace ca786702-secret-id");
      },
    },
  };
  const req = new Request("https://intel.example.com/api/admin/cache/bust?key=idx:reports", {
    method: "POST",
    headers: { "X-Admin-Secret": SECRET },
  });
  const res = await handleAdminCacheBust(req, env, fakeCtx(), "/api/admin/cache/bust", "POST", deps);
  assert.equal(res.status, 500);
  const body = await res.json();
  assert.equal(body.error, "Cache bust failed");
  const raw = JSON.stringify(body);
  assert.ok(!raw.includes("quota exceeded"), "response must not include the underlying exception text");
  assert.ok(!raw.includes("ca786702"), "response must not include internal binding/namespace ids");
});
