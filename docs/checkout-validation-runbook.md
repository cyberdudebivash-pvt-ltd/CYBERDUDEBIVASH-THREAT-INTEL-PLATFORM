# Live Checkout Validation Runbook

**Scope:** end-to-end verification that a real (or Razorpay test-mode) payment
actually results in a working API key against production — User Checkout →
Razorpay Payload Verification (HMAC) → Cloudflare Edge State Switch → Full
Dashboard Telemetry Unlock.

**Audience:** whoever is validating a deploy that touches checkout, webhook
handling, or key provisioning in `workers/intel-gateway/src/index.js` or
`workers/revenue-engine/src/`.

---

## Why "test mode," not a low-cost real charge

Don't invent a ₹1/$1 test SKU — that still moves real money and needs a new
Razorpay plan. Razorpay's **Test Mode** exercises the identical code path
(order creation, Checkout.js modal, HMAC-signed verification and webhook
delivery) with zero real money, using test API keys (`rzp_test_...`) and
Razorpay's documented test card numbers. This is the standard, safe way to
validate this flow and is what the two-track approach below uses.

Track A (test mode) validates the code. Track B (webhook replay) validates
production credentials without a live charge. Run both before signing off
on a checkout-path change; you don't need a real charge for either.

---

## The two write paths (know which one you're testing)

There are **two independent routes into `API_KEYS_KV`** — the same KV
`resolveAuth()` reads on every gated request, so either path landing
correctly is sufficient, but a regression could break just one of them:

| Path | Trigger | Verification | Idempotency key |
|---|---|---|---|
| **Client verify** | Browser calls `POST /api/payment/razorpay/verify` after the Checkout.js modal succeeds | HMAC-SHA256 of `{order_id}\|{payment_id}` against `RAZORPAY_KEY_SECRET` (`index.js:2890-2894`) | `rzp_payment:{payment_id}` in `SECURITY_HUB_KV` |
| **Server webhook** | Razorpay's servers POST `/api/webhooks/razorpay` directly | HMAC-SHA256 of the raw request body via `X-Razorpay-Signature` against `RAZORPAY_WEBHOOK_SECRET` (`index.js:2950-2954`) | `rzp_payment:{payment_id}` (unified) + `rzp_webhook:{payment_id}` (legacy) |

Both call `provisionApiKey()` (`index.js:2730`), which writes directly to
`API_KEYS_KV` — no queue, no batch job, effective immediately.

---

## Track A — Test-mode checkout (validates the code path)

1. **Get Razorpay test credentials**: Razorpay Dashboard → toggle to **Test
   Mode** → Settings → API Keys. Note the test `Key ID` and `Key Secret`.
2. **Point the Worker at test credentials** — in a staging environment (never
   swap production's live `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` secrets for
   this): `wrangler secret put RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` with
   the test values, in a non-production Worker deploy.
3. **Run the checkout**: open `/upgrade.html?plan=pro` against that staging
   Worker, fill the checkout form, and when the Razorpay modal opens, use a
   [documented test card](https://razorpay.com/docs/payments/payments/test-card-upi-details/)
   (e.g. `4111 1111 1111 1111`, any future expiry, any 3-digit CVV, any name).
4. **Watch the network tab** for the three real calls, in order:
   - `POST /api/payment/razorpay/create-order` → expect `200` with
     `order_id`, `key_id`, `amount`
   - Razorpay's own hosted checkout traffic (not your Worker) — not
     traceable/needed
   - `POST /api/payment/razorpay/verify` → expect `201` with
     `{status: "activated", api_key: "cdb_pro_...", tier: "PRO"}`
5. **A second `verify` call with the same `payment_id`** (replay it manually
   with the same body) must now return `409 {code: "ALREADY_PROVISIONED"}` —
   confirms the idempotency guard survived your change.

## Track B — Webhook replay (validates production credentials without a live charge)

1. Razorpay Dashboard → **Webhooks** → find the configured production
   webhook (should point at `https://intel.cyberdudebivash.com/api/webhooks/razorpay`)
   → use its **"Send Test Webhook"** feature, event type `payment.captured`.
   This is signed with the real `RAZORPAY_WEBHOOK_SECRET` and delivered to
   production — safe to do because it never touches a real charge, only
   exercises the webhook handler.
2. Confirm in the Worker's logs / `SECURITY_HUB_KV` (`wrangler kv:key get
   "audit:{ts}:{rand}"` around the delivery time, or check
   `wrangler tail` live) that `handleWebhookRazorpay` ran, signature
   verified, and `key_auto_provisioned` was audit-logged.
3. **Do not** use a `payment_id` value that also exists in `API_KEYS_KV`
   from a real customer transaction — Razorpay's test-webhook payloads use
   synthetic IDs, so this should not collide, but confirm before sending if
   in doubt.

---

## Cloudflare Edge State Switch — confirm the KV write landed

```bash
# Requires wrangler auth against the intel-gateway Worker's account
wrangler kv:key get "cdb_pro_XXXXXXXXXXXXXXXXXXXX" \
  --namespace-id <API_KEYS_KV namespace id> --preview false
```

Expect a JSON record with `tier: "PRO"`, `customer_id: <email>`,
`source: "razorpay_checkout"` or `"razorpay_webhook"`, matching whichever
track you ran.

---

## Full Dashboard Telemetry Unlock — confirm the key actually works

```bash
# FREE/no key -- masked response (no iocs, no stix_bundle, truncated fields)
curl -s https://intel.cyberdudebivash.com/api/v1/intel/latest.json | python3 -m json.tool | head -30

# With the freshly provisioned key -- full, unmasked response
curl -s -H "Authorization: Bearer cdb_pro_XXXXXXXXXXXXXXXXXXXX" \
  https://intel.cyberdudebivash.com/api/v1/intel/latest.json | python3 -m json.tool | head -30
```

The PRO response should include populated `iocs`, `stix_bundle`, and
detection-rule fields the FREE response nulled out
(`applyTierGateV2`, `revenue-enforcement.js`). If it doesn't, or if this
request 401s, stop here — the key was provisioned but isn't authenticating,
which points at a mismatch between `API_KEYS_KV` (what got written) and
`resolveAuth()` (what gets read) rather than anything in the checkout flow
itself.

Also confirm TAXII access works, since it's gated by the same tier check:

```bash
curl -s -H "Authorization: Bearer cdb_pro_XXXXXXXXXXXXXXXXXXXX" \
  https://intel.cyberdudebivash.com/taxii/collections/ | python3 -m json.tool
```

---

## Sign-off checklist

- [ ] Track A: `create-order` → checkout modal → `verify` returns `201` with a real key
- [ ] Track A: replayed `verify` call returns `409 ALREADY_PROVISIONED`
- [ ] Track B: test webhook delivery logged as processed, no signature failure
- [ ] `API_KEYS_KV` contains the new key with the expected tier/email
- [ ] `/api/v1/intel/latest.json` with the new key returns unmasked data
- [ ] `/taxii/collections/` with the new key returns the collection list (not `401`)
- [ ] No `webhook_sig_fail` or `SIG_MISMATCH` audit-log entries during the test window

If any step fails, the failure mode tells you which half of the pipeline
broke: create-order/verify failures are checkout-side; webhook signature
failures are secret/config-side; a provisioned key that still 401s is an
auth-resolution-side bug (`resolveAuth()`, `index.js:323-377`), not a
payment bug at all.
