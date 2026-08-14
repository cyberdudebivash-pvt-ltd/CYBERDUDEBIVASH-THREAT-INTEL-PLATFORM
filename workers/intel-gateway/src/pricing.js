/**
 * Canonical pricing provider for workers/intel-gateway.
 *
 * Phase 1 architecture consolidation: this module is now the ONE place the
 * Worker's Razorpay pricing lives. It replaces the RAZORPAY_TIER_PRICES
 * object that used to be defined inline in index.js - the values are
 * unchanged, only their location moved, so this is a zero commercial-impact
 * refactor. See pricing-data.json's "_note" for the known, deliberately
 * unresolved discrepancy against config/pricing.json - do not "fix" that
 * here by editing numbers based on inference; it requires a supplied,
 * business-approved figure (tracked separately).
 */
// RX-PUB-A0.6C: explicit import attribute -- required by Node's native ESM
// loader (which `node --test` uses) since Node 22; esbuild/Wrangler's
// bundler (the actual Workers deploy path) has always accepted this syntax
// too, so this is not a behavior change for production, only what makes a
// direct `node --test` import of this module (or anything importing it,
// e.g. index.js) work at all. Never triggered before this PR because no
// existing test imported index.js or pricing.js directly.
import pricingData from './pricing-data.json' with { type: 'json' };

// Same shape/keys as the constant this replaces, so existing call sites
// (handleRazorpayCreateOrder, etc.) need no changes beyond the import.
export const RAZORPAY_TIER_PRICES = pricingData.tiers;

export function getPricingSnapshot() {
  return {
    status: pricingData._status,
    currency: pricingData.currency,
    unit: pricingData.unit,
    tiers: pricingData.tiers,
  };
}
