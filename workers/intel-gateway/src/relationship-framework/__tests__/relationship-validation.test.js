import assert from "node:assert/strict";
import { test } from "node:test";
import { RelationshipValidationService } from "../relationship-validation.js";
import { RelationshipRegistry } from "../relationship-registry.js";
import { RelationshipMetricsService } from "../relationship-metrics.js";

function service(metrics) {
  return new RelationshipValidationService({ registry: new RelationshipRegistry(), metrics });
}

test("constructor requires a registry dependency", () => {
  assert.throws(() => new RelationshipValidationService({}), /requires a `registry`/);
});

test("validateEdge accepts a well-formed, correctly-typed edge", () => {
  const result = service().validateEdge(
    { source: "advisory:X", target: "actor:fin7", relation: "ATTRIBUTED_TO", confidence: 0.8 },
    { sourceEntityClass: "Advisory", targetEntityClass: "ThreatActor" }
  );
  assert.equal(result.valid, true);
  assert.deepEqual(result.errors, []);
});

test("validateEdge rejects missing required fields", () => {
  const result = service().validateEdge({ source: "a" });
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.startsWith("SCHEMA")));
});

test("validateEdge rejects a bare self-loop", () => {
  const result = service().validateEdge({ source: "a", target: "a", relation: "REFERENCES", confidence: 0.9 });
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.startsWith("SELF_LOOP")));
});

test("validateEdge rejects an unknown relationship type", () => {
  const result = service().validateEdge({ source: "a", target: "b", relation: "NOT_A_TYPE", confidence: 0.5 });
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.startsWith("UNKNOWN_TYPE")));
});

test("validateEdge rejects an invalid entity-class pairing when classes are supplied", () => {
  const result = service().validateEdge(
    { source: "a", target: "b", relation: "ATTRIBUTED_TO", confidence: 0.9 },
    { sourceEntityClass: "IOC", targetEntityClass: "ThreatActor" }
  );
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.startsWith("ENTITY_CLASS")));
});

test("validateEdge rejects missing confidence when the type requires it", () => {
  const result = service().validateEdge({ source: "a", target: "b", relation: "ATTRIBUTED_TO" });
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.startsWith("MISSING_CONFIDENCE")));
});

test("validateEdge accepts missing confidence when the type does not require it", () => {
  const result = service().validateEdge({ source: "a", target: "b", relation: "MENTIONS" });
  assert.equal(result.valid, true);
});

test("validateEdge rejects out-of-range confidence", () => {
  const result = service().validateEdge({ source: "a", target: "b", relation: "REFERENCES", confidence: 1.5 });
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.startsWith("CONFIDENCE_RANGE")));
});

test("validateEdge records a validation failure metric with a stable reason code", () => {
  const metrics = new RelationshipMetricsService();
  service(metrics).validateEdge({ source: "a", target: "a", relation: "REFERENCES", confidence: 0.9 });
  const snapshot = metrics.snapshot();
  assert.equal(snapshot.validation_failures, 1);
  assert.equal(snapshot.validation_failures_by_reason.SELF_LOOP, 1);
});

test("validateBatch reports per-edge results and a correct summary count", () => {
  const result = service().validateBatch([
    { source: "a", target: "b", relation: "REFERENCES", confidence: 0.9 },
    { source: "c", target: "c", relation: "REFERENCES", confidence: 0.9 }, // self-loop, invalid
  ]);
  assert.equal(result.valid, false);
  assert.equal(result.validCount, 1);
  assert.equal(result.invalidCount, 1);
  assert.equal(result.results.length, 2);
});

test("findOrphanEntities returns entities that appear in exactly one edge", () => {
  const edges = [
    { source: "a", target: "b", relation: "REFERENCES", confidence: 0.9 },
    { source: "a", target: "c", relation: "REFERENCES", confidence: 0.9 },
  ];
  // a: degree 2 (appears in both edges); b: degree 1; c: degree 1.
  const orphans = service().findOrphanEntities(edges).sort();
  assert.deepEqual(orphans, ["b", "c"]);
});

test("findCycles detects a simple 3-node cycle", () => {
  const edges = [
    { source: "a", target: "b", relation: "REFERENCES", confidence: 0.9 },
    { source: "b", target: "c", relation: "REFERENCES", confidence: 0.9 },
    { source: "c", target: "a", relation: "REFERENCES", confidence: 0.9 },
  ];
  const cycles = service().findCycles(edges);
  assert.equal(cycles.length, 1);
  assert.deepEqual(cycles[0], ["a", "b", "c", "a"]);
});

test("findCycles on an acyclic graph returns an empty array", () => {
  const edges = [
    { source: "a", target: "b", relation: "REFERENCES", confidence: 0.9 },
    { source: "b", target: "c", relation: "REFERENCES", confidence: 0.9 },
  ];
  assert.deepEqual(service().findCycles(edges), []);
});
