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
