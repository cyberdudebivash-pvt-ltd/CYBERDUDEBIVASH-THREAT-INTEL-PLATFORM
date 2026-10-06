/**
 * End-to-end integration test -- Stage 16 Phase 5 (Gateway Integration) + Phase 4 (Correlation)
 * proof. This is the test that demonstrates the actual acceptance criteria: P31-shaped edges,
 * ingested through Stage 16's RelationshipService, are reachable as REAL data through Stage 12's
 * RelationshipResolutionService, Stage 13's IntelligenceCorrelationService, and ALL THE WAY
 * through Stage 14's EnterpriseGateway -- with zero modification to any of those three stages'
 * own files (only relationship-resolution.js's docstring/message text and
 * correlation-engine.js's docstring and gateway-service.js's one description string changed;
 * see this stage's completion report for the full list). Composition happens exactly the way
 * every prior stage's own architecture already supported: dependency injection at a composition
 * root (here, createIntelligencePlatform()'s `deps` parameter), never a hardcoded default.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { RelationshipService } from "../relationship-service.js";
import { createIntelligencePlatform } from "../../intelligence-platform/platform.js";
import { EnterpriseGateway } from "../../enterprise-gateway/gateway-service.js";

const FIXTURE_EDGES = [
  // Matches R1's exact documented shape (p31-handlers.js's _buildGraph()/handleP31Relationships()).
  { source: "advisory:CVE-2026-9999", target: "actor:fin7", relation: "attributed_to", confidence: 0.85, evidence: "CVSS: 9.1", verified: true },
  { source: "advisory:CVE-2026-9999", target: "technique:T1566", relation: "uses_technique", confidence: 0.9, evidence: "MITRE mapping", verified: true },
];

function buildWiredGateway() {
  const relationshipService = new RelationshipService();
  const { platform } = createIntelligencePlatform({
    environment: "testing",
    deps: { relationshipResolution: relationshipService.resolution },
  });
  const gateway = new EnterpriseGateway({ platform });
  return { relationshipService, platform, gateway };
}

test("end-to-end: ingested P31-shaped edges are real data through Gateway.dispatch('evidence.relationships')", async () => {
  const { relationshipService, gateway } = buildWiredGateway();
  await relationshipService.ingestEdges(FIXTURE_EDGES);

  const result = await gateway.dispatch({
    capability: "evidence.relationships",
    method: "resolveRelationships",
    args: ["advisory:CVE-2026-9999"],
    caller: { id: "integration-test", kind: "test" },
    grantedCapabilities: ["evidence.relationships"],
  });

  assert.equal(result.length, 2);
  const relatedIds = result.map((r) => r.relatedEntityId).sort();
  assert.deepEqual(relatedIds, ["actor:fin7", "technique:T1566"]);
});

test("end-to-end: the SAME ingested data is reachable through Gateway.dispatch('intelligence.correlation'/'correlateByRelationship') -- Phase 4 proof", async () => {
  const { relationshipService, gateway } = buildWiredGateway();
  await relationshipService.ingestEdges(FIXTURE_EDGES);

  const result = await gateway.dispatch({
    capability: "intelligence.correlation",
    method: "correlateByRelationship",
    args: ["advisory:CVE-2026-9999"],
    caller: { id: "integration-test", kind: "test" },
    grantedCapabilities: ["intelligence.correlation"],
  });

  assert.equal(result.length, 2, "correlateByRelationship must return the same real data, via Stage 13's pass-through to Stage 12");
});

test("end-to-end: an entity with no ingested edges resolves to [] through the Gateway, not an error", async () => {
  const { gateway } = buildWiredGateway();
  const result = await gateway.dispatch({
    capability: "evidence.relationships",
    method: "resolveRelationships",
    args: ["nothing-was-ingested-for-this-id"],
    caller: { id: "integration-test", kind: "test" },
    grantedCapabilities: ["evidence.relationships"],
  });
  assert.deepEqual(result, []);
});

test("end-to-end: a platform composed WITHOUT injecting relationshipResolution still throws NOT_WIRED through the Gateway -- composition, not the Gateway, decides wiring", async () => {
  const { platform } = createIntelligencePlatform({ environment: "testing" }); // no deps.relationshipResolution
  const gateway = new EnterpriseGateway({ platform });
  await assert.rejects(
    () =>
      gateway.dispatch({
        capability: "evidence.relationships",
        method: "resolveRelationships",
        args: ["advisory:CVE-2026-9999"],
        caller: { id: "integration-test", kind: "test" },
        grantedCapabilities: ["evidence.relationships"],
      }),
    /no RelationshipProviderInterface has been supplied/
  );
});

test("end-to-end: dispatch without the required grantedCapabilities is denied (Gateway authorization is not bypassed by Stage 16's wiring)", async () => {
  const { relationshipService, gateway } = buildWiredGateway();
  await relationshipService.ingestEdges(FIXTURE_EDGES);
  await assert.rejects(
    () =>
      gateway.dispatch({
        capability: "evidence.relationships",
        method: "resolveRelationships",
        args: ["advisory:CVE-2026-9999"],
        caller: { id: "integration-test", kind: "test" },
        grantedCapabilities: [], // deliberately missing
      }),
    /denied/
  );
});

test("end-to-end: RelationshipService's own traversal/validation are usable standalone, independent of Gateway composition (no hidden coupling)", async () => {
  const relationshipService = new RelationshipService();
  await relationshipService.ingestEdges(FIXTURE_EDGES);
  const traversal = await relationshipService.traverse("advisory:CVE-2026-9999");
  assert.ok(traversal.visited.includes("actor:fin7"));
  assert.ok(traversal.visited.includes("technique:T1566"));
});
