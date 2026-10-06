import assert from "node:assert/strict";
import { test } from "node:test";
import { ExecutiveViewService } from "../executive-views.js";
import { buildKnowledgePlatform, evidence, UUID_1, UUID_2 } from "./test-helpers.js";

const VALID_BASES = new Set(["evidence", "analyst_recommendation"]);

function assertEveryItemHasBasis(items) {
  for (const item of items) {
    assert.ok(VALID_BASES.has(item.basis), `item missing a valid basis: ${JSON.stringify(item)}`);
  }
}

test("ExecutiveViewService requires knowledgeObject and navigation dependencies", () => {
  assert.throws(() => new ExecutiveViewService({}), /requires knowledgeObject and navigation/);
});

test("executiveBriefing(): reports found:false for an unregistered evidence_uuid", async () => {
  const { platform } = buildKnowledgePlatform();
  const briefing = await platform.executiveViews.executiveBriefing("does-not-exist");
  assert.equal(briefing.found, false);
});

test("executiveBriefing(): returns all six Phase 5 fields", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-6001"] }));

  const briefing = await platform.executiveViews.executiveBriefing(UUID_1);
  assert.equal(briefing.found, true);
  assert.ok(briefing.businessImpact);
  assert.ok(briefing.operationalImpact);
  assert.ok(Array.isArray(briefing.strategicObservations));
  assert.ok(Array.isArray(briefing.keyEvidence));
  assert.ok(Array.isArray(briefing.recommendedActions));
  assert.ok(Array.isArray(briefing.intelligenceLimitations));
});

test("executiveBriefing(): businessImpact/operationalImpact are traced to evidence and explicitly state no score is computed", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_1));

  const briefing = await platform.executiveViews.executiveBriefing(UUID_1);
  assert.equal(briefing.businessImpact.basis, "evidence");
  assert.match(briefing.businessImpact.note, /does not compute a business-impact score/);
  assert.equal(briefing.operationalImpact.basis, "evidence");
  assert.match(briefing.operationalImpact.note, /does not compute an operational-impact score/);
});

test("executiveBriefing(): every strategicObservations/keyEvidence/recommendedActions/intelligenceLimitations item carries a valid basis", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_1, { related_cves: ["CVE-2026-6002"], related_threat_actors: ["APT-EXEC"] })
  );
  await intelligenceService.evidenceService.registerEvidence(evidence(UUID_2, { related_cves: ["CVE-2026-6002"] }));

  const briefing = await platform.executiveViews.executiveBriefing(UUID_1);
  assertEveryItemHasBasis(briefing.strategicObservations);
  assertEveryItemHasBasis(briefing.keyEvidence);
  assertEveryItemHasBasis(briefing.recommendedActions);
  assertEveryItemHasBasis(briefing.intelligenceLimitations);
});

test("executiveBriefing(): recommendedActions are labeled analyst_recommendation, never evidence", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_1, { related_threat_actors: ["APT-UNCORROBORATED"] })
  );

  const briefing = await platform.executiveViews.executiveBriefing(UUID_1);
  assert.ok(briefing.recommendedActions.length > 0);
  for (const action of briefing.recommendedActions) {
    assert.equal(action.basis, "analyst_recommendation");
  }
});

test("executiveBriefing(): intelligenceLimitations flags a missing confidence value and contradictory evidence when present", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_1, { related_cves: ["CVE-2026-6003"], verification_status: "VERIFIED" })
  );
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_2, { related_cves: ["CVE-2026-6003"], verification_status: "DISPUTED" })
  );

  const briefing = await platform.executiveViews.executiveBriefing(UUID_1);
  const statements = briefing.intelligenceLimitations.map((limitation) => limitation.statement).join(" ");
  assert.match(statements, /ADR-0007/);
  assert.match(statements, /contradictory record/);
});

test("executiveBriefing(): intelligenceLimitations reports no gap/confidence/contradiction limitation when nothing is missing", async () => {
  const { intelligenceService, platform } = buildKnowledgePlatform();
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_1, {
      related_cves: ["CVE-2026-6004"],
      canonical_confidence_object: { tier: "LOW" },
      verification_status: "VERIFIED",
    })
  );
  await intelligenceService.evidenceService.registerEvidence(
    evidence(UUID_2, { related_cves: ["CVE-2026-6004"], verification_status: "VERIFIED" })
  );

  const briefing = await platform.executiveViews.executiveBriefing(UUID_1);
  const statements = briefing.intelligenceLimitations.map((l) => l.statement).join(" ");
  assert.doesNotMatch(statements, /collection gap/);
  assert.doesNotMatch(statements, /ADR-0007/);
  assert.doesNotMatch(statements, /contradictory record/);
});
