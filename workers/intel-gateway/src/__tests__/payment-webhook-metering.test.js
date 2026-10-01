/**
 * Payment-provider webhooks and the anonymous commercial gate, through the
 * REAL gateway router (watchdog-harness.js supplies the env; index.js's
 * default export serves the request).
 *
 * Defect (F9, docs/CUSTOMER_RELEASE_LEDGER.md): /api/webhooks/razorpay and
 * /api/webhooks/gumroad are dispatched AFTER the commercial rate/daily gate.
 * A delivery carries a signature (Razorpay: HMAC-SHA256 of the raw body in
 * X-Razorpay-Signature) or a shared secret (Gumroad: ?secret=), never a
 * customer credential, so it resolved to anonymous FREE: 30/min against the
 * per-IP minute bucket (rl:{ip}:{minute}) and 50/day against the IP's FREE
 * daily quota. A provider egress IP that had made 30 deliveries in a minute,
 * or 50 in a UTC day, got 429 for the next one: a paid order or sale was not
 * provisioned until the provider retried, and a provider disables an
 * endpoint that keeps failing.
 *
 * Contract after the fix: a delivery that passes its route's own check is
 * not metered against the anonymous budget. Anything else (missing, wrong or
 * crossed secret, a signature over a different body, an unconfigured secret,
 * a body over the verification cap) is metered exactly as before, and the
 * handlers still verify every delivery themselves.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { createHmac } from "node:crypto";

import worker from "../index.js";
import { harness } from "./watchdog-harness.js";
import { dailyQuotaKey, utcDateString } from "../daily-quota.js";

const RZP_SECRET = "rzp-webhook-test-secret";
const GUM_SECRET = "gumroad-webhook-test-secret";

function h() {
  const hx = harness();
  hx.env.RAZORPAY_WEBHOOK_SECRET = RZP_SECRET;
  hx.env.GUMROAD_WEBHOOK_SECRET = GUM_SECRET;
  return hx;
}

// Pin the clock mid-window so no test straddles a minute boundary (the
// counter assertions read the current window's bucket).
function freezeClock() {
  const real = Date.now;
  const t = Math.floor(real() / 60000) * 60000 + 30000;
  Date.now = () => t;
  return () => { Date.now = real; };
}

const bucketKey = (ip) => `rl:${ip}:${Math.floor(Date.now() / 60000)}`;

function saturateMinuteBucket(hx, ip, count = 45) {
  hx.env.RATE_LIMIT_KV.map.set(bucketKey(ip), String(count));
}

function exhaustFreeDailyQuota(hx, ip) {
  hx.env.RATE_LIMIT_KV.map.set(dailyQuotaKey(ip, utcDateString()), "50");
}

async function post(hx, path, { headers = {}, body = "" } = {}) {
  const waits = [];
  const res = await worker.fetch(new Request("https://intel.cyberdudebivash.com" + path, {
    method: "POST", headers, body,
  }), hx.env, { waitUntil: (p) => waits.push(p) });
  await Promise.allSettled(waits);
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch { json = null; }
  return { status: res.status, body: json, headers: res.headers };
}

const sign = (raw, secret = RZP_SECRET) => createHmac("sha256", secret).update(raw).digest("hex");

function razorpayOrder(id) {
  return JSON.stringify({ event: "payment.captured", payload: { payment: { entity: {
    id, amount: 410000, currency: "INR", status: "captured", order_id: "order_" + id, invoice_id: null,
    email: "buyer@example.com", notes: { tier: "PRO", email: "buyer@example.com", billing: "monthly" },
  } } } });
}

function razorpay(hx, ip, raw, signature = sign(raw)) {
  const headers = { "cf-connecting-ip": ip, "content-type": "application/json" };
  if (signature !== null) headers["x-razorpay-signature"] = signature;
  return post(hx, "/api/webhooks/razorpay", { headers, body: raw });
}

const gumroadSale = (saleId) => new URLSearchParams({
  sale_id: saleId, email: "buyer@example.com", permalink: "pxyfcb", price: "4900", currency: "usd",
  product_name: "SENTINEL APEX PRO",
}).toString();

function gumroad(hx, ip, form, secret = GUM_SECRET) {
  const qs = secret === null ? "" : "?secret=" + encodeURIComponent(secret);
  return post(hx, "/api/webhooks/gumroad" + qs, {
    headers: { "cf-connecting-ip": ip, "content-type": "application/x-www-form-urlencoded" }, body: form,
  });
}

test("reproduction: a signed Razorpay order payment from a busy provider IP is provisioned", async (t) => {
  t.after(freezeClock());
  const hx = h();
  const ip = "203.0.113.40";
  saturateMinuteBucket(hx, ip);
  const res = await razorpay(hx, ip, razorpayOrder("pay_F9_RZP1"));
  assert.equal(res.status, 200, "the provider delivery was metered as anonymous FREE traffic: " + JSON.stringify(res.body));
  assert.equal(res.body.status, "provisioned");
  assert.equal(res.body.tier, "PRO");
  assert.ok(hx.env.SECURITY_HUB_KV.map.has("payment_key_map:pay_F9_RZP1"), "the paid order received a key");
  assert.equal(hx.env.RATE_LIMIT_KV.map.get(bucketKey(ip)), "45", "a verified delivery spends no anonymous budget");
});

test("reproduction: a Gumroad sale with the valid secret from a busy provider IP is provisioned", async (t) => {
  t.after(freezeClock());
  const hx = h();
  const ip = "203.0.113.41";
  saturateMinuteBucket(hx, ip);
  exhaustFreeDailyQuota(hx, ip);
  const res = await gumroad(hx, ip, gumroadSale("sale_F9_GUM1"));
  assert.equal(res.status, 200, "the provider delivery was metered as anonymous FREE traffic: " + JSON.stringify(res.body));
  assert.equal(res.body.status, "provisioned");
  assert.equal(res.body.tier, "PRO");
  assert.equal(hx.env.RATE_LIMIT_KV.map.get(bucketKey(ip)), "45");
  assert.equal(hx.env.RATE_LIMIT_KV.map.get(dailyQuotaKey(ip, utcDateString())), "50");
});

test("verified Razorpay deliveries pass an exhausted FREE daily quota and spend none of it", async (t) => {
  t.after(freezeClock());
  const hx = h();
  const ip = "203.0.113.42";
  exhaustFreeDailyQuota(hx, ip);
  for (const id of ["pay_F9_D1", "pay_F9_D2", "pay_F9_D3"]) {
    const res = await razorpay(hx, ip, razorpayOrder(id));
    assert.equal(res.status, 200, JSON.stringify(res.body));
    assert.equal(res.body.status, "provisioned");
  }
  assert.equal(hx.env.RATE_LIMIT_KV.map.get(dailyQuotaKey(ip, utcDateString())), "50");
  assert.equal(hx.env.RATE_LIMIT_KV.map.get(bucketKey(ip)), undefined, "no anonymous minute budget spent");
});

test("negative controls: unverified Razorpay deliveries are still metered and provision nothing", async (t) => {
  t.after(freezeClock());
  const hx = h();
  const ip = "203.0.113.43";
  saturateMinuteBucket(hx, ip);
  const raw = razorpayOrder("pay_F9_NEG");
  const cases = [
    ["no signature", raw, null],
    ["signature made with another secret", raw, sign(raw, "not-the-secret")],
    ["signature over a different body", raw, sign(razorpayOrder("pay_F9_OTHER"))],
    ["Gumroad secret used as the Razorpay key", raw, sign(raw, GUM_SECRET)],
    ["non-hex signature", raw, "zz-not-hex"],
  ];
  for (const [label, body, signature] of cases) {
    const res = await razorpay(hx, ip, body, signature);
    assert.equal(res.status, 429, `${label}: must not escape anonymous metering`);
    assert.equal(res.headers.get("Retry-After"), "60");
  }
  assert.equal(hx.env.RATE_LIMIT_KV.map.get(bucketKey(ip)), String(45 + cases.length), "each unverified delivery was counted");
  assert.equal(hx.env.SECURITY_HUB_KV.map.has("payment_key_map:pay_F9_NEG"), false, "nothing provisioned");
});

test("negative controls: Razorpay verification is bounded and needs a configured secret", async (t) => {
  t.after(freezeClock());
  const hx = h();
  const ip = "203.0.113.44";
  saturateMinuteBucket(hx, ip);

  // A correctly signed body over the 64 KiB verification cap is not read
  // in full at the gate, so it is metered like any unverified request.
  const big = JSON.stringify({ event: "payment.authorized", padding: "x".repeat(70 * 1024) });
  const bigRes = await razorpay(hx, ip, big);
  assert.equal(bigRes.status, 429, "an oversized body must not be verified at the gate");

  // With no RAZORPAY_WEBHOOK_SECRET nothing can be verified, so nothing is exempt.
  delete hx.env.RAZORPAY_WEBHOOK_SECRET;
  const unconfigured = await razorpay(hx, ip, razorpayOrder("pay_F9_UNSET"));
  assert.equal(unconfigured.status, 429);
});

test("negative controls: unverified Gumroad pings are still metered and provision nothing", async (t) => {
  t.after(freezeClock());
  const hx = h();
  const ip = "203.0.113.45";
  saturateMinuteBucket(hx, ip);
  const form = gumroadSale("sale_F9_NEG");
  for (const [label, secret] of [["no secret", null], ["wrong secret", "not-the-secret"], ["Razorpay secret", RZP_SECRET], ["empty secret", ""]]) {
    const res = await gumroad(hx, ip, form, secret);
    assert.equal(res.status, 429, `${label}: must not escape anonymous metering`);
  }
  assert.equal(hx.env.RATE_LIMIT_KV.map.get(bucketKey(ip)), "49");
  assert.equal(hx.env.SECURITY_HUB_KV.map.has("gumroad_sale:sale_F9_NEG"), false, "nothing provisioned");

  delete hx.env.GUMROAD_WEBHOOK_SECRET;
  const unconfigured = await gumroad(hx, ip, form, GUM_SECRET);
  assert.equal(unconfigured.status, 429, "with no configured secret nothing is exempt");
});

test("only POST deliveries to the two webhook routes are exempt", async (t) => {
  t.after(freezeClock());
  const hx = h();
  const ip = "203.0.113.46";
  saturateMinuteBucket(hx, ip);

  // The valid Gumroad secret on another route buys nothing.
  const other = await post(hx, "/api/sla/ping?secret=" + GUM_SECRET, { headers: { "cf-connecting-ip": ip } });
  assert.equal(other.status, 429);

  // A GET carrying the valid secret is not a provider delivery.
  const waits = [];
  const get = await worker.fetch(new Request("https://intel.cyberdudebivash.com/api/webhooks/gumroad?secret=" + GUM_SECRET, {
    method: "GET", headers: { "cf-connecting-ip": ip },
  }), hx.env, { waitUntil: (p) => waits.push(p) });
  await Promise.allSettled(waits);
  assert.equal(get.status, 429);
});
