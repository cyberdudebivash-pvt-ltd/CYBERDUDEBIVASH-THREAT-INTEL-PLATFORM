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
    email: "buyer@example.com", notes: { platform: "SENTINEL-APEX", tier: "PRO", email: "buyer@example.com", billing: "monthly" },
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

// ---------------------------------------------------------------------------
// Adversarial audit (2026-10-01, post-merge of #636). The exemption must be
// granted ONLY to a delivery the real handler accepts: each case is sent from
// a fresh IP (the handler's own verdict) and from a saturated IP (the gate's
// verdict). Exempt implies accepted, always; accepted implies exempt for every
// body within the 64 KiB verification cap.
// ---------------------------------------------------------------------------

function freshIp(n) { return `198.18.${Math.floor(n / 250)}.${(n % 250) + 1}`; }

async function verdicts(hx, n, send) {
  const handler = await send(freshIp(n));
  const ip = freshIp(n + 1000);
  saturateMinuteBucket(hx, ip);
  const gate = await send(ip);
  return { accepted: handler.status !== 401, exempt: gate.status !== 429, handler, gate };
}

function rawRazorpay(hx, ip, bytes, signature) {
  return post(hx, "/api/webhooks/razorpay", {
    headers: { "cf-connecting-ip": ip, "content-type": "application/json", "x-razorpay-signature": signature },
    body: bytes,
  });
}

const enc = new TextEncoder();
const hmacHex = (bytesOrString, secret = RZP_SECRET) => createHmac("sha256", secret).update(bytesOrString).digest("hex");

test("audit: Razorpay exemption tracks the handler's own verdict, byte for byte", async (t) => {
  t.after(freezeClock());
  const hx = h();
  const event = JSON.stringify({ event: "payment.authorized", payload: {} });
  const bom = new Uint8Array([0xef, 0xbb, 0xbf, ...enc.encode(event)]);
  // Invalid UTF-8 (a lone 0xC3) inside a JSON string value.
  const invalid = new Uint8Array([...enc.encode('{"event":"payment.authorized","note":"'), 0xc3, ...enc.encode('"}')]);
  const invalidDecoded = new TextDecoder().decode(invalid);
  const atCap = (() => { const pad = 64 * 1024 - enc.encode('{"event":"payment.authorized","p":""}').length; return enc.encode(`{"event":"payment.authorized","p":"${"x".repeat(pad)}"}`); })();
  assert.equal(atCap.byteLength, 64 * 1024);
  const overCap = enc.encode(`{"event":"payment.authorized","p":"${"x".repeat(64 * 1024)}"}`);

  const cases = [
    // [label, body bytes, signature, expect handler accepts, expect exempt]
    ["valid body and signature", enc.encode(event), hmacHex(event), true, true],
    ["BOM-prefixed, signed over raw bytes incl. BOM", bom, hmacHex(bom), false, false],
    ["BOM-prefixed, signed over the decoded text", bom, hmacHex(event), true, true],
    ["invalid UTF-8, signed over raw bytes", invalid, hmacHex(invalid), false, false],
    ["invalid UTF-8, signed over the replacement-decoded text", invalid, hmacHex(invalidDecoded), true, true],
    ["exactly 64 KiB, valid signature", atCap, hmacHex(atCap), true, true],
    ["64 KiB + 34 bytes, valid signature (over the cap: metered)", overCap, hmacHex(overCap), true, false],
    ["signature in upper-case hex", enc.encode(event), hmacHex(event).toUpperCase(), true, true],
    ["truncated signature", enc.encode(event), hmacHex(event).slice(0, 62), false, false],
    ["signature with a trailing byte", enc.encode(event), hmacHex(event) + "00", false, false],
    ["empty body, signature over empty string", new Uint8Array(0), hmacHex(""), true, true],
  ];
  let n = 0;
  for (const [label, bytes, sig, expectAccepted, expectExempt] of cases) {
    const v = await verdicts(hx, n++, (ip) => rawRazorpay(hx, ip, bytes, sig));
    assert.equal(v.accepted, expectAccepted, `${label}: handler verdict (HTTP ${v.handler.status} ${JSON.stringify(v.handler.body)})`);
    assert.equal(v.exempt, expectExempt, `${label}: gate verdict (HTTP ${v.gate.status})`);
    assert.ok(!v.exempt || v.accepted, `${label}: exempt but the handler rejects it`);
    if (v.exempt) assert.equal(v.gate.status, v.handler.status, `${label}: exempt request answered like the handler`);
  }
});

test("audit: Gumroad exemption reads the same query value the handler reads", async (t) => {
  t.after(freezeClock());
  const hx = h();
  const form = new URLSearchParams({ subscription_id: "sub_F9_AUDIT", cancelled: "true" }).toString();
  const send = (qs, body = form) => (ip) => post(hx, "/api/webhooks/gumroad" + qs, {
    headers: { "cf-connecting-ip": ip, "content-type": "application/x-www-form-urlencoded" }, body,
  });
  const cases = [
    ["valid secret", "?secret=" + encodeURIComponent(GUM_SECRET), true],
    ["percent-encoded valid secret", "?secret=" + [...GUM_SECRET].map((c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0")).join(""), true],
    ["wrong secret first, valid second (first value wins in both)", "?secret=nope&secret=" + GUM_SECRET, false],
    ["valid secret first, wrong second", "?secret=" + GUM_SECRET + "&secret=nope", true],
    ["wrong-case parameter name", "?Secret=" + GUM_SECRET, false],
    ["valid secret plus a NUL byte", "?secret=" + GUM_SECRET + "%00", false],
    ["valid secret as a prefix only", "?secret=" + GUM_SECRET.slice(0, -1), false],
    ["secret moved into the POST body", "", false],
  ];
  let n = 100;
  for (const [label, qs, expected] of cases) {
    const body = label === "secret moved into the POST body" ? form + "&secret=" + encodeURIComponent(GUM_SECRET) : form;
    const v = await verdicts(hx, n++, send(qs, body));
    assert.equal(v.accepted, expected, `${label}: handler verdict (HTTP ${v.handler.status})`);
    assert.equal(v.exempt, expected, `${label}: gate verdict (HTTP ${v.gate.status})`);
  }
});

test("audit: replayed deliveries stay idempotent while exempt", async (t) => {
  t.after(freezeClock());
  const hx = h();
  const ip = "203.0.113.60";
  saturateMinuteBucket(hx, ip);
  const raw = razorpayOrder("pay_F9_REPLAY");
  const first = await razorpay(hx, ip, raw);
  const second = await razorpay(hx, ip, raw);
  assert.equal(first.body.status, "provisioned");
  assert.equal(second.status, 200);
  assert.equal(second.body.status, "already_provisioned", "a replayed signed order must not mint a second key");
  const sale = gumroadSale("sale_F9_REPLAY");
  const g1 = await gumroad(hx, ip, sale);
  const g2 = await gumroad(hx, ip, sale);
  assert.equal(g1.body.status, "provisioned");
  assert.equal(g2.body.status, "already_provisioned", "a replayed Gumroad sale must not mint a second key");
  assert.equal(hx.env.RATE_LIMIT_KV.map.get(bucketKey(ip)), "45", "verified replays spend no anonymous budget");
});
