import assert from "node:assert/strict";
import { test } from "node:test";
import { handleAdmin } from "../index.js";

// ---------------------------------------------------------------------------
// P0 regression suite -- CYBERDUDEBIVASH SENTINEL APEX
//
// scripts/bust_kv_cache.py (pipeline STAGE 3.7) has been POSTing to
// /api/admin/cache/bust[-prefix] with an "X-Admin-Secret" header carrying
// WORKER_ADMIN_SECRET since it was written. handleAdmin() never had a route
// for these paths -- every call fell through to the ADMIN_SECRET/X-Admin-Key
// check below (a different header, a different secret), so every single
// cache-bust request 403'd regardless of WORKER_ADMIN_SECRET's value. Three
// consecutive secret rotations reproduced the identical failure because the
// secret was never the problem. These tests lock in the new routes so this
// cannot silently regress back to always-403 (or, worse, an accidentally
// open cache-bust endpoint).
// ---------------------------------------------------------------------------

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

test("cache/bust: 403 with missing X-Admin-Secret header", async () => {
  const env = { WORKER_ADMIN_SECRET: SECRET, SECURITY_HUB_KV: fakeKV({ "idx:reports": "{}" }) };
  const req = new Request("https://intel.example.com/api/admin/cache/bust?key=idx:reports", { method: "POST" });
  const res = await handleAdmin(req, env, fakeCtx(), "/api/admin/cache/bust", "POST");
  assert.equal(res.status, 403);
  assert.equal(env.SECURITY_HUB_KV.store.has("idx:reports"), true, "must not delete anything on failed auth");
});

test("cache/bust: 403 with wrong X-Admin-Secret value", async () => {
  const env = { WORKER_ADMIN_SECRET: SECRET, SECURITY_HUB_KV: fakeKV({ "idx:reports": "{}" }) };
  const req = new Request("https://intel.example.com/api/admin/cache/bust?key=idx:reports", {
    method: "POST",
    headers: { "X-Admin-Secret": "wrong-value" },
  });
  const res = await handleAdmin(req, env, fakeCtx(), "/api/admin/cache/bust", "POST");
  assert.equal(res.status, 403);
});

test("cache/bust: 403 when WORKER_ADMIN_SECRET is unset (fail closed, never open)", async () => {
  const env = { SECURITY_HUB_KV: fakeKV({ "idx:reports": "{}" }) };
  const req = new Request("https://intel.example.com/api/admin/cache/bust?key=idx:reports", {
    method: "POST",
    headers: { "X-Admin-Secret": "" },
  });
  const res = await handleAdmin(req, env, fakeCtx(), "/api/admin/cache/bust", "POST");
  assert.equal(res.status, 403);
});

test("cache/bust: 200 and deletes the exact key with correct secret", async () => {
  const env = { WORKER_ADMIN_SECRET: SECRET, SECURITY_HUB_KV: fakeKV({ "idx:reports": "{}", other: "x" }) };
  const req = new Request("https://intel.example.com/api/admin/cache/bust?key=idx:reports", {
    method: "POST",
    headers: { "X-Admin-Secret": SECRET },
  });
  const res = await handleAdmin(req, env, fakeCtx(), "/api/admin/cache/bust", "POST");
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
  const res = await handleAdmin(req, env, fakeCtx(), "/api/admin/cache/bust", "POST");
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
  const res = await handleAdmin(req, env, fakeCtx(), "/api/admin/cache/bust", "POST");
  assert.equal(res.status, 400);
  assert.equal(env.SECURITY_HUB_KV.store.has("audit:123:abc"), true);
});

test("cache/bust: deleting a never-written but canonical key is a harmless no-op (200)", async () => {
  const env = { WORKER_ADMIN_SECRET: SECRET, SECURITY_HUB_KV: fakeKV() };
  const req = new Request("https://intel.example.com/api/admin/cache/bust?key=ai:index", {
    method: "POST",
    headers: { "X-Admin-Secret": SECRET },
  });
  const res = await handleAdmin(req, env, fakeCtx(), "/api/admin/cache/bust", "POST");
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
  const res = await handleAdmin(req, env, fakeCtx(), "/api/admin/cache/bust-prefix", "POST");
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
  const res = await handleAdmin(req, env, fakeCtx(), "/api/admin/cache/bust-prefix", "POST");
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
  const res = await handleAdmin(req, env, fakeCtx(), "/api/admin/cache/bust-prefix", "POST");
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
  const res = await handleAdmin(req, env, fakeCtx(), "/api/admin/cache/bust-prefix", "POST");
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
  const res = await handleAdmin(req, env, fakeCtx(), "/api/admin/cache/bust", "GET");
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
  const res = await handleAdmin(req, env, fakeCtx(), "/api/admin/cache/bust", "POST");
  assert.equal(res.status, 500);
  const body = await res.json();
  assert.equal(body.error, "Cache bust failed");
  const raw = JSON.stringify(body);
  assert.ok(!raw.includes("quota exceeded"), "response must not include the underlying exception text");
  assert.ok(!raw.includes("ca786702"), "response must not include internal binding/namespace ids");
});

test("cache/bust routes do not affect the pre-existing ADMIN_SECRET-gated routes", async () => {
  // The new cache/bust branch only matches its own two exact paths, so
  // /api/admin/health falls through to the original, untouched X-Admin-Key/
  // ADMIN_SECRET check exactly as before. Verifying that boundary is intact
  // (still 403s on a wrong key) rather than the full health-check success
  // path, which needs unrelated KV/R2 bindings this test isn't about.
  const env = { ADMIN_SECRET: "admin-secret-value", SECURITY_HUB_KV: fakeKV() };
  const req = new Request("https://intel.example.com/api/admin/health", {
    method: "GET",
    headers: { "X-Admin-Key": "wrong-value" },
  });
  const res = await handleAdmin(req, env, fakeCtx(), "/api/admin/health", "GET");
  assert.equal(res.status, 403);
});
