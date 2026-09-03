/**
 * Guards the /api/metrics route (index.js) against regressing on the two
 * defects it was added to close, both discovered while implementing
 * p0-revenue-os/config/metric_integrity_contract.json (contract_id
 * APEX-METRIC-INTEGRITY-v1, landed on main alongside js/p0-public-contract.js
 * in a concurrent session):
 *
 *   1. That contract's own runtime (js/p0-public-contract.js's loadMetrics())
 *      has always called GET /api/metrics first -- a route that, until this
 *      fix, did not exist at all. A contract with no backend behind it is
 *      the same drift class as a backend route with no frontend consumer,
 *      just inverted.
 *   2. Two pre-existing sibling routes (/api/platform/stats,
 *      /api/v1/intel/stats) hardcoded feed_count/active_feeds/feeds_active
 *      to the literal 74 -- exactly the "hardcoded marketing number" class
 *      metric_integrity_contract.json's forbidden_hardcodes list exists to
 *      forbid, just living in a JSON API field instead of HTML copy.
 *
 * index.js is a single ~6000+ line request handler with no clean per-route
 * import seam (see reports-canonical-write-guard.test.js's header for the
 * same rationale in more detail, and this file's own pricing-data.json ->
 * Node-ESM-JSON-import-attribute incompatibility, which is why no test file
 * in this directory imports index.js directly under plain `node --test`).
 * Static source-invariant checks are the honest, low-risk way to lock this
 * in without constructing a fake Request/env/R2 binding for a handler this
 * large.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const INDEX_JS_PATH = join(HERE, "..", "index.js");
const source = readFileSync(INDEX_JS_PATH, "utf-8");

test("/api/metrics route exists", () => {
  assert.match(
    source, /path === "\/api\/metrics"/,
    "GET /api/metrics must exist -- js/p0-public-contract.js's loadMetrics() has always called this " +
    "path first on every page that loads it; removing the route silently breaks that contract's " +
    "primary (non-fallback) data source."
  );
});

test("/api/metrics reuses computeStats/loadFeedItems/classifyFreshness instead of re-implementing feed aggregation", () => {
  const routeStart = source.indexOf('path === "/api/metrics"');
  assert.ok(routeStart > -1, "route not found (see previous test)");
  const routeBody = source.slice(routeStart, routeStart + 3000);
  for (const fn of ["loadFeedItems(env)", "computeStats(", "classifyFreshness("]) {
    assert.ok(
      routeBody.includes(fn),
      `/api/metrics must call the existing ${fn} rather than re-implementing feed loading, stat ` +
      `aggregation, or freshness classification -- these are the same engines /api/platform/stats, ` +
      `/api/v1/intel/stats, and /api/health already use (Single Source of Truth).`
    );
  }
});

test("/api/metrics never fabricates api_uptime_30d_pct (no uptime-history store exists in this codebase)", () => {
  const routeStart = source.indexOf('path === "/api/metrics"');
  const routeBody = source.slice(routeStart, routeStart + 3000);
  assert.match(
    routeBody, /api_uptime_30d_pct:\s*null/,
    "api_uptime_30d_pct must stay a literal null until a real uptime-history data source exists -- " +
    "inventing a percentage here is exactly what metric_integrity_contract.json's own sample file " +
    "calls a contract violation ('Shipping this file with invented integers is a contract violation')."
  );
});

test("no route hardcodes the legacy feed_count/active_feeds/feeds_active literal 74", () => {
  for (const pattern of [/feed_count:\s*74\b/, /active_feeds:\s*74\b/, /feeds_active:\s*74\b/]) {
    assert.doesNotMatch(
      source, pattern,
      `Found a hardcoded 74 for a feed-count field. This regressed once already (both ` +
      `/api/platform/stats and /api/v1/intel/stats shipped this literal) -- these fields must come ` +
      `from _liveFeedSourceCount(env) (P40's live source registry), with the 74 fallback only inside ` +
      `that function's own error path via the named _LEGACY_FEED_COUNT_FALLBACK constant, never typed ` +
      `directly at a route's response-object literal again.`
    );
  }
});

test("_liveFeedSourceCount exists, is reused by both legacy stats routes and /api/metrics, and never silently defaults to a fabricated number for the contract route", () => {
  assert.match(
    source, /async function _liveFeedSourceCount\(env\)/,
    "_liveFeedSourceCount(env) must exist as the single source of truth for 'how many feed sources " +
    "are live' -- both legacy stats routes and /api/metrics should share one read, not duplicate it."
  );
  const callSites = (source.match(/_liveFeedSourceCount\(env\)/g) || []).length;
  assert.ok(
    callSites >= 4,
    `expected _liveFeedSourceCount(env) to be both defined and called at least 3 times (2 legacy ` +
    `routes + /api/metrics), found ${callSites} total occurrences (including the definition itself).`
  );
  // The two legacy routes are allowed their own explicit `?? _LEGACY_FEED_COUNT_FALLBACK` for
  // backward compatibility; /api/metrics must not apply that same fallback, since a contract route
  // silently substituting 74 for a genuinely unavailable registry is the same fabrication the whole
  // route exists to prevent.
  const metricsStart = source.indexOf('path === "/api/metrics"');
  const metricsBody = source.slice(metricsStart, metricsStart + 3000);
  assert.doesNotMatch(
    metricsBody, /_liveFeedSourceCount\(env\)\)\s*\?\?\s*_LEGACY_FEED_COUNT_FALLBACK/,
    "/api/metrics must not apply the legacy-74 fallback to feed_source_count -- it must stay honestly " +
    "null when the source registry is unavailable, per the contract's own no-invented-integers rule."
  );
});
