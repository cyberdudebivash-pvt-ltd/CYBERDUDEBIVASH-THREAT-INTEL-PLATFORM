# CYBERDUDEBIVASH SENTINEL APEX — Payment Webhook → Subscription Lifecycle Mapping (v185)

**Mission:** SENTINEL APEX v185.0 Phase 2. Documents what this platform's
**actual** payment integration can and cannot signal, and what was built to
map real events into the new `subscription_status` model
(`docs/SUBSCRIPTION_STATE_MODEL_V185.md`).

---

## 1. Architecture correction

Mission Phase 2 asks for mappings like "successful renewal → active +
updated expiry" and "cancellation → cancelled" as if this were a recurring
subscription integration. **It is not.** `handleRazorpayCreateOrder`
(`workers/intel-gateway/src/index.js`) calls
`https://api.razorpay.com/v1/orders` — Razorpay's one-time **Orders API**,
never the recurring **Subscriptions API** (`/v1/subscriptions`). There is no
`subscription_id`, `plan_id`, or recurring-mandate concept anywhere in this
codebase's Razorpay integration. Every "renewal" is, from Razorpay's
perspective, an indistinguishable fresh one-time Order/Payment.

This has real consequences for what's honestly implementable:

| Mission-requested mapping | Real signal available? | What was built |
|---|---|---|
| Successful payment → `active` | Yes — `payment.captured`/`order.paid` webhook, already existed | Already provisions a key; now the record additionally carries `subscription_status` implicitly (absent = active) |
| Successful renewal → `active` + updated expiry | **No native signal** — a renewal is just another `payment.captured` event, provisioning a *new* key rather than updating an existing subscription's expiry (there is no subscription object to update) | Not built — would require moving off one-time Orders to Razorpay Subscriptions, an architectural change out of this pass's scope |
| Failed renewal → `past_due` | **No native signal** — `payment.failed` fires for a failed *initial* checkout attempt (before any key exists), not a failed recurring charge (there is no recurring charge) | Not built as a webhook mapping; `past_due` remains admin-settable only, via `PATCH /api/admin/keys/{key}/status`, for a customer manually flagged as behind on an off-platform renewal |
| Cancellation → `cancelled` | **No native signal** — Razorpay's Subscriptions API emits `subscription.cancelled`; the Orders API this integration uses has no equivalent concept | Built as an **admin/support-initiated action**, not a webhook: `PATCH /api/admin/keys/{key}/status {"subscription_status":"cancelled"}` |
| Refund → `refunded` | **Yes** — `refund.created`/`refund.processed` fire against Payment objects regardless of Orders vs. Subscriptions API | **Built**, see §2 |
| Manual suspension → `suspended` | N/A — inherently admin-initiated in any architecture | Built via the same `PATCH .../status` endpoint |
| `time > expires_at` → `expired` | Already existed (`resolveAuth()`'s `expires_at` check) | Unchanged; `evaluateKeyRecordAccess()` also now accepts an explicit `subscription_status: "expired"` as a redundant signal |
| API-key revocation → denied regardless of subscription state | Already existed (`DELETE /api/admin/keys/{key}`, hard-delete) | Unchanged — this axis is independent of `subscription_status` by design, per the mission's own Phase 2 language |

## 2. What was actually implemented

### Refund → `refunded` (real webhook mapping)

`handleWebhookRazorpay`'s `payment.captured`/`order.paid` branch now writes
a `payment_key_map:{payment_id} → api_key` entry (1-year TTL, matching the
existing idempotency keys) at provisioning time. A new
`refund.created`/`refund.processed` branch resolves that mapping and calls
`applySubscriptionStatusChange(env, ctx, key, "refunded", reason)` — the
same function the admin endpoint uses (single source of truth, Principle 3).
If no mapping is found (payment older than the 1-year TTL, or a refund for
a payment that predates this change), the event is logged
(`refund_key_lookup_failed`) and alerted to Telegram for manual follow-up
rather than silently dropped.

Signature verification, idempotency (via the existing HMAC + unified
idempotency-key mechanism this handler already had), order/payment binding,
and out-of-order safety are inherited from the existing webhook
infrastructure — this addition doesn't introduce a new trust boundary, it
extends the existing signed-webhook handler with one more event type.

### `applySubscriptionStatusChange()` (`workers/intel-gateway/src/index.js`)

Single function backing both the refund webhook above and:

```
PATCH /api/admin/keys/{key}/status   body: {subscription_status, reason?}
```

Used for cancellation, suspension, reactivation, and any other admin- or
support-initiated lifecycle transition. Preserves the KV record's TTL
(Cloudflare KV drops it on a bare `put()` otherwise — a real bug this
implementation had to account for) and audit-logs every transition with
`from`/`to`/`reason`.

### Key rotation (Mission Phase 8)

```
POST /api/admin/keys/{key}/rotate
```

Issues a new key for the same customer/tier/billing cycle and hard-deletes
the old one in the same request — "new key issuance → old key immediately
revoked, no overlap window," per the mission's own minimum bar.

## 3. Gumroad

`handleWebhookGumroad` only ever receives Gumroad's "sale" ping (per the
comment in that handler, the webhook URL is configured for that one ping
type). Gumroad supports separate refund/dispute pings via different webhook
configuration, not currently set up — out of scope for this pass. Any
Gumroad refund today would need the same admin-initiated
`PATCH .../status` path.

---
*CYBERDUDEBIVASH SENTINEL APEX — Mission v185.0 Phase 2 deliverable*
