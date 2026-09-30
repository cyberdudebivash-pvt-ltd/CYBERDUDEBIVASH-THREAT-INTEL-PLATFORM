/**
 * Commercial per-minute limit: the request that crosses the limit must get
 * the documented 429, through the REAL gateway router.
 *
 * Defect (found 2026-09-30): the 429 branch of the commercial gate built
 * X-RateLimit-Reset from `resetAtMs`, an identifier defined nowhere (added in
 * #290, 2026-09-01; the only no-undef hit across the gateway source). Every
 * time the limit tripped, the gateway threw a ReferenceError and the
 * top-level handler answered HTTP 500 "Internal gateway error": no
 * Retry-After, no X-RateLimit-* headers, no FREE/PRO upgrade block. This is
 * why live certification (#596, phase 8) never observed a 429 at request 31,
 * and it also turned operator calls made from a busy IP into 500s.
 *
 * Contract (config/commercial-contract.json _quota_authority): the per-IP
 * fixed 60s window denies with HTTP 429 at the cap. X-RateLimit-Reset is the
 * end of that window, in epoch seconds.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { harness, fakeNamespace, PRO_KEY, ENT_KEY, MSSP_KEY } from "./watchdog-harness.js";
import { GumroadProvisioningLock } from "../gumroad-provisioning-lock.js";

const at = (ip) => ({ "cf-connecting-ip": ip });
const PROBE = "/api/sla/status"; // commercial plane, same path the live phase 8 burst uses

// Pin the clock mid-window so no test can straddle a minute boundary.
function freezeClock() {
  const real = Date.now;
  const t = Math.floor(real() / 60000) * 60000 + 30000;
  Date.now = () => t;
  return () => { Date.now = real; };
}

function seedWindow(hx, ip, count) {
  hx.env.RATE_LIMIT_KV.map.set(`rl:${ip}:${Math.floor(Date.now() / 60000)}`, String(count));
}

function assertRateLimited(res, limit, { upgrade }) {
  assert.equal(res.status, 429, `expected 429 at the cap, got ${res.status}: ${res.text}`);
  assert.equal(res.body.error, "Too Many Requests");
  assert.equal(res.body.limit, limit);
  assert.equal(res.body.retry_after, 60);
  assert.equal(res.headers.get("Retry-After"), "60");
  assert.equal(res.headers.get("X-RateLimit-Limit"), String(limit));
  assert.equal(res.headers.get("X-RateLimit-Remaining"), "0");
  const reset = Number(res.headers.get("X-RateLimit-Reset"));
  const windowEnd = (Math.floor(Date.now() / 60000) + 1) * 60;
  assert.equal(reset, windowEnd, "X-RateLimit-Reset must be the end of the current fixed 60s window");
  assert.equal(Boolean(res.body.upgrade), upgrade, "upgrade block is only for FREE and PRO");
}

test("FREE: the 31st request in a window gets 429 with Retry-After, never a 500", async (t) => {
  t.after(freezeClock());
  const hx = harness();
  const ip = "198.18.0.1";
  for (let i = 1; i <= 30; i += 1) {
    const r = await hx.call("GET", PROBE, { headers: at(ip) });
    assert.ok(r.status < 400, `request ${i} of 30 must be allowed, got ${r.status}: ${r.text}`);
  }
  const over = await hx.call("GET", PROBE, { headers: at(ip) });
  assertRateLimited(over, 30, { upgrade: true });
  assert.equal(over.body.upgrade.target_tier !== undefined || over.body.upgrade.cta !== undefined || typeof over.body.upgrade === "object", true);

  const again = await hx.call("GET", PROBE, { headers: at(ip) });
  assertRateLimited(again, 30, { upgrade: true });
});

test("PRO, ENTERPRISE and MSSP get the same 429 shape at their own caps", async (t) => {
  t.after(freezeClock());
  const cases = [
    [PRO_KEY, 120, true],
    [ENT_KEY, 600, false],
    [MSSP_KEY, 1200, false],
  ];
  for (const [key, limit, upgrade] of cases) {
    const hx = harness();
    const ip = "198.18.1." + limit % 250;
    seedWindow(hx, ip, limit - 1);
    const last = await hx.call("GET", PROBE, { key, headers: at(ip) });
    assert.ok(last.status < 400, `request ${limit} must be allowed, got ${last.status}: ${last.text}`);
    const over = await hx.call("GET", PROBE, { key, headers: at(ip) });
    assertRateLimited(over, limit, { upgrade });
  }
});

test("dormant strong-consistency path (RATE_STRONG_CONSISTENCY_ENABLED) returns the same 429 at request 31", async (t) => {
  t.after(freezeClock());
  const hx = harness();
  hx.env.RATE_STRONG_CONSISTENCY_ENABLED = "true";
  hx.env.GUMROAD_PROVISIONING_LOCK = fakeNamespace(GumroadProvisioningLock, { env: hx.env });
  const ip = "198.18.2.1";
  for (let i = 1; i <= 30; i += 1) {
    const r = await hx.call("GET", PROBE, { headers: at(ip) });
    assert.ok(r.status < 400, `request ${i} of 30 must be allowed, got ${r.status}: ${r.text}`);
  }
  const over = await hx.call("GET", PROBE, { headers: at(ip) });
  assertRateLimited(over, 30, { upgrade: true });
  assert.ok(hx.env.GUMROAD_PROVISIONING_LOCK.requests >= 31, "every request was counted by the authority");
});

test("a counter fault still fails open (unchanged posture), and an allowed request carries no rate-limit headers", async (t) => {
  t.after(freezeClock());
  const hx = harness();
  const ip = "198.18.3.1";
  const realGet = hx.env.RATE_LIMIT_KV.get;
  hx.env.RATE_LIMIT_KV.get = async (k, o) => { if (String(k).startsWith("rl:")) throw new Error("kv down"); return realGet(k, o); };
  const r = await hx.call("GET", PROBE, { headers: at(ip) });
  assert.ok(r.status < 400, `fail-open expected, got ${r.status}: ${r.text}`);
  assert.equal(r.headers.get("X-RateLimit-Reset"), null);
});
