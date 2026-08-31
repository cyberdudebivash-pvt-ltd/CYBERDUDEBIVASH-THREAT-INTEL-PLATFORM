import assert from "node:assert/strict";
import { test } from "node:test";
import { DAILY_QUOTA, checkDailyQuota, hashClientIp, utcDayString, nextUtcMidnight, buildQuotaExceededBody } from "../daily-quota.js";

// ---------------------------------------------------------------------------
// Unit coverage for the 24h daily-quota layer (additive to the existing
// per-minute checkRateLimit()/RATE_LIMITS in index.js). Imported directly
// from daily-quota.js (not index.js), same reason as
// subscription-lifecycle.test.js: index.js transitively imports
// pricing.js -> pricing-data.json, which Node's native ESM loader rejects
// outside the wrangler/esbuild bundler.
//
// FakeKV below is a minimal in-memory stand-in for the real RATE_LIMIT_KV
// binding (get/put only, matching exactly what checkDailyQuota() calls) --
// no miniflare/wrangler dev required.
// ---------------------------------------------------------------------------

class FakeKV {
  constructor() { this.store = new Map(); }
  async get(key) { return this.store.has(key) ? this.store.get(key) : null; }
  async put(key, value) { this.store.set(key, value); }
}

test("an unauthenticated (FREE-tier) caller is allowed under the 50/day cap", async () => {
  const env = { RATE_LIMIT_KV: new FakeKV() };
  const result = await checkDailyQuota(env, { tier: "FREE", key: null }, "8.8.8.8");
  assert.equal(result.allowed, true);
  assert.equal(result.limit, DAILY_QUOTA.FREE);
  assert.equal(result.remaining, DAILY_QUOTA.FREE - 1);
});

test("the 51st call from the same anonymous IP in the same UTC day trips the FREE cap", async () => {
  const env = { RATE_LIMIT_KV: new FakeKV() };
  const auth = { tier: "FREE", key: null };
  let last;
  for (let i = 0; i < DAILY_QUOTA.FREE; i++) {
    last = await checkDailyQuota(env, auth, "203.0.113.7");
    assert.equal(last.allowed, true, `call ${i + 1} should be allowed`);
  }
  const blocked = await checkDailyQuota(env, auth, "203.0.113.7");
  assert.equal(blocked.allowed, false);
  assert.equal(blocked.remaining, 0);
  assert.equal(blocked.limit, 50);
});

test("two different anonymous IPs get independent counters (hashed, not shared)", async () => {
  const env = { RATE_LIMIT_KV: new FakeKV() };
  const auth = { tier: "FREE", key: null };
  for (let i = 0; i < DAILY_QUOTA.FREE; i++) {
    await checkDailyQuota(env, auth, "198.51.100.1");
  }
  const otherIpStillFresh = await checkDailyQuota(env, auth, "198.51.100.2");
  assert.equal(otherIpStillFresh.allowed, true, "a different IP must not inherit another IP's exhausted quota");
});

test("an API key identity is metered independently of its caller's IP", async () => {
  const env = { RATE_LIMIT_KV: new FakeKV() };
  const auth = { tier: "PRO", key: "cdb_pro_testkey" };
  const r1 = await checkDailyQuota(env, auth, "10.0.0.1");
  const r2 = await checkDailyQuota(env, auth, "10.0.0.2"); // same key, different IP
  assert.equal(r1.limit, DAILY_QUOTA.PRO);
  assert.equal(r2.remaining, DAILY_QUOTA.PRO - 2, "same API key from two IPs must share one counter");
});

test("PRO and ENTERPRISE tiers use the right quota matrix values", async () => {
  const env = { RATE_LIMIT_KV: new FakeKV() };
  const pro = await checkDailyQuota(env, { tier: "PRO", key: "k1" }, "1.1.1.1");
  const ent = await checkDailyQuota(env, { tier: "ENTERPRISE", key: "k2" }, "1.1.1.1");
  assert.equal(pro.limit, 5000);
  assert.equal(ent.limit, 50000);
});

test("RATE_LIMIT_KV.get() throwing fails open (never blocks a real customer on our own outage)", async () => {
  const env = { RATE_LIMIT_KV: { get: async () => { throw new Error("kv down"); }, put: async () => {} } };
  const result = await checkDailyQuota(env, { tier: "FREE", key: null }, "8.8.4.4");
  assert.equal(result.allowed, true);
});

test("hashClientIp never returns the raw IP and is stable for the same input", async () => {
  const h1 = await hashClientIp("8.8.8.8");
  const h2 = await hashClientIp("8.8.8.8");
  const h3 = await hashClientIp("1.1.1.1");
  assert.equal(h1, h2);
  assert.notEqual(h1, h3);
  assert.equal(h1.includes("8.8.8.8"), false);
});

test("utcDayString/nextUtcMidnight agree on the UTC calendar day", () => {
  const at = new Date("2026-08-31T23:59:59.000Z");
  assert.equal(utcDayString(at), "2026-08-31");
  assert.equal(nextUtcMidnight(at), Date.parse("2026-09-01T00:00:00.000Z") / 1000);
});

// ---------------------------------------------------------------------------
// buildQuotaExceededBody() -- the exact JSON schema returned on a real 429,
// matching the task brief's required shape (error/status/tier/message/
// upgrade_url/direct_checkout with pro_usd+pro_inr direct checkout links).
// ---------------------------------------------------------------------------

test("FREE-tier 429 body matches the required schema exactly, with pro_usd/pro_inr direct checkout", () => {
  const body = buildQuotaExceededBody({ tier: "FREE", limit: 50, reset: 1735689600 });
  assert.equal(body.error, "RATE_LIMIT_EXCEEDED");
  assert.equal(body.status, 429);
  assert.equal(body.tier, "FREE");
  assert.match(body.message, /Daily request quota reached \(50\/50\)/);
  assert.match(body.message, /Sentinel Pro/);
  assert.match(body.message, /5,000 requests\/day/);
  assert.equal(body.upgrade_url, "https://intel.cyberdudebivash.com/pricing.html?ref=api_429");
  assert.deepEqual(body.direct_checkout, {
    pro_usd: "https://intel.cyberdudebivash.com/api/billing/checkout?tier=pro&currency=usd",
    pro_inr: "https://intel.cyberdudebivash.com/api/billing/checkout?tier=pro&currency=inr",
  });
});

test("PRO-tier 429 body upsells to ENTERPRISE, not PRO-to-PRO", () => {
  const body = buildQuotaExceededBody({ tier: "PRO", limit: 5000, reset: 1735689600 });
  assert.match(body.message, /Sentinel Enterprise/);
  assert.deepEqual(Object.keys(body.direct_checkout), ["enterprise_usd", "enterprise_inr"]);
});

test("ENTERPRISE-tier 429 body has no higher tier to upsell to -- points to sales instead", () => {
  const body = buildQuotaExceededBody({ tier: "ENTERPRISE", limit: 50000, reset: 1735689600 });
  assert.match(body.message, /enterprise@cyberdudebivash\.com/);
  assert.equal(body.direct_checkout, undefined);
});
