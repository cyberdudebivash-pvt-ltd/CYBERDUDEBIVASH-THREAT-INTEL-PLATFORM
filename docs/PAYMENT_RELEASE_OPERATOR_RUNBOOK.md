# Payment release: operator runbook and audits (2026-10-02)

This runbook covers what the code cannot do: owner decisions, secrets and
provider credentials. It also records the audits behind them.

- Base: `main` `fcb252bd7`.
- Deployed Workers: `acc38a24d`.
- Current status of each row: `docs/CUSTOMER_RELEASE_LEDGER.md`.
- Key-delivery policy: `docs/COMMERCIAL_POLICY_V1.md`.

Never paste a secret into a ticket, a log or this file. The commands below
read secrets from a prompt or stdin.

## 1. F21: Gumroad production safety

Production state:

- The webhook answers 500 "Webhook secret not configured"
  (billing canary, 2026-10-02 06:48Z).
- The checkout offers Gumroad only when `GET /api/pricing` reports
  `checkout.gumroad.available === true`. Today it reports `available: false`
  (`automated_provisioning_not_configured`), and a failed or missing
  answer also hides the button (`upgrade.html`, fail-closed).

### The four access products

All four answered HTTP 200 with their product page at 2026-10-02 08:33Z.
They are still purchasable by direct link.

| Permalink | Gumroad product | Grants (catalog `gumroad-products.js`) |
| --- | --- | --- |
| `pxyfcb` | SENTINEL APEX Pro Monthly | PRO, monthly |
| `xtnzu` | SENTINEL APEX Pro Annual | PRO, annual |
| `cdedlo` | SENTINEL APEX Enterprise Monthly | ENTERPRISE, monthly |
| `vxoczs` | SENTINEL APEX Enterprise Annual | ENTERPRISE, annual |

### Where the platform links them

- **`upgrade.html`:** the Gumroad button and its URLs, shown only while the
  gateway reports Gumroad available.
- **`pricing.html`:** its structured data (JSON-LD) used to describe PRO and
  Enterprise as "30-day access grant via Gumroad (pxyfcb / cdedlo) …
  Does not auto-renew". It now describes the Razorpay subscription.
- **No other shipped page, Worker response or email** links the four
  products.
- **Content products:** the Gumroad storefront (`store.html`,
  `services.html`) sells content products that Gumroad delivers itself and
  that grant no API access.
- **Copy fixes:** pages that offered Gumroad unconditionally now say "when
  the checkout page offers it". These are `pricing.html`, `compare.html`,
  `trial-center.html`, `lead-capture.html`, `mssp-partner-onboarding.html`,
  `api-key-manager.html`, `user-test-kit.html`, `docs/faq.html` and the two
  `alternative-to-*` pages.
- **Regression guard:** `config/evidence-register.json` (withdrawn claim
  "Gumroad offered unconditionally, or an API key delivered by email")
  makes `verify_public_claims.py` fail if the old wording returns.

### Owner action: choose one

**A. Stop selling through Gumroad until provisioning works**

In the Gumroad dashboard, open Products, then each of `pxyfcb`, `xtnzu`,
`cdedlo` and `vxoczs`, and choose Unpublish. Nothing in the repository
needs to change.

**B. Turn Gumroad provisioning on**

1. Set the gateway secret. Paste the value at the prompt; never echo it:

   ```
   cd workers/intel-gateway && npx wrangler secret put GUMROAD_WEBHOOK_SECRET --env production
   ```

2. In Gumroad's Settings, under Advanced, set the Ping URL to
   `https://intel.cyberdudebivash.com/api/webhooks/gumroad?secret=<same value>`.
3. Optionally set `GUMROAD_SELLER_ID` on the gateway.
4. `RESEND_API_KEY` must also be set on the gateway. The buyer's one-time
   key link is emailed, and Gumroad stays unavailable without it.
5. Verify, with no real money (section 5): the billing canary in public mode
   must show `gumroad_webhook_requires_secret` PASS, and `/api/pricing` must
   report `available: true`.

### Historical sales (owner; never manufacture a transaction)

1. In Gumroad's Sales view, export the sales of the four products. The
   window is at least 2026-09-25 (the first canary that saw the 500) to the
   day option A or B is done. Check whether any earlier sale went
   unprovisioned too.
2. For each sale that was not refunded, find out whether a key exists. A
   provisioned sale wrote `gumroad_sale:<sale_id>` in the gateway's
   `SECURITY_HUB_KV`.
