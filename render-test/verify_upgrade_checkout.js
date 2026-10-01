#!/usr/bin/env node
/**
 * SENTINEL APEX -- upgrade.html checkout (real browser).
 *
 * Owner commercial policy (2026-09-24): PRO / Enterprise / MSSP are recurring
 * services sold ONLY as Razorpay Subscriptions (no one-time Order fallback).
 * Checkout P0 (2026-10-01): Razorpay is the one primary checkout; Gumroad is
 * the secondary checkout, offered only while GET /api/pricing reports that a
 * Gumroad sale is provisioned and delivered automatically; assisted payments
 * are one contact note, never a checkout path. Failures are shown inline
 * (never alert()), and nothing claims success before the backend confirms.
 *
 * Headless Chromium drives the shipped page with every network edge stubbed
 * (no real payment, no Razorpay call): checkout.razorpay.com is replaced by a
 * recorder, and the billing APIs answer fixtures. All identifiers here are
 * test-only fixtures.
 *
 * Checks:
 *   1. configured plan: Subscriptions modal opens with the subscription id;
 *      buyer GSTIN / state / name / address reach subscriptions/create; the
 *      page sends no price; no one-time order is ever created
 *   2. every pre-payment failure is inline, says no payment was taken and
 *      leaves a working retry: plan not configured (503), provider error,
 *      network drop, Razorpay script blocked, already subscribed (409),
 *      payment already in progress (409), invalid email / GSTIN in the page,
 *      a server field refusal next to its field, a declined attempt, a
 *      closed checkout window
 *   3. after payment authorization (state machine):
 *      - backend confirms "active" + key -> ACTIVE; the key stays masked
 *        until the buyer reveals it; activation actions shown
 *      - backend not yet active (timeout / offline) -> ACTIVATION_PENDING:
 *        never "failed", never "provisioned", masked reference, pay button
 *        stays disabled even after a late ondismiss, recheck works
 *      - a reload resumes the tab's own pending activation
 *      - ?checkout=success in the URL renders no success state
 *   4. Gumroad (secondary): grant / membership labels when available; no
 *      Gumroad link at all when unavailable, unconfirmed, or for MSSP
 *   5. deep links: ?plan= selects the plan; an unknown plan selects nothing
 *      paid and says so; utm_* stay in the URL; amount / price / tier /
 *      currency in the URL change nothing
 *   6. no manual-payment UI (proof upload, UTR, QR, UPI handles, bank or
 *      crypto details); the assisted note is verbatim, has both contact
 *      addresses, sits below both automated checkouts and has no pay button
 *   7. copy: no retracted claims; the refund guarantee is qualified and
 *      linked; Razorpay renewal and cancellation stated
 *   8. layout at 320 / 360 / 390 / 430 / 768 / 1280 px: no horizontal
 *      overflow, Razorpay CTA fully visible and >= 44px tall, Razorpay above
 *      Gumroad above the assisted note; keyboard: plan radios and the
 *      Razorpay button work without a mouse
 *   9. no page error and no alert() dialog on any path
 *
 * Usage:
 *   PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers NODE_PATH="$(npm root -g)" \
 *     node render-test/verify_upgrade_checkout.js [root]   (default: repo root; CI passes dist)
 *   UPGRADE_HTML=/path/to/other/upgrade.html ...   (serve another revision)
 *   CHECKOUT_SCREENSHOT_DIR=/some/dir ...         (also save layout screenshots)
 *
 * Exit 0 = all checks passed, 1 = at least one failed.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { startStaticServer } = require('./lib/static-server');
const { chromium } = require('playwright');

const ROOT = path.resolve(process.argv[2] || path.join(__dirname, '..'));
const PORT = 8791;
const ORIGIN = `http://127.0.0.1:${PORT}`;
const MIME = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.ico': 'image/x-icon' };
const OVERRIDE = process.env.UPGRADE_HTML ? fs.readFileSync(process.env.UPGRADE_HTML, 'utf8') : null;
const SHOTS = process.env.CHECKOUT_SCREENSHOT_DIR || '';
const SUB_ID = 'sub_TESTFIXTURE01';
const KEY = 'cdb_test_fixture_only_key';
const ASSISTED = 'Need an alternative payment method? Assisted payments via crypto, Paytm, PayPal, UPI, Amazon Pay or bank NEFT ' +
  'may be arranged by contacting contact@cyberdudebivash.in or bivash@cyberdudebivash.com. Access is provisioned only after payment verification.';

const RAZORPAY_STUB = `
  window.__rzp = { opened: [], options: null, handlers: {} };
  window.Razorpay = function (options) {
    window.__rzp.options = options;
    this.on = function (ev, fn) { window.__rzp.handlers[ev] = fn; };
    this.open = function () { window.__rzp.opened.push(options); };
  };`;

const pricing = (gumroad) => ({
  status: 'transitional', currency: 'INR', unit: 'paise',
  tiers: {
    PRO: { monthly: 410000, annual: 4100000 },
    ENTERPRISE: { monthly: 4160000, annual: 41600000 },
    MSSP: { monthly: 8330000, annual: 83300000 },
  },
  checkout: {
    razorpay: { role: 'primary', currency: 'INR', billing: 'subscription' },
    gumroad: gumroad ? { role: 'secondary', currency: 'USD', available: true }
                     : { role: 'secondary', currency: 'USD', available: false, reason: 'automated_provisioning_not_configured' },
  },
});

let failures = 0;
function check(name, ok, detail) {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok || !detail ? '' : '  -- ' + detail}`);
  if (!ok) failures++;
}
const allDialogs = [];
const allErrors = [];

async function open(browser, opts = {}) {
  const context = await browser.newContext({ viewport: opts.viewport || { width: 1280, height: 900 } });
  const page = await context.newPage();
  const rec = { errors: [], dialogs: [], subs: [], orders: [], statusCalls: [], feedCalls: [] };
  page.on('pageerror', (e) => { rec.errors.push(String(e && e.message || e)); allErrors.push(String(e && e.message || e)); });
  page.on('dialog', async (d) => { rec.dialogs.push(d.message()); allDialogs.push(d.message()); await d.dismiss(); });
  await page.route('**/*', async (route) => {
    const url = route.request().url();
    if (url.startsWith('https://checkout.razorpay.com/')) {
      return route.fulfill({ status: 200, contentType: 'application/javascript', body: opts.razorpay === 'blocked' ? '/* blocked */' : RAZORPAY_STUB });
    }
    if (!url.startsWith(ORIGIN)) return route.abort();
    const u = new URL(url);
    const p = u.pathname;
    if (p === '/upgrade.html' && OVERRIDE) return route.fulfill({ status: 200, contentType: 'text/html', body: OVERRIDE });
    if (p === '/api/pricing') {
      if (opts.pricing === 'network') return route.abort();
      if (!opts.pricing) return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(opts.pricing) });
    }
    if (p === '/api/v2/billing/subscriptions/create') {
      rec.subs.push(JSON.parse(route.request().postData() || '{}'));
      if (opts.subStatus === 'network') return route.abort();
      const body = opts.subBody || { subscription_id: SUB_ID, key_id: 'rzp_test_key', tier: 'PRO', billing_cycle: 'monthly', status: 'created' };
      return route.fulfill({ status: opts.subStatus || 200, contentType: 'application/json', body: JSON.stringify(body) });
    }
    if (p === '/api/payment/razorpay/create-order') {
      rec.orders.push(JSON.parse(route.request().postData() || '{}'));
      return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ error: 'subscription_required' }) });
    }
    if (p === '/api/v2/billing/subscriptions/status') {
      rec.statusCalls.push(u.searchParams.toString());
      const replies = opts.statusReplies || [{ body: { status: 'created', tier: 'PRO' } }];
      const r = replies[Math.min(rec.statusCalls.length - 1, replies.length - 1)];
      if (r === 'network') return route.abort();
      return route.fulfill({ status: r.status || 200, contentType: 'application/json', body: JSON.stringify(r.body) });
    }
    if (p === '/api/feed') {
      rec.feedCalls.push(route.request().headers()['x-api-key'] || '');
      return route.fulfill({ status: 200, contentType: 'application/json', body: '{"items":[]}' });
    }
    if (p.startsWith('/api/')) return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' });
    return route.continue();
  });
  await page.goto(`${ORIGIN}/upgrade.html${opts.query || ''}`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof window.initiateRazorpayCheckout === 'function', null, { timeout: 15000 });
  if (opts.razorpay !== 'blocked') await page.waitForFunction(() => typeof window.Razorpay === 'function', null, { timeout: 15000 });
  else await page.waitForLoadState('load');
  // Gumroad availability resolved (a revision without it is reported by the
  // checks below, not as a crash).
  await page.waitForFunction(() => window.CHECKOUT_AVAILABILITY && window.CHECKOUT_AVAILABILITY.gumroad !== null, null, { timeout: 15000 })
    .catch(() => { rec.errors.push('checkout availability never resolved'); });
  if (opts.pollAttempts !== undefined) await page.evaluate((n) => { ACTIVATION_POLL_MAX_ATTEMPTS = n; }, opts.pollAttempts);
  return { context, page, rec, opts };
}

