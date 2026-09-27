import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { buildAccountUsage, maskCredential, KEY_MANAGEMENT } from "../account-usage.js";

// ---------------------------------------------------------------------------
// GET /api/account/usage (2026-09-26): the customer API console called it,
// but it did not exist (404). account-usage.js shapes the output of two
// existing engines (the enforced daily quota and usage-meter.js counters);
// these tests pin that shape and that the credential is never echoed.
// ---------------------------------------------------------------------------

const KEY = "cdb_live_9f8e7d6c5b4a3210fedcba";
const quota = { available: true, limit: 5000, used: 1250, remaining: 3750, exhausted: false,
                date_utc: "2026-09-26", reset_utc: "2026-09-27T00:00:00.000Z" };
const today = { requests_count: 1250, credits_consumed: 1400, peak_hour: 14, peak_count: 300,
                endpoint_usage: { feed: 900, search: 350 } };

test("API-key caller: tier, masked key, enforced daily quota, today's usage", () => {
  const r = buildAccountUsage({ tier: "PRO", key: KEY, sub: "cust_42", kv: true,
                                subscription_status: "active", expires_at: "2027-01-01T00:00:00Z" }, quota, today);
  assert.equal(r.tier, "PRO");
  assert.equal(r.account.customer_id, "cust_42");
  // \u2026 escape, not a literal ellipsis: deploy-worker.yml runs
  // sanitize_encoding.py --fix before this suite, which rewrites non-ASCII in
  // Worker JS (U+2026 -> "...") and would make this expectation disagree with
  // account-usage.js, which emits U+2026 through the same escape.
  assert.equal(r.account.credential, `${KEY.slice(0, 8)}\u2026${KEY.slice(-4)}`);
  assert.equal(r.account.credential_type, "api_key");
  assert.equal(r.account.subscription_status, "active");
  assert.deepEqual(r.daily_quota, { ...quota, used_pct: 25 });
  assert.equal(r.today.requests, 1250);
  assert.deepEqual(r.today.endpoint_usage, { feed: 900, search: 350 });
});

test("the raw credential never appears anywhere in the response", () => {
  const r = buildAccountUsage({ tier: "PRO", key: KEY, sub: "c" }, quota, today);
  assert.ok(!JSON.stringify(r).includes(KEY));
  // Synthetic, unsigned token assembled at runtime (no token-shaped literal in source).
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
  const jwt = [b64({ alg: "none" }), b64({ sub: "test" }), "x".repeat(24)].join(".");
  const j = buildAccountUsage({ tier: "ENTERPRISE", key: jwt, sub: "c", jwt: true }, quota, today);
  assert.ok(!JSON.stringify(j).includes(jwt.slice(10)));
  assert.equal(j.account.credential_type, "jwt");
});

test("maskCredential: short or missing values reveal nothing", () => {
  assert.equal(maskCredential("abc", false), "****");
  assert.equal(maskCredential(null, false), "****");
  assert.equal(maskCredential("x".repeat(40), true), "session token (JWT)");
});

test("quota unavailable (KV down) -> no invented numbers", () => {
  const r = buildAccountUsage({ tier: "FREE", key: KEY, sub: "c" },
                              { available: false, limit: 50, used: null, remaining: null }, null);
  assert.equal(r.daily_quota.available, false);
  assert.equal(r.daily_quota.used, null);
  assert.equal(r.daily_quota.used_pct, null);
  assert.equal(r.today, null);
});

test("key management is declared not self-service (no buttons that 404)", () => {
  const r = buildAccountUsage({ tier: "PRO", key: KEY, sub: "c" }, quota, today);
  assert.equal(r.key_management.self_service_create, false);
  assert.equal(r.key_management.self_service_revoke, false);
  assert.equal(r.key_management.free_key_endpoint, "/api/keys/free");
  assert.ok(Object.isFrozen(KEY_MANAGEMENT));
});

test("index.js wires the route: GET only, auth required, no-store, existing engines", () => {
  const src = readFileSync(new URL("../index.js", import.meta.url), "utf8");
  const i = src.indexOf('if (path === "/api/account/usage")');
  assert.ok(i > 0, "route missing");
  const block = src.slice(i, i + 1200);
  assert.match(block, /method !== "GET"/);
  assert.match(block, /if \(!auth\.key\)/);
  assert.match(block, /readSwarmQuotaSnapshot\(env, auth\.key, auth\.tier\)/);
  assert.match(block, /getUsageSummary\(env, auth\.sub, utcDateString\(\)\)/);
  assert.match(block, /no-store/);
  const free = src.indexOf('path === "/api/keys/free"');
  assert.ok(free > 0, "the free-key route the console points to must exist");
});
