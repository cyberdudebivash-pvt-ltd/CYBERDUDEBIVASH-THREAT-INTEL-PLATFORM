import assert from "node:assert/strict";
import { test } from "node:test";
import {
  COMMERCIAL_SERVICE_CATALOG,
  CATALOG_VISIBILITY,
  CATALOG_LIFECYCLE,
  CATALOG_SECURITY_CLASSIFICATION,
  getCatalogEntry,
  listNewAdapterEntries,
  listExistingCapabilityEntries,
  INTERNAL_ONLY_CAPABILITY_ANNOTATIONS,
} from "../catalog.js";

test("the catalog and every entry are frozen (documentation-as-data, mirroring service-contracts.js's convention)", () => {
  assert.ok(Object.isFrozen(COMMERCIAL_SERVICE_CATALOG));
  for (const entry of COMMERCIAL_SERVICE_CATALOG) {
    assert.ok(Object.isFrozen(entry), `${entry.id} is not frozen`);
  }
});

test("catalog entry ids are unique -- no duplicate catalog entries (Single Source of Truth)", () => {
  const ids = COMMERCIAL_SERVICE_CATALOG.map((entry) => entry.id);
  assert.equal(new Set(ids).size, ids.length);
});

test("every catalog entry has a complete, correctly-typed required field set", () => {
  for (const entry of COMMERCIAL_SERVICE_CATALOG) {
    assert.equal(typeof entry.id, "string", `${entry.id}: id`);
    assert.equal(typeof entry.name, "string", `${entry.id}: name`);
    assert.equal(typeof entry.description, "string", `${entry.id}: description`);
    assert.equal(typeof entry.newAdapter, "boolean", `${entry.id}: newAdapter`);
    assert.equal(typeof entry.sourceLayer, "string", `${entry.id}: sourceLayer`);
    assert.equal(typeof entry.owner, "string", `${entry.id}: owner`);
    assert.ok(Array.isArray(entry.classification) && entry.classification.length > 0, `${entry.id}: classification`);
    assert.ok(CATALOG_VISIBILITY.includes(entry.visibility), `${entry.id}: visibility "${entry.visibility}" not in ${CATALOG_VISIBILITY}`);
    assert.ok(
      CATALOG_SECURITY_CLASSIFICATION.includes(entry.securityClassification),
      `${entry.id}: securityClassification "${entry.securityClassification}" not in ${CATALOG_SECURITY_CLASSIFICATION}`
    );
    assert.ok(CATALOG_LIFECYCLE.includes(entry.lifecycle), `${entry.id}: lifecycle "${entry.lifecycle}" not in ${CATALOG_LIFECYCLE}`);
    assert.equal(typeof entry.commercialValue, "string", `${entry.id}: commercialValue`);
    assert.ok(Array.isArray(entry.internalConsumers), `${entry.id}: internalConsumers`);
    assert.ok(Number.isFinite(entry.expectedLatencyMs) && entry.expectedLatencyMs > 0, `${entry.id}: expectedLatencyMs`);
    assert.equal(typeof entry.documentationStatus, "string", `${entry.id}: documentationStatus`);
    assert.ok(Array.isArray(entry.dependencies) && entry.dependencies.length > 0, `${entry.id}: dependencies`);
  }
});

test("newAdapter entries have gatewayCapability: null; non-newAdapter entries have a non-empty gatewayCapability string", () => {
  for (const entry of COMMERCIAL_SERVICE_CATALOG) {
    if (entry.newAdapter) {
      assert.equal(entry.gatewayCapability, null, `${entry.id}: newAdapter entries must not name an existing gatewayCapability`);
    } else {
      assert.equal(typeof entry.gatewayCapability, "string", `${entry.id}: non-newAdapter entries must name a gatewayCapability`);
      assert.ok(entry.gatewayCapability.length > 0, `${entry.id}`);
    }
  }
});

test("getCatalogEntry() finds a known entry and returns undefined for an unknown id", () => {
  assert.equal(getCatalogEntry("commercial.knowledgeObject").name, "Knowledge Object Summary");
  assert.equal(getCatalogEntry("does.not.exist"), undefined);
});

test("listNewAdapterEntries() and listExistingCapabilityEntries() partition the catalog without overlap or omission", () => {
  const newEntries = listNewAdapterEntries();
  const existingEntries = listExistingCapabilityEntries();
  for (const entry of newEntries) assert.equal(entry.newAdapter, true);
  for (const entry of existingEntries) assert.equal(entry.newAdapter, false);
  assert.equal(newEntries.length + existingEntries.length, COMMERCIAL_SERVICE_CATALOG.length);
});

test("INTERNAL_ONLY_CAPABILITY_ANNOTATIONS names exactly the 3 pre-existing capabilities that are neither a catalog entry nor superseded by a narrower Stage 21 adapter", () => {
  const names = INTERNAL_ONLY_CAPABILITY_ANNOTATIONS.map((a) => a.gatewayCapability).sort();
  assert.deepEqual(names, ["evidence.provenance", "intelligence.query", "platform.metrics"]);
  for (const annotation of INTERNAL_ONLY_CAPABILITY_ANNOTATIONS) {
    assert.equal(annotation.visibility, "internal", `${annotation.gatewayCapability} must be internal`);
  }
});

test("all 9 pre-existing capabilities are covered exactly once by either a catalog entry or an internal-only annotation, never both", () => {
  const fromCatalog = listExistingCapabilityEntries().map((entry) => entry.gatewayCapability);
  const fromAnnotations = INTERNAL_ONLY_CAPABILITY_ANNOTATIONS.map((a) => a.gatewayCapability);
  const overlap = fromCatalog.filter((id) => fromAnnotations.includes(id));
  assert.deepEqual(overlap, [], "a capability must not be both a catalog entry and an internal-only annotation");
  const covered = [...fromCatalog, ...fromAnnotations].sort();
  const expected = [
    "evidence.lookup",
    "evidence.provenance",
    "evidence.relationships",
    "intelligence.correlation",
    "intelligence.explainability",
    "intelligence.query",
    "intelligence.threatProfile",
    "intelligence.validation",
    "platform.metrics",
  ];
  assert.deepEqual(covered, expected);
});

test("evidence.relationships is catalogued as blocked-pending-wiring, not ga -- it must not be marketed as ready", () => {
  const entry = getCatalogEntry("evidence.relationships");
  assert.equal(entry.lifecycle, "blocked-pending-wiring");
});

test("commercial.msspPartnerPackage is the only entry classified as partner-only visibility", () => {
  const partnerOnly = COMMERCIAL_SERVICE_CATALOG.filter((entry) => entry.visibility === "partner");
  assert.deepEqual(partnerOnly.map((entry) => entry.id), ["commercial.msspPartnerPackage"]);
});