async function fillAndPay(page, { plan = 'pro', email = 'buyer@example.com', gstin, fill = {}, click = true } = {}) {
  await page.evaluate((p) => selectPlan(p), plan);
  if (email !== null) await page.fill('#rzp-email', email);
  if (gstin !== undefined || Object.keys(fill).length) await page.evaluate(() => { const d = document.getElementById('tax-details'); if (d) d.open = true; });
  if (gstin !== undefined) await page.fill('#rzp-gstin', gstin);
  if (fill.state) await page.selectOption('#rzp-billing-state', fill.state);
  // Set directly: the field is hidden unless "Outside India" is chosen, and a
  // value typed before switching back to an Indian state must not be sent.
  if (fill.country) await page.evaluate((v) => { document.getElementById('rzp-billing-country').value = v; }, fill.country);
  if (fill.name) await page.fill('#rzp-billing-name', fill.name);
  if (fill.address) await page.fill('#rzp-billing-address', fill.address);
  if (click) await page.click('#rzp-pay-btn');
  await page.waitForTimeout(300);
}

const status = (page) => page.evaluate(() => {
  const s = document.getElementById('checkout-status');
  if (!s) return { hidden: true, role: null, text: '', links: [] };
  return { hidden: s.hidden, role: s.getAttribute('role'), text: s.innerText, links: [...s.querySelectorAll('a')].map((a) => a.getAttribute('href')) };
});
const state = (page) => page.evaluate(() => document.body.getAttribute('data-checkout-state') || 'IDLE');
const payDisabled = (page) => page.evaluate(() => document.getElementById('rzp-pay-btn').disabled);
const modalCount = (page) => page.evaluate(() => (window.__rzp ? window.__rzp.opened.length : 0));
const authorize = (page) => page.evaluate(() => window.__rzp.options.handler({ razorpay_payment_id: 'pay_T1', razorpay_signature: 'test_only_signature' }));
const waitState = (page, s, ms = 10000) => page.waitForFunction((x) => document.body.getAttribute('data-checkout-state') === x, s, { timeout: ms });
const result = (page) => page.evaluate(() => ({
  state: document.body.getAttribute('data-checkout-state'),
  title: document.getElementById('success-title').textContent,
  ref: document.getElementById('success-review-id').textContent,
  text: document.getElementById('success-state').innerText,
  html: document.getElementById('success-state').innerHTML,
  visible: document.getElementById('success-state').style.display === 'block',
  checkoutHidden: document.getElementById('checkout-state').style.display === 'none',
  actions: document.getElementById('activation-actions').style.display,
  keyBoxHidden: document.getElementById('activation-key-box').hidden,
  key: document.getElementById('activation-key').textContent,
  payDisabled: document.getElementById('rzp-pay-btn').disabled,
}));

