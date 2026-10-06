/**
 * Enterprise Evidence Service Platform  -  Stage 12 Phase 5, Internal Contracts
 * (Project TITAN). Not imported by index.js or any production route. See README.md.
 *
 * Five versioned internal contracts (EvidenceServiceContract, RelationshipContract,
 * ProvenanceContract, ValidationContract, MetricsContract)  -  documentation-as-data describing
 * each Phase 1-4/6 service's public method surface, not runtime-enforced interfaces (this
 * codebase's existing pattern for "interface" is an abstract class with NOT_IMPLEMENTED methods,
 * per interfaces.js/registry-repository-interface.js; these contracts describe services that
 * already concretely exist, so that pattern doesn't apply here  -  a contract violation is
 * "the documented method list drifted from the real exported method list," which
 * check_contract_drift() (Phase 7, titan_architecture_governance_check.py) verifies against the
 * actual source files, not against this file's own claims).
 *
 * Versioning reuses schema.js's exact compatibility algorithm (Stage 10)  -  `isCompatible()`
 * below is not a new compatibility scheme, it is the same "every step must be recorded additive"
 * walk, applied to a contract's own version history instead of the Evidence schema's.
 * "Validate backward compatibility": `checkContractCompatibility()` is that check, reusable
 * across all five contracts rather than five hand-written copies.
 */

/**
 * @typedef {Object} ContractVersionEntry
 * @property {string} version
 * @property {string} change
 * @property {boolean | null} backwardCompatibleWithPrevious
 */

/**
 * Generic, reusable "is fromVersion forward-compatible with toVersion" walk over any contract's
 * own version history array  -  the exact algorithm schema.js's isForwardCompatible() already
 * implements for the Evidence schema specifically, generalized here so five contracts can share
 * one implementation instead of five copies. Not a duplication of schema.js: that module governs
 * CanonicalEvidence's schema_version; this one governs these five method-surface contracts'
 * own, separate version strings. Two different things being versioned, one shared algorithm.
 * @param {ContractVersionEntry[]} history
 * @param {string} fromVersion @param {string} toVersion
 * @returns {boolean}
 */
export function isContractForwardCompatible(history, fromVersion, toVersion) {
  const fromIndex = history.findIndex((entry) => entry.version === fromVersion);
  const toIndex = history.findIndex((entry) => entry.version === toVersion);
  if (fromIndex === -1 || toIndex === -1) return false;
  if (fromIndex > toIndex) return false;
  for (let i = fromIndex + 1; i <= toIndex; i += 1) {
    if (history[i].backwardCompatibleWithPrevious !== true) return false;
  }
  return true;
}

/**
 * @param {{name: string, version: string, history: ContractVersionEntry[], methods: string[]}} contract
 * @param {string} callerExpectedVersion
 * @returns {{compatible: boolean, currentVersion: string, callerExpectedVersion: string}}
 */
export function checkContractCompatibility(contract, callerExpectedVersion) {
  return {
    compatible: isContractForwardCompatible(contract.history, callerExpectedVersion, contract.version),
    currentVersion: contract.version,
    callerExpectedVersion,
  };
}

export const EvidenceServiceContract = Object.freeze({
  name: "EvidenceServiceContract",
  version: "1.0.0",
  source: "evidence-service.js",
  methods: Object.freeze([
    "EvidenceService.registerEvidence", "EvidenceService.updateEvidence",
    "EvidenceService.supersedeEvidence", "EvidenceService.archiveEvidence",
    "EvidenceLookupService.getEvidence", "EvidenceLookupService.findEvidence",
    "EvidenceLookupService.findByCVE", "EvidenceLookupService.findByThreatActor",
    "EvidenceLookupService.findByReport", "EvidenceLookupService.findByCampaign",
    "EvidenceLookupService.findByAttackTechnique", "EvidenceLookupService.findByIOC",
    "EvidenceLookupService.findBySource", "EvidenceLookupService.findByConfidenceTier",
    "EvidenceLifecycleService.getLifecycleState", "EvidenceLifecycleService.getAuditTrail",
    "EvidenceLifecycleService.transitionLifecycle",
  ]),
  history: Object.freeze([
    Object.freeze({ version: "1.0.0", change: "Initial contract (Stage 12 Phase 1/5)", backwardCompatibleWithPrevious: null }),
  ]),
});

export const RelationshipContract = Object.freeze({
  name: "RelationshipContract",
  version: "1.0.0",
  source: "relationship-resolution.js + evidence-service.js's EvidenceRelationshipService",
  methods: Object.freeze([
    "EvidenceRelationshipService.findByRelationship",
    "RelationshipResolutionService.resolveRelationships",
    "RelationshipResolutionService.isWired",
  ]),
  history: Object.freeze([
    Object.freeze({
      version: "1.0.0",
      change:
        "Initial contract (Stage 12 Phase 4). Consumption-contract only, no concrete provider " +
        "wired  -  ADR-0010 not Accepted. See relationship-resolution.js's module docstring.",
      backwardCompatibleWithPrevious: null,
    }),
  ]),
});

export const ProvenanceContract = Object.freeze({
  name: "ProvenanceContract",
  version: "1.0.0",
  source: "provenance-engine.js",
  methods: Object.freeze([
    "EvidenceProvenanceEngine.getEvidenceLineage", "EvidenceProvenanceEngine.getVersionLineage",
    "EvidenceProvenanceEngine.getRelationshipLineage", "EvidenceProvenanceEngine.getConfidenceLineage",
    "EvidenceProvenanceEngine.getSourceLineage", "EvidenceProvenanceEngine.getAuditLineage",
  ]),
  history: Object.freeze([
    Object.freeze({ version: "1.0.0", change: "Initial contract (Stage 12 Phase 3/5): six lineage kinds", backwardCompatibleWithPrevious: null }),
  ]),
});

export const ValidationContract = Object.freeze({
  name: "ValidationContract",
  version: "1.0.0",
  source: "evidence-service.js's EvidenceValidationService",
  methods: Object.freeze([
    "EvidenceValidationService.validateEvidence", "EvidenceValidationService.validateBatch",
  ]),
  history: Object.freeze([
    Object.freeze({ version: "1.0.0", change: "Initial contract (Stage 12 Phase 1/5)", backwardCompatibleWithPrevious: null }),
  ]),
});

export const MetricsContract = Object.freeze({
  name: "MetricsContract",
  version: "1.0.0",
  source: "service-metrics.js + evidence-service.js's EvidenceMetricsService",
  methods: Object.freeze([
    "EvidenceMetricsService.snapshot", "ServicePlatformMetrics.timed",
    "ServicePlatformMetrics.recordQuery", "ServicePlatformMetrics.recordRelationshipResolution",
    "ServicePlatformMetrics.recordProvenanceLookup", "ServicePlatformMetrics.snapshot",
  ]),
  history: Object.freeze([
    Object.freeze({ version: "1.0.0", change: "Initial contract (Stage 12 Phase 6/5)", backwardCompatibleWithPrevious: null }),
  ]),
});

export const ALL_SERVICE_CONTRACTS = Object.freeze([
  EvidenceServiceContract,
  RelationshipContract,
  ProvenanceContract,
  ValidationContract,
  MetricsContract,
]);
