import assert from "node:assert/strict";
import { test } from "node:test";
import {
  DAILY_QUOTAS, dailyQuotaConfig, dailyQuotaKey, quotaAlertDedupeKey,
  evaluateDailyQuota, utcDateString, secondsUntilNextUtcMidnight,
} from "../daily-quota.js";

// ---------------------------------------------------------------------------
// Business decision (2026-08-31): Community/Free = 50/day (alert at 40),
// Pro = 5,000/day (alert at 4,000), Enterprise = 50,000/day (alert at
// 40,000). Boundary conditions specifically requested: request 40 triggers
// the alert check, request 50 still succeeds, request 51 is denied.
// ---------------------------------------------------------------------------

test("dailyQuotaConfig: FREE/PRO/ENTERPRISE match the finalized business decision", () => {
  assert.deepEqual(dailyQuotaConfig("FREE"), { limit: 50, alertAt: 40 });
  assert.deepEqual(dailyQuotaConfig("PRO"), { limit: 5000, alertAt: 4000 });
  assert.deepEqual(dailyQuotaConfig("ENTERPRISE"), { limit: 50000, alertAt: 40000 });
});

test("dailyQuotaConfig: MSSP inherits ENTERPRISE's cap (no distinct figure was specified, MSSP ranks >= ENTERPRISE elsewhere in this codebase)", () => {
  assert.deepEqual(dailyQuotaConfig("MSSP"), dailyQuotaConfig("ENTERPRISE"));
});

test("dailyQuotaConfig: unknown/missing tier defaults to FREE, fails closed not open", () => {
  assert.deepEqual(dailyQuotaConfig(undefined), DAILY_QUOTAS.FREE);
  assert.deepEqual(dailyQuotaConfig("totally_made_up"), DAILY_QUOTAS.FREE);
});

test("evaluateDailyQuota: FREE tier boundary -- request 39 does not alert, request 40 does, request 50 still succeeds, request 51 is denied", () => {
  const at39 = evaluateDailyQuota("FREE", 39);
  assert.equal(at39.exceeded, false);
  assert.equal(at39.crossedAlertThreshold, false);

  const at40 = evaluateDailyQuota("FREE", 40);
  assert.equal(at40.exceeded, false, "the 40th request itself must still succeed -- 40 is the alert point, not the limit");
  assert.equal(at40.crossedAlertThreshold, true);

  const at50 = evaluateDailyQuota("FREE", 50);
  assert.equal(at50.exceeded, false, "the 50th request is exactly at the limit and must still succeed");
  assert.equal(at50.remaining, 0);

  const at51 = evaluateDailyQuota("FREE", 51);
  assert.equal(at51.exceeded, true, "the 51st request must be denied");
});

test("evaluateDailyQuota: crossedAlertThreshold uses >= so a racy counter that skips past 40 in one jump still fires the alert check", () => {
  // Cloudflare KV's read-then-write counter pattern (same one checkRateLimit()
  // already uses) isn't atomic under concurrency -- a burst of parallel
  // requests can land the counter on, say, 42 without any single request
  // having observed exactly 40. Strict equality would silently skip the
  // alert forever for that day; >= does not.
  const result = evaluateDailyQuota("FREE", 42);
  assert.equal(result.crossedAlertThreshold, true);
});

test("evaluateDailyQuota: remaining never goes negative once past the limit", () => {
  const result = evaluateDailyQuota("PRO", 5010);
  assert.equal(result.remaining, 0);
  assert.equal(result.exceeded, true);
});

test("evaluateDailyQuota: PRO and ENTERPRISE boundaries match their own configured limits", () => {
  assert.equal(evaluateDailyQuota("PRO", 5000).exceeded, false);
  assert.equal(evaluateDailyQuota("PRO", 5001).exceeded, true);
  assert.equal(evaluateDailyQuota("ENTERPRISE", 50000).exceeded, false);
  assert.equal(evaluateDailyQuota("ENTERPRISE", 50001).exceeded, true);
});

test("dailyQuotaKey / quotaAlertDedupeKey: stable, distinct, human-inspectable KV key shapes", () => {
  assert.equal(dailyQuotaKey("sk_live_abc", "2026-08-31"), "quota:daily:sk_live_abc:2026-08-31");
  assert.equal(quotaAlertDedupeKey("sk_live_abc", "2026-08-31"), "alert_sent:80pct:sk_live_abc:2026-08-31");
  // Never collide with each other or with unrelated identifiers.
  assert.notEqual(dailyQuotaKey("a", "2026-08-31"), dailyQuotaKey("b", "2026-08-31"));
});

test("utcDateString: matches the {YYYY-MM-DD} convention used elsewhere in this codebase (usage-meter.js)", () => {
  const d = new Date("2026-08-31T23:59:59.000Z");
  assert.equal(utcDateString(d), "2026-08-31");
});

test("secondsUntilNextUtcMidnight: counts down to the real UTC day boundary, not a fixed round number", () => {
  const justAfterMidnight = new Date("2026-08-31T00:00:01.000Z");
  assert.equal(secondsUntilNextUtcMidnight(justAfterMidnight), 86399);

  const oneSecondBeforeMidnight = new Date("2026-08-31T23:59:59.000Z");
  assert.equal(secondsUntilNextUtcMidnight(oneSecondBeforeMidnight), 1);
});
