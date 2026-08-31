// =============================================================================
// CYBERDUDEBIVASH(R) SENTINEL APEX -- Billing Checkout Router (pure module)
//
// GET /api/billing/checkout?tier=pro|enterprise&currency=usd|inr redirects
// to the correct REAL, already-live checkout destination. This does not
// add a new payment processor: India/INR already checks out through
// Razorpay via upgrade.html's existing client-side flow
// (handleRazorpayCreateOrder + the Razorpay Checkout JS widget, both in
// index.js); Global/USD already checks out through the real, live Gumroad
// product links below (verified live against the Gumroad v2 /products API,
// see upgrade.html's v184.0 comment -- reused verbatim here, not
// re-derived). This route only decides which of the two already-working
// destinations a given request should land on.
//
// No Stripe integration: this platform's real dual-gateway split is
// Razorpay (India) + Gumroad (global), not Razorpay + Stripe -- confirmed
// by grepping the deployed worker (POST /api/webhooks/gumroad,
// handleWebhookGumroad) and upgrade.html (GUMROAD_URLS). There is no
// Stripe reference anywhere in this repository.
//
// Pure function, no KV/network -- extracted the same way as
// subscription-lifecycle.js and daily-quota.js so it's unit-testable
// under plain `node --test`.
// =============================================================================

export const GUMROAD_CHECKOUT_URLS = {
  pro:        "https://cyberdudebivash.gumroad.com/l/pxyfcb",
  enterprise: "https://cyberdudebivash.gumroad.com/l/cdedlo",
};

export const UPGRADE_PAGE_URL = "https://intel.cyberdudebivash.com/upgrade.html";

const VALID_TIERS = new Set(["pro", "enterprise", "mssp"]);

/**
 * Resolve the checkout redirect target for GET /api/billing/checkout.
 * @param {{tier?: string, currency?: string, email?: string}} params - parsed query string
 * @param {string|undefined} cfCountry - request.cf.country (Cloudflare-provided geo)
 * @returns {string} absolute URL to redirect the caller to
 */
export function resolveCheckoutUrl({ tier, currency, email } = {}, cfCountry) {
  const normTier = VALID_TIERS.has((tier || "").toLowerCase()) ? tier.toLowerCase() : "pro";
  const currencyLower = (currency || "").toLowerCase();
  const normCurrency = currencyLower === "inr" || currencyLower === "usd"
    ? currencyLower
    : (cfCountry === "IN" ? "inr" : "usd");

  if (normCurrency === "inr") {
    return withUpgradePageParams(normTier, email);
  }

  // MSSP has no Gumroad product (upgrade.html's v184.0 comment: routed to
  // a mailto there instead of a dead link) -- send it to the upgrade page,
  // which already handles that case, rather than fabricating a Gumroad URL.
  const gumroadUrl = GUMROAD_CHECKOUT_URLS[normTier];
  return gumroadUrl || withUpgradePageParams(normTier, email);
}

function withUpgradePageParams(tier, email) {
  const url = new URL(UPGRADE_PAGE_URL);
  url.searchParams.set("plan", tier);
  if (email) url.searchParams.set("email", email);
  return url.toString();
}
