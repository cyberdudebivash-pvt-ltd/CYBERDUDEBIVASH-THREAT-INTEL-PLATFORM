/**
 * Enterprise Intelligence Platform Services (EIPS) -- Stage 13 Phase 5, Internal Contracts
 * (Project TITAN). Not imported by index.js or any production route. See README.md.
 *
 * Six versioned internal contracts (IntelligenceServiceContract, QueryContract,
 * CorrelationContract, ProvenanceContract, IntelligenceValidationContract,
 * IntelligenceMetricsContract) -- documentation-as-data describing each Stage 13 service's
 * public method surface, exactly mirroring evidence-registry/service-contracts.js's (Stage 12)
 * pattern and format.
 *
 * Reuses isContractForwardCompatible()/checkContractCompatibility() from Stage 12's
 * service-contracts.js UNCHANGED rather than redefining them -- those two functions are
 * already generic over any {history, version} shape, not specific to Stage 12's five
 * contracts, so there is nothing here to duplicate, only reuse.
 *
 * Naming note: two of Stage 12's five contract names (ValidationContract, MetricsContract)
 * would collide as identifiers with genuinely different Stage 13 contracts of the same
 * conceptual shape but different method surface -- prefixed Intelligence* here to keep every
 * contract name globally unique across the platform (governance's
 * check_no_duplicate_eips_contracts()/check_no_duplicate_service_contracts() both verify this).
 * ProvenanceContract is the third case, but resolved the other way: Stage 13 Phase 4 adds zero
 * new provenance code (see intelligence-service.js's IntelligenceService.provenance property
 * docs), so rather than mint a second, identical contract under a different name, this module
 * imports and re-exports Stage 12's ProvenanceContract UNCHANGED below -- one contract, one
 * name, reused.
 */

import {
  isContractForwardCompatible,
  checkContractCompatibility,
  ProvenanceContract,
} from "../evidence-registry/service-contracts.js";

export { isContractForwardCompatible, checkContractCompatibility, ProvenanceContract };

export const IntelligenceServiceContract = Object.freeze({
  name: "IntelligenceServiceContract",
  version: "1.0.0",
  source: "intelligence-service.js",
  methods: Object.freeze([
    "IntelligenceLookupService.getEvidence", "IntelligenceLookupService.findEvidence",
    "IntelligenceLookupService.byCVE", "IntelligenceLookupService.byThreatActor",
    "IntelligenceLookupService.byCampaign", "IntelligenceLookupService.byIOC",
    "IntelligenceLookupService.byReport", "IntelligenceLookupService.byAttackTechnique",
    "IntelligenceLookupService.bySource", "IntelligenceLookupService.byConfidenceTier",
    "IntelligenceLookupService.byVendor", "IntelligenceLookupService.byProduct",
    "IntelligenceLookupService.byMalware", "ThreatIntelligenceService.getThreatProfile",
  ]),
  history: Object.freeze([
    Object.freeze({ version: "1.0.0", change: "Initial contract (Stage 13 Phase 1/5)", backwardCompatibleWithPrevious: null }),
  ]),
});

export const QueryContract = Object.freeze({
  name: "QueryContract",
  version: "1.0.0",
  source: "query-service.js",
  methods: Object.freeze([
    "EnterpriseQueryService.queryByEvidence", "EnterpriseQueryService.queryByReport",
    "EnterpriseQueryService.queryByCVE", "EnterpriseQueryService.queryByThreatActor",
    "EnterpriseQueryService.queryByCampaign", "EnterpriseQueryService.queryByIOC",
    "EnterpriseQueryService.queryByConfidence", "EnterpriseQueryService.queryBySource",
    "EnterpriseQueryService.queryByAttackTechnique",
    "EnterpriseQueryService.queryByVendor", "EnterpriseQueryService.queryByProduct",
    "EnterpriseQueryService.queryByMalware",
  ]),
  history: Object.freeze([
    Object.freeze({
      version: "1.0.0",
      change:
        "Initial contract (Stage 13 Phase 2/5): 12 dimensions, 9 delegate to " +
        "EvidenceQueryEngine, 3 (Vendor/Product/Malware) document a confirmed platform gap and " +
        "throw rather than invent a model -- see query-service.js.",
      backwardCompatibleWithPrevious: null,
    }),
  ]),
});

export const CorrelationContract = Object.freeze({
  name: "CorrelationContract",
  version: "1.0.0",
  source: "correlation-engine.js",
  methods: Object.freeze([
    "IntelligenceCorrelationService.correlateEvidence", "IntelligenceCorrelationService.aggregateConfidence",
    "IntelligenceCorrelationService.correlateBySource", "IntelligenceCorrelationService.correlateByReport",
    "IntelligenceCorrelationService.correlateByIOC", "IntelligenceCorrelationService.correlateByRelationship",
  ]),
  history: Object.freeze([
    Object.freeze({
      version: "1.0.0",
      change:
        "Initial contract (Stage 13 Phase 3/5). correlateByRelationship is consumption-contract " +
        "only, no concrete graph provider wired -- ADR-0010 not Accepted. See correlation-engine.js's module docstring.",
      backwardCompatibleWithPrevious: null,
    }),
  ]),
});

export const IntelligenceValidationContract = Object.freeze({
  name: "IntelligenceValidationContract",
  version: "1.0.0",
  source: "intelligence-service.js",
  methods: Object.freeze([
    "IntelligenceValidationService.validateEvidence", "IntelligenceValidationService.validateBatch",
    "IntelligenceValidationService.validateIntelligenceBundle",
  ]),
  history: Object.freeze([
    Object.freeze({ version: "1.0.0", change: "Initial contract (Stage 13 Phase 1/5)", backwardCompatibleWithPrevious: null }),
  ]),
});

export const IntelligenceMetricsContract = Object.freeze({
  name: "IntelligenceMetricsContract",
  version: "1.0.0",
  source: "intelligence-service.js + evidence-registry/service-metrics.js (single shared ServicePlatformMetrics instance)",
  methods: Object.freeze([
    "IntelligenceMetricsService.snapshot", "IntelligenceMetricsService.sharedServiceMetrics",
    "ServicePlatformMetrics.timed", "ServicePlatformMetrics.recordQuery", "ServicePlatformMetrics.snapshot",
  ]),
  history: Object.freeze([
    Object.freeze({
      version: "1.0.0",
      change:
        "Initial contract (Stage 13 Phase 7/5). No new counter class -- Stage 13 shares Stage " +
        "12's ServicePlatformMetrics instance rather than introducing a second one.",
      backwardCompatibleWithPrevious: null,
    }),
  ]),
});

export const ALL_EIPS_CONTRACTS = Object.freeze([
  IntelligenceServiceContract,
  QueryContract,
  CorrelationContract,
  ProvenanceContract,
  IntelligenceValidationContract,
  IntelligenceMetricsContract,
]);
