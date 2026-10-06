import assert from "node:assert/strict";
import { test } from "node:test";

import { GumroadProvisioningLock } from "../gumroad-provisioning-lock.js";
import {
  strongConsistencyEnabled,
  strongRateConsistencyEnabled,
  putStrongAuthState,
  getStrongAuthState,
  incrementStrongRate,
  authStateDenies,
  strongConsistencyCanaryEnabled,
  runStrongConsistencyCanary,
} from "../strong-consistency-authority.js";

function state() {
  const map = new Map();
  return {
    storage: {
      async get(key) { return map.get(key); },
      async put(key, value) { map.set(key, value); },
    },
  };
}

function authorityNamespace() {
  const objects = new Map();
  return {
    idFromName(name) { return name; },
    get(id) {
      if (!objects.has(id)) {
        const lock = new GumroadProvisioningLock(state(), {});
        objects.set(id, {
          async fetch(url, init) {
            return lock.fetch(new Request(url, init));
          },
        });
      }
      return objects.get(id);
    },
  };
}

function env(enabled = true, canaryEnabled = false) {
  return {
    AUTH_STRONG_CONSISTENCY_ENABLED: enabled ? "true" : "false",
    AUTH_STRONG_CONSISTENCY_CANARY_ENABLED: canaryEnabled ? "true" : "false",
    GUMROAD_PROVISIONING_LOCK: authorityNamespace(),
  };
}

test("strongConsistencyEnabled requires exact true", () => {
  assert.equal(strongConsistencyEnabled(env(true)), true);
  assert.equal(strongConsistencyEnabled(env(false)), false);
  assert.equal(strongConsistencyEnabled({ AUTH_STRONG_CONSISTENCY_ENABLED: "TRUE" }), false);
});

test("strongRateConsistencyEnabled is independent and exact", () => {
  assert.equal(strongRateConsistencyEnabled({ RATE_STRONG_CONSISTENCY_ENABLED: "true" }), true);
  assert.equal(strongRateConsistencyEnabled({ RATE_STRONG_CONSISTENCY_ENABLED: "false", AUTH_STRONG_CONSISTENCY_ENABLED: "true" }), false);
  assert.equal(strongRateConsistencyEnabled({ RATE_STRONG_CONSISTENCY_ENABLED: "TRUE" }), false);
});

test("auth authority is read-after-write consistent for the same identity", async () => {
  const e = env();
  await putStrongAuthState(e, "customer:cust-1", {
    status: "suspended",
    version: 1,
    updatedAt: 1000,
  });
  const got = await getStrongAuthState(e, "customer:cust-1");
  assert.equal(got.status, "suspended");
  assert.equal(got.version, 1);
  assert.equal(authStateDenies(got), true);

  await putStrongAuthState(e, "customer:cust-1", {
    status: "active",
    version: 2,
    updatedAt: 2000,
  });
  const active = await getStrongAuthState(e, "customer:cust-1");
  assert.equal(active.status, "active");
  assert.equal(active.version, 2);
  assert.equal(authStateDenies(active), false);
});

test("key identities are isolated from customer identities", async () => {
  const e = env();
  await putStrongAuthState(e, "key:key-a", {
    status: "revoked",
    version: 1,
    updatedAt: 1000,
  });
  assert.equal((await getStrongAuthState(e, "key:key-a")).status, "revoked");
  assert.equal(await getStrongAuthState(e, "customer:key-a"), null);
});

test("strong rate counter enforces the exact boundary serially", async () => {
  const e = env();
  const resetAt = Date.now() + 60000;
  for (let i = 1; i <= 30; i++) {
    const r = await incrementStrongRate(e, "rl:203.0.113.1:1", 30, resetAt);
    assert.equal(r.allowed, true, `request ${i} should be allowed`);
    assert.equal(r.count, i);
  }
  const blocked = await incrementStrongRate(e, "rl:203.0.113.1:1", 30, resetAt);
  assert.equal(blocked.allowed, false);
  assert.equal(blocked.count, 31);
  assert.equal(blocked.remaining, 0);
});

test("different rate identities do not share counters", async () => {
  const e = env();
  const resetAt = Date.now() + 60000;
  const a = await incrementStrongRate(e, "rl:a:1", 1, resetAt);
  const b = await incrementStrongRate(e, "rl:b:1", 1, resetAt);
  assert.equal(a.allowed, true);
  assert.equal(b.allowed, true);
  assert.equal(a.count, 1);
  assert.equal(b.count, 1);
});


test("strong consistency canary remains disabled unless explicitly enabled", async () => {
  const e = env(false, false);
  assert.equal(strongConsistencyCanaryEnabled(e), false);
  const result = await runStrongConsistencyCanary(e);
  assert.equal(result.ok, false);
  assert.equal(result.disabled, true);
});

test("explicit canary defaults to minimal auth-only proof", async () => {
  const e = env(false, true);
  assert.equal(strongConsistencyEnabled(e), false);
  assert.equal(strongConsistencyCanaryEnabled(e), true);
  const result = await runStrongConsistencyCanary(e);
  assert.equal(result.ok, true);
  assert.equal(result.scope, "auth");
  assert.equal(result.auth_suspend_read_after_write, true);
  assert.equal(result.auth_reactivate_read_after_write, true);
  assert.equal(result.rate_checked, false);
  assert.equal(result.first_denied_request, undefined);
  assert.equal(result.canary_identities_reused, true);
});

test("full canary additionally validates exact request 31 rate denial", async () => {
  const e = env(false, true);
  const result = await runStrongConsistencyCanary(e, "full");
  assert.equal(result.ok, true);
  assert.equal(result.scope, "full");
  assert.equal(result.rate_checked, true);
  assert.equal(result.first_denied_request, 31);
  assert.equal(result.final_count, 31);
});