(async () => {
  const server = await startStaticServer(ROOT, PORT, MIME);
  const browser = await chromium.launch();
  try {
    // ── 1. configured plan ───────────────────────────────────────────────
    {
      const { context, page, rec } = await open(browser);
      await fillAndPay(page, { gstin: '21arkpn8270g1zp', fill: { name: 'Acme Security Pvt Ltd', address: '12 MG Road, Bengaluru 560001' } });
      const rzp = await page.evaluate(() => window.__rzp);
      check('configured plan: subscriptions/create called once', rec.subs.length === 1, JSON.stringify(rec.subs));
      check('configured plan: Razorpay opened with the subscription id',
        rzp.opened.length === 1 && rzp.options && rzp.options.subscription_id === SUB_ID && !rzp.options.order_id && !rzp.options.amount);
      check('configured plan: no price or amount sent by the page', rec.subs[0] && !('amount' in rec.subs[0]) && !('price' in rec.subs[0]) && !('plan_id' in rec.subs[0]));
      check('configured plan: buyer GSTIN, name and address sent',
        rec.subs[0] && rec.subs[0].gstin === '21ARKPN8270G1ZP' && rec.subs[0].billing_name === 'Acme Security Pvt Ltd' &&
        rec.subs[0].billing_address === '12 MG Road, Bengaluru 560001', JSON.stringify(rec.subs[0]));
      check('configured plan: no one-time order', rec.orders.length === 0);
      check('configured plan: state CHECKOUT_OPEN, pay button disabled while the window is open',
        (await state(page)) === 'CHECKOUT_OPEN' && (await payDisabled(page)));
      check('configured plan: no page error', rec.errors.length === 0, rec.errors.join(' | '));
      await context.close();
    }
    {
      const s = await open(browser);
      await fillAndPay(s.page, { fill: { state: '27', country: 'US' } });
      const countryVisible = await s.page.evaluate(() => document.getElementById('rzp-country-row').style.display !== 'none');
      check('billing state sent when chosen', s.rec.subs[0] && s.rec.subs[0].billing_state === '27', JSON.stringify(s.rec.subs[0]));
      check('a buyer in India sends no country (field hidden)', s.rec.subs[0] && !('billing_country' in s.rec.subs[0]) && !countryVisible,
        JSON.stringify(s.rec.subs[0]));
      await s.context.close();
      const a = await open(browser);
      await fillAndPay(a.page, { fill: { state: 'OUTSIDE_INDIA', country: 'sg' } });
      const abroadVisible = await a.page.evaluate(() => document.getElementById('rzp-country-row').style.display !== 'none');
      check('a buyer outside India sees and sends the country (export invoice)',
        abroadVisible && a.rec.subs[0] && a.rec.subs[0].billing_state === 'OUTSIDE_INDIA' && a.rec.subs[0].billing_country === 'SG',
        JSON.stringify(a.rec.subs[0]));
      await a.context.close();
    }

    // ── 2. pre-payment failures: inline, no payment taken, retry works ─────
    {
      const m = await open(browser, { subStatus: 503, subBody: { error: 'plan_price_unverified', message: 'This billing cycle is temporarily unavailable. No payment was taken.' } });
      await fillAndPay(m.page);
      const st = await status(m.page);
      check('plan not configured (503): NO one-time order fallback, no modal', m.rec.orders.length === 0 && (await modalCount(m.page)) === 0);
      check('plan not configured: inline alert "temporarily unavailable. No payment was taken."',
        !st.hidden && st.role === 'alert' && /This billing cycle is temporarily unavailable\. No payment was taken\./.test(st.text), JSON.stringify(st));
      check('plan not configured: pay button usable again (retry), state FAILED', !(await payDisabled(m.page)) && (await state(m.page)) === 'FAILED');
      await m.context.close();
    }
    {
      const e = await open(browser, { subStatus: 502, subBody: { error: 'Razorpay subscription creation failed', message: 'Checkout could not be started. No payment was taken.' } });
      await fillAndPay(e.page);
      const st = await status(e.page);
      check('provider error (502): inline, no payment taken, no modal',
        st.role === 'alert' && /could not be started\. No payment was taken/.test(st.text) && (await modalCount(e.page)) === 0, JSON.stringify(st));
      await e.context.close();
    }
    {
      const opts = { subStatus: 'network' };
      const n = await open(browser, opts);
      await fillAndPay(n.page);
      const st = await status(n.page);
      check('network drop on create: inline, no payment taken, retry enabled',
        st.role === 'alert' && /No payment was taken/.test(st.text) && /connection/.test(st.text) && !(await payDisabled(n.page)), JSON.stringify(st));
      n.opts.subStatus = 200;
      await n.page.click('#rzp-pay-btn');
      await n.page.waitForTimeout(300);
      check('network drop: retry opens checkout once the connection is back', (await modalCount(n.page)) === 1 && n.rec.subs.length === 2);
      await n.context.close();
    }
    {
      const b = await open(browser, { razorpay: 'blocked' });
      await fillAndPay(b.page);
      const st = await status(b.page);
      check('Razorpay script blocked: inline, no payment taken, retry enabled',
        st.role === 'alert' && /could not load\. No payment was taken/.test(st.text) && !(await payDisabled(b.page)), JSON.stringify(st));
      await b.context.close();
    }
    {
      const d = await open(browser, { subStatus: 409, subBody: { error: 'already_subscribed', billing_center_url: '/billing.html' } });
      await fillAndPay(d.page);
      const st = await status(d.page);
      check('already subscribed: no modal, inline note with a Billing Center link, no payment taken',
        (await modalCount(d.page)) === 0 && /already have an active subscription/.test(st.text) && /no payment was taken/i.test(st.text) &&
        st.links.includes('/billing.html'), JSON.stringify(st));
      await d.context.close();
    }
    {
      const ip = await open(browser, { subStatus: 409, subBody: { error: 'checkout_in_progress', message: 'x' } });
      await fillAndPay(ip.page);
      const st = await status(ip.page);
      check('payment already in progress (409): no modal, told not to pay again',
        (await modalCount(ip.page)) === 0 && /do not pay again/i.test(st.text) && /No new payment was started/.test(st.text), JSON.stringify(st));
      await ip.context.close();
    }
    {
      const v = await open(browser);
      await fillAndPay(v.page, { email: 'not-an-email' });
      const err = await v.page.evaluate(() => ({ text: document.getElementById('rzp-email-error').textContent, hidden: document.getElementById('rzp-email-error').hidden,
        invalid: document.getElementById('rzp-email').getAttribute('aria-invalid'), focused: document.activeElement && document.activeElement.id }));
      check('invalid email: inline field error, focused, aria-invalid, no request',
        !err.hidden && /valid email/.test(err.text) && err.invalid === 'true' && err.focused === 'rzp-email' && v.rec.subs.length === 0, JSON.stringify(err));
      await v.context.close();
    }
    {
      const g = await open(browser);
      await fillAndPay(g.page, { gstin: '22AAAAA0000A1Z5' });
      const err = await g.page.evaluate(() => ({ text: document.getElementById('rzp-gstin-error').textContent, invalid: document.getElementById('rzp-gstin').getAttribute('aria-invalid'),
        open: document.getElementById('tax-details').open }));
      check('invalid GSTIN: refused in the page next to the field', /GSTIN/.test(err.text) && err.invalid === 'true' && err.open, JSON.stringify(err));
      check('invalid GSTIN: no request, no modal, no order', g.rec.subs.length === 0 && g.rec.orders.length === 0 && (await modalCount(g.page)) === 0);
      await g.context.close();
    }
    {
      const r = await open(browser, { subStatus: 400, subBody: { error: 'Billing address must be 10-250 characters.', field: 'billing_address' } });
      await fillAndPay(r.page, { gstin: 'DE123456789' });
      const err = await r.page.evaluate(() => ({ text: document.getElementById('rzp-billing-address-error').textContent,
        invalid: document.getElementById('rzp-billing-address').getAttribute('aria-invalid') }));
      check('server field refusal shown verbatim next to its field', err.text === 'Billing address must be 10-250 characters.' && err.invalid === 'true', JSON.stringify(err));
      check('server field refusal: no modal, no order, retry enabled', (await modalCount(r.page)) === 0 && r.rec.orders.length === 0 && !(await payDisabled(r.page)));
      await r.context.close();
    }
    {
      const c = await open(browser);
      await fillAndPay(c.page);
      await c.page.evaluate(() => window.__rzp.handlers['payment.failed']({ error: { description: 'TEST_ONLY declined by issuer' } }));
      const st = await status(c.page);
      check('declined attempt: inline, the buyer may retry in the open window, no "no charge" claim',
        st.role === 'alert' && /did not go through/.test(st.text) && /TEST_ONLY declined by issuer/.test(st.text) && !/no charge/i.test(st.text) &&
        (await state(c.page)) === 'CHECKOUT_OPEN', JSON.stringify(st));
      await c.page.evaluate(() => window.__rzp.options.modal.ondismiss());
      const st2 = await status(c.page);
      check('closed checkout window: inline, nothing charged unless paid, retry enabled',
        /Checkout closed/.test(st2.text) && /nothing was charged/.test(st2.text) && !(await payDisabled(c.page)) && (await state(c.page)) === 'CANCELLED_BY_BUYER', JSON.stringify(st2));
      await c.page.click('#rzp-pay-btn');
      await c.page.waitForTimeout(300);
      check('closed checkout window: continuing opens checkout again', (await modalCount(c.page)) === 2 && c.rec.subs.length === 2);
      await c.context.close();
    }

    // ── 3. after payment authorization ───────────────────────────────────
    {
      const a = await open(browser, { statusReplies: [{ body: { status: 'created', tier: 'PRO' } }, { body: { status: 'active', tier: 'PRO', api_key: KEY } }] });
      await fillAndPay(a.page);
      await authorize(a.page);
      await waitState(a.page, 'ACTIVE');
      const r = await result(a.page);
      check('ACTIVE only after the backend confirmed status "active" with the key', r.state === 'ACTIVE' && a.rec.statusCalls.length === 2 && r.visible && r.checkoutHidden, JSON.stringify(r).slice(0, 300));
      check('ACTIVE: status poll carries the payment proof', /payment_id=pay_T1/.test(a.rec.statusCalls[0]) && /signature=test_only_signature/.test(a.rec.statusCalls[0]));
      check('ACTIVE: the key is masked until the buyer reveals it (not in the DOM)', !r.keyBoxHidden && r.key !== KEY && !r.html.includes(KEY), r.key);
      await a.page.click('#activation-reveal-key');
      const shown = await a.page.evaluate(() => ({ key: document.getElementById('activation-key').textContent, pressed: document.getElementById('activation-reveal-key').getAttribute('aria-pressed') }));
      check('ACTIVE: "Show key" reveals the provisioned key', shown.key === KEY && shown.pressed === 'true', JSON.stringify(shown));
      check('ACTIVE: activation actions shown (copy key, Test API, Watchdog, docs, Billing Center)',
        r.actions === 'flex' && /Copy API key/.test(r.text) && /Test API/.test(r.text) && /Open Cyber Watchdog/.test(r.text) && /API docs/.test(r.text) && /Billing Center/.test(r.text), r.text);
      await a.page.click('#activation-test-api');
      await a.page.waitForFunction(() => /key works/.test(document.getElementById('activation-test-result').textContent), null, { timeout: 5000 });
      check('ACTIVE: Test API sends the new key to the API', a.rec.feedCalls.length === 1 && a.rec.feedCalls[0] === KEY);
      const snip = await a.page.evaluate(() => { const s = document.getElementById('onboard-snippets'); return { hidden: s.hidden, text: s.innerText }; });
      check('ACTIVE: first-request snippets read the key from the environment, never embed it', !snip.hidden && /SENTINEL_APEX_API_KEY/.test(snip.text) && !snip.text.includes(KEY));
      check('ACTIVE: no "instant" claim, no page error', !/INSTANT/i.test(r.text) && a.rec.errors.length === 0, a.rec.errors.join(' | '));
      await a.context.close();
    }
    {
      const p = await open(browser, { pollAttempts: 1, statusReplies: [{ body: { status: 'created', tier: 'PRO' } }] });
      await fillAndPay(p.page);
      await authorize(p.page);
      await waitState(p.page, 'ACTIVATION_PENDING');
      await p.page.evaluate(() => window.__rzp.options.modal.ondismiss());
      const pf = await result(p.page);
      check('timeout -> ACTIVATION_PENDING with "PAYMENT CONFIRMED — ACTIVATION IN PROGRESS"',
        pf.state === 'ACTIVATION_PENDING' && pf.visible && /PAYMENT CONFIRMED/.test(pf.title) && /ACTIVATION IN PROGRESS/.test(pf.title), JSON.stringify(pf).slice(0, 300));
      check('timeout: masked reference (never the full subscription id, the key or the payment signature)',
        pf.ref === 'sub_…TURE01' && !pf.html.includes(SUB_ID) && !/test_only_signature|pay_T1/.test(pf.html), pf.ref);
      check('timeout: never says the payment failed, never says access is on',
        !/fail/i.test(pf.text) && !/provisioned|is active|API KEY PROVISIONED/i.test(pf.text) && pf.keyBoxHidden && pf.actions === 'none', pf.text);
      check('timeout: buyer told not to pay again; pay button stays disabled even after a late ondismiss',
        /do not pay again/i.test(pf.text) && pf.payDisabled && (await state(p.page)) === 'ACTIVATION_PENDING');
      await p.page.click('#activation-recheck-btn');
      await p.page.waitForTimeout(2600);
      check('timeout: "check again" re-polls the backend', p.rec.statusCalls.length >= 3 && (await state(p.page)) === 'ACTIVATION_PENDING', String(p.rec.statusCalls.length));
      check('timeout: no page error', p.rec.errors.length === 0, p.rec.errors.join(' | '));
      // A reload in the same tab resumes the pending activation with the
      // stored proof; once the backend confirms, the key appears.
      p.opts.statusReplies = [{ body: { status: 'active', tier: 'PRO', api_key: KEY } }];
      const before = p.rec.statusCalls.length;
      await p.page.reload({ waitUntil: 'domcontentloaded' });
      await waitState(p.page, 'ACTIVE');
      const after = p.rec.statusCalls.slice(before);
      check('reload during activation: resumes with the stored proof and shows ACTIVE once confirmed',
        after.length >= 1 && /payment_id=pay_T1/.test(after[0]) && (await result(p.page)).title === 'SUBSCRIPTION ACTIVE', JSON.stringify(after));
      await p.context.close();
    }
    {
      const o = await open(browser, { pollAttempts: 0, statusReplies: ['network'] });
      await fillAndPay(o.page);
      await authorize(o.page);
      await waitState(o.page, 'ACTIVATION_PENDING');
      const r = await result(o.page);
      check('status endpoint unreachable -> ACTIVATION_PENDING, not a failure', r.state === 'ACTIVATION_PENDING' && !/fail/i.test(r.text) && o.rec.errors.length === 0, JSON.stringify(r).slice(0, 200));
      await o.context.close();
    }
    {
      const s = await open(browser, { query: '?checkout=success&plan=pro' });
      await s.page.waitForTimeout(400);
      const shown = await s.page.evaluate(() => document.getElementById('success-state').style.display === 'block');
      check('?checkout=success in the URL renders no success state', !shown && (await state(s.page)) === 'IDLE');
      await s.context.close();
    }

    // ── 4. Gumroad (secondary) ───────────────────────────────────────────
    {
      const g = await open(browser, { pricing: pricing(true) });
      const read = () => g.page.evaluate(() => {
        const b = document.getElementById('gumroad-btn');
        return { hidden: b.hidden, href: b.getAttribute('href') || '', type: b.getAttribute('data-gumroad-sale-type'), label: b.textContent.trim(),
          price: document.getElementById('gumroad-price').textContent, terms: document.getElementById('gumroad-terms').textContent,
          caption: document.getElementById('gumroad-caption').innerText, note: document.getElementById('gumroad-unavailable').hidden ? '' : document.getElementById('gumroad-unavailable').textContent };
      });
      await g.page.evaluate(() => { selectPlan('pro'); if (isAnnual) toggleBilling(); });
      const grant = await read();
      const periodMonthly = await g.page.evaluate(() => document.getElementById('period-pro').textContent);
      check('gumroad available: "Continue with Gumroad", labelled secondary, sells the catalog product',
        !grant.hidden && grant.label === 'Continue with Gumroad' && /pxyfcb/.test(grant.href) && /Secondary automated checkout/.test(grant.caption), JSON.stringify(grant));
      check('gumroad: without a membership product the grant is labelled a one-time grant',
        grant.type === 'grant' && /30-day access grant, does not auto-renew/.test(grant.terms) && grant.price === 'US$49', JSON.stringify(grant));
      await g.page.evaluate(() => { GUMROAD_MEMBERSHIP_URLS.pro.monthly = 'https://cyberdudebivash.gumroad.com/l/test-membership'; updateGumroadPanel(); });
      const membership = await read();
      check('gumroad: a configured membership is what the button sells',
        membership.type === 'membership' && membership.href === 'https://cyberdudebivash.gumroad.com/l/test-membership' &&
        /renews monthly/.test(membership.terms), JSON.stringify(membership));
      await g.page.evaluate(() => toggleBilling());
      const annual = await read();
      const periodAnnual = await g.page.evaluate(() => document.getElementById('period-pro').textContent);
      check('gumroad: annual without a yearly membership falls back to the labelled 12-month grant',
        annual.type === 'grant' && /xtnzu/.test(annual.href) && /12-month access grant, does not auto-renew/.test(annual.terms), JSON.stringify(annual));
      check('plan card period follows the billing period', periodMonthly === 'per month' && periodAnnual === 'per year', periodMonthly + ' / ' + periodAnnual);
      await g.page.evaluate(() => selectPlan('mssp'));
      const mssp = await read();
      check('gumroad: MSSP has no Gumroad product, so no Gumroad link is offered', mssp.hidden && mssp.href === '' && /not offered/.test(mssp.note), JSON.stringify(mssp));
      check('gumroad: no page error', g.rec.errors.length === 0, g.rec.errors.join(' | '));
      await g.context.close();
      for (const [label, pr] of [['reports Gumroad unavailable', pricing(false)], ['request fails', 'network'], ['answers 404', null]]) {
        const u = await open(browser, { pricing: pr, query: '?plan=pro' });
        const s = await u.page.evaluate(() => { const b = document.getElementById('gumroad-btn');
          return { hidden: b.hidden, href: b.getAttribute('href'), note: document.getElementById('gumroad-unavailable').textContent,
            anyLink: [...document.querySelectorAll('a[href*="gumroad.com/l/"]')].length }; });
        check(`gumroad when /api/pricing ${label}: no Gumroad link anywhere, Razorpay offered instead`,
          s.hidden && s.href === null && s.anyLink === 0 && /Use Razorpay above/.test(s.note), JSON.stringify(s));
        await u.context.close();
      }
    }

    // ── 5. deep links, UTM, URL tampering ────────────────────────────────
    {
      const t = await open(browser, { query: '?plan=pro&utm_source=newsletter&utm_campaign=q4&amount=1&price=1&tier=MSSP&currency=USD&plan_id=plan_x' });
      const view = await t.page.evaluate(() => ({ plan: currentPlan, inr: document.getElementById('rzp-display-inr').textContent, search: location.search }));
      await fillAndPay(t.page, { plan: view.plan });
      const sent = t.rec.subs[0] || {};
      check('deep link ?plan=pro selects PRO', view.plan === 'pro');
      check('utm_* stay in the URL; amount / price / tier / currency in the URL change nothing',
        /utm_source=newsletter/.test(view.search) && view.inr === '₹4,100' && sent.tier === 'PRO' && sent.billing_cycle === 'monthly' &&
        Object.keys(sent).sort().join(',') === 'billing_cycle,email,tier', JSON.stringify({ view, sent }));
      await t.context.close();
      const ea = await open(browser, { query: '?plan=enterprise-annual' });
      const eav = await ea.page.evaluate(() => ({ plan: currentPlan, annual: isAnnual, inr: document.getElementById('rzp-display-inr').textContent }));
      await fillAndPay(ea.page, { plan: 'enterprise' });
      check('deep link ?plan=enterprise-annual selects Enterprise yearly (INR from the canonical table)',
        eav.plan === 'enterprise' && eav.annual && eav.inr === '₹4,16,000' && ea.rec.subs[0] && ea.rec.subs[0].tier === 'ENTERPRISE' &&
        ea.rec.subs[0].billing_cycle === 'annual', JSON.stringify({ eav, sub: ea.rec.subs[0] }));
      await ea.context.close();
      for (const [q, label] of [['?plan=platinum', 'unknown'], ['?plan=pro&plan=enterprise', 'conflicting']]) {
        const x = await open(browser, { query: q });
        const v = await x.page.evaluate(() => ({ plan: currentPlan, notice: document.getElementById('plan-notice').hidden ? '' : document.getElementById('plan-notice').textContent,
          pay: document.getElementById('section-payment-methods').style.display, free: document.getElementById('free-plan-panel').style.display }));
        check(`${label} plan in the link: nothing paid pre-selected, the page says so`,
          v.plan === 'free' && /could not be matched/.test(v.notice) && v.pay === 'none' && v.free === '', JSON.stringify(v));
        await x.context.close();
      }
      const none = await open(browser);
      const nv = await none.page.evaluate(() => ({ plan: currentPlan, notice: document.getElementById('plan-notice').hidden }));
      check('no plan in the link: Community selected, no notice', nv.plan === 'free' && nv.notice, JSON.stringify(nv));
      await none.context.close();
    }

    // ── 6 + 7. no manual payment UI; assisted note; copy ─────────────────
    {
      const c = await open(browser, { pricing: pricing(true), query: '?plan=pro' });
      const d = await c.page.evaluate((assisted) => {
        const html = document.documentElement.outerHTML;
        const note = document.getElementById('assisted-payments');
        const norm = (s) => s.replace(/\s+/g, ' ').trim();
        const pay = document.getElementById('section-payment-methods');
        const rzp = document.getElementById('rzp-pay-btn'), gum = document.getElementById('gumroad-btn');
        const outside = norm(document.body.innerText.replace(note.innerText, ''));
        return {
          fileInputs: document.querySelectorAll('input[type=file]').length,
          proofFields: [...document.querySelectorAll('input,textarea,select')].filter((e) => /utr|transaction|proof|screenshot|reference/i.test(e.id + ' ' + e.name)).map((e) => e.id),
          qr: document.querySelectorAll('img[src*="qr" i], canvas').length,
          creds: (html.match(/\b[\w.-]+@(?:upi|ybl|okaxis|oksbi|okhdfcbank|okicici|paytm|ibl|axl)\b|\bIFSC\b|\b[A-Z]{4}0[A-Z0-9]{6}\b|\b\d{9,18}\b(?=[^<]*(?:a\/c|account))|\b0x[0-9a-fA-F]{40}\b|\bbc1q[0-9a-z]{20,}|\bT[1-9A-HJ-NP-Za-km-z]{33}\b/g) || []),
          utrText: /\bUTR\b/.test(document.body.innerText),
          noteText: norm(note.querySelector('p').innerText),
          noteMailto: [...note.querySelectorAll('a')].map((a) => a.getAttribute('href')),
          noteControls: note.querySelectorAll('button,input,form,select,textarea').length,
          noteAfterGumroad: !!(gum.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING),
          rzpBeforeGumroad: !!(rzp.compareDocumentPosition(gum) & Node.DOCUMENT_POSITION_FOLLOWING),
          primaries: [...pay.querySelectorAll('.btn-primary')].map((b) => b.id),
          rzpLabel: norm(rzp.innerText),
          caption: norm(document.getElementById('rzp-cta-caption').innerText),
          outsideMentions: (outside.match(/Paytm|Amazon ?Pay|PhonePe|GPay|BHIM|crypto|NEFT|PayPal/gi) || []),
          text: document.body.innerText,
          alerts: /\balert\(/.test([...document.scripts].map((s) => s.textContent).join('\n')),
        };
      }, ASSISTED);
      check('no manual-payment UI: no file upload, proof / UTR / reference field, QR or canvas', d.fileInputs === 0 && d.proofFields.length === 0 && d.qr === 0 && !d.utrText, JSON.stringify(d.proofFields));
      check('no payment credentials published (UPI handle, IFSC, bank account, crypto address)', d.creds.length === 0, JSON.stringify(d.creds));
      check('assisted note: verbatim text with both contact addresses', d.noteText === ASSISTED &&
        d.noteMailto.join(',') === 'mailto:contact@cyberdudebivash.in,mailto:bivash@cyberdudebivash.com', JSON.stringify({ t: d.noteText, m: d.noteMailto }));
      check('assisted note: below both automated checkouts, no pay button or form in it', d.noteAfterGumroad && d.rzpBeforeGumroad && d.noteControls === 0);
      check('one primary CTA: Continue with Razorpay (subscribe), captioned secure automated checkout',
        d.primaries.join(',') === 'rzp-pay-btn' && /^Continue with Razorpay Subscribe/.test(d.rzpLabel) && /Secure automated checkout/.test(d.caption), JSON.stringify({ p: d.primaries, l: d.rzpLabel }));
      check('alternative methods are named only in the assisted note', d.outsideMentions.length === 0, JSON.stringify(d.outsideMentions));
      check('no alert() left in the page scripts', !d.alerts);
      const t = d.text;
      check('copy: no EMI / wallets offered for a subscription', !/\bEMI\b|Wallets \(/.test(t));
      check('copy: no "API key within 2 hours" claim', !/within 2 ?h|in 2 hours/i.test(t));
      check('copy: no blanket "No Auto-Renewal" for Razorpay', !/No Auto-Renewal/i.test(t));
      check('copy: no SOC 2 / ISO 27001 claim', !/SOC 2|ISO 27001/.test(t));
      check('copy: no instant / 24/7 / guaranteed-delivery claims', !/\binstant(ly)?\b|24\/7|guaranteed delivery/i.test(t));
      check('copy: guarantee qualified to eligible first purchases', /7-Day Money-Back Guarantee on eligible first purchases/i.test(t) && /No pro-rata refunds/i.test(t));
      check('copy: Razorpay renewal and cancellation stated', /renews automatically, cancel any time/i.test(t));
      await c.context.close();
    }

    // ── 8. layout and keyboard ───────────────────────────────────────────
    for (const width of [320, 360, 390, 430, 768, 1280]) {
      const l = await open(browser, { pricing: pricing(true), query: '?plan=pro', viewport: { width, height: 800 } });
      const m = await l.page.evaluate(() => {
        const vw = window.innerWidth;
        const box = (id) => { const r = document.getElementById(id).getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, height: r.height, width: r.width }; };
        const offenders = [...document.querySelectorAll('body *')].filter((el) => {
          const r = el.getBoundingClientRect();
          return r.width > 1 && r.height > 0 && (r.right > vw + 1 || r.left < -1) && getComputedStyle(el).position !== 'fixed';
        }).map((el) => `${el.tagName.toLowerCase()}#${el.id}.${el.className}`).slice(0, 6);
        return { vw, scroll: document.documentElement.scrollWidth, rzp: box('rzp-pay-btn'), gum: box('gumroad-btn'), note: box('assisted-payments'), offenders };
      });
      check(`${width}px: no horizontal overflow`, m.scroll <= m.vw && m.offenders.length === 0, JSON.stringify({ scroll: m.scroll, vw: m.vw, off: m.offenders }));
      check(`${width}px: Razorpay CTA fully inside the viewport and at least 44px tall`, m.rzp.left >= 0 && m.rzp.right <= m.vw && m.rzp.height >= 44, JSON.stringify(m.rzp));
      check(`${width}px: Razorpay above Gumroad above the assisted note`, m.rzp.top < m.gum.top && m.gum.top < m.note.top, JSON.stringify({ r: m.rzp.top, g: m.gum.top, n: m.note.top }));
      if (SHOTS) {
        fs.mkdirSync(SHOTS, { recursive: true });
        await l.page.screenshot({ path: path.join(SHOTS, `checkout-${width}.png`), fullPage: true });
      }
      await l.context.close();
    }
    {
      const k = await open(browser);
      await k.page.focus('input[name="plan"][value="free"]');
      await k.page.keyboard.press('ArrowDown');
      const viaKeys = await k.page.evaluate(() => currentPlan);
      await k.page.fill('#rzp-email', 'buyer@example.com');
      await k.page.focus('#rzp-pay-btn');
      await k.page.keyboard.press('Enter');
      await k.page.waitForTimeout(300);
      check('keyboard: arrow keys move through the plan radios; Enter on the Razorpay button starts checkout',
        viaKeys === 'pro' && k.rec.subs.length === 1 && (await modalCount(k.page)) === 1, JSON.stringify({ viaKeys, subs: k.rec.subs.length }));
      await k.context.close();
    }

    check('no alert() dialog on any path', allDialogs.length === 0, JSON.stringify(allDialogs));
    check('no page error on any path', allErrors.length === 0, allErrors.join(' | '));
  } finally {
    await browser.close();
    server.close();
  }
  console.log(failures ? `\n${failures} check(s) FAILED` : '\nAll upgrade checkout checks passed');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
