/**
 * Operator control-plane metering, through the REAL gateway router
 * (watchdog-harness.js drives index.js's default export).
 *
 * Defect (2026-09-30, commercial certification runs 36685097733,
 * 36688506829, 36690549981: "MSSP rotation preserves membership: FAIL
 * (rotation returned no key)"): /api/admin/*, /api/sla/ping,
 * /api/alerts/dispatch, /api/watchdog/ops and /api/ai-feed/ingest are
 * dispatched AFTER the commercial rate/daily gate. They carry an operator
 * secret, not a customer credential, so they resolved to the anonymous FREE
 * tier: 30/min against the per-IP minute bucket that every tier's traffic
 * from that IP shares (rl:{ip}:{minute}), and 50/day against the IP's FREE
 * daily quota. A key rotation, revocation or refund issued from an IP that
 * also carried customer traffic could be refused with 429.
 *
 * Contract after the fix: a request presenting the VALID operator secret
 * for its route is not metered against the anonymous commercial budget.
 * Anything else on those routes (missing or wrong secret) is metered exactly
 * as before, and handleAdmin's own brute-force lockout is unchanged.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { harness, MSSP_KEY, PRO_KEY } from "./watchdog-harness.js";
import { dailyQuotaKey, utcDateString } from "../daily-quota.js";

const ADMIN = "admin-test-secret";
const WORKER_ADMIN = "worker-admin-test-secret";

function h() {
  const hx = harness();
  hx.env.WORKER_ADMIN_SECRET = WORKER_ADMIN;
  return hx;
}

// Saturate the shared per-IP minute bucket for this minute AND the next one,
// so a minute rollover mid-test cannot turn a negative control green.
function saturateMinuteBucket(hx, ip, count = 45) {
  const minute = Math.floor(Date.now() / 60000);
  for (const m of [minute, minute + 1]) hx.env.RATE_LIMIT_KV.map.set(`rl:${ip}:${m}`, String(count));
}

function exhaustFreeDailyQuota(hx, ip) {
  hx.env.RATE_LIMIT_KV.map.set(dailyQuotaKey(ip, utcDateString()), "50");
}

const at = (ip, extra = {}) => ({ "cf-connecting-ip": ip, ...extra });

// Pin the clock mid-window so no test straddles a minute boundary (the
// counter assertions below read the current window's bucket).
function freezeClock() {
  const real = Date.now;
  const t = Math.floor(real() / 60000) * 60000 + 30000;
  Date.now = () => t;
  return () => { Date.now = real; };
}

test("reproduction: customer traffic from one IP must not block the operator's key rotation", async (t) => {
  t.after(freezeClock());
  const hx = h();
  const ip = "203.0.113.10";
  // An MSSP customer's normal traffic: 31 authenticated requests this minute
  // from the same egress IP the operator works from (the certification
  // canary's exact shape: ~50 MSSP/PRO requests, then an admin rotation).
  for (let i = 0; i < 31; i += 1) {
    const r = await hx.call("GET", "/api/mssp/tenants", { key: MSSP_KEY, headers: at(ip) });
    assert.notEqual(r.status, 429, `customer request ${i + 1} must stay inside the MSSP 1200/min limit`);
  }
  const rot = await hx.call("POST", `/api/admin/keys/${MSSP_KEY}/rotate`, { admin: ADMIN, headers: at(ip) });
  assert.equal(rot.status, 201, "operator rotation was metered as anonymous FREE traffic: " + JSON.stringify(rot.body));
  assert.match(rot.body.new_key, /^cdb_mssp_[0-9a-f]{40}$/);
  assert.equal(hx.env.API_KEYS_KV.map.has(MSSP_KEY), false, "old key revoked");
});

test("valid ADMIN_SECRET on /api/admin/* is not metered: saturated minute bucket and exhausted FREE daily quota", async (t) => {
  t.after(freezeClock());
  const hx = h();
  const ip = "203.0.113.11";
  saturateMinuteBucket(hx, ip);
  exhaustFreeDailyQuota(hx, ip);
  const before = hx.env.RATE_LIMIT_KV.map.get(`rl:${ip}:${Math.floor(Date.now() / 60000)}`);

  const status = await hx.call("PATCH", `/api/admin/keys/${PRO_KEY}/status`, {
    admin: ADMIN, headers: at(ip), body: { subscription_status: "suspended", reason: "refund" },
  });
  assert.equal(status.status, 200, JSON.stringify(status.body));
  assert.equal(status.body.subscription_status, "suspended");

  // Authorization: Bearer <ADMIN_SECRET> is the other form handleAdmin accepts.
  const created = await hx.call("POST", "/api/admin/keys", {
    headers: at(ip, { Authorization: "Bearer " + ADMIN }), body: { customer_id: "cust_op_plane", tier: "PRO" },
  });
  assert.equal(created.status, 201, JSON.stringify(created.body));

  // Operator calls neither spend nor reset the IP's anonymous budget.
  const after = hx.env.RATE_LIMIT_KV.map.get(`rl:${ip}:${Math.floor(Date.now() / 60000)}`);
  assert.equal(before, "45");
  assert.equal(after, "45", "operator traffic bumped the anonymous minute bucket");
});

test("negative controls: missing or wrong operator secret is still metered as anonymous FREE traffic", async (t) => {
  t.after(freezeClock());
  const hx = h();
  const ip = "203.0.113.12";
  saturateMinuteBucket(hx, ip);

  const anon = await hx.call("GET", "/api/sla/status", { headers: at(ip) });
  assert.equal(anon.status, 429, "anonymous commercial traffic from a saturated IP must still be limited");
  assert.equal(anon.headers.get("Retry-After"), "60");

  const wrongAdmin = await hx.call("POST", `/api/admin/keys/${MSSP_KEY}/rotate`, { admin: "not-the-secret", headers: at(ip) });
  assert.equal(wrongAdmin.status, 429, "a wrong admin secret must not escape metering");
  assert.equal(hx.env.API_KEYS_KV.map.has(MSSP_KEY), true, "nothing rotated");

  const noAdmin = await hx.call("POST", `/api/admin/keys/${MSSP_KEY}/rotate`, { headers: at(ip) });
  assert.equal(noAdmin.status, 429);

  // The WORKER_ADMIN_SECRET must not unlock ADMIN_SECRET routes' metering,
  // and vice versa: each route is matched to its own secret only.
  const crossed = await hx.call("POST", `/api/admin/keys/${MSSP_KEY}/rotate`, { headers: at(ip, { "X-Admin-Secret": WORKER_ADMIN }) });
  assert.equal(crossed.status, 429);
  const crossedPing = await hx.call("POST", "/api/sla/ping", { admin: ADMIN, headers: at(ip), body: { ok: true } });
  assert.equal(crossedPing.status, 429);

  // A customer credential is never the operator plane: metered as PRO (51 of
  // 120 this minute, so allowed) and then refused by the route itself.
  const custOps = await hx.call("GET", "/api/watchdog/ops", { key: PRO_KEY, headers: at(ip) });
  assert.equal(custOps.status, 404, JSON.stringify(custOps.body));
  // 45 seeded + the 5 denied calls above + this one: every non-operator
  // request on these routes was counted.
  assert.equal(hx.env.RATE_LIMIT_KV.map.get(`rl:${ip}:${Math.floor(Date.now() / 60000)}`), "51", "non-operator requests were metered");
});

test("negative control: an exhausted FREE daily quota still denies anonymous and wrong-secret calls", async (t) => {
  t.after(freezeClock());
  const hx = h();
  const ip = "203.0.113.13";
  exhaustFreeDailyQuota(hx, ip);

  const wrong = await hx.call("POST", "/api/admin/keys", { admin: "wrong", headers: at(ip), body: { customer_id: "x", tier: "PRO" } });
  assert.equal(wrong.status, 429);
  assert.equal(wrong.body.reason, "daily_quota_exceeded");

  const ok = await hx.call("POST", "/api/admin/keys", { admin: ADMIN, headers: at(ip), body: { customer_id: "cust_daily", tier: "PRO" } });
  assert.equal(ok.status, 201, JSON.stringify(ok.body));
});

test("WORKER_ADMIN_SECRET routes (SLA heartbeat, cache bust, alert dispatch) are not metered with the valid secret", async (t) => {
  t.after(freezeClock());
  const hx = h();
  const ip = "203.0.113.14";
  saturateMinuteBucket(hx, ip);
  const worker = at(ip, { "X-Admin-Secret": WORKER_ADMIN });

  const ping = await hx.call("POST", "/api/sla/ping", { headers: worker, body: { ok: true, latency_ms: 42, probe_id: "op-plane-test-1" } });
  assert.equal(ping.status, 200, JSON.stringify(ping.body));

  const bust = await hx.call("POST", "/api/admin/cache/bust?key=idx:reports", { headers: worker });
  assert.equal(bust.status, 200, JSON.stringify(bust.body));

  const dispatch = await hx.call("POST", "/api/alerts/dispatch", { headers: worker, body: { advisories: [] } });
  assert.notEqual(dispatch.status, 429, JSON.stringify(dispatch.body));
  assert.notEqual(dispatch.status, 403, JSON.stringify(dispatch.body));
});

test("Watchdog operator routes accept the ADMIN_SECRET X-Admin-Key without commercial metering", async (t) => {
  t.after(freezeClock());
  const hx = h();
  const ip = "203.0.113.15";
  saturateMinuteBucket(hx, ip);
  const ops = await hx.call("GET", "/api/watchdog/ops", { admin: ADMIN, headers: at(ip) });
  assert.equal(ops.status, 200, JSON.stringify(ops.body));
});

test("handleAdmin's brute-force lockout still refuses even a valid secret from a locked IP", async (t) => {
  t.after(freezeClock());
  const hx = h();
  const ip = "203.0.113.16";
  hx.env.RATE_LIMIT_KV.map.set(`bf:${ip}`, JSON.stringify({ count: 5, locked_until: Date.now() + 600000 }));
  const r = await hx.call("POST", `/api/admin/keys/${MSSP_KEY}/rotate`, { admin: ADMIN, headers: at(ip) });
  assert.equal(r.status, 429);
  assert.equal(r.body.error, "Too many failed attempts");
  assert.equal(hx.env.API_KEYS_KV.map.has(MSSP_KEY), true, "nothing rotated while locked");
});
