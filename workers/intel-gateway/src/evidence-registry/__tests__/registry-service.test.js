import assert from "node:assert/strict";
import { test } from "node:test";
import { createCanonicalEvidence, createEvidenceEntity } from "../entity.js";
import { IllegalLifecycleTransitionError } from "../lifecycle.js";
import {
  EvidenceRegistry,
  EvidenceValidationError,
  UnregisteredEvidenceError,
} from "../registry-service.js";

// registerEvidence()/updateEvidence()/bulkImport() run full validateCanonicalEvidence(), which
// (via Stage 8's validateEvidenceEntity) enforces evidence_uuid to be a real UUID v4 when
// present -- unlike the repository-level tests, which call InMemoryEvidenceRepository directly
// and never validate. Real UUID-v4-shaped constants here, not "u1"/"u2", for exactly that
// reason.
const U1 = "11111111-1111-4111-8111-111111111111";
const U2 = "22222222-2222-4222-8222-222222222222";
const U3 = "33333333-3333-4333-8333-333333333333";
const GHOST = "99999999-9999-4999-8999-999999999999"; // valid format, never registered

function evidence(uuid, extra = {}) {
  return createCanonicalEvidence(
    createEvidenceEntity({ evidence_id: `EC-${uuid}`, reliability_code: "B" }, { evidence_uuid: uuid }),
    extra
  );
}

test("registerEvidence: stores a valid record, sets DRAFT state, indexes it, increments evidence_count", async () => {
  const registry = new EvidenceRegistry();
  const { evidence: stored, reused } = await registry.registerEvidence(evidence(U1, { related_cves: ["CVE-2026-1"] }));

  assert.equal(reused, false);
  assert.equal(stored.evidence_uuid, U1);
  assert.ok(stored.content_hash, "registerEvidence must compute and attach a content_hash");
  assert.equal(registry.getLifecycleState(U1), "DRAFT");
  assert.deepEqual(await registry.findByCVE("CVE-2026-1"), [stored]);
  assert.equal(registry.getMetricsSnapshot().evidence_count, 1);

  const trail = registry.getAuditTrail(U1);
  assert.equal(trail.length, 1);
  assert.equal(trail[0].from, null);
  assert.equal(trail[0].to, "DRAFT");
});

test("registerEvidence: rejects structurally invalid evidence and records a validation-failure metric", async () => {
  const registry = new EvidenceRegistry();
  const invalid = { ...evidence(U1), visibility: "NOT_A_REAL_LEVEL" };
  await assert.rejects(() => registry.registerEvidence(invalid), EvidenceValidationError);
  assert.equal(registry.getMetricsSnapshot().validation_failures, 1);
});

test("registerEvidence: requires evidence_uuid", async () => {
  const registry = new EvidenceRegistry();
  const noUuid = createCanonicalEvidence(createEvidenceEntity({}));
  await assert.rejects(() => registry.registerEvidence(noUuid), /requires evidence\.evidence_uuid/);
});

test("registerEvidence: rejects an unknown initialState", async () => {
  const registry = new EvidenceRegistry();
  await assert.rejects(
    () => registry.registerEvidence(evidence(U1), { initialState: "NOT_A_STATE" }),
    /Unknown initial lifecycle state/
  );
});

test("registerEvidence: cross-report reuse (Phase 7)  -  identical substantive content returns the existing record, not a duplicate", async () => {
  const registry = new EvidenceRegistry();
  // Same evidence_id/reliability_code/related_cves on purpose (the "identical substantive
  // content" this test is about). Built directly rather than via evidence()  -  that helper
  // derives evidence_id from the uuid (EC-${uuid}), and createCanonicalEvidence's `extension`
  // argument never reads evidence_id (only createEvidenceEntity's `core` argument sets it), so
  // two different uuids built via evidence() are never substantively identical.
  const sharedCore = { evidence_id: "SHARED-EC", reliability_code: "B" };
  const first = createCanonicalEvidence(createEvidenceEntity(sharedCore, { evidence_uuid: U1 }), {
    related_cves: ["CVE-2026-1"],
  });
  const second = createCanonicalEvidence(createEvidenceEntity(sharedCore, { evidence_uuid: U2 }), {
    related_cves: ["CVE-2026-1"],
  }); // different uuid, same substance

  const r1 = await registry.registerEvidence(first);
  const r2 = await registry.registerEvidence(second);

  assert.equal(r1.reused, false);
  assert.equal(r2.reused, true);
  assert.deepEqual(r2.evidence, r1.evidence, "reuse must return the ORIGINAL record, not register a second one");
  assert.equal(registry.getMetricsSnapshot().evidence_count, 1, "a reused registration must not double-count");
  assert.equal(await registry.getEvidence(U2), null, "the second, unused uuid must never have been stored");
});

test("registerEvidence: skipReuseCheck bypasses dedup and registers a genuine duplicate", async () => {
  const registry = new EvidenceRegistry();
  await registry.registerEvidence(evidence(U1));
  const { reused } = await registry.registerEvidence(evidence(U2), { skipReuseCheck: true });
  assert.equal(reused, false);
  assert.equal(registry.getMetricsSnapshot().evidence_count, 2);
});

