/**
 * P0 R16 — /api/preview must not re-stamp old R2 intelligence as fresh.
 * Exercised through the real Worker route with stubbed R2 and no secrets,
 * production network, writes or customer credentials.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import worker from "../index.js";

function fakeKV() {
  return {
    get: async () => null,
    put: async () => {},
    delete: async () => {},
    list: async () => ({ keys: [], list_complete: true }),
  };
}
const fmt = (ms) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");
async function preview(feedDate) {
  globalThis.caches = { default: { match: async () => undefined, put: async () => {} } };
  const feed = {
    generated_at: feedDate,
    count: 1,
    items: [{
      id: "intel--evidence-1", title: "Verified source advisory",
      tlp: "TLP:CLEAR", severity: "HIGH", risk_score: 7.5,
      description: "Evidence is source-backed", iocs: ["198.51.100.5"],
    }],
  };
  const env = {
    INTEL_R2: { get: async (key) => key === "api/v1/intel/latest.json"
      ? { text: async () => JSON.stringify(feed) } : null },
    RATE_LIMIT_KV: fakeKV(), API_KEYS_KV: fakeKV(), SECURITY_HUB_KV: fakeKV(),
    ANALYTICS_KV: fakeKV(), REVENUE_CRM_KV: fakeKV(),
    CDB_JWT_SECRET: "not-production-jwt", ADMIN_SECRET: "not-production-admin",
  };
  const res = await worker.fetch(
    new Request("https://intel.cyberdudebivash.com/api/preview?limit=1"),
    env, { waitUntil() {} },
  );
  return { status: res.status, headers: res.headers, body: await res.json() };
}

test("fresh feed keeps canonical source timestamp and a separately named response timestamp", async () => {
  const sourceTime = fmt(Date.now() - 60_000);
  const { status, body, headers } = await preview(sourceTime);
  assert.equal(status, 200);
  assert.equal(body.status, "ok");
  assert.equal(body.preview.generated_at, sourceTime);
  assert.match(body.preview.response_generated_at, /^\d{4}-\d\d-\d\dT/);
  assert.equal(body.preview.freshness_status, "FRESH");
  assert.equal(body.preview.publication_state, "fresh");
  assert.equal(headers.get("X-Sentinel-Freshness"), "FRESH");
  assert.match(headers.get("Cache-Control"), /max-age=\d+/);
  assert.equal(body.preview.items.length, 1);
  assert.deepEqual(body.preview.items[0].iocs, []);
});

test("stale feed remains available for historical viewing but cannot be represented as fresh", async () => {
  const published = fmt(Date.now() - 7 * 3600_000);
  const { status, body, headers } = await preview(published);
  assert.equal(status, 200, "historical preview must not disappear");
  assert.equal(body.status, "ok", "existing success envelope preserved");
  assert.equal(body.preview.generated_at, published);
  assert.equal(body.preview.publication_state, "stale");
  assert.equal(body.preview.freshness_status, "STALE");
  assert.equal(body.preview.freshness_reason, "intelligence_stale");
  assert.ok(body.preview.age_seconds > 6 * 3600);
  assert.equal(body.preview.max_age_seconds, 6 * 3600);
  assert.equal(headers.get("X-Sentinel-Freshness"), "STALE");
  assert.equal(headers.get("Cache-Control"), "no-store");
});

test("invalid source timestamp is surfaced as unverified instead of minting a fresh time", async () => {
  const { status, body, headers } = await preview("not-a-timestamp");
  assert.equal(status, 200);
  assert.equal(body.preview.generated_at, "not-a-timestamp");
  assert.equal(body.preview.freshness_status, "INVALID");
  assert.equal(body.preview.freshness_reason, "generated_at_invalid");
  assert.equal(headers.get("Cache-Control"), "no-store");
});

test("healthy edge cache TTL cannot outlive approaching six-hour feed expiry", async () => {
  const published = fmt(Date.now() - (6 * 3600_000 - 90_000));
  const { body, headers } = await preview(published);
  assert.equal(body.preview.freshness_status, "FRESH");
  const match = /max-age=(\d+)/.exec(headers.get("Cache-Control") || "");
  assert.ok(match, "bounded cache-control required");
  assert.ok(Number(match[1]) <= 90);
  assert.ok(Number(match[1]) >= 0);
});
