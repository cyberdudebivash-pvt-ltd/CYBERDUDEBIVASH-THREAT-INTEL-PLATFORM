/**
 * Enterprise Intelligence Product & Delivery Platform (EIPDP) -- Project TITAN Stage 19, Internal
 * Contracts. Not imported by index.js or any production route. See README.md.
 *
 * Four versioned internal contracts (ProductEngineContract, ProductProfileContract,
 * ProductPackagingContract, ProductQualityContract) -- documentation-as-data describing each
 * Stage 19 service's public method surface, mirroring evidence-registry/service-contracts.js's
 * (Stage 12), intelligence-platform/service-contracts.js's (Stage 13), and
 * knowledge-platform/service-contracts.js's (Stage 18) pattern and format exactly.
 *
 * Reuses isContractForwardCompatible()/checkContractCompatibility() from knowledge-platform/
 * UNCHANGED rather than redefining them a third time -- those two functions are already generic
 * over any {history, version} shape.
 */

import {
  isContractForwardCompatible,
  checkContractCompatibility,
} from "../knowledge-platform/service-contracts.js";

export { isContractForwardCompatible, checkContractCompatibility };

export const ProductEngineContract = Object.freeze({
  name: "ProductEngineContract",
  version: "1.0.0",
  source: "product-engine.js",
  methods: Object.freeze(["ProductEngineService.assemble", "ProductEngineService.assembleMany"]),
  history: Object.freeze([
    Object.freeze({ version: "1.0.0", change: "Initial contract (Stage 19 Phase 2)", backwardCompatibleWithPrevious: null }),
  ]),
});

export const ProductProfileContract = Object.freeze({
  name: "ProductProfileContract",
  version: "1.0.0",
  source: "product-profiles.js",
  methods: Object.freeze([
    "ProductProfileService.listProfiles",
    "ProductProfileService.resolveProfile",
    "ProductProfileService.applyProfile",
  ]),
  history: Object.freeze([
    Object.freeze({
      version: "1.0.0",
      change:
        "Initial contract (Stage 19 Phase 3). Six audience profiles: soc_analyst, " +
        "threat_intelligence_analyst, executive_leadership, mssp_operations, " +
        "vulnerability_management, incident_response -- each a named, deterministic subset of " +
        "an already-assembled product's sections. Profiles reshape presentation only; they do " +
        "not alter underlying intelligence values.",
      backwardCompatibleWithPrevious: null,
    }),
  ]),
});

export const ProductPackagingContract = Object.freeze({
  name: "ProductPackagingContract",
  version: "1.0.0",
  source: "product-packaging.js",
  methods: Object.freeze(["ProductPackagingService.package", "ProductPackagingService.validatePackageType"]),
  history: Object.freeze([
    Object.freeze({
      version: "1.0.0",
      change:
        "Initial contract (Stage 19 Phase 4). Four package types: " +
        "enterprise_threat_intelligence_report, tactical_dossier, " +
        "executive_intelligence_briefing, knowledge_summary. Every package preserves metadata, " +
        "evidence references, provenance, a correlation summary, explainability, and " +
        "intelligence gaps regardless of package type or audience profile.",
      backwardCompatibleWithPrevious: null,
    }),
  ]),
});

export const ProductQualityContract = Object.freeze({
  name: "ProductQualityContract",
  version: "1.0.0",
  source: "product-quality.js",
  methods: Object.freeze([
    "ProductQualityService.evaluate",
    "ProductQualityService.describeQualityFramework",
    "ProductQualityService.evaluateForEvidence",
  ]),
  history: Object.freeze([
    Object.freeze({
      version: "1.0.0",
      change:
        "Initial contract (Stage 19 Phase 5). Delegates evidence-completeness/provenance/" +
        "correlation/explanation/unsupported-assertion checks to knowledge-platform's " +
        "evaluateKnowledgeObjectQuality() wholesale; adds only package-level checks " +
        "(provenance preserved in package, explainability included in package, profile " +
        "compliance, packaging consistency) that have no Stage 18 equivalent.",
      backwardCompatibleWithPrevious: null,
    }),
  ]),
});

export const ALL_PP_CONTRACTS = Object.freeze([
  ProductEngineContract,
  ProductProfileContract,
  ProductPackagingContract,
  ProductQualityContract,
]);
