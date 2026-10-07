import assert from "node:assert/strict";
import { test } from "node:test";
import {
  CERTIFICATION_SINK_MAX_BODY_BYTES,
  createCertificationWebhookSink,
  deleteCertificationWebhookSink,
  routeCertificationWebhookSink,
} from "../certification-webhook-sink.js";

class FakeKV {
  constructor() { this.map = new Map(); }
  async get(key) { return this.map.get(key) ?? null; }
  async put(key, value) { this.map.set(key, value); }
  async delete(key) { this.map.delete(key); }
  async list({ prefix = "", limit = 1000 } = {}) {
    const keys = [...this.map.keys()].filter((k) => k.startsWith(prefix)).slice(0, limit).map((name) => ({ name }));
    return { keys, list_complete: true };
  }
}

async function created() {
  const env = { SECURITY_HUB_KV: new FakeKV() };
  const res = await createCertificationWebhookSink(new Request("https://intel.example/api/admin/certification/webhook-sink", { method: "POST" }), env);
  assert.equal(res.status, 201);
  const body = await res.json();
  return { env, ...body };
}

test("creates a short-lived capability sink without embedding inspect token in sink URL", async () => {
  const c = await created();
  assert.match(c.sink_url, /^https:\/\/intel\.example\/api\/certification\/webhook-sink\/[0-9a-f]{32}$/);
  assert.match(c.inspect_token, /^[0-9a-f]{64}$/);
  assert.equal(c.sink_url.includes(c.inspect_token), false);
  assert.equal(c.ttl_seconds, 900);
});

test("verification challenge is answered and bounded evidence is inspectable only with bearer token", async () => {
  const c = await created();
  const verify = await routeCertificationWebhookSink(new Request(c.sink_url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CDB-Watchdog-Delivery-ID": "d-verify",
      "X-CDB-Watchdog-Signature": "v1=" + "a".repeat(64),
    },
    body: JSON.stringify({ type: "watchdog.verification", challenge: "abc123" }),
  }), c.env, new URL(c.sink_url).pathname);
  assert.equal(verify.status, 200);
  assert.deepEqual(await verify.json(), { challenge: "abc123" });

  const unauth = await routeCertificationWebhookSink(new Request(c.inspect_url), c.env, new URL(c.inspect_url).pathname);
  assert.equal(unauth.status, 401);

  const inspect = await routeCertificationWebhookSink(new Request(c.inspect_url, {
    headers: { Authorization: "Bearer " + c.inspect_token },
  }), c.env, new URL(c.inspect_url).pathname);
  assert.equal(inspect.status, 200);
  const body = await inspect.json();
  assert.equal(body.records.length, 1);
  assert.equal(body.records[0].headers["x-cdb-watchdog-delivery-id"], "d-verify");
  assert.equal(body.records[0].raw.includes("abc123"), true);
});

test("forced 503 mode returns Retry-After and mode endpoint advertises KV settle requirement", async () => {
  const c = await created();
  const modeUrl = c.inspect_url + "/mode";
  const mode = await routeCertificationWebhookSink(new Request(modeUrl, {
    method: "POST",
    headers: { Authorization: "Bearer " + c.inspect_token, "Content-Type": "application/json" },
    body: JSON.stringify({ status: 503, retry_after: 120 }),
  }), c.env, new URL(modeUrl).pathname);
  assert.equal(mode.status, 200);
  const m = await mode.json();
  assert.equal(m.status, 503);
  assert.equal(m.retry_after, 120);
  assert.equal(m.settle_ms, 65000);

  const delivery = await routeCertificationWebhookSink(new Request(c.sink_url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type: "watchdog.event", id: "evt-1" }),
  }), c.env, new URL(c.sink_url).pathname);
  assert.equal(delivery.status, 503);
  assert.equal(delivery.headers.get("Retry-After"), "120");
});

test("rejects oversized payloads before retaining evidence", async () => {
  const c = await created();
  const body = "x".repeat(CERTIFICATION_SINK_MAX_BODY_BYTES + 1);
  const res = await routeCertificationWebhookSink(new Request(c.sink_url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  }), c.env, new URL(c.sink_url).pathname);
  assert.equal(res.status, 413);
});

test("explicit cleanup removes state and evidence", async () => {
  const c = await created();
  const id = c.sink_id;
  const del = await deleteCertificationWebhookSink(c.env, id);
  assert.equal(del.status, 200);
  const after = await routeCertificationWebhookSink(new Request(c.sink_url, { method: "POST", body: "{}" }), c.env, new URL(c.sink_url).pathname);
  assert.equal(after.status, 404);
});