3. For each sale without a key, after option B:
   - Re-send that sale's ping from Gumroad if your account offers it. The
     sale is then provisioned and its one-time link emailed.
   - Otherwise, create the key with the admin API
     (`POST /api/admin/keys {customer_id: <buyer email>, tier, expires_in_days}`)
     and send the link with `POST /api/admin/keys/{key}/redemption`.
4. Record each reconciled sale ID (no payment details) in the ledger.

## 2. F22: key delivery (implemented; see the policy doc)

No email contains an API key. Buyers get the key in one of two ways:

- shown once on the Razorpay checkout page;
- revealed once from an emailed link
  (`customer/api-keys.html#redeem=<token>`, `POST /api/keys/redeem`).

A lost or expired link is replaced by an operator:

```
curl -X POST -H "X-Admin-Key: $GATEWAY_ADMIN_SECRET" \
  https://intel.cyberdudebivash.com/api/admin/keys/<key>/redemption
```

The new link goes to the address on the key record, never to an address the
caller supplies.

**Owner decision (optional):** `KEY_EMAIL_DELIVERY_ENABLED="true"` and
`SENDGRID_API_KEY` on the revenue engine turn on the Razorpay activation
notice. It carries a one-time link, never a key.

## 3. F24: `REVENUE_ADMIN_SECRET`

### Who holds it

| Holder | What it is | What uses it |
| --- | --- | --- |
| Revenue engine Worker secret | **Canonical** | Verifies `X-Admin-Secret` (`isAdmin`). Keys the customer-portal HMAC (`portal:` + email) and the Enterprise quote links (`quote:` + id). |
| Gateway Worker secret | Copy; must equal the canonical value | Portal link in activation emails; quota-alert calls to the revenue engine's `/api/automation/trigger` |
| GitHub repository secret | Copy; must equal the canonical value | `deploy-revenue-engine.yml` readiness report |

### Evidence

- Deploy run 36962733371 (04:03Z) printed: "HTTP 401: the revenue engine
  rejected the REVENUE_ADMIN_SECRET repository secret".
- The repository secret is set: it is masked in the log.
- So the repository copy differs from the Worker's value.
- Whether the gateway copy matches is unknown; it cannot be read back.
- The billing canary's admin and live modes read
  `CDB_BILLING_CANARY_ADMIN_SECRET`, which must hold the same value.

### Owner action

Cloudflare secrets cannot be read back.

**Option A: you know the revenue engine's value.** Set the repository secret
to it, pasting at the prompt:

```
gh secret set REVENUE_ADMIN_SECRET --repo cyberdudebivash/CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM
```

**Option B: rotate.** Generate one new value and set all three copies from it
without printing it:

```
NEW=$(openssl rand -hex 32)
(cd workers/revenue-engine && printf %s "$NEW" | npx wrangler secret put REVENUE_ADMIN_SECRET --env production)
(cd workers/intel-gateway  && printf %s "$NEW" | npx wrangler secret put REVENUE_ADMIN_SECRET --env production)
printf %s "$NEW" | gh secret set REVENUE_ADMIN_SECRET --repo cyberdudebivash/CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM
unset NEW
```

Rotation also invalidates:

- every customer-portal link already emailed;
- every outstanding Enterprise quote link (both are HMACs of this secret);
- operators' saved admin logins.

Tell operators, and re-send any open quote.

### Proof

Run both probes. Neither prints the secret.

```
curl -s -o /dev/null -w '%{http_code}\n' -H "X-Admin-Secret: $REVENUE_ADMIN_SECRET" \
  https://revenue.intel.cyberdudebivash.com/api/v2/billing/admin/readiness   # expect 200
curl -s -o /dev/null -w '%{http_code}\n' \
  https://revenue.intel.cyberdudebivash.com/api/v2/billing/admin/readiness   # expect 401
```

The next run of `deploy-revenue-engine.yml` then prints the readiness
verdict.

## 4. Enterprise certification canary

`commercial-customer-ops-certification.yml`, Phases 8-15, runs
`deploy/cyber-watchdog/canary.mjs enterprise`.

### What already passed

On deployed `acc38a24d` (run 36962733292), every credential-independent part
passed:

- PRO canary;
- MSSP self-service;
- MSSP rotation;
- autonomous scheduler;
- authenticated customer ops;
- lifecycle matrix;
- expiry boundary;
- MSSP isolation;
- FREE rate limit.

The Enterprise webhook unit tests pass in the regression gate.

### What is missing

