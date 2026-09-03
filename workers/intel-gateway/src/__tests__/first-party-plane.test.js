import assert from "node:assert/strict";
import { test } from "node:test";
import {
  WEB_PLANE_LIMITS, FIRST_PARTY_READ_PATHS, isFirstPartyRead, normalizePlanePath,
  webPlaneRateKey, webPlaneDailyKey, evaluateWebPlaneDaily, firstPartyPlaneObservability,
} from "../first-party-plane.js";
import { DAILY_QUOTAS } from "../daily-quota.js";

// ---------------------------------------------------------------------------
// P0 incident 2026-09-03. Measured against production in a real Chromium: one
// render of https://intel.cyberdudebivash.com/ issues 27 requests to /api/*
// (docs/incidents/P0-PRODUCTION-REQUEST-MATRIX.md). The commercial FREE tier
// allows 30/minute (RATE_LIMITS, index.js) and 50/day (DAILY_QUOTAS,
// daily-quota.js). The dashboard was metered against that plane, so the
// second page view of a UTC day exhausted the quota for the visitor's whole
// IP. These tests pin the separation that fixes it, and -- just as
// importantly -- pin that the commercial plane was NOT weakened to do so.
// ---------------------------------------------------------------------------

const RENDER_COST = 27; // measured, see the request matrix

test("REGRESSION: one dashboard render must not exhaust the plane it is metered against", () => {
  // This is the defect, stated as an assertion. Against the commercial FREE
  // tier a single render costs 27 of 30 per-minute and 27 of 50 per-day --
  // so two renders (54) exceed the daily quota. That is the outage.
  assert.ok(RENDER_COST * 2 > DAILY_QUOTAS.FREE.limit,
    "precondition: two renders exceeded the commercial FREE daily quota -- this is the bug being fixed");

  // Against the web plane, a render must be comfortably affordable, repeatedly.
  assert.ok(WEB_PLANE_LIMITS.perMinute >= RENDER_COST * 8,
    "web plane must permit at least 8 renders per minute (hard refresh + auto-refresh + several tabs)");
  assert.ok(WEB_PLANE_LIMITS.perDay >= RENDER_COST * 70,
    "web plane must permit at least 70 renders per UTC day from one IP (shared NAT egress)");
});

test("the commercial plane's own limits are untouched by this change", () => {
  // Guards against the prohibited 'fix': raising FREE's quota or disabling it.
  assert.deepEqual(DAILY_QUOTAS.FREE, { limit: 50, alertAt: 40 },
    "commercial FREE daily quota must remain exactly 50/day -- separation, not inflation");
  assert.deepEqual(DAILY_QUOTAS.PRO, { limit: 5000, alertAt: 4000 });
  assert.deepEqual(DAILY_QUOTAS.ENTERPRISE, { limit: 50000, alertAt: 40000 });
});

// --- admission ------------------------------------------------------------

test("isFirstPartyRead: anonymous GET of a dashboard read path is admitted", () => {
  assert.equal(isFirstPartyRead({ path: "/api/feed.json", method: "GET", hasCredential: false }), true);
  assert.equal(isFirstPartyRead({ path: "/api/v1/intel/latest.json", method: "GET", hasCredential: false }), true);
  assert.equal(isFirstPartyRead({ path: "/api/v1/intel/stats", method: "HEAD", hasCredential: false }), true);
  assert.equal(isFirstPartyRead({ path: "/api/feed.json", method: "get", hasCredential: false }), true,
    "method comparison must be case-insensitive");
});

test("isFirstPartyRead: ANY credential routes to the commercial plane, on every path", () => {
  // The commercial guarantee. A FREE-tier API customer calling a dashboard
  // endpoint must still be metered at 50/day -- they must not be able to
  // reach the web plane's larger budget by picking a dashboard route.
  for (const p of FIRST_PARTY_READ_PATHS) {
    assert.equal(isFirstPartyRead({ path: p, method: "GET", hasCredential: true }), false,
      `credentialed caller must stay on the commercial plane for ${p}`);
  }
});

test("isFirstPartyRead: the web plane is read-only", () => {
  for (const m of ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"]) {
    assert.equal(isFirstPartyRead({ path: "/api/feed.json", method: m, hasCredential: false }), false,
      `${m} must never reach the web plane`);
  }
});

test("isFirstPartyRead: unlisted paths fail closed to the commercial plane", () => {
  // Exact-match allowlist, deliberately not a prefix -- a prefix would enrol
  // future routes silently, which is the drift that caused this incident.
  const unlisted = [
    "/api/v1/intel/premium-only-future-route",
    "/api/admin/keys",
    "/api/auth/login",
    "/api/payment/create-order",
    "/taxii/collections/",
    "/api/v1/intel/",
    "/api/feed.json/extra",
    "/api/health",
  ];
  for (const p of unlisted) {
    assert.equal(isFirstPartyRead({ path: p, method: "GET", hasCredential: false }), false,
      `${p} must not be admitted to the web plane`);
  }
});

test("isFirstPartyRead: tolerates malformed input without throwing", () => {
  assert.equal(isFirstPartyRead(null), false);
  assert.equal(isFirstPartyRead(undefined), false);
  assert.equal(isFirstPartyRead("/api/feed.json"), false);
  assert.equal(isFirstPartyRead({}), false);
  assert.equal(isFirstPartyRead({ path: undefined, method: "GET", hasCredential: false }), false);
});

