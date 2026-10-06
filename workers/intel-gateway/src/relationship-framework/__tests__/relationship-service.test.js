import assert from "node:assert/strict";
import { test } from "node:test";
import { RelationshipService } from "../relationship-service.js";

const FIXTURE_EDGES = [
  { source: "advisory:CVE-2026-0001", target: "actor:fin7", relation: "attributed_to", confidence: 0.85 },
  { source: "advisory:CVE-2026-0001", target: "technique:T1566", relation: "uses_technique", confidence: 0.9 },
  { source: "actor:fin7", target: "cve:CVE-2026-0001", relation: "exploits", confidence: 0.8 },
];

test("a zero-arg RelationshipService composes real, wired instances -- resolution.isWired() is true by default", () => {
  const service = new RelationshipService();
  assert.equal(service.resolution.isWired(), true, "the facade's whole purpose is to wire a real provider by default");
});

test("ingestEdges validates then persists only the valid subset, reporting both", async () => {
  const service = new RelationshipService();
  const { validation, ingest } = await service.ingestEdges([
    ...FIXTURE_EDGES,
    { source: "bad", target: "bad", relation: "REFERENCES", confidence: 0.9 }, // self-loop, invalid
  ]);
  assert.equal(validation.validCount, 3);
  assert.equal(validation.invalidCount, 1);
  assert.equal(ingest.stored, 3);
  assert.equal(await service.edgeCount(), 3);
});

test("lookupRelationships returns enriched, real data after ingestion", async () => {
  const service = new RelationshipService();
  await service.ingestEdges(FIXTURE_EDGES);
  const relationships = await service.lookupRelationships("advisory:CVE-2026-0001");
  assert.equal(relationships.length, 2);
  assert.ok(relationships.some((r) => r.relatedEntityId === "actor:fin7" && r.category === "threat"));
});

test("traverse and shortestPath operate over ingested data through the facade", async () => {
  const service = new RelationshipService();
  await service.ingestEdges(FIXTURE_EDGES);
  const traversal = await service.traverse("advisory:CVE-2026-0001", { maxDepth: 2 });
  assert.ok(traversal.visited.includes("actor:fin7"));

  const path = await service.shortestPath("advisory:CVE-2026-0001", "actor:fin7");
  assert.deepEqual(path.path, ["advisory:CVE-2026-0001", "actor:fin7"]);
});

test("getMetricsSnapshot reflects activity across traversal and validation", async () => {
  const service = new RelationshipService();
  await service.ingestEdges([...FIXTURE_EDGES, { source: "x", target: "x", relation: "REFERENCES", confidence: 0.9 }]);
  await service.traverse("advisory:CVE-2026-0001");
  const snapshot = service.getMetricsSnapshot();
  assert.ok(snapshot.traversal_latency_stats.traverse.count >= 1);
  assert.equal(snapshot.validation_failures, 1);
});

test("two independently-constructed RelationshipService instances do not share state (no hidden global)", async () => {
  const a = new RelationshipService();
  const b = new RelationshipService();
  await a.ingestEdges(FIXTURE_EDGES);
  assert.equal(await a.edgeCount(), 3);
  assert.equal(await b.edgeCount(), 0);
});

test("dependency injection: a caller can supply its own repository/registry/metrics", async () => {
  const { InMemoryRelationshipEdgeRepository } = await import("../in-memory-edge-repository.js");
  const { RelationshipRegistry } = await import("../relationship-registry.js");
  const { RelationshipMetricsService } = await import("../relationship-metrics.js");
  const repository = new InMemoryRelationshipEdgeRepository();
  const registry = new RelationshipRegistry();
  const metrics = new RelationshipMetricsService();
  const service = new RelationshipService({ repository, registry, metrics });
  assert.equal(service.registry, registry);
  assert.equal(service.metrics, metrics);
  await service.ingestEdges(FIXTURE_EDGES);
  assert.equal(await repository.count(), 3, "ingested edges should land in the injected repository instance");
});
