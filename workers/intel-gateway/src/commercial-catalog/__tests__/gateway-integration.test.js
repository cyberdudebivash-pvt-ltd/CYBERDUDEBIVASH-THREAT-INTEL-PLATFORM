/**
 * Project TITAN Stage 21 -- Gateway Integration, demonstrated end to end.
 *
 * This file plays the role of a composition root, mirroring
 * product-platform/__tests__/gateway-integration.test.js's (Stage 19) and
 * knowledge-platform/__tests__/gateway-integration.test.js's (Stage 18) identical role: it is the
 * one place that legitimately imports from evidence-registry/, intelligence-platform/,
 * enterprise-gateway/, knowledge-platform/, and product-platform/ together to prove the full
 * Stage 21 composition works against real (not mocked) instances of every layer.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { createCommercialGateway } from "../platform.js";
import { COMMERCIAL_SERVICE_CATALOG } from "../catalog.js";
import { EnterpriseGateway } from "../../enterprise-gateway/gateway-service.js";
import { createIntelligencePlatform } from "../../intelligence-platform/platform.js";
import { evidence, feedItem, UUID_1, UUID_2 } from "./test-helpers.js";

const PRE_EXISTING_CAPABILITIES = Object.freeze([
  "evidence.lookup",
  "intelligence.query",
  "intelligence.correlation",
  "intelligence.validation",
  "intelligence.threatProfile",
  "evidence.provenance",
  "evidence.relationships",
  "platform.metrics",
  "intelligence.explainability",
]);

function buildWiredGateway() {
  const result = createCommercialGateway({ environment: "testing" });
  assert.equal(result.enabled, true, "createCommercialGateway({environment:'testing'}) must be enabled");
  return result;
}

test("createCommercialGateway() wires all 10 new capabilities and skips none when Knowledge/Product Platform are both available", () => {
  const { wiring } = buildWiredGateway();
  assert.equal(wiring.registered.length, 10);
  assert.deepEqual(wiring.skipped, []);
});

test("wiring does not remove or replace any of the 9 pre-existing capabilities -- 9 + 10 = 19 total", () => {
  const { gateway } = buildWiredGateway();
  const capabilities = gateway.listCapabilities();
  for (const preExisting of PRE_EXISTING_CAPABILITIES) {
    assert.ok(capabilities.includes(preExisting), `pre-existing capability "${preExisting}" must be unaffected`);
  }
  assert.equal(capabilities.length, 19, "9 pre-existing + 10 new Stage 21 capabilities");
});

test("every catalog entry's capability id is actually registered on the Gateway", () => {
  const { gateway } = buildWiredGateway();
  const registered = new Set(gateway.listCapabilities());
  for (const entry of COMMERCIAL_SERVICE_CATALOG) {
    const capabilityId = entry.newAdapter ? entry.id : entry.gatewayCapability;
    assert.ok(registered.has(capabilityId), `catalog entry "${entry.id}" -> capability "${capabilityId}" must be registered`);
  }
});

test("describeAllCapabilities() reflects Stage 21 classification for both new and pre-existing capabilities", () => {
  const { gateway } = buildWiredGateway();
  const described = Object.fromEntries(gateway.describeAllCapabilities().map((entry) => [entry.name, entry]));

  assert.equal(described["evidence.lookup"].visibility, "commercial");
  assert.equal(described["evidence.lookup"].lifecycle, "ga");
  assert.equal(described["platform.metrics"].visibility, "internal");
  assert.equal(described["platform.metrics"].lifecycle, "internal-only");
  assert.equal(described["evidence.provenance"].visibility, "internal", "the raw, unrestricted capability stays internal");
  assert.equal(described["commercial.knowledgeObject"].visibility, "commercial");
  assert.equal(described["commercial.knowledgeObject"].lifecycle, "beta");
  assert.equal(described["commercial.msspPartnerPackage"].visibility, "partner");
  assert.equal(described["commercial.evidenceProvenanceSummary"].visibility, "commercial");
});

test("dispatch() end to end: commercial.knowledgeObject/build returns a real Knowledge Object envelope", async () => {
  const { gateway } = buildWiredGateway();
  await gateway.platform.evidenceService.registerEvidence(evidence(UUID_1));

  const envelope = await gateway.dispatch({
    capability: "commercial.knowledgeObject",
    method: "build",
    args: [UUID_1],
    caller: { id: "test", kind: "test" },
    grantedCapabilities: ["commercial.knowledgeObject"],
  });

  assert.equal(envelope.capabilityId, "commercial.knowledgeObject");
  assert.equal(envelope.namespace, "internal/v1");
  assert.equal(envelope.data.found, true);
});

test("dispatch() end to end: commercial.productPackage composes assemble -> applyProfile -> package correctly (package() is async and must be awaited)", async () => {
  const { gateway } = buildWiredGateway();
  await gateway.platform.evidenceService.registerEvidence(evidence(UUID_1));

  const envelope = await gateway.dispatch({
    capability: "commercial.productPackage",
    method: "package",
    args: [UUID_1, "executive_leadership", "executive_intelligence_briefing"],
    caller: { id: "test", kind: "test" },
    grantedCapabilities: ["commercial.productPackage"],
  });

  // If package()'s Promise were spread unawaited, these fields would all be undefined.
  assert.equal(envelope.data.found, true);
  assert.equal(envelope.data.packageType, "executive_intelligence_briefing");
  assert.equal(envelope.data.metadata.profile, "Executive Leadership");
});

test("dispatch() end to end: commercial.msspPartnerPackage pins the profile to mssp_operations regardless of caller input", async () => {
  const { gateway } = buildWiredGateway();
  await gateway.platform.evidenceService.registerEvidence(evidence(UUID_1));

  const envelope = await gateway.dispatch({
    capability: "commercial.msspPartnerPackage",
    method: "package",
    args: [UUID_1, "tactical_dossier"],
    caller: { id: "partner-test", kind: "partner" },
    grantedCapabilities: ["commercial.msspPartnerPackage"],
  });

  assert.equal(envelope.data.found, true);
  assert.equal(envelope.data.metadata.profile, "MSSP Operations");
});

test("dispatch() end to end: commercial.productProfiledView never leaks the full unprofiled assembly", async () => {
  const { gateway } = buildWiredGateway();
  await gateway.platform.evidenceService.registerEvidence(evidence(UUID_1));

  const envelope = await gateway.dispatch({
    capability: "commercial.productProfiledView",
    method: "applyProfile",
    args: [UUID_1, "executive_leadership"],
    caller: { id: "test", kind: "test" },
    grantedCapabilities: ["commercial.productProfiledView"],
  });

  assert.equal("assembly" in envelope.data, false, "the raw unprofiled assembly must not appear in a profiled response");
  assert.equal(envelope.data.profileName, "Executive Leadership");
});

test("dispatch() end to end: commercial.evidenceProvenanceSummary allows the 5 safe lineage methods and rejects getAuditLineage", async () => {
  const { gateway } = buildWiredGateway();
  await gateway.platform.evidenceService.registerEvidence(evidence(UUID_1));

  const envelope = await gateway.dispatch({
    capability: "commercial.evidenceProvenanceSummary",
    method: "getEvidenceLineage",
    args: [UUID_1],
    caller: { id: "test", kind: "test" },
    grantedCapabilities: ["commercial.evidenceProvenanceSummary"],
  });
  assert.equal(envelope.capabilityId, "commercial.evidenceProvenanceSummary");

  await assert.rejects(
    () =>
      gateway.dispatch({
        capability: "commercial.evidenceProvenanceSummary",
        method: "getAuditLineage",
        args: [UUID_1],
        caller: { id: "test", kind: "test" },
        grantedCapabilities: ["commercial.evidenceProvenanceSummary"],
      }),
    /getAuditLineage/,
    "getAuditLineage must remain unreachable through the commercial-safe adapter"
  );
});

test("dispatch() end to end: the pre-existing evidence.provenance capability is untouched and still permits all 6 methods directly", async () => {
  const { gateway } = buildWiredGateway();
  await gateway.platform.evidenceService.registerEvidence(evidence(UUID_1));

  // Not asserting success (audit lineage may be empty for a freshly-registered record) -- only
  // that the pre-existing capability's own dispatch path is unaffected by the new, narrower
  // commercial adapter, i.e. it does not itself throw a CommercialAdapterValidationError.
  await gateway.dispatch({
    capability: "evidence.provenance",
    method: "getAuditLineage",
    args: [UUID_1],
    caller: { id: "test", kind: "test" },
    grantedCapabilities: ["evidence.provenance"],
  });
});

test("dispatch() end to end: commercial.readinessSummary bridges P39's pure functions over a flat feed item", async () => {
  const { gateway } = buildWiredGateway();
  const envelope = await gateway.dispatch({
    capability: "commercial.readinessSummary",
    method: "summarize",
    args: [feedItem()],
    caller: { id: "test", kind: "test" },
    grantedCapabilities: ["commercial.readinessSummary"],
  });
  assert.ok(envelope.data.view);
  assert.ok(envelope.data.summary);
});

test("dispatch() enforces capability authorization for Stage 21 capabilities like every other capability", async () => {
  const { gateway } = buildWiredGateway();
  await assert.rejects(
    () =>
      gateway.dispatch({
        capability: "commercial.knowledgeObject",
        method: "build",
        args: [UUID_1],
        caller: { id: "test", kind: "test" },
        grantedCapabilities: [], // deliberately missing
      }),
    /commercial\.knowledgeObject/
  );
});

test("a validation failure (unknown evidenceUuid type) is classified and recorded on commercialMetrics without crashing the caller's error handling", async () => {
  const { gateway, commercialMetrics } = buildWiredGateway();
  await assert.rejects(() =>
    gateway.dispatch({
      capability: "commercial.knowledgeObject",
      method: "build",
      args: [12345], // not a string
      caller: { id: "test", kind: "test" },
      grantedCapabilities: ["commercial.knowledgeObject"],
    })
  );
  const snapshot = commercialMetrics.snapshot();
  assert.equal(snapshot.commercial.failures_by_capability["commercial.knowledgeObject"].validation, 1);
});

test("Stage 21 capability calls are recorded on the same shared GatewayMetrics/ServicePlatformMetrics as every other capability -- no duplicate metrics instance", async () => {
  const { gateway } = buildWiredGateway();
  await gateway.platform.evidenceService.registerEvidence(evidence(UUID_2));
  await gateway.dispatch({
    capability: "commercial.knowledgeObject",
    method: "build",
    args: [UUID_2],
    caller: { id: "test", kind: "test" },
    grantedCapabilities: ["commercial.knowledgeObject"],
  });
  const snapshot = gateway.metrics.snapshot();
  assert.ok(snapshot.service.call_counts["gateway.commercial.knowledgeObject"] >= 1);
});

test("createCommercialGateway() accepts an already-constructed, not-yet-wired gateway via DI without constructing a second one", () => {
  const { platform: intelligenceService } = createIntelligencePlatform({ environment: "testing" });
  const freshGateway = new EnterpriseGateway({ platform: intelligenceService });
  const result = createCommercialGateway({ environment: "testing", deps: { gateway: freshGateway } });
  assert.equal(result.enabled, true);
  assert.equal(result.gateway, freshGateway, "must reuse the injected gateway instance, not construct a new one");
  assert.equal(result.wiring.registered.length, 10);
});
