/**
 * Dedicated backward-compatibility test  -  Stage 10 Phase 9's explicit requirement, kept
 * separate from entity.test.js/validation.test.js's inline backward-compat assertions so
 * there is one file whose sole purpose is "did Stage 10 change anything about Stage 8's
 * already-shipped behavior," independently reviewable and independently runnable.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  EVIDENCE_ENTITY_CORE_FIELDS,
  EVIDENCE_ENTITY_INTEGRITY_FIELDS,
  EVIDENCE_ENTITY_SCHEMA_VERSION,
  createEvidenceEntity,
} from "../entity.js";
import { EVIDENCE_REGISTRY_FLAGS } from "../feature-flags.js";
import { EvidenceRepositoryInterface } from "../repository-interface.js";
import { validateEvidenceEntity } from "../validation.js";

test("EVIDENCE_ENTITY_SCHEMA_VERSION string is byte-identical to Stage 8's original value", () => {
  assert.equal(EVIDENCE_ENTITY_SCHEMA_VERSION, "evidence-registry.0.1-scaffolding");
});

test("EVIDENCE_ENTITY_CORE_FIELDS is exactly Stage 8's original 8 fields, same order", () => {
  assert.deepEqual(EVIDENCE_ENTITY_CORE_FIELDS, [
    "evidence_id",
    "reliability_code",
    "source_reliability",
    "source_category",
    "analyst_review",
    "chain_of_custody",
    "known_limitations",
    "iq_breakdown",
  ]);
});

test("EVIDENCE_ENTITY_INTEGRITY_FIELDS is exactly Stage 8's original 3 fields", () => {
  assert.deepEqual(EVIDENCE_ENTITY_INTEGRITY_FIELDS, ["evidence_uuid", "content_hash", "schema_version"]);
});

test("createEvidenceEntity's output shape is unchanged: exactly core + 3 integrity keys, nothing more", () => {
  const entity = createEvidenceEntity({ evidence_id: "X", reliability_code: "A" }, { evidence_uuid: "u" });
  const keys = Object.keys(entity).sort();
  assert.deepEqual(keys, ["evidence_id", "evidence_uuid", "reliability_code", "content_hash", "schema_version"].sort());
});

test("validateEvidenceEntity's permissiveness is unchanged: an empty object is still valid", () => {
  assert.equal(validateEvidenceEntity({}).valid, true);
});

test("EvidenceRepositoryInterface still throws NOT_IMPLEMENTED for every method (persistence still out of scope)", async () => {
  const repo = new EvidenceRepositoryInterface();
  await assert.rejects(() => repo.get("x"), /not an implementation/);
  await assert.rejects(() => repo.put({}), /not an implementation/);
  await assert.rejects(() => repo.findByContentHash("x"), /not an implementation/);
  await assert.rejects(() => repo.delete("x"), /not an implementation/);
});

test("EVIDENCE_REGISTRY_FLAGS.SCAFFOLDING_ENABLED is still hardcoded false (the one flag that actually gates production wiring)", () => {
  assert.equal(EVIDENCE_REGISTRY_FLAGS.SCAFFOLDING_ENABLED, false);
});
