// =============================================================================
// CYBERDUDEBIVASH(R) SENTINEL APEX -- checkout provider availability (pure)
//
// upgrade.html reads this from GET /api/pricing (the request it already
// makes) to decide which automated checkouts it may offer:
//
//   razorpay  PRIMARY. Always offered: the revenue engine's
//             subscriptions/create fails closed (no Plan, unverified Plan
//             price, no keys -> 503) before any payment UI opens, and the
//             key is shown on the checkout page once the payment activates.
//   gumroad   SECONDARY. Checkout happens on Gumroad's own page, so access
//             depends on two things this Worker does after the sale:
//               1. provisioning: only the signed ping to
//                  POST /api/webhooks/gumroad grants access, and it refuses
//                  every ping while GUMROAD_WEBHOOK_SECRET is unset (F21,
//                  production 2026-10-01);
//               2. delivery: email is the only way a Gumroad buyer receives
//                  the key (sendActivationEmail, RESEND_API_KEY).
//             Without both, a Gumroad buyer pays and gets no key
//             automatically, so Gumroad is offered only while both are set.
//
// Presence only: never a secret, a product id or any other configuration
// value. Zero imports, so plain `node --test` can load it.
// =============================================================================

export const GUMROAD_UNAVAILABLE_REASONS = Object.freeze({
  provisioning: "automated_provisioning_not_configured",
  delivery: "key_delivery_not_configured",
});

function configured(value) {
  return typeof value === "string" && value.trim().length > 0;
}

/** @returns {{razorpay: object, gumroad: object}} */
export function checkoutProviderAvailability(env) {
  const e = env || {};
  const razorpay = { role: "primary", currency: "INR", billing: "subscription" };
  if (!configured(e.GUMROAD_WEBHOOK_SECRET)) {
    return { razorpay, gumroad: { role: "secondary", currency: "USD", available: false, reason: GUMROAD_UNAVAILABLE_REASONS.provisioning } };
  }
  if (!configured(e.RESEND_API_KEY)) {
    return { razorpay, gumroad: { role: "secondary", currency: "USD", available: false, reason: GUMROAD_UNAVAILABLE_REASONS.delivery } };
  }
  return { razorpay, gumroad: { role: "secondary", currency: "USD", available: true } };
}
