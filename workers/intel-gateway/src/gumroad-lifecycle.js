// =============================================================================
// CYBERDUDEBIVASH(R) SENTINEL APEX -- Gumroad Lifecycle (pure module)
//
// Extracted from handleWebhookGumroad() (index.js) for the same reason
// subscription-lifecycle.js was extracted (see that file's header comment):
// zero imports of its own, so it can be unit-tested under plain
// `node --test` without pulling in index.js's full import chain (which
// transitively fails Node's native ESM loader via pricing.js's
// pricing-data.json import). Pure decision logic only -- no KV, no
// network. handleWebhookGumroad() is the only production caller.
//
// inferGumroadTier() is a straight move of the tier-inference logic that
// already lived inline in handleWebhookGumroad() (Principle 3: single
// source of truth, not a second implementation).
//
// isGumroadCancellationEvent() covers a gap the existing webhook never
// handled: Gumroad's "Subscription updated" ping (posted to the same
// webhook URL as the "sale" ping) carries `cancelled: "true"` when the
// buyer cancels auto-renewal, or `ended: "true"` once the subscription
// period actually ends -- neither field was read before, so a Gumroad
// subscription cancellation never revoked platform access.
// =============================================================================

export function inferGumroadTier(productName, variants) {
  const pnl = `${productName || ""}${variants || ""}`.toLowerCase();
  // Bug fix: the original inline check also matched the bare substring
  // "ent", which false-positives on every product name here -- all of them
  // are branded "CYBERDUDEBIVASH SENTINEL APEX ..." and "Sentinel" itself
  // contains "ent". That silently misclassified every PRO sale as
  // ENTERPRISE. "enterprise" (the full word) is unambiguous and sufficient.
  if (pnl.includes("mssp") || pnl.includes("white-label")) return "MSSP";
  if (pnl.includes("enterprise")) return "ENTERPRISE";
  return "PRO";
}

/**
 * Gumroad sends `recurrence` on subscription products: "monthly",
 * "quarterly", "biannually", "yearly", or "every_two_years". This platform's
 * billing model (provisionApiKey's cycleDays, and every Razorpay/Gumroad
 * price table in pricing-data.json / GUMROAD_URLS) only has two buckets --
 * monthly and annual -- so "quarterly"/"biannually"/"every_two_years"
 * collapse to "monthly" here, the same as they always have. No configured
 * Gumroad product currently uses those recurrences (GUMROAD_URLS in
 * upgrade.html only lists monthly/annual variants); if one ever does,
 * provisionApiKey's cycleDays needs a third bucket before this can be
 * accurate for it -- that's a cross-gateway pricing-model change, out of
 * scope here.
 * @param {string} recurrence
 * @param {string} productName
 * @param {string} variants
 * @returns {"monthly"|"annual"}
 */
export function inferGumroadBillingCycle(recurrence, productName, variants) {
  const r = String(recurrence || "").toLowerCase();
  if (r === "yearly" || r === "annually" || r === "annual") return "annual";
  const pnl = `${productName || ""}${variants || ""}`.toLowerCase();
  return pnl.includes("annual") ? "annual" : "monthly";
}

/**
 * @param {Record<string, string>} formData raw Gumroad Ping form fields
 * @returns {boolean} true when this ping represents a subscription
 *   cancellation or end-of-term event, not a new sale
 */
export function isGumroadCancellationEvent(formData) {
  if (!formData) return false;
  const cancelled = String(formData.cancelled || "").toLowerCase();
  const ended = String(formData.ended || "").toLowerCase();
  return cancelled === "true" || ended === "true";
}

/**
 * `cancelled: "true"` alone means the buyer turned off auto-renewal -- the
 * current paid period is not affected, so access must continue until it
 * actually ends. Only `ended: "true"` (Gumroad's ping once the subscription
 * has actually terminated) means access should be revoked now. Without this
 * distinction, a customer who cancels on day 1 of a 30-day period would
 * lose access to 29 days they already paid for.
 * @param {Record<string, string>} formData raw Gumroad Ping form fields
 * @returns {boolean} true only once access should actually be revoked
 */
export function isGumroadAccessRevokingEvent(formData) {
  if (!formData) return false;
  return String(formData.ended || "").toLowerCase() === "true";
}
