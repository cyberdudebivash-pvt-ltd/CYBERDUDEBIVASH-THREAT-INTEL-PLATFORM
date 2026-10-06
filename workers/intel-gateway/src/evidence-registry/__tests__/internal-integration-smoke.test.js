/**
 * Internal integration smoke test  -  Stage 10 Phase 8 (Project TITAN).
 *
 * "Internal integration" here means demonstrating, at smoke-test level, that the Canonical
 * Evidence Core's own pieces compose correctly across the four named integration surfaces
 * (report pipeline, Relationship Framework, Confidence Framework, validation pipeline)  -  NOT
 * wiring any of them into a live call path. Nothing in this file imports index.js or any
 * pNN-handlers.js file; the second test below makes that an enforced property of every file in
 * this directory, not just an assumption.
 *
 * Phase 8's own scope note: "do not modify customer-visible reports." This file adds a test
 * only; it modifies nothing outside __tests__/ and asserts nothing about customer-visible
 * output  -  it only proves the CEC's own components interoperate.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { isPublished, publishEvidenceEntity } from "../entity.js";
import { CanonicalRelationshipAdapter, P25ConfidenceAdapter, ReportItemAdapter } from "../migration-adapters.js";
import { JsonEvidenceSerializer } from "../serialization.js";
import { validateCanonicalEvidence, validateEvidenceBatch } from "../validation.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const SCAFFOLD_DIR = dirname(HERE); // .../evidence-registry

// Realistic full P-layer report item  -  same field-access contract ReportItemAdapter documents
// (item.id, item.evidence_chain, item.cve_id, item.actor_tag, item.campaign_id,
// item.mitre_techniques) plus a __trustScore the caller has already computed via P25's
// computeEnterpriseTrustScore(item). This test does not call that function itself  -  it only
// demonstrates CEC can carry its output, per Single Source of Truth.
const REALISTIC_REPORT_ITEM = {
  id: "SA-2026-0201",
  evidence_chain: {
    evidence_id: "EC-2026-000512",
    reliability_code: "B",
    source_reliability: "B - Usually Reliable",
    source_category: "External Intelligence Feed",
    analyst_review: "Automated - Pending Human Review",
    chain_of_custody: ["Collected by feed ingestion", "Enriched by P20"],
    known_limitations: ["Single-source, not independently corroborated"],
    iq_breakdown: { source: 72, enrichment: 80, attribution: 45, corroboration: 15 },
  },
  cve_id: "CVE-2026-8888",
  actor_tag: "APT-EXAMPLE",
  campaign_id: "CAMPAIGN-Z",
  mitre_techniques: [{ id: "T1566" }, "T1059"],
  __trustScore: {
    dims: { cvss: 20, epss: 14, kev: 20, exploit: 12 },
    totalEarned: 66,
    totalMax: 100,
    pct: 66,
    tier: "MEDIUM",
    tierColor: "#f59e0b",
  },
};

function relationshipsCiting(evidenceUuid) {
  return [
    {
      evidence_references: [evidenceUuid],
      source_entity: { entity_type: "ThreatActor", entity_id: "APT-EXAMPLE-SECONDARY" },
      target_entity: { entity_type: "Campaign", entity_id: "CAMPAIGN-Z-FOLLOWUP" },
    },
  ];
}

test("Phase 8 integration smoke: report pipeline -> relationship framework -> confidence framework -> validation pipeline -> serialization -> publish, end to end", () => {
  // 1. Report pipeline surface: ReportItemAdapter composes the P20 + P25 adapters internally
  // and already attaches __trustScore via the Confidence Framework surface.
  const reportAdapter = new ReportItemAdapter();
  let evidence = reportAdapter.adapt(REALISTIC_REPORT_ITEM);
  evidence = { ...evidence, evidence_uuid: "22222222-2222-4222-8222-222222222222" };

  assert.equal(evidence.related_cves[0], "CVE-2026-8888");
  assert.equal(
    evidence.canonical_confidence_object.tier,
    "MEDIUM",
    "Confidence Framework surface must already be attached by the report pipeline adapter"
  );

  // 2. Relationship Framework surface: a second, independent pass through
  // CanonicalRelationshipAdapter must layer in relationships this evidence didn't already know
  // about at report-adapt time, without disturbing what step 1 already populated.
  const relationshipAdapter = new CanonicalRelationshipAdapter();
  evidence = relationshipAdapter.adapt({
    evidence,
    relationships: relationshipsCiting(evidence.evidence_uuid),
  });
  assert.ok(evidence.related_threat_actors.includes("APT-EXAMPLE-SECONDARY"));
  assert.ok(evidence.related_campaigns.includes("CAMPAIGN-Z-FOLLOWUP"));
  assert.ok(
    evidence.related_campaigns.includes("CAMPAIGN-Z"),
    "step 1's relationships must survive step 2's adapter, not be overwritten"
  );

  // 3. Confidence Framework surface, exercised a second time directly (independent of
  // ReportItemAdapter's internal use of it), confirming P25ConfidenceAdapter is independently
  // composable when re-applied.
  const confidenceAdapter = new P25ConfidenceAdapter();
  evidence = confidenceAdapter.adapt({ evidence, trustScore: REALISTIC_REPORT_ITEM.__trustScore });
  assert.equal(evidence.evidence_weight, 0.66);

  // 4. Validation pipeline surface.
  const singleResult = validateCanonicalEvidence(evidence);
  assert.equal(singleResult.valid, true, JSON.stringify(singleResult.errors));
  const batchResult = validateEvidenceBatch([evidence]);
  assert.equal(batchResult.valid, true, JSON.stringify(batchResult.errors));

  // 5. Serialization + publish, confirming the fully-integrated object still satisfies Phase
  // 1's "immutable once published" requirement after passing through every adapter.
  const serializer = new JsonEvidenceSerializer();
  const roundTripped = serializer.deserialize(serializer.serialize(evidence));
  assert.equal(validateCanonicalEvidence(roundTripped).valid, true);

  const published = publishEvidenceEntity(evidence);
  assert.equal(isPublished(published), true);
  assert.throws(() => {
    published.evidence_weight = 0.99;
  }, TypeError);
});

test("no file in evidence-registry/ imports a live pNN-handlers.js or index.js (adapters operate on documented shapes only)", () => {
  // Closes a gap zero-blast-radius.test.js doesn't cover: that test checks the OUTBOUND
  // direction (nothing outside this directory references it). This checks the INBOUND
  // direction  -  that files inside this directory never import a real handler/router file  - 
  // which is the specific design property migration-adapters.js's file-level docstring claims
  // ("a deliberate design choice... it means adopting these adapters never creates a real
  // module dependency edge"). A prose mention of a filename in a comment (e.g. "verified
  // against p25-handlers.js's return statement") is not a violation; only an actual
  // import/require of one is.
  const IMPORT_FROM_HANDLERS_OR_ROUTER = /(?:from|require\()\s*["'][^"']*(?:-handlers(?:\.js)?|\/index\.js)["']/;

  function listJsFiles(dir) {
    const out = [];
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      const stat = statSync(full);
      if (stat.isDirectory()) {
        if (name === "node_modules") continue;
        out.push(...listJsFiles(full));
      } else if (name.endsWith(".js")) {
        out.push(full);
      }
    }
    return out;
  }

  const violations = [];
  for (const file of listJsFiles(SCAFFOLD_DIR)) {
    const text = readFileSync(file, "utf-8");
    if (IMPORT_FROM_HANDLERS_OR_ROUTER.test(text)) {
      violations.push(file);
    }
  }
  assert.deepEqual(violations, [], `handler/router import found in: ${violations.join(", ")}`);
});
