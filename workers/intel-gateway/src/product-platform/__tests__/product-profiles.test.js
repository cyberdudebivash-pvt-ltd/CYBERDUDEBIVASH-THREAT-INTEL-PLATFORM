import assert from "node:assert/strict";
import { test } from "node:test";
import {
  PRODUCT_AUDIENCE_PROFILES,
  ProductProfileService,
  resolveProductProfile,
  listProductProfiles,
  applyProductProfile,
} from "../product-profiles.js";
import { buildProductPlatform, evidence, UUID_1, UUID_NOT_FOUND } from "./test-helpers.js";

const ALL_PROFILE_KEYS = [
  "soc_analyst",
  "threat_intelligence_analyst",
  "executive_leadership",
  "mssp_operations",
  "vulnerability_management",
  "incident_response",
];

test("PRODUCT_AUDIENCE_PROFILES defines exactly the six brief-named profiles", () => {
  assert.deepEqual(Object.keys(PRODUCT_AUDIENCE_PROFILES).sort(), [...ALL_PROFILE_KEYS].sort());
});

test("every profile's sections are a non-empty subset of {knowledgeObject, correlation, briefing}", () => {
  for (const key of ALL_PROFILE_KEYS) {
    const profile = PRODUCT_AUDIENCE_PROFILES[key];
    assert.ok(profile.sections.length > 0, `${key} must include at least one section`);
    for (const section of profile.sections) {
      assert.ok(["knowledgeObject", "correlation", "briefing"].includes(section), `${key} has unknown section "${section}"`);
    }
  }
});

test("resolveProductProfile(): throws on an unknown profile key", () => {
  assert.throws(() => resolveProductProfile("nonexistent_profile"), /Unknown product profile/);
});

test("resolveProductProfile(): does not resolve inherited Object.prototype members", () => {
  assert.throws(() => resolveProductProfile("constructor"), /Unknown product profile/);
  assert.throws(() => resolveProductProfile("toString"), /Unknown product profile/);
});

test("listProductProfiles(): returns all six profiles with key/name/description/sections", () => {
  const profiles = listProductProfiles();
  assert.equal(profiles.length, 6);
  for (const profile of profiles) {
    assert.ok(typeof profile.key === "string");
    assert.ok(typeof profile.name === "string");
    assert.ok(typeof profile.description === "string");
    assert.ok(Array.isArray(profile.sections));
  }
});

test("applyProductProfile(): not-found assembly propagates found=false without throwing", () => {
  const view = applyProductProfile({ evidenceUuid: UUID_NOT_FOUND, found: false, reason: "not_found" }, "soc_analyst");
  assert.equal(view.found, false);
  assert.equal(view.reason, "not_found");
  assert.equal(view.profileKey, "soc_analyst");
});

test("applyProductProfile(): includes exactly the profile's declared sections, values unchanged", async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-8100"] }));
  const assembly = await platform.engine.assemble(UUID_1);

  for (const key of ALL_PROFILE_KEYS) {
    const view = applyProductProfile(assembly, key);
    const profile = PRODUCT_AUDIENCE_PROFILES[key];
    const presentSections = Object.keys(view).filter((k) => ["knowledgeObject", "correlation", "briefing"].includes(k));
    assert.deepEqual(presentSections.sort(), [...profile.sections].sort(), `profile ${key}`);
    for (const section of profile.sections) {
      assert.deepEqual(view[section], assembly[section], `profile ${key} section ${section} must be unchanged`);
    }
  }
});

test("applyProductProfile(): never mutates the source assembly", async () => {
  const { intelligenceService, platform } = buildProductPlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));
  const assembly = await platform.engine.assemble(UUID_1);
  // structuredClone(), not JSON.parse(JSON.stringify()) -- the latter silently drops
  // undefined-valued keys (e.g. an unset evidence_type/evidence_category), which would make
  // `before` structurally different from `assembly` even with zero real mutation.
  const before = structuredClone(assembly);
  applyProductProfile(assembly, "mssp_operations");
  assert.deepEqual(assembly, before);
});

test("ProductProfileService class wrapper delegates verbatim to the pure functions", () => {
  const service = new ProductProfileService();
  assert.deepEqual(service.listProfiles(), listProductProfiles());
  assert.deepEqual(service.resolveProfile("soc_analyst"), resolveProductProfile("soc_analyst"));
});