test("findEvidence: exact-match criteria lookup", async () => {
  const registry = new EvidenceRegistry();
  await registry.registerEvidence(evidence(U1, { evidence_type: "OSINT" }));
  await registry.registerEvidence(evidence(U2, { evidence_type: "TECHNICAL_ARTIFACT" }));
  const results = await registry.findEvidence({ evidence_type: "OSINT" });
  assert.equal(results.length, 1);
  assert.equal(results[0].evidence_uuid, U1);
});

test("named finders: findByThreatActor / findByCampaign / findByAttackTechnique / findByIOC / findBySource / findByConfidenceTier / findByReport", async () => {
  const registry = new EvidenceRegistry();
  const { evidence: stored } = await registry.registerEvidence(
    evidence(U1, {
      related_threat_actors: ["APT-X"],
      related_campaigns: ["CAMP-1"],
      related_attack_techniques: ["T1566"],
      related_iocs: ["1.2.3.4"],
      related_reports: ["SA-1"],
      source_id: "feed-alpha",
      canonical_confidence_object: { tier: "HIGH" },
    })
  );
  assert.deepEqual(await registry.findByThreatActor("APT-X"), [stored]);
  assert.deepEqual(await registry.findByCampaign("CAMP-1"), [stored]);
  assert.deepEqual(await registry.findByAttackTechnique("T1566"), [stored]);
  assert.deepEqual(await registry.findByIOC("1.2.3.4"), [stored]);
  assert.deepEqual(await registry.findByReport("SA-1"), [stored]);
  assert.deepEqual(await registry.findBySource("feed-alpha"), [stored]);
  assert.deepEqual(await registry.findByConfidenceTier("HIGH"), [stored]);
});

test("findByRelationship: unions across every related_* dimension for one entity id", async () => {
  const registry = new EvidenceRegistry();
  await registry.registerEvidence(evidence(U1, { related_cves: ["SHARED"] }));
  await registry.registerEvidence(evidence(U2, { related_campaigns: ["SHARED"] }));
  const results = await registry.findByRelationship("SHARED");
  assert.deepEqual(results.map((e) => e.evidence_uuid).sort(), [U1, U2].sort());
});

test("transitionLifecycle: advances state through the legal pipeline and records an audit trail + metrics", async () => {
  const registry = new EvidenceRegistry();
  await registry.registerEvidence(evidence(U1));
  await registry.transitionLifecycle(U1, "COLLECTED");
  await registry.transitionLifecycle(U1, "VALIDATED");
  assert.equal(registry.getLifecycleState(U1), "VALIDATED");
  assert.equal(registry.getAuditTrail(U1).length, 3); // registration + 2 transitions
  assert.equal(registry.getMetricsSnapshot().lifecycle_transitions, 2);
});

test("transitionLifecycle: illegal transition throws IllegalLifecycleTransitionError and does not change state", async () => {
  const registry = new EvidenceRegistry();
  await registry.registerEvidence(evidence(U1));
  await assert.rejects(() => registry.transitionLifecycle(U1, "PUBLISHED"), IllegalLifecycleTransitionError);
  assert.equal(registry.getLifecycleState(U1), "DRAFT", "state must be unchanged after a rejected transition");
});

test("transitionLifecycle / updateEvidence / supersedeEvidence / archiveEvidence on an unregistered uuid throw UnregisteredEvidenceError", async () => {
  const registry = new EvidenceRegistry();
  await assert.rejects(() => registry.transitionLifecycle(GHOST, "COLLECTED"), UnregisteredEvidenceError);
  await assert.rejects(() => registry.updateEvidence(GHOST, {}), UnregisteredEvidenceError);
  await assert.rejects(() => registry.supersedeEvidence(GHOST, {}), UnregisteredEvidenceError);
  await assert.rejects(() => registry.archiveEvidence(GHOST), UnregisteredEvidenceError);
});

async function publishedRegistry(uuid = U1, extra = {}) {
  const registry = new EvidenceRegistry();
  await registry.registerEvidence(evidence(uuid, extra));
  await registry.transitionLifecycle(uuid, "COLLECTED");
  await registry.transitionLifecycle(uuid, "VALIDATED");
  await registry.transitionLifecycle(uuid, "CORRELATED");
  await registry.transitionLifecycle(uuid, "PUBLISHED");
  return registry;
}

test("updateEvidence: from PUBLISHED bumps version, reindexes, moves state to UPDATED", async () => {
  const registry = await publishedRegistry(U1, { related_cves: ["CVE-2026-1"] });
  const updated = await registry.updateEvidence(U1, { related_cves: ["CVE-2026-2"] });

  assert.equal(updated.version, 2);
  assert.equal(registry.getLifecycleState(U1), "UPDATED");
  assert.deepEqual(await registry.findByCVE("CVE-2026-1"), [], "stale index entry must be gone");
  assert.deepEqual((await registry.findByCVE("CVE-2026-2"))[0].evidence_uuid, U1);
  assert.equal(registry.getMetricsSnapshot().version_updates, 1);
});

