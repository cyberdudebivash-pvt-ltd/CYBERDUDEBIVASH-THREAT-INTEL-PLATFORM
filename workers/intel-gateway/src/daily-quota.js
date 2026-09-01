// =============================================================================
// CYBERDUDEBIVASH SENTINEL APEX -- Daily Quota Decision Logic
// Small, dependency-free module (same reason subscription-lifecycle.js is one:
// index.js's full import chain fails Node's native ESM loader outside the
// wrangler/esbuild bundler via pricing.js's pricing-data.json import) so this
// pure decision logic can be unit-tested directly with `node --test`.
//
// Additive to, not a replacement for, checkRateLimit()'s existing per-*minute*
// RATE_LIMITS -- that mechanism is unchanged. This is a second, independent
// gate: a request must pass both the per-minute burst limit and this daily
// volume quota to proceed. Business decision (2026-08-31): Community/Free =
// 50/day (alert at 40), Pro = 5,000/day (alert at 4,000), Enterprise =
// 50,000/day (alert at 40,000). MSSP has no distinct figure in that decision;
// it inherits Enterprise's cap rather than inventing a number -- MSSP already
// ranks >= Enterprise everywhere else in this codebase (see api-extensions.js
// TIER_DEFAULT_SCOPES's own comment on this exact convention).
// =============================================================================

export const DAILY_QUOTAS = Object.freeze({
  FREE:       Object.freeze({ limit: 50,    alertAt: 40 }),
  PRO:        Object.freeze({ limit: 5000,  alertAt: 4000 }),
  ENTERPRISE: Object.freeze({ limit: 50000, alertAt: 40000 }),
  MSSP:       Object.freeze({ limit: 50000, alertAt: 40000 }),
});

export function dailyQuotaConfig(tier) {
  return DAILY_QUOTAS[tier] || DAILY_QUOTAS.FREE;
}

// UTC calendar day, matching the {YYYY-MM-DD} key convention usage-meter.js
// already uses for its own per-day counters.
export function utcDateString(now = new Date()) {
  return now.toISOString().slice(0, 10);
}

export function dailyQuotaKey(identifier, dateStr) {
  return `quota:daily:${identifier}:${dateStr}`;
}

export function quotaAlertDedupeKey(identifier, dateStr) {
  return `alert_sent:80pct:${identifier}:${dateStr}`;
}

/**
 * Pure decision function: given a tier and the counter value *after* this
 * request's increment has already been applied, decide what the caller
 * should see and whether an 80%-threshold alert check is warranted.
 *
 * @param {string} tier - "FREE" | "PRO" | "ENTERPRISE" | "MSSP".
 * @param {number} countAfterIncrement - the daily counter's value including
 *   the current request (i.e. count-before + 1).
 * @returns {{limit:number, remaining:number, exceeded:boolean, crossedAlertThreshold:boolean}}
 *   `exceeded` means this request itself should be denied (count is already
 *   over the limit). `crossedAlertThreshold` uses >= rather than === so a
 *   racy KV counter that jumps past the exact alert value in one step still
 *   correctly triggers the alert check on the first request at or above it --
 *   actual send-once-per-day is enforced separately via quotaAlertDedupeKey,
 *   not by this equality check.
 */
export function evaluateDailyQuota(tier, countAfterIncrement) {
  const cfg = dailyQuotaConfig(tier);
  return {
    limit: cfg.limit,
    remaining: Math.max(0, cfg.limit - countAfterIncrement),
    exceeded: countAfterIncrement > cfg.limit,
    crossedAlertThreshold: countAfterIncrement >= cfg.alertAt,
  };
}

// Seconds until the next UTC midnight -- used both for the KV entry's TTL
// (kept at a flat 48h per the spec, generous enough to survive clock/KV
// propagation skew right at the day boundary) and for the client-facing
// X-DailyLimit-Reset header, which reports the real reset instant rather
// than a fixed round number.
export function secondsUntilNextUtcMidnight(now = new Date()) {
  const next = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1, 0, 0, 0));
  return Math.max(1, Math.ceil((next.getTime() - now.getTime()) / 1000));
}
