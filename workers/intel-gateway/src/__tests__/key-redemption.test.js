/**
 * F22 (2026-10-02): a raw API key is never emailed. The activation email
 * carries a one-time link; POST /api/keys/redeem reveals the key once.
 *
 * Runs the real Worker with the real GumroadProvisioningLock class behind a
 * fake namespace (one instance per name, requests serialized per instance
 * like the Durable Object input gate), and captures every outbound email.
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import worker from "../index.js";
import { GumroadProvisioningLock } from "../gumroad-provisioning-lock.js";
import {
  issueKeyRedemption, redeemKeyToken, hashRedemptionToken, isRedemptionToken,
  REDEMPTION_PREFIX, REDEMPTION_TTL_SECONDS, REDEMPTION_PAGE,
} from "../key-redemption.js";

const GUMROAD_SECRET = "gumroad-redeem-secret";
const ADMIN = "admin-test";
const SALE = { sale_id: "s_redeem_1", email: "buyer@example.com", permalink: "pxyfcb", price: "4900", currency: "usd", product_name: "SENTINEL APEX PRO" };

function fakeKV() {
  const m = new Map();
  const ttl = new Map();
  const faults = [];
  const trip = (op, k) => {
    const f = faults.find((x) => x.op === op && k.startsWith(x.prefix) && x.remaining > 0);
    if (f) { f.remaining -= 1; throw new Error(`injected ${op} failure on ${k}`); }
  };
  return {
    store: m, ttl, faults,
    get: async (k, o) => {
      trip("get", k);
      const v = m.get(k);
      if (v === undefined) return null;
      return o === "json" || (o && o.type === "json") ? JSON.parse(v) : v;
    },
    put: async (k, v, opts) => { trip("put", k); m.set(k, v); if (opts?.expirationTtl) ttl.set(k, opts.expirationTtl); },
    delete: async (k) => { m.delete(k); },
    list: async ({ prefix = "" } = {}) => ({ keys: [...m.keys()].filter((k) => k.startsWith(prefix)).map((name) => ({ name })), list_complete: true }),
  };
}

function lockNamespace() {
  const objects = new Map();
  return {
    idFromName: (name) => name,
    get(id) {
      if (!objects.has(id)) {
        const storage = new Map();
        const instance = new GumroadProvisioningLock({ storage: {
          get: async (k) => storage.get(k), put: async (k, v) => { storage.set(k, v); }, delete: async (k) => { storage.delete(k); },
        } }, {});
        let queue = Promise.resolve();
        objects.set(id, {
          fetch: (url, init) => {
            const run = queue.then(() => instance.fetch(new Request(url, init)));
            queue = run.catch(() => {});
            return run;
          },
        });
      }
      return objects.get(id);
    },
  };
}

function harness(extra = {}) {
  globalThis.caches = { default: { match: async () => undefined, put: async () => {} } };
  const env = {
    INTEL_R2: { get: async () => null },
    RATE_LIMIT_KV: fakeKV(), API_KEYS_KV: fakeKV(), SECURITY_HUB_KV: fakeKV(),
    ANALYTICS_KV: fakeKV(), REVENUE_CRM_KV: fakeKV(),
    CDB_JWT_SECRET: "jwt-test", ADMIN_SECRET: ADMIN, SUBSCRIPTION_EXPIRY_ENABLED: "true",
    GUMROAD_WEBHOOK_SECRET: GUMROAD_SECRET, RESEND_API_KEY: "re_TEST_ONLY",
    GUMROAD_PROVISIONING_LOCK: lockNamespace(),
    ...extra,
  };
  const emails = [];
  let ip = 0;
  const call = async (path, init = {}) => {
    const realFetch = globalThis.fetch;
    globalThis.fetch = async (url, opts) => {
      if (String(url).includes("api.resend.com")) emails.push(JSON.parse(opts.body));
      return new Response("{}", { status: 200 });
    };
    const waits = [];
    try {
      const headers = { "cf-connecting-ip": `203.0.113.${(ip++ % 200) + 1}`, ...(init.headers || {}) };
      const res = await worker.fetch(new Request(`https://intel.cyberdudebivash.com${path}`, { ...init, headers }), env, { waitUntil: (p) => waits.push(p) });
      await Promise.allSettled(waits);
      let body = null;
      try { body = await res.json(); } catch (_) { body = null; }
      return { status: res.status, headers: res.headers, body };
    } finally {
      globalThis.fetch = realFetch;
    }
  };
  const redeem = (token) => call("/api/keys/redeem", {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ token }),
  });
  const liveKey = async (key, over = {}) => {
    await env.API_KEYS_KV.put(key, JSON.stringify({ key, tier: "PRO", customer_id: "buyer@example.com", label: "buyer@example.com", expires_at: new Date(Date.now() + 30 * 86400e3).toISOString(), ...over }));
    return key;
  };
  const audits = () => [...env.SECURITY_HUB_KV.store.entries()].filter(([k]) => k.startsWith("audit:")).map(([, v]) => v);
  return { env, emails, call, redeem, liveKey, audits };
}

function tokenFrom(html) {
  const m = /#redeem=([A-Za-z0-9_-]{43})/.exec(html || "");
  return m ? m[1] : null;
}

// --- the decision table (pure) -------------------------------------------------

test("issue: only the token's hash is stored, with a 72 h expiry; the link carries the token in the fragment", async () => {
  const kv = fakeKV();
  const r = await issueKeyRedemption(kv, "cdb_pro_SECRETKEYVALUE", { tier: "PRO", nowMs: Date.parse("2026-10-02T00:00:00Z") });
  assert.ok(isRedemptionToken(r.token));
  assert.equal(r.url, `${REDEMPTION_PAGE}#redeem=${r.token}`);
  const [name] = kv.store.keys();
  assert.equal(name, REDEMPTION_PREFIX + await hashRedemptionToken(r.token));
  assert.equal(kv.ttl.get(name), REDEMPTION_TTL_SECONDS);
  assert.equal(JSON.parse(kv.store.get(name)).expires_at, "2026-10-05T00:00:00.000Z");
  assert.equal([...kv.store.keys(), ...kv.store.values()].join("|").includes(r.token), false, "the token itself is never stored");
  assert.notEqual(r.ref, r.token.slice(0, 12));
});

test("redeem decision table: every refusal is non-revealing, and a 503 never spends the link", async () => {
  const kv = fakeKV();
  const active = { ok: true, record: { tier: "PRO", expires_at: null } };
  const deps = (over = {}) => ({ kv, claim: async () => "claimed", keyAccess: async () => active, ...over });
  for (const bad of [undefined, null, "", "short", "x".repeat(43) + "=", "a b".repeat(15), 42, { token: "x" }]) {
    assert.equal((await redeemKeyToken(bad, deps())).status, 400, String(bad));
  }
  const unknown = await redeemKeyToken("A".repeat(43), deps());
  assert.deepEqual([unknown.status, unknown.outcome], [410, "unknown_or_used"]);

  const now = Date.parse("2026-10-02T00:00:00Z");
  const expired = await issueKeyRedemption(kv, "cdb_pro_k1", { nowMs: now - REDEMPTION_TTL_SECONDS * 1000 - 1 });
  assert.equal((await redeemKeyToken(expired.token, deps(), now)).outcome, "expired");

  const t = await issueKeyRedemption(kv, "cdb_pro_k2", { nowMs: now });
  let claimed = 0;
  const outage = await redeemKeyToken(t.token, deps({ keyAccess: async () => ({ ok: false, reason: "unavailable" }), claim: async () => { claimed++; return "claimed"; } }), now);
  assert.deepEqual([outage.status, claimed], [503, 0], "authority outage: nothing claimed");
  const lockDown = await redeemKeyToken(t.token, deps({ claim: async () => "unavailable" }), now);
  assert.equal(lockDown.status, 503);
  const ok = await redeemKeyToken(t.token, deps(), now);
  assert.deepEqual([ok.status, ok.api_key], [200, "cdb_pro_k2"], "the link still worked after both 503s");
  assert.equal((await redeemKeyToken(t.token, deps(), now)).outcome, "unknown_or_used");

  const t3 = await issueKeyRedemption(kv, "cdb_pro_k3", { nowMs: now });
  assert.equal((await redeemKeyToken(t3.token, deps({ claim: async () => "replay" }), now)).outcome, "replay");

  const t4 = await issueKeyRedemption(kv, "cdb_pro_k4", { nowMs: now });
  const revoked = await redeemKeyToken(t4.token, deps({ keyAccess: async () => ({ ok: false, reason: "subscription_status_denied" }) }), now);
  assert.deepEqual([revoked.status, revoked.outcome, revoked.api_key], [410, "key_not_active", undefined]);
});

// --- the route ------------------------------------------------------------------

test("route: reveals the key once, no-store; a second use, GET and query-string tokens are refused", async () => {
  const h = harness();
  const key = await h.liveKey("cdb_pro_ROUTE_SECRET_0001");
  const { token } = await issueKeyRedemption(h.env.API_KEYS_KV, key, { tier: "PRO" });

  const first = await h.redeem(token);
  assert.equal(first.status, 200);
  assert.equal(first.body.api_key, key);
  assert.equal(first.headers.get("cache-control"), "no-store");
  const second = await h.redeem(token);
  assert.equal(second.status, 410);
  assert.equal(second.body.api_key, undefined);

  const { token: t2 } = await issueKeyRedemption(h.env.API_KEYS_KV, key, { tier: "PRO" });
  assert.equal((await h.call(`/api/keys/redeem?token=${t2}`)).status, 405);
  const viaQuery = await h.call(`/api/keys/redeem?token=${t2}`, { method: "POST", headers: { "content-type": "application/json" }, body: "{}" });
  assert.equal(viaQuery.status, 400, "a token in the query string is ignored");
  assert.equal((await h.call("/api/keys/redeem", { method: "POST", headers: { "content-type": "text/plain" }, body: t2 })).status, 415);
  assert.equal((await h.redeem(t2)).status, 200, "the refused attempts did not spend the link");

  for (const v of h.audits()) {
    assert.equal(v.includes(key), false, "audit never holds the key");
    assert.equal(v.includes(token) || v.includes(t2), false, "audit never holds a token");
  }
  assert.ok(h.audits().some((v) => v.includes('"outcome":"redeemed"')));
  assert.ok(h.audits().some((v) => v.includes('"outcome":"replay"') || v.includes('"outcome":"unknown_or_used"')));
});

test("route: an expired link, a revoked or deleted key, and an unknown token reveal nothing", async () => {
  const h = harness();
  const refunded = await h.liveKey("cdb_pro_REFUNDED_0001", { subscription_status: "refunded" });
  const suspended = await h.liveKey("cdb_pro_SUSPENDED_001", { subscription_status: "suspended" });
  const lapsed = await h.liveKey("cdb_pro_LAPSED_000001", { expires_at: new Date(Date.now() - 60e3).toISOString() });
  for (const k of [refunded, suspended, lapsed, "cdb_pro_DELETED_00001"]) {
    const { token } = await issueKeyRedemption(h.env.API_KEYS_KV, k, { tier: "PRO" });
    const r = await h.redeem(token);
    assert.equal(r.status, 410, k);
    assert.equal(JSON.stringify(r.body).includes(k), false, k);
  }
  const live = await h.liveKey("cdb_pro_EXPIRED_LINK_1");
  const { token } = await issueKeyRedemption(h.env.API_KEYS_KV, live, { nowMs: Date.now() - (REDEMPTION_TTL_SECONDS + 5) * 1000 });
  assert.equal((await h.redeem(token)).status, 410);
  assert.equal((await h.redeem("Z".repeat(43))).status, 410);
});

test("route: concurrent redemptions of one link reveal the key exactly once", async () => {
  const h = harness();
  const key = await h.liveKey("cdb_pro_CONCURRENT_001");
  const { token } = await issueKeyRedemption(h.env.API_KEYS_KV, key, { tier: "PRO" });
  const results = await Promise.all([1, 2, 3, 4, 5].map(() => h.redeem(token)));
  assert.equal(results.filter((r) => r.status === 200).length, 1);
  assert.equal(results.filter((r) => r.status === 410).length, 4);
});

test("route: without the claim lock nothing is revealed (fail closed) and the link survives", async () => {
  const h = harness({ GUMROAD_PROVISIONING_LOCK: undefined });
  const key = await h.liveKey("cdb_pro_NO_LOCK_00001");
  const { token } = await issueKeyRedemption(h.env.API_KEYS_KV, key, { tier: "PRO" });
  const r = await h.redeem(token);
  assert.equal(r.status, 503);
  assert.equal(r.body.api_key, undefined);
  h.env.GUMROAD_PROVISIONING_LOCK = lockNamespace();
  assert.equal((await h.redeem(token)).body.api_key, key);
});

// --- email delivery, end to end ----------------------------------------------------

test("Gumroad sale: the activation email has no key, and its one-time link reveals exactly the provisioned key", async () => {
  const h = harness();
  const ping = await h.call(`/api/webhooks/gumroad?secret=${GUMROAD_SECRET}`, {
    method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" }, body: new URLSearchParams(SALE).toString(),
  });
  assert.equal(ping.body.status, "provisioned");
  const keys = [...h.env.API_KEYS_KV.store.entries()].map(([k, v]) => { try { const r = JSON.parse(v); return r && r.key === k ? r : null; } catch (_) { return null; } }).filter(Boolean);
  assert.equal(keys.length, 1);
  const key = keys[0].key;
  assert.equal(h.emails.length, 1);
  const mail = h.emails[0];
  assert.deepEqual(mail.to, ["buyer@example.com"]);
  assert.equal(JSON.stringify(mail).includes(key), false, "the email never contains the key");
  assert.equal(/cdb_(pro|ent|mssp|free)_[0-9a-f]{8,}/.test(JSON.stringify(mail)), false, "nor anything key-shaped");
  const token = tokenFrom(mail.html);
  assert.ok(token, "the email carries a one-time link");
  assert.ok(mail.html.includes(`${REDEMPTION_PAGE}#redeem=`), "token in the fragment, not the query");
  const r = await h.redeem(token);
  assert.equal(r.body.api_key, key);
  assert.equal((await h.redeem(token)).status, 410);
});

test("admin re-issue: admin only, mailed to the key's own address, never returns the token or key; dead keys get nothing", async () => {
  const h = harness();
  const key = await h.liveKey("cdb_pro_REISSUE_00001");
  const path = `/api/admin/keys/${key}/redemption`;
  assert.equal((await h.call(path, { method: "POST" })).status, 403);
  assert.equal(h.emails.length, 0);
  const ok = await h.call(path, { method: "POST", headers: { "X-Admin-Key": ADMIN, "content-type": "application/json" }, body: JSON.stringify({ to: "attacker@example.net" }) });
  assert.equal(ok.status, 200);
  assert.equal(ok.body.sent, true);
  assert.equal(JSON.stringify(ok.body).includes(key), false);
  assert.equal(h.emails.length, 1);
  assert.deepEqual(h.emails[0].to, ["buyer@example.com"], "never a caller-supplied address");
  assert.equal((await h.redeem(tokenFrom(h.emails[0].html))).body.api_key, key);

  const dead = await h.liveKey("cdb_pro_REISSUE_DEAD01", { subscription_status: "refunded" });
  const refused = await h.call(`/api/admin/keys/${dead}/redemption`, { method: "POST", headers: { "X-Admin-Key": ADMIN } });
  assert.equal(refused.status, 409);
  assert.equal((await h.call("/api/admin/keys/cdb_pro_NOPE/redemption", { method: "POST", headers: { "X-Admin-Key": ADMIN } })).status, 404);
  assert.equal(h.emails.length, 1, "no email for a dead or unknown key");
});
