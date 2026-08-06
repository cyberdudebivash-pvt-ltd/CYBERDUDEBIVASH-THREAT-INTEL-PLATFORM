import assert from "node:assert/strict";
import { test } from "node:test";
import { createCanonicalEvidence, createEvidenceEntity } from "../entity.js";
import {
  CanonicalRelationshipAdapter,
  P20EvidenceChainAdapter,
  P25ConfidenceAdapter,
  ReportItemAdapter,
} from "../migration-adapters.js";
import { validateCanonicalEvidence } from "../validation.js";

// Realistic fixture matching p20-handlers.js's live item.evidence_chain shape, per entity.js's
// own EvidenceChainCore docstring.
const REALISTIC_P20_EVIDENCE_CHAIN = {
  evidence_id: "EC-2026-000481",
  reliability_code: "B",
  source_reliability: "B - Usually Reliable",
  source_category: "External Intelligence Feed",
  analyst_review: "Automated - Pending Human Review",
  chain_of_custody: ["Collected by feed ingestion", "Enriched by P20"],
  known_limitations: ["Single-source, not independently corroborated"],
  iq_breakdown: { source: 70, enrichment: 85, attribution: 40, corroboration: 20 },
};

// Realistic fixture matching p25-handlers.js's computeEnterpriseTrustScore() return shape.
const REALISTIC_P25_TRUST_SCORE = {
  dims: { cvss: 18, epss: 12, kev: 20, exploit: 10 },
  totalEarned: 78,
  totalMax: 100,
  pct: 78,
  tier: "HIGH",
  tierColor: "#3b82f6",
};

test("P20EvidenceChainAdapter: adapts a realistic evidence_chain into a valid CanonicalEvidence", () => {
  const adapter = new P20EvidenceChainAdapter();
  const evidence = adapter.adapt(REALISTIC_P20_EVIDENCE_CHAIN);

  assert.equal(evidence.evidence_id, "EC-2026-000481");
  assert.equal(evidence.reliability_code, "B");
  assert.deepEqual(evidence.iq_breakdown, REALISTIC_P20_EVIDENCE_CHAIN.iq_breakdown);
  assert.equal(evidence.audit_metadata.producer_implementation, "p20-evidence-chain");

  const result = validateCanonicalEvidence(evidence);
  assert.equal(result.valid, true, JSON.stringify(result.errors));
});

test("P20EvidenceChainAdapter: handles an empty/missing evidence_chain gracefully", () => {
  const adapter = new P20EvidenceChainAdapter();
  const evidence = adapter.adapt(undefined);
  assert.equal(validateCanonicalEvidence(evidence).valid, true);
});

test("CanonicalRelationshipAdapter: populates related_* from relationships citing this evidence", () => {
  const base = createCanonicalEvidence(createEvidenceEntity({}, { evidence_uuid: "ev-rel-1" }));
  const relationships = [
    {
      evidence_references: ["ev-rel-1"],
      source_entity: { entity_type: "ThreatReport", entity_id: "SA-2026-0099" },
      target_entity: { entity_type: "CVE", entity_id: "CVE-2026-5555" },
    },
    {
      evidence_references: ["ev-rel-1"],
      source_entity: { entity_type: "ThreatActor", entity_id: "APT-EXAMPLE" },
      target_entity: { entity_type: "Campaign", entity_id: "CAMPAIGN-X" },
    },
    {
      evidence_references: ["some-other-evidence"], // does not cite this evidence -- excluded
      source_entity: { entity_type: "CVE", entity_id: "CVE-2026-9999" },
    },
  ];

  const adapter = new CanonicalRelationshipAdapter();
  const evidence = adapter.adapt({ evidence: base, relationships });

  assert.deepEqual(evidence.related_reports, ["SA-2026-0099"]);
  assert.deepEqual(evidence.related_cves, ["CVE-2026-5555"]);
  assert.deepEqual(evidence.related_threat_actors, ["APT-EXAMPLE"]);
  assert.deepEqual(evidence.related_campaigns, ["CAMPAIGN-X"]);
  assert.equal(evidence.related_cves.includes("CVE-2026-9999"), false, "unrelated relationship must not leak in");
});

test("CanonicalRelationshipAdapter: throws without evidence", () => {
  const adapter = new CanonicalRelationshipAdapter();
  assert.throws(() => adapter.adapt({ relationships: [] }), /requires \{ evidence, relationships \}/);
});

test("P25ConfidenceAdapter: attaches trust score verbatim and derives evidence_weight from pct", () => {
  const base = createCanonicalEvidence(createEvidenceEntity({}));
  const adapter = new P25ConfidenceAdapter();
  const evidence = adapter.adapt({ evidence: base, trustScore: REALISTIC_P25_TRUST_SCORE });

  assert.deepEqual(evidence.canonical_confidence_object, REALISTIC_P25_TRUST_SCORE, "must be carried verbatim, not recomputed");
  assert.equal(evidence.evidence_weight, 0.78);
});

test("P25ConfidenceAdapter: throws without both evidence and trustScore", () => {
  const adapter = new P25ConfidenceAdapter();
  assert.throws(() => adapter.adapt({ evidence: {} }), /requires \{ evidence, trustScore \}/);
});

test("ReportItemAdapter: extracts evidence-relevant fields from a full report item", () => {
  const item = {
    id: "SA-2026-0142",
    evidence_chain: REALISTIC_P20_EVIDENCE_CHAIN,
    cve_id: "CVE-2026-7777",
    actor_tag: "FIN-EXAMPLE",
    campaign_id: "CAMPAIGN-Y",
    mitre_techniques: [{ id: "T1566" }, "T1059"],
    __trustScore: REALISTIC_P25_TRUST_SCORE,
  };

  const adapter = new ReportItemAdapter();
  const evidence = adapter.adapt(item);

  assert.deepEqual(evidence.related_reports, ["SA-2026-0142"]);
  assert.deepEqual(evidence.related_cves, ["CVE-2026-7777"]);
  assert.deepEqual(evidence.related_threat_actors, ["FIN-EXAMPLE"]);
  assert.deepEqual(evidence.related_campaigns, ["CAMPAIGN-Y"]);
  assert.deepEqual(evidence.related_attack_techniques, ["T1566", "T1059"]);
  assert.deepEqual(evidence.canonical_confidence_object, REALISTIC_P25_TRUST_SCORE);
  assert.equal(evidence.audit_metadata.producer_implementation, "p-layer-report-item");

  const result = validateCanonicalEvidence(evidence);
  assert.equal(result.valid, true, JSON.stringify(result.errors));
});

test("ReportItemAdapter: degrades gracefully when optional fields are absent", () => {
  const adapter = new ReportItemAdapter();
  const evidence = adapter.adapt({ id: "SA-MINIMAL" });
  assert.deepEqual(evidence.related_reports, ["SA-MINIMAL"]);
  assert.deepEqual(evidence.related_cves, []);
  assert.equal(validateCanonicalEvidence(evidence).valid, true);
});

test("ReportItemAdapter: throws on non-object input", () => {
  const adapter = new ReportItemAdapter();
  assert.throws(() => adapter.adapt(null), /requires a report item object/);
});
