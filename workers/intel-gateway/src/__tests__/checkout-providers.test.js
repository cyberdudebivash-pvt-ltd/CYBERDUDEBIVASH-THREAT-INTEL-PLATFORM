/**
 * Checkout P0 (2026-10-01): GET /api/pricing tells upgrade.html which
 * automated checkouts it may offer.
 *
 * Gumroad sales are provisioned only by POST /api/webhooks/gumroad, which
 * refuses every ping while GUMROAD_WEBHOOK_SECRET is unset (F21: production
 * answered 500 "Webhook secret not configured" on 2026-10-01 while
 * upgrade.html sold four Gumroad products), and the key reaches a Gumroad
 * buyer only by email. The page offers Gumroad only when this block says a
 * sale can be both provisioned and delivered. These tests pin the block, that
 * it never carries a secret, and that the pricing snapshot is unchanged.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import worker from "../index.js";
import { checkoutProviderAvailability, GUMROAD_UNAVAILABLE_REASONS } from "../checkout-providers.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const PRICING_DATA = JSON.parse(readFileSync(join(HERE, "..", "pricing-data.json"), "utf-8"));
const SECRET = "TEST_ONLY_gumroad_ping_secret_value";
const RESEND = "TEST_ONLY_resend_key_value";

function fakeKV() {
  const m = new Map();
  return {
    get: async (k, o) => {
      const v = m.get(k);
      if (v === undefined) return null;
      return o === "json" || (o && o.type === "json") ? JSON.parse(v) : v;
    },
    put: async (k, v) => { m.set(k, v); },
    delete: async (k) => { m.delete(k); },
    list: async () => ({ keys: [], list_complete: true }),
  };
}

async function pricing(extraEnv) {
  const edge = new Map();
  globalThis.caches = {
    default: { match: async (req) => edge.get(req.url), put: async (req, res) => { edge.set(req.url, res); } },
  };
  const env = {
    INTEL_R2: { get: async () => null },
    RATE_LIMIT_KV: fakeKV(), API_KEYS_KV: fakeKV(), SECURITY_HUB_KV: fakeKV(),
    ANALYTICS_KV: fakeKV(), REVENUE_CRM_KV: fakeKV(),
    CDB_JWT_SECRET: "jwt-test", ADMIN_SECRET: "admin-test", ...extraEnv,
  };
  const waits = [];
  const res = await worker.fetch(new Request("https://intel.cyberdudebivash.com/api/pricing"), env, { waitUntil: (p) => waits.push(p) });
  await Promise.allSettled(waits);
  const text = await res.text();
  return { res, text, body: JSON.parse(text) };
}

test("Gumroad is offered only while its provisioning webhook AND key delivery are configured", () => {
  const off = [{}, { GUMROAD_WEBHOOK_SECRET: "" }, { GUMROAD_WEBHOOK_SECRET: "   " }, { GUMROAD_WEBHOOK_SECRET: 42 }, null, undefined,
    { RESEND_API_KEY: RESEND }];
  for (const env of off) {
    const c = checkoutProviderAvailability(env);
    assert.equal(c.gumroad.available, false, JSON.stringify(env));
    assert.equal(c.gumroad.reason, GUMROAD_UNAVAILABLE_REASONS.provisioning, JSON.stringify(env));
    assert.equal(c.gumroad.role, "secondary");
    assert.equal(c.razorpay.role, "primary");
  }
  // Provisioned but the key could only reach the buyer by a human: not automated.
  for (const resend of [undefined, "", "  "]) {
    const c = checkoutProviderAvailability({ GUMROAD_WEBHOOK_SECRET: SECRET, RESEND_API_KEY: resend });
    assert.equal(c.gumroad.available, false);
    assert.equal(c.gumroad.reason, GUMROAD_UNAVAILABLE_REASONS.delivery);
  }
  const on = checkoutProviderAvailability({ GUMROAD_WEBHOOK_SECRET: SECRET, RESEND_API_KEY: RESEND });
  assert.deepEqual(on.gumroad, { role: "secondary", currency: "USD", available: true });
  const text = JSON.stringify(on);
  assert.equal(text.includes(SECRET) || text.includes(RESEND), false);
});

test("GET /api/pricing: secret unset -> Gumroad unavailable; pricing snapshot unchanged", async () => {
  const { res, body } = await pricing({});
  assert.equal(res.status, 200);
  assert.equal(body.currency, "INR");
  assert.equal(body.unit, "paise");
  assert.deepEqual(body.tiers, PRICING_DATA.tiers);
  assert.equal(body.checkout.razorpay.role, "primary");
  assert.equal(body.checkout.gumroad.available, false);
  assert.equal(body.checkout.gumroad.reason, GUMROAD_UNAVAILABLE_REASONS.provisioning);
});

test("GET /api/pricing: both configured -> Gumroad available, and no secret is ever in the response", async () => {
  const { res, text, body } = await pricing({ GUMROAD_WEBHOOK_SECRET: SECRET, RESEND_API_KEY: RESEND });
  assert.equal(res.status, 200);
  assert.equal(body.checkout.gumroad.available, true);
  assert.equal(body.checkout.gumroad.reason, undefined);
  assert.equal(text.includes(SECRET) || text.includes(RESEND), false);
  assert.deepEqual(body.tiers, PRICING_DATA.tiers);
});
