import assert from "node:assert/strict";
import { test } from "node:test";
import { RelationshipEdgeRepositoryInterface } from "../edge-repository-interface.js";
import { InMemoryRelationshipEdgeRepository } from "../in-memory-edge-repository.js";

test("bare RelationshipEdgeRepositoryInterface throws NOT_IMPLEMENTED for every method", async () => {
  const iface = new RelationshipEdgeRepositoryInterface();
  await assert.rejects(() => iface.put({}));
  await assert.rejects(() => iface.putMany([]));
  await assert.rejects(() => iface.getForEntity("x"));
  await assert.rejects(() => iface.getByRelation("x"));
  await assert.rejects(() => iface.getAll());
  await assert.rejects(() => iface.count());
  await assert.rejects(() => iface.clear());
});

test("InMemoryRelationshipEdgeRepository.put stores and getForEntity finds by source or target", async () => {
  const repo = new InMemoryRelationshipEdgeRepository();
  await repo.put({ source: "advisory:A", target: "actor:fin7", relation: "ATTRIBUTED_TO", confidence: 0.9 });
  const bySource = await repo.getForEntity("advisory:A");
  const byTarget = await repo.getForEntity("actor:fin7");
  assert.equal(bySource.length, 1);
  assert.equal(byTarget.length, 1);
  assert.equal(bySource[0].relation, "ATTRIBUTED_TO");
});

test("put() on an identical (source, relation, target) key overwrites, does not duplicate", async () => {
  const repo = new InMemoryRelationshipEdgeRepository();
  await repo.put({ source: "a", target: "b", relation: "REFERENCES", confidence: 0.5 });
  await repo.put({ source: "a", target: "b", relation: "REFERENCES", confidence: 0.99 });
  assert.equal(await repo.count(), 1);
  const edges = await repo.getForEntity("a");
  assert.equal(edges[0].confidence, 0.99);
});

test("putMany reports stored/skipped/errors and skips malformed edges without throwing", async () => {
  const repo = new InMemoryRelationshipEdgeRepository();
  const result = await repo.putMany([
    { source: "a", target: "b", relation: "REFERENCES", confidence: 0.9 },
    { source: "a" }, // malformed -- missing target/relation
    { source: "c", target: "d", relation: "MENTIONS", confidence: 0.5 },
  ]);
  assert.equal(result.stored, 2);
  assert.equal(result.skipped, 1);
  assert.equal(result.errors.length, 1);
  assert.equal(await repo.count(), 2);
});

test("getByRelation filters correctly", async () => {
  const repo = new InMemoryRelationshipEdgeRepository();
  await repo.putMany([
    { source: "a", target: "b", relation: "REFERENCES", confidence: 0.9 },
    { source: "c", target: "d", relation: "MENTIONS", confidence: 0.5 },
  ]);
  const refs = await repo.getByRelation("REFERENCES");
  assert.equal(refs.length, 1);
  assert.equal(refs[0].source, "a");
});

test("getForEntity for an unknown entity returns [] not undefined/throw", async () => {
  const repo = new InMemoryRelationshipEdgeRepository();
  const result = await repo.getForEntity("does-not-exist");
  assert.deepEqual(result, []);
});

test("getAll returns every edge; clear() empties everything including indexes", async () => {
  const repo = new InMemoryRelationshipEdgeRepository();
  await repo.putMany([
    { source: "a", target: "b", relation: "REFERENCES", confidence: 0.9 },
    { source: "c", target: "d", relation: "MENTIONS", confidence: 0.5 },
  ]);
  assert.equal((await repo.getAll()).length, 2);
  await repo.clear();
  assert.equal(await repo.count(), 0);
  assert.deepEqual(await repo.getForEntity("a"), []);
  assert.deepEqual(await repo.getByRelation("REFERENCES"), []);
});

test("put() rejects an edge missing required fields", async () => {
  const repo = new InMemoryRelationshipEdgeRepository();
  await assert.rejects(() => repo.put({ source: "a" }));
});