test("updateEvidence: from DRAFT is illegal (Updated is only reachable from Published/Updated)", async () => {
  const registry = new EvidenceRegistry();
  await registry.registerEvidence(evidence(U1));
  await assert.rejects(() => registry.updateEvidence(U1, {}), IllegalLifecycleTransitionError);
});

test("updateEvidence: rejects a patch that would make the record invalid, WITHOUT persisting it", async () => {
  const registry = await publishedRegistry(U1);
  await assert.rejects(
    () => registry.updateEvidence(U1, { visibility: "NOT_A_REAL_LEVEL" }),
    EvidenceValidationError
  );
  const stillCurrent = await registry.getEvidence(U1);
  assert.equal(stillCurrent.version, 1, "a rejected update must not bump the version or persist");
  assert.equal(registry.getLifecycleState(U1), "PUBLISHED", "a rejected update must not change lifecycle state");
});

test("supersedeEvidence: from PUBLISHED moves old version into frozen history with superseded_at, new version is current", async () => {
  const registry = await publishedRegistry(U1);
  const superseded = await registry.supersedeEvidence(U1, { evidence_category: "CORRECTED" });

  assert.equal(superseded.version, 2);
  assert.equal(registry.getLifecycleState(U1), "SUPERSEDED");
  const lineage = await registry.getVersionLineage(U1);
  assert.equal(lineage.length, 2);
  assert.ok(lineage[0].superseded_at);
  assert.ok(Object.isFrozen(lineage[0]));
});

test("archiveEvidence: legal from SUPERSEDED, keeps the record retrievable", async () => {
  const registry = await publishedRegistry(U1);
  await registry.supersedeEvidence(U1, {});
  const archived = await registry.archiveEvidence(U1);
  assert.equal(registry.getLifecycleState(U1), "ARCHIVED");
  assert.deepEqual(await registry.getEvidence(U1), archived);
});

test("archiveEvidence: illegal from DRAFT", async () => {
  const registry = new EvidenceRegistry();
  await registry.registerEvidence(evidence(U1));
  await assert.rejects(() => registry.archiveEvidence(U1), IllegalLifecycleTransitionError);
});

test("resolveVersion: with and without an explicit version number", async () => {
  const registry = await publishedRegistry(U1);
  await registry.updateEvidence(U1, {});
  assert.equal((await registry.resolveVersion(U1)).version, 2, "omitted version number resolves to current");
  assert.equal((await registry.resolveVersion(U1, 1)).version, 1);
  assert.equal(await registry.resolveVersion(U1, 99), null);
});

test("getHistoricalVersions / getSupersededVersions passthroughs", async () => {
  const registry = await publishedRegistry(U1);
  await registry.updateEvidence(U1, {});
  await registry.supersedeEvidence(U1, {});
  assert.equal((await registry.getHistoricalVersions(U1)).length, 2);
  assert.equal((await registry.getSupersededVersions(U1)).length, 1);
});

test("bulkImport: validates, imports genuinely new records, skips duplicates and invalid entries with reasons", async () => {
  const registry = new EvidenceRegistry();
  await registry.registerEvidence(evidence(U1), { skipReuseCheck: true });

  const result = await registry.bulkImport([
    evidence(U1, {}), // duplicate uuid -> skipped by repository
    evidence(U2, {}),
    { ...evidence(U3), visibility: "NOT_A_REAL_LEVEL" }, // invalid -> skipped by validation
  ]);

  assert.equal(result.imported, 1);
  assert.equal(result.skipped, 2);
  assert.equal(result.errors.length, 2);
  assert.equal(registry.getLifecycleState(U2), "DRAFT", "a genuinely-imported record must be tracked");
  assert.equal(registry.getLifecycleState(U3), undefined, "an invalid record must never be tracked");
  assert.equal(registry.getMetricsSnapshot().evidence_count, 2); // U1 (direct) + U2 (bulk)
});

test("bulkExport passthrough returns every current record", async () => {
  const registry = new EvidenceRegistry();
  await registry.registerEvidence(evidence(U1), { skipReuseCheck: true });
  await registry.registerEvidence(evidence(U2), { skipReuseCheck: true });
  assert.equal((await registry.bulkExport()).length, 2);
});

test("noteFeatureFlagActivation / noteMigrationEvent forward to the metrics collector", async () => {
  const registry = new EvidenceRegistry();
  registry.noteFeatureFlagActivation("EER_ENABLED");
  registry.noteMigrationEvent("p20-evidence-chain");
  const snap = registry.getMetricsSnapshot();
  assert.deepEqual(snap.feature_flag_activations, { EER_ENABLED: 1 });
  assert.deepEqual(snap.adapter_usage, { "p20-evidence-chain": 1 });
});

test("getLifecycleState / getAuditTrail on an unregistered uuid return undefined / empty array, not an error", async () => {
  const registry = new EvidenceRegistry();
  assert.equal(registry.getLifecycleState(GHOST), undefined);
  assert.deepEqual(registry.getAuditTrail(GHOST), []);
});
