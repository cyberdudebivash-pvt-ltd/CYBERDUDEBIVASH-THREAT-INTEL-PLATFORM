import assert from "node:assert/strict";
import { test } from "node:test";
import { createCanonicalEvidence, createEvidenceEntity } from "../entity.js";
import { EvidenceRegistryIndexes } from "../indexes.js";

function evidence(uuid, extra = {}) {
  return createCanonicalEvidence(
    createEvidenceEntity({ evidence_id: extra.evidence_id }, { evidence_uuid: uuid }),
    extra
  );
}

test("index + byCve / byThreatActor / byCampaign / byAttackTechnique / byReport / byIoc", () => {
  const idx = new EvidenceRegistryIndexes();
  idx.index(
    evidence("u1", {
      related_cves: ["CVE-2026-1"],
      related_threat_actors: ["APT-X"],
      related_campaigns: ["CAMP-1"],
      related_attack_techniques: ["T1566"],
      related_reports: ["SA-1"],
      related_iocs: ["1.2.3.4"],
    })
  );
  assert.deepEqual(idx.byCve("CVE-2026-1"), ["u1"]);
  assert.deepEqual(idx.byThreatActor("APT-X"), ["u1"]);
  assert.deepEqual(idx.byCampaign("CAMP-1"), ["u1"]);
  assert.deepEqual(idx.byAttackTechnique("T1566"), ["u1"]);
  assert.deepEqual(idx.byReport("SA-1"), ["u1"]);
  assert.deepEqual(idx.byIoc("1.2.3.4"), ["u1"]);
});

test("byEvidenceId / bySource / byConfidenceTier", () => {
  const idx = new EvidenceRegistryIndexes();
  idx.index(
    evidence("u1", {
      evidence_id: "EC-1",
      source_id: "feed-alpha",
      canonical_confidence_object: { tier: "HIGH" },
    })
  );
  assert.deepEqual(idx.byEvidenceId("EC-1"), ["u1"]);
  assert.deepEqual(idx.bySource("feed-alpha"), ["u1"]);
  assert.deepEqual(idx.byConfidenceTier("HIGH"), ["u1"]);
});

test("multiple evidence records sharing the same CVE are both returned", () => {
  const idx = new EvidenceRegistryIndexes();
  idx.index(evidence("u1", { related_cves: ["CVE-2026-1"] }));
  idx.index(evidence("u2", { related_cves: ["CVE-2026-1"] }));
  idx.index(evidence("u3", { related_cves: ["CVE-2026-9999"] }));
  assert.deepEqual(idx.byCve("CVE-2026-1").sort(), ["u1", "u2"]);
});

test("byRelatedEntity unions across every related_* dimension for one entity id", () => {
  const idx = new EvidenceRegistryIndexes();
  idx.index(evidence("u1", { related_cves: ["SHARED-ID"] }));
  idx.index(evidence("u2", { related_threat_actors: ["SHARED-ID"] }));
  idx.index(evidence("u3", { related_cves: ["UNRELATED"] }));
  assert.deepEqual(idx.byRelatedEntity("SHARED-ID").sort(), ["u1", "u2"]);
});

test("remove() fully clears one record's index entries without affecting others", () => {
  const idx = new EvidenceRegistryIndexes();
  const e1 = evidence("u1", { related_cves: ["CVE-2026-1"] });
  const e2 = evidence("u2", { related_cves: ["CVE-2026-1"] });
  idx.index(e1);
  idx.index(e2);
  idx.remove(e1);
  assert.deepEqual(idx.byCve("CVE-2026-1"), ["u2"]);
});

test("reindex() drops stale associations from the previous version and applies the new ones", () => {
  const idx = new EvidenceRegistryIndexes();
  const v1 = evidence("u1", { related_cves: ["CVE-2026-1"] });
  idx.index(v1);
  const v2 = evidence("u1", { related_cves: ["CVE-2026-2"] }); // edit removed the old CVE reference
  idx.reindex(v1, v2);
  assert.deepEqual(idx.byCve("CVE-2026-1"), [], "stale association must not linger");
  assert.deepEqual(idx.byCve("CVE-2026-2"), ["u1"]);
});

test("querying an unknown key returns an empty array, not undefined or an error", () => {
  const idx = new EvidenceRegistryIndexes();
  assert.deepEqual(idx.byCve("does-not-exist"), []);
  assert.deepEqual(idx.byRelatedEntity("does-not-exist"), []);
});

test("index() on evidence with no evidence_uuid is a safe no-op", () => {
  const idx = new EvidenceRegistryIndexes();
  assert.doesNotThrow(() => idx.index({ related_cves: ["CVE-2026-1"] }));
  assert.deepEqual(idx.byCve("CVE-2026-1"), []);
});
