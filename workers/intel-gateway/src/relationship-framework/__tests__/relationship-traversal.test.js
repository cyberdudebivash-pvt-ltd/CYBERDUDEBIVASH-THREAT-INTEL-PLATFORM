import assert from "node:assert/strict";
import { test } from "node:test";
import { RelationshipTraversalService } from "../relationship-traversal.js";
import { InMemoryRelationshipEdgeRepository } from "../in-memory-edge-repository.js";
import { RelationshipMetricsService } from "../relationship-metrics.js";

async function chainRepo(length) {
  // A -> B -> C -> ... a simple linear chain, `length` edges long.
  const repo = new InMemoryRelationshipEdgeRepository();
  for (let i = 0; i < length; i += 1) {
    await repo.put({ source: `n${i}`, target: `n${i + 1}`, relation: "LINKED_TO", confidence: 0.9 });
  }
  return repo;
}

test("constructor requires a repository dependency", () => {
  assert.throws(() => new RelationshipTraversalService({}), /requires a `repository`/);
});

test("traverse respects maxDepth", async () => {
  const repository = await chainRepo(5);
  const traversal = new RelationshipTraversalService({ repository });
  const result = await traversal.traverse("n0", { maxDepth: 2 });
  // n0 -> n1 -> n2 reachable in 2 hops; n3/n4/n5 should not appear.
  assert.ok(result.visited.includes("n0"));
  assert.ok(result.visited.includes("n1"));
  assert.ok(result.visited.includes("n2"));
  assert.ok(!result.visited.includes("n4"));
  assert.equal(result.depthReached, 2);
});

test("traverse respects maxNodes and reports truncated: true", async () => {
  const repository = await chainRepo(20);
  const traversal = new RelationshipTraversalService({ repository });
  const result = await traversal.traverse("n0", { maxDepth: 20, maxNodes: 3 });
  assert.ok(result.visited.length <= 3);
  assert.equal(result.truncated, true);
});

test("traverse is cycle-safe: terminates on a graph with a cycle instead of looping forever", async () => {
  const repo = new InMemoryRelationshipEdgeRepository();
  await repo.putMany([
    { source: "a", target: "b", relation: "LINKED_TO", confidence: 0.9 },
    { source: "b", target: "c", relation: "LINKED_TO", confidence: 0.9 },
    { source: "c", target: "a", relation: "LINKED_TO", confidence: 0.9 }, // cycle back to a
  ]);
  const traversal = new RelationshipTraversalService({ repository: repo });
  const result = await traversal.traverse("a", { maxDepth: 10 });
  assert.deepEqual([...result.visited].sort(), ["a", "b", "c"]);
  assert.equal(result.truncated, false);
});

test("traverse filters by minConfidence", async () => {
  const repo = new InMemoryRelationshipEdgeRepository();
  await repo.putMany([
    { source: "a", target: "b", relation: "LINKED_TO", confidence: 0.9 },
    { source: "a", target: "c", relation: "LINKED_TO", confidence: 0.2 },
  ]);
  const traversal = new RelationshipTraversalService({ repository: repo });
  const result = await traversal.traverse("a", { maxDepth: 1, minConfidence: 0.5 });
  assert.ok(result.visited.includes("b"));
  assert.ok(!result.visited.includes("c"));
});

test("traverse from an entity with no edges returns just the start node", async () => {
  const repo = new InMemoryRelationshipEdgeRepository();
  const traversal = new RelationshipTraversalService({ repository: repo });
  const result = await traversal.traverse("isolated");
  assert.deepEqual(result.visited, ["isolated"]);
  assert.equal(result.edges.length, 0);
});

test("traverse records latency via injected metrics", async () => {
  const metrics = new RelationshipMetricsService();
  const repo = await chainRepo(2);
  const traversal = new RelationshipTraversalService({ repository: repo, metrics });
  await traversal.traverse("n0");
  assert.equal(metrics.snapshot().traversal_latency_stats.traverse.count, 1);
});

test("shortestPath finds the direct path", async () => {
  const repo = await chainRepo(3);
  const traversal = new RelationshipTraversalService({ repository: repo });
  const result = await traversal.shortestPath("n0", "n3");
  assert.deepEqual(result.path, ["n0", "n1", "n2", "n3"]);
  assert.equal(result.edges.length, 3);
});

test("shortestPath returns null when unreachable within maxDepth", async () => {
  const repo = await chainRepo(10);
  const traversal = new RelationshipTraversalService({ repository: repo });
  const result = await traversal.shortestPath("n0", "n10", { maxDepth: 2 });
  assert.equal(result, null);
});

test("shortestPath from an entity to itself is a trivial zero-edge path", async () => {
  const repo = await chainRepo(1);
  const traversal = new RelationshipTraversalService({ repository: repo });
  const result = await traversal.shortestPath("n0", "n0");
  assert.deepEqual(result, { path: ["n0"], edges: [] });
});
