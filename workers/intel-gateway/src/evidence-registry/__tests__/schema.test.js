import assert from "node:assert/strict";
import { test } from "node:test";
import { CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION, EVIDENCE_ENTITY_SCHEMA_VERSION } from "../entity.js";
import {
  FIELD_GROUPS,
  SCHEMA_VERSION_HISTORY,
  generateSchemaDocumentation,
  isBackwardCompatible,
  isForwardCompatible,
} from "../schema.js";

test("SCHEMA_VERSION_HISTORY records all three known versions in order (Stage 8, Stage 10, Stage 11 Phase 5)", () => {
  assert.equal(SCHEMA_VERSION_HISTORY.length, 3);
  assert.equal(SCHEMA_VERSION_HISTORY[0].version, EVIDENCE_ENTITY_SCHEMA_VERSION);
  assert.equal(SCHEMA_VERSION_HISTORY[1].version, "canonical-evidence-core.1.0.0-draft");
  assert.equal(SCHEMA_VERSION_HISTORY[2].version, CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION);
  assert.notEqual(
    SCHEMA_VERSION_HISTORY[1].version,
    CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION,
    "the current CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION must be the LATEST entry, not the Stage 10 original"
  );
});

test("isForwardCompatible: Stage 8 schema is forward compatible with Stage 10 (additive-only)", () => {
  assert.equal(
    isForwardCompatible(EVIDENCE_ENTITY_SCHEMA_VERSION, CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION),
    true
  );
});

test("isForwardCompatible: a version is compatible with itself", () => {
  assert.equal(isForwardCompatible(CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION, CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION), true);
});

test("isForwardCompatible: false for unknown versions or reversed direction", () => {
  assert.equal(isForwardCompatible("nonexistent-version", CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION), false);
  assert.equal(isForwardCompatible(CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION, EVIDENCE_ENTITY_SCHEMA_VERSION), false);
});

test("isBackwardCompatible: Stage 10 schema can be read by Stage-8-aware code", () => {
  assert.equal(
    isBackwardCompatible(CANONICAL_EVIDENCE_CORE_SCHEMA_VERSION, EVIDENCE_ENTITY_SCHEMA_VERSION),
    true
  );
});

test("FIELD_GROUPS sources directly from entity.js's exported field-name constants", () => {
  assert.ok(FIELD_GROUPS["Identity / Core (Stage 8)"].includes("evidence_id"));
  assert.ok(FIELD_GROUPS["Classification (Stage 10)"].includes("evidence_type"));
  assert.ok(FIELD_GROUPS["Relationships (Stage 10)"].includes("related_cves"));
});

test("generateSchemaDocumentation produces non-empty Markdown covering every field group", () => {
  const doc = generateSchemaDocumentation();
  assert.match(doc, /# Canonical Evidence Core/);
  assert.match(doc, /## Version history/);
  assert.match(doc, /## Field groups/);
  for (const groupName of Object.keys(FIELD_GROUPS)) {
    assert.ok(doc.includes(groupName), `documentation must mention field group "${groupName}"`);
  }
});