**BLOCKED — OPERATOR SECRET REQUIRED.** The canary needs an owner-controlled
HTTPS receiver running `deploy/cyber-watchdog/sink.mjs` behind TLS on 443:

```
PORT=8787 SINK_TOKEN=<24+ chars> [WATCHDOG_SECRET=<whsec_...>] node sink.mjs
```

Create these GitHub repository secrets (Settings, then Secrets and variables,
then Actions):

| Secret name | Value |
| --- | --- |
| `CDB_WATCHDOG_SINK_URL` | The receiver's HTTPS URL |
| `CDB_WATCHDOG_SINK_INSPECT_URL` | Its `/__inspect` endpoint |
| `CDB_WATCHDOG_SINK_TOKEN` | The `SINK_TOKEN` above |

No other secret is needed. The workflow issues its own short-lived
ENTERPRISE canary key with `ADMIN_SECRET` (already set), passes it to the
canary as `CDB_WATCHDOG_CANARY_ENT_KEY`, and deletes it afterwards. Then
run `commercial-customer-ops-certification.yml` (workflow_dispatch) on the
deployed SHA.

## 5. Provider E2E test procedure

**BLOCKED — AUTHORIZED PROVIDER TEST CREDENTIALS REQUIRED.** Never charge
real money to satisfy certification. Use Razorpay test mode, a staging
deployment, and test cards or UPI test handles.

### Razorpay (test mode)

**Prerequisites:**

- A staging Worker pair, or the production Worker pair temporarily pointed
  at test keys with the owner's approval.
- Secrets:
  - `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` (`rzp_test_…`);
  - `RAZORPAY_WEBHOOK_SECRET`;
  - six test Plans as `RAZORPAY_PLAN_ID_{TIER}_{CYCLE}`, at the contract INR
    amounts.
- A test-mode webhook pointed at `/api/v2/billing/webhooks/razorpay` with
  the events in the policy doc.
- `CDB_BILLING_CANARY_ADMIN_SECRET` for the canary.

**Procedure:**

1. **Readiness.** Run `node deploy/billing-canary/canary.mjs test-checkout`.
   It refuses unless readiness proves an `rzp_test_` key, and creates one
   unpaid test subscription.
2. **Checkout.** Open `upgrade.html` and pick PRO monthly. The server sets
   the amount (S19 check). Pay with a Razorpay test card.
3. **Authenticity.** The signed `subscription.activated` webhook is
   accepted. The same body with a forged signature gets 401 and no record.
4. **Entitlement.**
   - The checkout page shows the key (status endpoint plus signature).
   - `GET /api/auth/validate` with the key returns valid.
   - The key's tier is the Plan's tier.
   - `expires_at` is `current_end` + 96 h.
5. **Duplicate.** Re-deliver the same event from the Razorpay dashboard. The
   answer is `already_processed`, and there is still one key.
6. **Renewal.** Use the test-mode "charge now" or wait for the next cycle.
   `subscription.charged` extends `expires_at` to the new `current_end` +
   96 h. Re-delivering it extends nothing further.
7. **Refund.** Refund the test payment.
   - `refund.created` revokes access at once: the key is refused and the JWT
     is denied.
   - `refund.processed` issues the credit note.
   - A later charge or activation never revives the key.
8. **Cancellation.** On a second subscription, `subscription.cancelled`
   denies access. `subscription.halted` (three failed test charges) denies
   access, and a captured recovery charge restores the same key.
9. **Activation link.** With the activation notice on (test SendGrid key),
   the email contains no key. Its link reveals the key once, and a second
   use gets 410.

**Evidence:** keep the event IDs, HTTP codes and key prefixes. Never keep
full keys, card data or buyer emails.

### Gumroad (only after section 1, option B)

**Prerequisites:** a Gumroad test purchase (a 100% discount code or a
test-mode product) on a test copy of one access product.

**Procedure:**

1. Buy. The authenticated ping provisions one key mapped to the catalog
   tier and cycle.
2. A ping with a wrong `?secret=` gets 401 and provisions nothing.
3. The buyer email contains a one-time link and no key. The link reveals the
   key once.
4. Duplicate ping: `already_provisioned`, one key.
5. Refund or cancel in Gumroad. The `refunded` ping revokes the key;
   `cancelled` keeps access to the end of the paid period; `ended` revokes.

## 6. 96-hour renewal grace (audit)

