import assert from "node:assert/strict";
import { test } from "node:test";
import { RelationshipLookupService } from "../relationship-lookup.js";
import { RelationshipRegistry } from "../relationship-registry.js";
import { RelationshipResolutionService } from "../../evidence-registry/relationship-resolution.js";
import { P31RelationshipProvider } from "../relationship-provider.js";
import { InMemoryRelationshipEdgeRepository } from "../in-memory-edge-repository.js";

test("constructor requires resolution and registry dependencies", () => {
  assert.throws(() => new RelationshipLookupService({}), /requires `resolution` and `registry`/);
});

test("isWired() reflects the underlying RelationshipResolutionService's own state", () => {
  const unwired = new RelationshipLookupService({ resolution: new RelationshipResolutionService(), registry: new RelationshipRegistry() });
  assert.equal(unwired.isWired(), false);

  const provider = new P31RelationshipProvider({ repository: new InMemoryRelationshipEdgeRepository() });
  const wired = new RelationshipLookupService({
    resolution: new RelationshipResolutionService({ provider }),
    registry: new RelationshipRegistry(),
  });
  assert.equal(wired.isWired(), true);
});

test("lookup() delegates to resolution unchanged, then enriches with registry category/description", async () => {
  const repository = new InMemoryRelationshipEdgeRepository();
  const provider = new P31RelationshipProvider({ repository });
  await provider.ingestEdges([{ source: "advisory:X", target: "actor:fin7", relation: "attributed_to", confidence: 0.85 }]);

  const lookupService = new RelationshipLookupService({
    resolution: new RelationshipResolutionService({ provider }),
    registry: new RelationshipRegistry(),
  });

  const result = await lookupService.lookup("advisory:X");
  assert.equal(result.length, 1);
  assert.equal(result[0].relatedEntityId, "actor:fin7");
  assert.equal(result[0].relationshipType, "ATTRIBUTED_TO"); // normalized from lowercase alias
  assert.equal(result[0].category, "threat");
  assert.equal(result[0].confidence, 0.85);
});

test("lookup() on an unwired resolution service still throws the same NOT_WIRED error, not silently returns []", async () => {
  const lookupService = new RelationshipLookupService({ resolution: new RelationshipResolutionService(), registry: new RelationshipRegistry() });
  await assert.rejects(() => lookupService.lookup("x"), /no RelationshipProviderInterface has been supplied/);
});

test("lookup() passes through an unrecognized relationshipType unchanged rather than dropping it", async () => {
  const repository = new InMemoryRelationshipEdgeRepository();
  await repository.put({ source: "a", target: "b", relation: "SOME_FUTURE_TYPE_NOT_YET_REGISTERED", confidence: 0.5 });
  const provider = new P31RelationshipProvider({ repository });
  const lookupService = new RelationshipLookupService({
    resolution: new RelationshipResolutionService({ provider }),
    registry: new RelationshipRegistry(),
  });
  const result = await lookupService.lookup("a");
  assert.equal(result[0].relationshipType, "SOME_FUTURE_TYPE_NOT_YET_REGISTERED");
  assert.equal(result[0].category, undefined);
});
