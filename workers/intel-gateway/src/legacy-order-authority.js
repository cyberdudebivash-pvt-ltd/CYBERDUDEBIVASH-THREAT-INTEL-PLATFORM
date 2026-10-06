// =============================================================================
// CYBERDUDEBIVASH(R) SENTINEL APEX -- legacy one-time Razorpay Order authority
//
// P0 (2026-10-02). The gateway's one-time Order paths (POST
// /api/payment/razorpay/verify and POST /api/webhooks/razorpay) provisioned a
// key for any captured one-time payment: the webhook defaulted the tier to
// PRO and the email to "unknown@razorpay", and /verify took the billing cycle
// from the browser. Create-order has refused every paid tier since 2026-09-24
// (paid plans are Razorpay Subscriptions, handled by the revenue engine), so
// the only one-time payment that may still activate a key is an Order this
// gateway created before then: notes { platform: "SENTINEL-APEX", tier,
// billing, email } and exactly the INR amount for that tier and cycle.
// Anything else (a payment link, a payment page, a different amount or
// currency, missing notes) provisions nothing.
//
// Pure: no KV, no network. The prices come from pricing.js
// (RAZORPAY_TIER_PRICES), the same table create-order charged from.
// =============================================================================

export const LEGACY_ORDER_PLATFORM = "SENTINEL-APEX";
export const LEGACY_ORDER_CYCLES = Object.freeze(["monthly", "annual"]);

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Decide whether a captured one-time Razorpay payment may activate a key.
 * @param {{amount?: number, currency?: string, notes?: object}} payment the
 *   payment entity (from Razorpay's API or a signed webhook), with the
 *   Order's notes
 * @param {Record<string, {monthly: number, annual: number}>} prices paise per
 *   tier and cycle
 * @returns {{ok: true, tier: string, billing: string, email: string} |
 *   {ok: false, reason: string}}
 */
export function legacyOrderEntitlement(payment, prices) {
  const p = payment && typeof payment === "object" ? payment : {};
  const notes = p.notes && typeof p.notes === "object" ? p.notes : {};
  if (notes.platform !== LEGACY_ORDER_PLATFORM) return { ok: false, reason: "not_created_by_this_platform" };
  const tier = String(notes.tier || "").toUpperCase();
  const price = prices && Object.prototype.hasOwnProperty.call(prices, tier) ? prices[tier] : null;
  if (!price) return { ok: false, reason: "unknown_tier" };
  const billing = notes.billing;
  if (!LEGACY_ORDER_CYCLES.includes(billing)) return { ok: false, reason: "unknown_billing_cycle" };
  if (p.currency !== "INR") return { ok: false, reason: "currency_mismatch" };
  if (!Number.isInteger(p.amount) || p.amount !== price[billing]) return { ok: false, reason: "amount_mismatch" };
  const email = typeof notes.email === "string" ? notes.email.trim() : "";
  if (!EMAIL_RE.test(email)) return { ok: false, reason: "missing_email" };
  return { ok: true, tier, billing, email };
}
