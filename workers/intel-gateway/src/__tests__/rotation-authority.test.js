import assert from "node:assert/strict";
import { test } from "node:test";
import { handleAdmin } from "../index.js";

for (const status of ["suspended", "cancelled", "expired", "refunded", "revoked"]) {
  test("rotation rejects strong " + status + " despite stale active KV", async () => {
    let writes = 0;
    const env = {
      ADMIN_SECRET: "test-admin",
      AUTH_STRONG_CONSISTENCY_ENABLED: "true",
      API_KEYS_KV: {
        async get() { return { tier: "PRO", customer_id: "test-customer", subscription_status: "active" }; },
        async put() { writes++; },
        async delete() { writes++; },
      },
      GUMROAD_PROVISIONING_LOCK: {
        idFromName(name) { return name; },
        get() { return { async fetch() {
          return Response.json({ ok: true, state: { status } });
        } }; },
      },
    };
    const req = new Request("https://intel.example/api/admin/keys/test-key/rotate", {
      method: "POST", headers: { "X-Admin-Key": "test-admin" },
    });
    const res = await handleAdmin(req, env, { waitUntil() {} }, "/api/admin/keys/test-key/rotate", "POST");
    assert.equal(res.status, 409);
    assert.equal(writes, 0);
  });
}
test("rotation fails closed when strong authority is unavailable", async () => {
  let writes = 0;
  const env = {
    ADMIN_SECRET: "test-admin", AUTH_STRONG_CONSISTENCY_ENABLED: "true",
    API_KEYS_KV: {
      async get() { return { tier: "PRO", customer_id: "test-customer", subscription_status: "active" }; },
      async put() { writes++; }, async delete() { writes++; },
    },
  };
  const req = new Request("https://intel.example/api/admin/keys/test-key/rotate", {
    method: "POST", headers: { "X-Admin-Key": "test-admin" },
  });
  const res = await handleAdmin(req, env, { waitUntil() {} }, "/api/admin/keys/test-key/rotate", "POST");
  assert.equal(res.status, 503);
  assert.equal(writes, 0);
});

// F17 (2026-10-01): without the strong authority the old key is only deleted
// from KV, and live certification saw stale key state served 1-2 s after a
// write. The rotate response must not promise "no overlap" in that mode.
function rotationEnv(strong) {
  const kv = new Map([["old-key-0123456789abcdef", JSON.stringify({ tier: "PRO", customer_id: "rot-msg@test", subscription_status: "active" })]]);
  const env = {
    ADMIN_SECRET: "test-admin",
    AUTH_STRONG_CONSISTENCY_ENABLED: strong ? "true" : "false",
    API_KEYS_KV: {
      async get(k, type) { const v = kv.get(k); return v === undefined ? null : (type === "json" ? JSON.parse(v) : v); },
      async put(k, v) { kv.set(k, v); },
      async delete(k) { kv.delete(k); },
    },
  };
  if (strong) {
    env.GUMROAD_PROVISIONING_LOCK = {
      idFromName(name) { return name; },
      get() { return { async fetch() { return Response.json({ ok: true, state: { status: "active" } }); } }; },
    };
  }
  return { env, kv };
}

async function rotate(env) {
  const path = "/api/admin/keys/old-key-0123456789abcdef/rotate";
  const req = new Request("https://intel.example" + path, { method: "POST", headers: { "X-Admin-Key": "test-admin" } });
  const res = await handleAdmin(req, env, { waitUntil() {} }, path, "POST");
  return { status: res.status, body: await res.json() };
}

test("rotate message does not promise zero overlap while the strong authority is off", async () => {
  const { env, kv } = rotationEnv(false);
  const { status, body } = await rotate(env);
  assert.equal(status, 201);
  assert.equal(body.old_key_revoked, true);
  assert.ok(body.new_key && kv.has(body.new_key), "new key provisioned");
  assert.ok(!kv.has("old-key-0123456789abcdef"), "old key deleted from KV");
  assert.ok(!/no overlap/i.test(body.message), body.message);
  assert.match(body.message, /about a minute/);
});

test("negative control: with the strong authority on, the rotate message keeps its no-overlap wording", async () => {
  const { env } = rotationEnv(true);
  const { status, body } = await rotate(env);
  assert.equal(status, 201);
  assert.match(body.message, /immediately revoked, no overlap window/);
});
