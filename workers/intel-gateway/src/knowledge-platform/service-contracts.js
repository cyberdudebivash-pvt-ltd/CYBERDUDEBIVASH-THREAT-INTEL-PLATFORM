/**
 * Enterprise Intelligence Knowledge Platform (EIKP) -- Project TITAN Stage 18, Internal
 * Contracts. Not imported by index.js or any production route. See README.md.
 *
 * Five versioned internal contracts (KnowledgeObjectContract, KnowledgeNavigationContract,
 * AnalystViewContract, ExecutiveViewContract, KnowledgeQualityContract) -- documentation-as-data
 * describing each Stage 18 service's public method surface, mirroring
 * evidence-registry/service-contracts.js's (Stage 12) and intelligence-platform/
 * service-contracts.js's (Stage 13) pattern and format exactly.
 *
 * Reuses isContractForwardCompatible()/checkContractCompatibility() from intelligence-platform/
 * UNCHANGED rather than redefining them -- those two functions are already generic over any
 * {history, version} shape.
 */

import {
  isContractForwardCompatible,
  checkContractCompatibility,
} from "../intelligence-platform/service-contracts.js";

export { isContractForwardCompatible, checkContractCompatibility };

export const KnowledgeObjectContract = Object.freeze({
  name: "KnowledgeObjectContract",
  version: "1.0.0",
  source: "knowledge-object.js",
  methods: Object.freeze(["KnowledgeObjectService.build"]),
  history: Object.freeze([
    Object.freeze({ version: "1.0.0", change: "Initial contract (Stage 18 Phase 2)", backwardCompatibleWithPrevious: null }),
  ]),
});

export const KnowledgeNavigationContract = Object.freeze({
  name: "KnowledgeNavigationContract",
  version: "1.0.0",
  source: "knowledge-navigation.js",
  methods: Object.freeze([
    "KnowledgeNavigationService.relatedIntelligence",
    "KnowledgeNavigationService.similarIntelligence",
    "KnowledgeNavigationService.supportingEvidence",
    "KnowledgeNavigationService.contradictoryEvidence",
    "KnowledgeNavigationService.historicalIntelligence",
    "KnowledgeNavigationService.collectionGaps",
  ]),
  history: Object.freeze([
    Object.freeze({
      version: "1.0.0",
      change:
        "Initial contract (Stage 18 Phase 3). similarIntelligence() is the one new computation " +
        "(deterministic structural overlap); every other method delegates to an existing " +
        "Stage 12/13/17 service.",
      backwardCompatibleWithPrevious: null,
    }),
  ]),
});

export const AnalystViewContract = Object.freeze({
  name: "AnalystViewContract",
  version: "1.0.0",
  source: "analyst-views.js",
  methods: Object.freeze([
    "AnalystViewService.investigationView",
    "AnalystViewService.correlationView",
    "AnalystViewService.evidenceTimeline",
    "AnalystViewService.confidenceContext",
    "AnalystViewService.intelligenceGapView",
    "AnalystViewService.collectionPriorityView",
  ]),
  history: Object.freeze([
    Object.freeze({
      version: "1.0.0",
      change:
        "Initial contract (Stage 18 Phase 4). confidenceContext() surfaces existing verbatim " +
        "values only -- no confidence computation (ADR-0007 Proposed, not Accepted).",
      backwardCompatibleWithPrevious: null,
    }),
  ]),
});

export const ExecutiveViewContract = Object.freeze({
  name: "ExecutiveViewContract",
  version: "1.0.0",
  source: "executive-views.js",
  methods: Object.freeze(["ExecutiveViewService.executiveBriefing"]),
  history: Object.freeze([
    Object.freeze({
      version: "1.0.0",
      change:
        "Initial contract (Stage 18 Phase 5). No business/operational-impact score is computed " +
        "-- every returned item carries an explicit basis of \"evidence\" or " +
        "\"analyst_recommendation\".",
      backwardCompatibleWithPrevious: null,
    }),
  ]),
});

export const KnowledgeQualityContract = Object.freeze({
  name: "KnowledgeQualityContract",
  version: "1.0.0",
  source: "knowledge-quality.js",
  methods: Object.freeze([
    "KnowledgeQualityService.validateEvidenceCompleteness",
    "KnowledgeQualityService.validateProvenanceAvailability",
    "KnowledgeQualityService.validateCorrelationCoverage",
    "KnowledgeQualityService.validateExplanationAvailability",
    "KnowledgeQualityService.detectMissingReferences",
    "KnowledgeQualityService.detectUnsupportedAssertions",
    "KnowledgeQualityService.describeQualityFramework",
    "KnowledgeQualityService.evaluate",
    "KnowledgeQualityService.evaluateForEvidence",
  ]),
  history: Object.freeze([
    Object.freeze({ version: "1.0.0", change: "Initial contract (Stage 18 Phase 6)", backwardCompatibleWithPrevious: null }),
  ]),
});

export const ALL_KP_CONTRACTS = Object.freeze([
  KnowledgeObjectContract,
  KnowledgeNavigationContract,
  AnalystViewContract,
  ExecutiveViewContract,
  KnowledgeQualityContract,
]);
