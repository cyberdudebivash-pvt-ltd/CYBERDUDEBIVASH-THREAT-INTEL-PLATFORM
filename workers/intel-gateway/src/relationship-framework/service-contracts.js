/**
 * Relationship Framework -- Stage 16 Phase 1, Internal Contracts (Project TITAN).
 * Not imported by index.js or any production route. See README.md.
 *
 * Versioned internal contracts describing this stage's public method surface, mirroring
 * evidence-registry/service-contracts.js (Stage 12) and intelligence-platform/service-contracts.js
 * (Stage 13)'s exact pattern and format. Reuses isContractForwardCompatible()/
 * checkContractCompatibility() UNCHANGED from Stage 12 rather than redefining them -- both
 * functions are already generic over any {history, version} shape.
 */

import { isContractForwardCompatible, checkContractCompatibility } from "../evidence-registry/service-contracts.js";

export { isContractForwardCompatible, checkContractCompatibility };

export const RelationshipServiceContract = Object.freeze({
  name: "RelationshipServiceContract",
  version: "1.0.0",
  source: "relationship-service.js",
  methods: Object.freeze([
    "RelationshipService.lookup", "RelationshipService.traverse", "RelationshipService.shortestPath",
    "RelationshipService.validateEdge", "RelationshipService.validateBatch", "RelationshipService.ingestEdges",
    "RelationshipService.getMetricsSnapshot", "RelationshipService.registry",
  ]),
  history: Object.freeze([
    Object.freeze({
      version: "1.0.0",
      change:
        "Initial contract (Stage 16 Phase 1). Composes Stage 12's RelationshipResolutionService " +
        "(now wired to a real P31RelationshipProvider, per ADR-0010 Acceptance) and Stage 13's " +
        "IntelligenceCorrelationService.correlateByRelationship rather than reimplementing either.",
      backwardCompatibleWithPrevious: null,
    }),
  ]),
});

export const RelationshipRegistryContract = Object.freeze({
  name: "RelationshipRegistryContract",
  version: "1.0.0",
  source: "relationship-registry.js",
  methods: Object.freeze([
    "RelationshipRegistry.register", "RelationshipRegistry.get", "RelationshipRegistry.list",
    "RelationshipRegistry.isKnownType", "RelationshipRegistry.normalizeTypeName", "RelationshipRegistry.validateEntityPair",
  ]),
  history: Object.freeze([
    Object.freeze({ version: "1.0.0", change: "Initial contract (Stage 16 Phase 2)", backwardCompatibleWithPrevious: null }),
  ]),
});

export const RelationshipTraversalContract = Object.freeze({
  name: "RelationshipTraversalContract",
  version: "1.0.0",
  source: "relationship-traversal.js",
  methods: Object.freeze(["RelationshipTraversalService.traverse", "RelationshipTraversalService.shortestPath"]),
  history: Object.freeze([
    Object.freeze({ version: "1.0.0", change: "Initial contract (Stage 16 Phase 1/3)", backwardCompatibleWithPrevious: null }),
  ]),
});

export const RelationshipValidationContract = Object.freeze({
  name: "RelationshipValidationContract",
  version: "1.0.0",
  source: "relationship-validation.js",
  methods: Object.freeze([
    "RelationshipValidationService.validateEdge", "RelationshipValidationService.validateBatch",
    "RelationshipValidationService.findOrphanEntities", "RelationshipValidationService.findCycles",
  ]),
  history: Object.freeze([
    Object.freeze({ version: "1.0.0", change: "Initial contract (Stage 16 Phase 1/8)", backwardCompatibleWithPrevious: null }),
  ]),
});

export const RelationshipMetricsContract = Object.freeze({
  name: "RelationshipMetricsContract",
  version: "1.0.0",
  source: "relationship-metrics.js",
  methods: Object.freeze([
    "RelationshipMetricsService.recordTraversalLatency", "RelationshipMetricsService.recordCorrelation",
    "RelationshipMetricsService.recordValidationFailure", "RelationshipMetricsService.recordConfidencePropagation",
    "RelationshipMetricsService.snapshot",
  ]),
  history: Object.freeze([
    Object.freeze({ version: "1.0.0", change: "Initial contract (Stage 16 Phase 1/7)", backwardCompatibleWithPrevious: null }),
  ]),
});

export const ALL_RELATIONSHIP_FRAMEWORK_CONTRACTS = Object.freeze([
  RelationshipServiceContract,
  RelationshipRegistryContract,
  RelationshipTraversalContract,
  RelationshipValidationContract,
  RelationshipMetricsContract,
]);