| Question | Finding |
| --- | --- |
| Where it is implemented | `subscription-engine.js`: `RENEWAL_GRACE_HOURS_DEFAULT = 96`, bounded 0-336, applied on activation, `subscription.charged` and halt recovery. `index.js` `handleSubExpireCheck`: Razorpay-managed subscriptions expire only after the period plus the grace. |
| Where it is documented | `docs/COMMERCIAL_POLICY_V1.md`, "Payment-to-entitlement hardening". No public page states it. Public copy says access runs to the end of the paid period, which the grace never shortens. |
| What it solves | The gateway refuses a key the moment `expires_at` passes. A renewal is only recorded when Razorpay's `subscription.charged` arrives, after the charge at `current_end`. Razorpay retries a failed card charge on days 1-3 before halting. The policy already promised access while retrying (`subscription.pending`: allowed). Without the grace, a paying customer lost access at every renewal boundary, and the 09:00 expiry check made that loss permanent. |
| Does it keep access after a confirmed refund, cancellation or halt? | **No.** These all deny at once, inside the grace or not, by writing a deny status the gateway refuses: `refund.created` or `refund.processed`, `subscription.cancelled`, `subscription.completed`, `subscription.halted`, and the gateway's own admin revoke. Tests: "renewal grace keeps a paying key valid past the period end; halted still denies at once", plus the cross-worker refund and cancellation tests. Control: "renewal grace removed (key lapses at period end)". |
| Who gets it | Every Razorpay subscription tier (PRO, Enterprise, MSSP) gets the same grace. Gumroad and assisted/PO subscriptions do not; they expire at period end. |
| Conflict with the contract | None. The contract promises access to the end of the paid period. The grace adds at most 96 h, and only while no terminal event has arrived (a retry in progress or a lost webhook). |
| Decision | Kept, and documented as an operational payment-reconciliation grace. The owner may confirm or change `RENEWAL_GRACE_HOURS`. |

## 7. Security negative controls

"Control" means a mutation in `billing-negative-controls.mjs` that the
regression gate proves the test suite catches.

| Attack | Result | Proof |
| --- | --- | --- |
| Forged Razorpay signature | DENY 401, nothing written | `subscription-engine.test.js`, `legacy-order-authority.test.js`; controls "Razorpay subscription webhook signature not verified", "legacy Razorpay webhook signature not verified"; live canary 401 |
| Forged Gumroad secret | DENY | `payment-webhook-metering.test.js` (wrong, encoded, NUL); control "Gumroad webhook secret not checked"; live: every ping refused (500, no secret set) |
| Unknown product | DENY | `gumroad-products.test.js` (`unknown_product` held); legacy `not_created_by_this_platform`; unknown Razorpay Plan (`subscription-webhook-hardening.test.js`) |
| Price manipulation | DENY | S19 Plan price check; legacy `amount_mismatch` and `currency_mismatch`; Gumroad below-price hold; control "legacy Order amount not checked" |
| Tier manipulation | DENY | Plan binding (notes cannot raise the tier); verify ignores the browser's tier, cycle and email; Gumroad catalog; controls for Plan binding and the verify cycle |
| Replay or duplicate | One entitlement | Event-id claim; retry marker; replayed renewal; Gumroad lock (1 key from 3 concurrent deliveries); `rzp_payment:` idempotency; controls for each |
| Refund | Revoke | `billing-policy.test.js` (`refund.created` and `refund.processed` revoke, `refund.failed` does not); cross-worker refund test; Gumroad `refunded` |
| Cancelled or halted | Deny per contract | Cross-worker halted, cancelled and completed tests; halted inside the grace |
| Unauthenticated key retrieval | DENY | Status endpoint needs the payment signature (401, IDOR test); portal needs its HMAC token; redemption needs the one-time token (400 or 410) |
| Expired redemption | DENY 410 | `key-redemption.test.js`; control "redemption expiry not checked" |
| Reused redemption | DENY 410 | `key-redemption.test.js` (second use; 1 of 5 concurrent); control "redemption replay allowed" |
| Revoked key | DENY | Gateway auth tests; redemption refuses refunded, suspended, lapsed and deleted keys; control "redemption reveals a revoked key" |
| Wrong tenant | DENY | `mssp-tenants.test.js`; live MSSP isolation PASS (certification) |
| Admin-secret mismatch | DENY 401/403 | Readiness and admin tests; live canary 401/403; deploy run 36962733371 401 |
| Manual-payment request | Cannot auto-provision | `manual-payment-retirement` and `manual-notify-retirement` tests; live 410 on both Workers |
