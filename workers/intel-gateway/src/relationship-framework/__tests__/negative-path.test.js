/**
 * Cross-cutting negative-path tests -- Stage 16 Phase 8's own explicit requirement, beyond the
 * per-file negative cases already covered in each unit test file (unknown types, self-loops,
 * malformed edges, unwired providers, missing Gateway authorization, etc. -- see those files).
 * This file covers edge cases that span multiple components rather than one.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { RelationshipService } from "../relationship-service.js";
import { RelationshipTraversalService } from "../relationship-traversal.js";
import { InMemoryRelationshipEdgeRepository } from "../in-memory-edge-repository.js";
import { RelationshipRegistry, UnknownRelationshipTypeError } from "../relationship-registry.js";

test("ingestEdges with an empty array is a no-op, not an error", async () => {
  const service = new RelationshipService();
  const { validation, ingest } = await service.ingestEdges([]);
  assert.equal(validation.validCount, 0);
  assert.equal(ingest.stored, 0);
  assert.equal(await service.edgeCount(), 0);
});

test("ingestEdges where EVERY edge is invalid stores nothing and reports every failure", async () => {
  const service = new RelationshipService();
  const { validation, ingest } = await service.ingestEdges([
    { source: "a", target: "a", relation: "REFERENCES", confidence: 0.9 }, // self-loop
    { source: "b", target: "c", relation: "TOTALLY_UNKNOWN", confidence: 0.5 }, // unknown type
  ]);
  assert.equal(validation.validCount, 0);
  assert.equal(validation.invalidCount, 2);
  assert.equal(ingest.stored, 0);
  assert.equal(await service.edgeCount(), 0);
});

test("traverse() with maxDepth: 0 returns only the start node", async () => {
  const repo = new InMemoryRelationshipEdgeRepository();
  await repo.put({ source: "a", target: "b", relation: "REFERENCES", confidence: 0.9 });
  const traversal = new RelationshipTraversalService({ repository: repo });
  const result = await traversal.traverse("a", { maxDepth: 0 });
  assert.deepEqual(result.visited, ["a"]);
});

test("traverse() from an entity that has never been ingested does not throw", async () => {
  const service = new RelationshipService();
  const result = await service.traverse("never-seen-before");
  assert.deepEqual(result.visited, ["never-seen-before"]);
});

test("shortestPath() between two entities that are both unknown to the repository returns null, not throw", async () => {
  const service = new RelationshipService();
  const result = await service.shortestPath("ghost-a", "ghost-b");
  assert.equal(result, null);
});

test("registry.get() on an empty string does not silently match anything", () => {
  const registry = new RelationshipRegistry();
  assert.throws(() => registry.get(""), UnknownRelationshipTypeError);
  assert.equal(registry.normalizeTypeName(""), null);
});

test("registry.normalizeTypeName(null/undefined) returns null, not throw", () => {
  const registry = new RelationshipRegistry();
  assert.equal(registry.normalizeTypeName(null), null);
  assert.equal(registry.normalizeTypeName(undefined), null);
});

test("edge repository putMany with a null/undefined array behaves like empty, not throw", async () => {
  const repo = new InMemoryRelationshipEdgeRepository();
  const result = await repo.putMany(undefined);
  assert.deepEqual(result, { stored: 0, skipped: 0, errors: [] });
});

test("RelationshipService constructed twice in a row never leaks the registry's mutable seed state (register() duplicate-name guard survives fresh instances)", () => {
  const a = new RelationshipService();
  const b = new RelationshipService();
  // Both should have independently seeded, equally-complete registries -- not a shared Map that
  // would make the second construction see "already registered" errors for catalog entries.
  assert.equal(a.registry.list().length, b.registry.list().length);
  assert.notEqual(a.registry, b.registry);
});
