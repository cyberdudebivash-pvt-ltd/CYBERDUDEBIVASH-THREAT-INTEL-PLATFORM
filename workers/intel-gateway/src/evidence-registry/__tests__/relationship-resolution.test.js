import assert from "node:assert/strict";
import { test } from "node:test";
import {
  RelationshipResolutionService,
  RelationshipProviderInterface,
  NullRelationshipProvider,
} from "../relationship-resolution.js";
import { ServicePlatformMetrics } from "../service-metrics.js";

test("default (no provider injected) throws a clearly-labelled NOT_WIRED error, not a silent empty result", async () => {
  const service = new RelationshipResolutionService();
  assert.equal(service.isWired(), false);
  await assert.rejects(
    () => service.resolveRelationships("CVE-2026-0001"),
    /no RelationshipProviderInterface has been supplied/,
    "the error must clearly say no provider was injected into THIS instance, not just 'not implemented' " +
      "-- Stage 16: this is provider-agnostic-by-design DI, independent of ADR-0010's (now Accepted) status"
  );
});

test("NullRelationshipProvider.getRelationshipsFor throws the same NOT_WIRED error directly", async () => {
  const provider = new NullRelationshipProvider();
  await assert.rejects(() => provider.getRelationshipsFor("x"), /RelationshipProviderInterface/);
});

test("a concrete injected provider is used, and isWired() reflects that", async () => {
  class FixtureProvider extends RelationshipProviderInterface {
    async getRelationshipsFor(entityId) {
      return [{ relatedEntityId: `related-to-${entityId}`, relationshipType: "MENTIONS", confidence: 0.9 }];
    }
  }
  const service = new RelationshipResolutionService({ provider: new FixtureProvider() });
  assert.equal(service.isWired(), true);
  const result = await service.resolveRelationships("CVE-2026-0001");
  assert.equal(result.length, 1);
  assert.equal(result[0].relatedEntityId, "related-to-CVE-2026-0001");
});

test("resolveRelationships records success/failure metrics correctly for both wired and unwired cases", async () => {
  const metrics = new ServicePlatformMetrics();
  const unwired = new RelationshipResolutionService({ metrics });
  await assert.rejects(() => unwired.resolveRelationships("x"));
  assert.equal(metrics.snapshot().relationship_resolution_failures, 1);

  class OkProvider extends RelationshipProviderInterface {
    async getRelationshipsFor() {
      return [];
    }
  }
  const wired = new RelationshipResolutionService({ provider: new OkProvider(), metrics });
  await wired.resolveRelationships("x");
  const snapshot = metrics.snapshot();
  assert.equal(snapshot.relationship_resolutions, 2, "both the failed and the successful attempt count as resolutions");
  assert.equal(snapshot.relationship_resolution_failures, 1, "only the first attempt failed");
});

test("base RelationshipProviderInterface itself throws NOT_WIRED for an un-overridden subclass", async () => {
  const bareInterface = new RelationshipProviderInterface();
  await assert.rejects(() => bareInterface.getRelationshipsFor("x"));
});
