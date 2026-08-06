import assert from "node:assert/strict";
import { test } from "node:test";
import { createIntelligencePlatform } from "../platform.js";
import { IntelligenceService } from "../intelligence-service.js";

test("createIntelligencePlatform returns a disabled, null platform for production (default environment)", () => {
  const result = createIntelligencePlatform();
  assert.equal(result.enabled, false);
  assert.equal(result.platform, null);
  assert.equal(result.environment, "production");
  assert.match(result.reason, /EIPS_ENABLED is false/);
});

test("createIntelligencePlatform returns a disabled, null platform for canary", () => {
  const result = createIntelligencePlatform({ environment: "canary" });
  assert.equal(result.enabled, false);
  assert.equal(result.platform, null);
});

test("createIntelligencePlatform returns a fully-wired platform for development", () => {
  const result = createIntelligencePlatform({ environment: "development" });
  assert.equal(result.enabled, true);
  assert.ok(result.platform instanceof IntelligenceService);
});

test("createIntelligencePlatform returns a fully-wired platform for testing", () => {
  const result = createIntelligencePlatform({ environment: "testing" });
  assert.equal(result.enabled, true);
  assert.ok(result.platform instanceof IntelligenceService);
});

test("createIntelligencePlatform falls back to production (disabled) for an unrecognized environment string -- secure by default", () => {
  const result = createIntelligencePlatform({ environment: "not-a-real-environment" });
  assert.equal(result.enabled, false);
});

test("createIntelligencePlatform forwards custom deps through to IntelligenceService when enabled", async () => {
  const { EvidenceService } = await import("../../evidence-registry/evidence-service.js");
  const customEvidenceService = new EvidenceService();
  const result = createIntelligencePlatform({ environment: "development", deps: { evidenceService: customEvidenceService } });
  assert.equal(result.platform.evidenceService, customEvidenceService);
});
