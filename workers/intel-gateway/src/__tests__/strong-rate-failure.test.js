/** Opted-in authoritative rate enforcement must never fail open. Offline only. */
import assert from "node:assert/strict";
import { test } from "node:test";
import { harness, PRO_KEY } from "./watchdog-harness.js";

const PROBE = "/api/sla/status";
const at = (ip) => ({ "cf-connecting-ip": ip });

function authority(fetch) {
  return { idFromName: (name) => name, get: () => ({ fetch }) };
}

function assertUnavailable(res) {
  assert.equal(res.status, 503, `authority failure must stop the request: ${res.text}`);
  assert.equal(res.body.reason, "rate_limit_service_unavailable");
  assert.equal(res.headers.get("Retry-After"), "10");
  assert.equal(res.headers.get("Cache-Control"), "no-store");
  assert.equal(res.headers.get("X-RateLimit-Remaining"), null);
  assert.equal(res.headers.get("X-RateLimit-Reset"), null);
  assert.equal(res.body.upgrade, undefined, "backend failure is not an exhausted subscription");
  assert.ok(!res.text.includes("private-authority-diagnostic"));
}

for (const mode of ["missing-binding", "transport", "http", "invalid-json", "rejected"]) {
  test(`strong mode fails closed on ${mode}, without a KV fallback`, async () => {
    const hx = harness();
    hx.env.RATE_STRONG_CONSISTENCY_ENABLED = "true";
    let kvFallbacks = 0;
    const get = hx.env.RATE_LIMIT_KV.get;
    hx.env.RATE_LIMIT_KV.get = async (key, opts) => {
      if (String(key).startsWith("rl:")) kvFallbacks++;
      return get(key, opts);
    };
    if (mode === "missing-binding") delete hx.env.GUMROAD_PROVISIONING_LOCK;
    else hx.env.GUMROAD_PROVISIONING_LOCK = authority(async () => {
      if (mode === "transport") throw new Error("private-authority-diagnostic");
      if (mode === "http") return new Response("private-authority-diagnostic", { status: 503 });
      if (mode === "invalid-json") return new Response("private-authority-diagnostic");
      return Response.json({ ok: false, error: "private-authority-diagnostic" });
    });
    assertUnavailable(await hx.call("GET", PROBE, { key: PRO_KEY, headers: at("198.18.40.1") }));
    assert.equal(kvFallbacks, 0);
  });
}

const badDecisions = [
  { ok: true },
  { ok: "true", allowed: true, count: 1, limit: 120, remaining: 119 },
  { ok: true, allowed: "true", count: 1, limit: 120, remaining: 119 },
  { ok: true, allowed: true, count: -1, limit: 120, remaining: 121 },
  { ok: true, allowed: true, count: "1", limit: 120, remaining: 119 },
  { ok: true, allowed: true, count: 1, limit: 1200, remaining: 1199 },
  { ok: true, allowed: true, count: 121, limit: 120, remaining: 0 },
  { ok: true, allowed: true, count: 1, limit: 120, remaining: 120 },
];
for (const [i, decision] of badDecisions.entries()) {
  test(`malformed authoritative decision ${i + 1} cannot authorize a request`, async () => {
    const hx = harness();
    hx.env.RATE_STRONG_CONSISTENCY_ENABLED = "true";
    hx.env.GUMROAD_PROVISIONING_LOCK = authority(async () => Response.json(decision));
    assertUnavailable(await hx.call("GET", PROBE, { key: PRO_KEY, headers: at(`198.18.41.${i + 1}`) }));
  });
}

test("disabled strong mode never contacts the dormant authority", async () => {
  const hx = harness();
  let contacts = 0;
  hx.env.GUMROAD_PROVISIONING_LOCK = authority(async () => { contacts++; throw new Error("disabled"); });
  const res = await hx.call("GET", PROBE, { headers: at("198.18.42.1") });
  assert.equal(res.status, 200);
  assert.equal(contacts, 0);
});

test("lead capture stops when its second authoritative check fails", async () => {
  const hx = harness();
  hx.env.RATE_STRONG_CONSISTENCY_ENABLED = "true";
  let calls = 0;
  hx.env.GUMROAD_PROVISIONING_LOCK = authority(async (url, init) => {
    calls++;
    if (calls > 1) throw new Error("private-authority-diagnostic");
    const request = JSON.parse(init.body);
    return Response.json({ ok: true, allowed: true, count: 1, limit: request.limit,
      remaining: request.limit - 1, resetAt: request.resetAt });
  });
  const res = await hx.call("POST", "/api/leads/capture", {
    headers: at("198.18.43.1"), body: { email: "offline@example.test" },
  });
  assertUnavailable(res);
  assert.equal(calls, 2);
});

test("public health stays available without an authoritative rate request", async () => {
  const hx = harness();
  hx.env.RATE_STRONG_CONSISTENCY_ENABLED = "true";
  let contacts = 0;
  hx.env.GUMROAD_PROVISIONING_LOCK = authority(async () => { contacts++; throw new Error("down"); });
  const res = await hx.call("GET", "/api/health", { headers: at("198.18.44.1") });
  assert.equal(res.status, 200);
  assert.equal(contacts, 0);
});
