import assert from "node:assert/strict";
import { test } from "node:test";
import {
  TIER_DEFAULT_SCOPES, SCOPE_DEFINITIONS, buildScopeSet, enforceScopeMiddleware,
  detectIndicatorType, maskIOCLookupForTier,
} from "../api-extensions.js";

// ---------------------------------------------------------------------------
// Public IOC lookup sandbox (2026-09-01): read:iocs follows the exact same
// free-tier-masked classification as read:cves (api-extensions.cve-scope.
// test.js) -- a basic verdict is public, correlation detail is Pro-gated.
// Mirrors that file's assertions for the new scope, plus the two pure
// helpers (detectIndicatorType, maskIOCLookupForTier) extracted specifically
// to be testable without a mock KV/R2 env, same rationale as
// gumroad-lifecycle.js's own pure-function extraction.
// ---------------------------------------------------------------------------

test("TIER_DEFAULT_SCOPES.free includes read:iocs", () => {
  assert.ok(TIER_DEFAULT_SCOPES.free.includes("read:iocs"));
});

test("SCOPE_DEFINITIONS agrees with TIER_DEFAULT_SCOPES: read:iocs is classified free, not premium", () => {
  assert.equal(SCOPE_DEFINITIONS["read:iocs"].tier, "free");
});

test("buildScopeSet('FREE', null) grants read:iocs", () => {
  const scopes = buildScopeSet("FREE", null);
  assert.ok(scopes.includes("read:iocs"));
});

test("enforceScopeMiddleware allows a FREE-tier (including anonymous) caller to reach read:iocs", () => {
  const auth = { tier: "FREE" };
  const result = enforceScopeMiddleware(auth, "read:iocs", "rid_test");
  assert.equal(result, null, "null means allowed -- a non-null return is the 403 response");
});

test("detectIndicatorType: recognizes every supported shape", () => {
  assert.equal(detectIndicatorType("185.220.101.182"), "ipv4");
  assert.equal(detectIndicatorType("2001:db8::1"), "ipv6");
  assert.equal(detectIndicatorType("secure-audit.info"), "domain");
  assert.equal(detectIndicatorType("https://update-service.cloud/payload/init.ps1"), "url");
  assert.equal(detectIndicatorType("a3d7a58c8a8b55a7c9d2e1f4b6c8d0e2f4a6b8c0d2e4f6a8b0c2d4e6f8a0b2c4"), "sha256");
  assert.equal(detectIndicatorType("da39a3ee5e6b4b0d3255bfef95601890afd80709"), "sha1");
  assert.equal(detectIndicatorType("5d41402abc4b2a76b9719d911017c592"), "md5");
  assert.equal(detectIndicatorType("CVE-2024-12345"), "cve");
});

test("detectIndicatorType: rejects garbage and out-of-range octets", () => {
  assert.equal(detectIndicatorType(""), null);
  assert.equal(detectIndicatorType("not a real indicator!!"), null);
  assert.equal(detectIndicatorType("999.999.999.999"), null);
});

const FULL_RESULT = {
  value: "185.220.101.182", type: "ipv4",
  malicious: true, confidence: 85,
  first_seen: "2026-01-01T00:00:00Z", last_seen: "2026-06-01T00:00:00Z",
  report_count: 2, source_count: 2, severity_max: "critical",
  sources: ["CISA AA22-110A", "Mandiant UNC4166"],
  actor_tags: ["APT29"],
  reports: [{ id: "r1", title: "Report 1", date: "2026-01-01", severity: "critical", risk_score: 9.1 }],
  detection_artifacts: [{ artifact_id: "r1:yara", artifact_type: "yara", content: "rule x { condition: true }" }],
};

test("maskIOCLookupForTier: FREE strips correlation detail but keeps the basic verdict", () => {
  const masked = maskIOCLookupForTier(FULL_RESULT, "FREE");
  assert.equal(masked.locked, true);
  assert.ok(masked.upgrade?.url);
  // Basic verdict survives the mask
  assert.equal(masked.malicious, true);
  assert.equal(masked.confidence, 85);
  assert.equal(masked.report_count, 2);
  assert.equal(masked.source_count, 2);
  // Deep detail does not
  assert.deepEqual(masked.sources, []);
  assert.deepEqual(masked.actor_tags, []);
  assert.deepEqual(masked.reports, []);
  assert.deepEqual(masked.detection_artifacts, []);
});

test("maskIOCLookupForTier: PRO+ receives full correlation detail, unlocked", () => {
  for (const tier of ["PRO", "ENTERPRISE", "MSSP"]) {
    const masked = maskIOCLookupForTier(FULL_RESULT, tier);
    assert.equal(masked.locked, false, `tier=${tier}`);
    assert.equal(masked.reports.length, 1, `tier=${tier}`);
    assert.equal(masked.detection_artifacts.length, 1, `tier=${tier}`);
    assert.deepEqual(masked.actor_tags, ["APT29"], `tier=${tier}`);
  }
});
