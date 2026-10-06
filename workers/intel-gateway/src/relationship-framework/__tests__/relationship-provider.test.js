import assert from "node:assert/strict";
import { test } from "node:test";
import { P31RelationshipProvider } from "../relationship-provider.js";
import { InMemoryRelationshipEdgeRepository } from "../in-memory-edge-repository.js";
import { RelationshipProviderInterface } from "../../evidence-registry/relationship-resolution.js";

test("P31RelationshipProvider IS-A RelationshipProviderInterface (Stage 12 contract)", () => {
  const provider = new P31RelationshipProvider({ repository: new InMemoryRelationshipEdgeRepository() });
  assert.ok(provider instanceof RelationshipProviderInterface);
});

test("constructor requires a repository dependency", () => {
  assert.throws(() => new P31RelationshipProvider({}), /requires a `repository`/);
});

test("ingestEdges then getRelationshipsFor returns real data in the Stage 12 contract shape", async () => {
  const provider = new P31RelationshipProvider({ repository: new InMemoryRelationshipEdgeRepository() });
  await provider.ingestEdges([
    { source: "advisory:CVE-2026-0001", target: "actor:fin7", relation: "attributed_to", confidence: 0.85 },
    { source: "advisory:CVE-2026-0001", target: "technique:T1566", relation: "uses_technique", confidence: 0.9 },
  ]);
  const relationships = await provider.getRelationshipsFor("advisory:CVE-2026-0001");
  assert.equal(relationships.length, 2);
  for (const rel of relationships) {
    assert.ok("relatedEntityId" in rel);
    assert.ok("relationshipType" in rel);
    assert.ok("confidence" in rel);
  }
  const targets = relationships.map((r) => r.relatedEntityId).sort();
  assert.deepEqual(targets, ["actor:fin7", "technique:T1566"]);
});

test("getRelationshipsFor for an entity with no edges returns [], not throw", async () => {
  const provider = new P31RelationshipProvider({ repository: new InMemoryRelationshipEdgeRepository() });
  const result = await provider.getRelationshipsFor("nothing-ingested");
  assert.deepEqual(result, []);
});

test("ingestEdges surfaces malformed-edge skips from the underlying repository", async () => {
  const provider = new P31RelationshipProvider({ repository: new InMemoryRelationshipEdgeRepository() });
  const result = await provider.ingestEdges([{ source: "a", target: "b", relation: "REFERENCES", confidence: 0.9 }, { bad: true }]);
  assert.equal(result.stored, 1);
  assert.equal(result.skipped, 1);
});
