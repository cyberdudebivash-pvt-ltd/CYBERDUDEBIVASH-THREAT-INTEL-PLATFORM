import assert from "node:assert/strict";
import { test } from "node:test";
import {
  IntelligenceService,
  IntelligenceLookupService,
  IntelligenceValidationService,
  IntelligenceMetricsService,
  ThreatIntelligenceService,
} from "../intelligence-service.js";
import { EnterpriseQueryService } from "../query-service.js";
import { IntelligenceCorrelationService } from "../correlation-engine.js";
import { IntelligenceExplainabilityService } from "../explainability-engine.js";
import { EvidenceProvenanceEngine } from "../../evidence-registry/provenance-engine.js";
import { evidence, UUID_1, UUID_2 } from "./test-helpers.js";

test("IntelligenceService composes every Stage 13 service over one shared EvidenceService/registry", () => {
  const service = new IntelligenceService();
  assert.ok(service.lookup instanceof IntelligenceLookupService);
  assert.ok(service.correlation instanceof IntelligenceCorrelationService);
  assert.ok(service.validation instanceof IntelligenceValidationService);
  assert.ok(service.metrics instanceof IntelligenceMetricsService);
  assert.ok(service.threatIntelligence instanceof ThreatIntelligenceService);
  assert.ok(service.enterpriseQuery instanceof EnterpriseQueryService);
  assert.ok(service.provenance instanceof EvidenceProvenanceEngine, "Phase 4: reused directly, no Stage 13 wrapper class");
  assert.equal(service.lookup._evidenceLookup, service.evidenceService.lookup, "must share the same EvidenceService.lookup instance");
  assert.ok(service.explainability instanceof IntelligenceExplainabilityService, "Stage 17: composed last, over lookup/correlation/provenance above");
});

test("IntelligenceService accepts full dependency injection (matching EvidenceService's own deps pattern)", async () => {
  const inner = new (await import("../../evidence-registry/evidence-service.js")).EvidenceService();
  const service = new IntelligenceService({ evidenceService: inner });
  assert.equal(service.evidenceService, inner);
  await service.evidenceService.registerEvidence(evidence(UUID_1));
  const found = await service.lookup.getEvidence(UUID_1);
  assert.equal(found.evidence_uuid, UUID_1, "mutation through the injected EvidenceService must be visible via Stage 13's lookup");
});

test("IntelligenceService injected with an evidenceService but NO explicit serviceMetrics shares that evidenceService's own metrics instance, not a fresh one", async () => {
  const { EvidenceService } = await import("../../evidence-registry/evidence-service.js");
  const { ServicePlatformMetrics } = await import("../../evidence-registry/service-metrics.js");
  const ownMetrics = new ServicePlatformMetrics();
  const inner = new EvidenceService({ serviceMetrics: ownMetrics });

  const service = new IntelligenceService({ evidenceService: inner });
  assert.equal(
    service.metrics.sharedServiceMetrics,
    ownMetrics,
    "queryEngine/provenance/correlation must share the INJECTED evidenceService's own metrics, not a newly-created one"
  );

  await service.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2029-0001"] }));
  await service.enterpriseQuery.queryByCVE("CVE-2029-0001");
  assert.ok(
    ownMetrics.snapshot().query_counts.cve >= 1,
    "a query made through Stage 13's own components must be recorded on the injected EvidenceService's metrics instance, proving they are the same object"
  );
});

test("IntelligenceService rejects an explicit serviceMetrics that does not match an injected evidenceService's own metrics instance (fail loudly, not silently)", async () => {
  const { EvidenceService } = await import("../../evidence-registry/evidence-service.js");
  const { ServicePlatformMetrics } = await import("../../evidence-registry/service-metrics.js");
  const inner = new EvidenceService({ serviceMetrics: new ServicePlatformMetrics() });
  const mismatchedMetrics = new ServicePlatformMetrics();

  assert.throws(
    () => new IntelligenceService({ evidenceService: inner, serviceMetrics: mismatchedMetrics }),
    /does not match the injected deps\.evidenceService/
  );
});

test("IntelligenceLookupService unifies evidence-registry lookups and enterprise-query dimensions", async () => {
  const service = new IntelligenceService();
  await service.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-1234"] }));
  assert.equal((await service.lookup.getEvidence(UUID_1)).evidence_uuid, UUID_1);
  assert.equal((await service.lookup.byCVE("CVE-2026-1234")).length, 1);
  await assert.rejects(() => service.lookup.byVendor("Cisco"), /no canonical, composable Vendor implementation/);
});

test("IntelligenceValidationService.validateEvidence delegates verbatim to EvidenceValidationService", () => {
  const service = new IntelligenceService();
  const result = service.validation.validateEvidence(evidence(UUID_1));
  assert.equal(result.valid, true);
});

test("IntelligenceValidationService.validateIntelligenceBundle flags an unknown sourceId", async () => {
  const service = new IntelligenceService();
  const result = await service.validation.validateIntelligenceBundle({
    evidence: evidence(UUID_1),
    sourceId: "SRC-does-not-exist",
  });
  assert.equal(result.valid, false);
  assert.ok(result.errors.some((e) => e.includes("SRC-does-not-exist")));
});

test("IntelligenceValidationService.validateIntelligenceBundle passes when the sourceId resolves to registered evidence", async () => {
  const service = new IntelligenceService();
  await service.evidenceService.registerEvidence(evidence(UUID_1, { source_id: "SRC-001" }));
  const result = await service.validation.validateIntelligenceBundle({
    evidence: evidence(UUID_2, { source_id: "SRC-001" }),
    sourceId: "SRC-001",
  });
  assert.equal(result.valid, true);
});

test("ThreatIntelligenceService.getThreatProfile composes lookup + correlation + provenance into one response", async () => {
  const service = new IntelligenceService();
  await service.evidenceService.registerEvidence(evidence(UUID_1, { related_cves: ["CVE-2026-5555"] }));
  await service.evidenceService.registerEvidence(evidence(UUID_2, { related_cves: ["CVE-2026-5555"] }));

  const profile = await service.threatIntelligence.getThreatProfile("cve", "CVE-2026-5555");
  assert.equal(profile.evidenceCount, 2);
  assert.equal(profile.confidence.total, 2);
  assert.ok(Array.isArray(profile.provenanceSample));
});

test("ThreatIntelligenceService.getThreatProfile rejects an unknown dimension", async () => {
  const service = new IntelligenceService();
  await assert.rejects(() => service.threatIntelligence.getThreatProfile("vendor", "Cisco"), /unknown dimension "vendor"/);
});

test("IntelligenceLookupService/IntelligenceValidationService/IntelligenceCorrelationService reject missing dependencies (negative-path/DI test)", () => {
  assert.throws(() => new IntelligenceLookupService({}), /requires evidenceLookup and enterpriseQuery/);
  assert.throws(() => new IntelligenceValidationService({}), /requires evidenceValidation and lookup/);
  assert.throws(() => new IntelligenceCorrelationService({}), /requires evidenceService and queryEngine/);
});