test("normalizePlanePath: one trailing slash is optional, bare / is preserved", () => {
  assert.equal(normalizePlanePath("/api/v1/intel/stats/"), "/api/v1/intel/stats");
  assert.equal(normalizePlanePath("/api/v1/intel/stats"), "/api/v1/intel/stats");
  assert.equal(normalizePlanePath("/"), "/");
  assert.equal(normalizePlanePath(""), "");
  assert.equal(normalizePlanePath(null), "");
  assert.equal(isFirstPartyRead({ path: "/api/preview/", method: "GET", hasCredential: false }), true,
    "/api/preview/ is registered both ways and must match either");
  assert.equal(isFirstPartyRead({ path: "/api/preview", method: "GET", hasCredential: false }), true);
});

// --- plane membership completeness ----------------------------------------

test("every endpoint the production dashboard requests is in the plane", () => {
  // Captured from a real Chromium page load against production -- if a
  // renderer is ever pointed at an endpoint missing from this set, that
  // endpoint silently falls back onto the commercial FREE quota and
  // reintroduces the outage for that widget.
  const OBSERVED_IN_PRODUCTION_RENDER = [
    "/api/feed.json", "/api/reports/index.json", "/api/reports/stats.json",
    "/api/ai/tracker.json", "/api/platform/stats", "/api/metrics",
    "/api/v1/intel/stats", "/api/v1/intel/latest.json", "/api/v1/intel/apex.json",
    "/api/v1/intel/ai_summary.json", "/api/v1/intel/defcon", "/api/v1/intel/cybermap",
    "/api/v1/intel/pulse", "/api/v1/intel/ransomware", "/api/v1/intel/apt",
    "/api/v1/intel/epss", "/api/v1/intel/campaigns", "/api/v1/intel/darkweb",
    "/api/v1/cve/live", "/api/v1/news/feed",
  ];
  assert.equal(OBSERVED_IN_PRODUCTION_RENDER.length, 20, "20 distinct endpoints were observed");
  for (const p of OBSERVED_IN_PRODUCTION_RENDER) {
    assert.ok(FIRST_PARTY_READ_PATHS.has(p), `observed dashboard endpoint ${p} is missing from the plane`);
  }
});

test("the plane never admits an auth, admin, payment or TAXII route", () => {
  for (const p of FIRST_PARTY_READ_PATHS) {
    assert.ok(!p.startsWith("/api/admin"), `${p} must not be in the web plane`);
    assert.ok(!p.startsWith("/api/auth"), `${p} must not be in the web plane`);
    assert.ok(!p.startsWith("/api/payment"), `${p} must not be in the web plane`);
    assert.ok(!p.startsWith("/taxii"), `${p} must not be in the web plane`);
    assert.ok(p.startsWith("/api/"), `${p} must be an /api/ path`);
  }
});

// --- KV keyspace isolation -------------------------------------------------

test("web plane counters live in their own KV keyspace", () => {
  // If the two planes shared a key, anonymous rendering would consume a
  // commercial caller's budget (or vice versa) -- exactly the conflation
  // this module exists to end.
  assert.equal(webPlaneRateKey("1.2.3.4", 29473920), "rl:web:1.2.3.4:29473920");
  assert.equal(webPlaneDailyKey("1.2.3.4", "2026-09-03"), "quota:web:1.2.3.4:2026-09-03");
  assert.notEqual(webPlaneRateKey("1.2.3.4", 1), "rl:1.2.3.4:1", "must not collide with checkRateLimit's key");
  assert.notEqual(webPlaneDailyKey("1.2.3.4", "2026-09-03"), "quota:daily:1.2.3.4:2026-09-03",
    "must not collide with dailyQuotaKey's key");
});

// --- daily evaluation ------------------------------------------------------

test("evaluateWebPlaneDaily: boundary matches evaluateDailyQuota's contract", () => {
  const limit = WEB_PLANE_LIMITS.perDay;
  const at = n => evaluateWebPlaneDaily(n);
  assert.equal(at(1).exceeded, false);
  assert.equal(at(limit - 1).exceeded, false);
  assert.equal(at(limit).exceeded, false, "the request exactly at the limit still succeeds");
  assert.equal(at(limit).remaining, 0);
  assert.equal(at(limit + 1).exceeded, true, "the first request past the limit is denied");
  assert.equal(at(limit + 500).remaining, 0, "remaining never goes negative");
});

test("the web plane still enforces a real ceiling -- it is a quota, not an exemption", () => {
  assert.ok(Number.isFinite(WEB_PLANE_LIMITS.perMinute) && WEB_PLANE_LIMITS.perMinute > 0);
  assert.ok(Number.isFinite(WEB_PLANE_LIMITS.perDay) && WEB_PLANE_LIMITS.perDay > 0);
  assert.equal(evaluateWebPlaneDaily(WEB_PLANE_LIMITS.perDay + 1).exceeded, true,
    "abuse protection must remain: the web plane throttles once its own ceiling is crossed");
});

// --- observability ---------------------------------------------------------

test("firstPartyPlaneObservability exposes the live plane for drift detection", () => {
  const o = firstPartyPlaneObservability();
  assert.equal(o.plane, "first_party_web_read");
  assert.equal(o.path_count, FIRST_PARTY_READ_PATHS.size);
  assert.equal(o.paths.length, FIRST_PARTY_READ_PATHS.size);
  assert.deepEqual(o.paths, [...o.paths].sort(), "paths are sorted for stable diffing");
  assert.deepEqual(o.limits, { per_minute: WEB_PLANE_LIMITS.perMinute, per_day: WEB_PLANE_LIMITS.perDay });
  assert.equal(o.commercial_plane_unchanged, true);
  assert.deepEqual(o.admission.methods, ["GET", "HEAD"]);
});
