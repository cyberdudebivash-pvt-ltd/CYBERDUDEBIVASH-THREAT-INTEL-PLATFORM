/**
 * Commercial Catalog (Project TITAN Stage 21 Phase 3) -- internal/v1 Service Contracts.
 * Not imported by index.js or any production route. See TITAN_STAGE21_GATEWAY_ACTIVATION_AUDIT.md.
 *
 * Four `internal/v1`-namespaced contracts (CommercialCatalogContract, CommercialAdaptersContract,
 * CommercialMetricsContract, CommercialReadinessContract) -- documentation-as-data describing this
 * stage's own public surface, mirroring enterprise-gateway/service-contracts.js's exact
 * {name, version, source, methods, history} shape and reusing
 * isContractForwardCompatible()/checkContractCompatibility() UNCHANGED (nothing here to
 * duplicate, only reuse -- see evidence-registry/service-contracts.js, the canonical origin,
 * reused transitively through every layer above it).
 *
 * The `namespace: "internal/v1"` field on every contract below is a deliberately DIFFERENT
 * concept from ADR-0012 (API Versioning & Interface Governance, Accepted)'s `/api/v1/` path-prefix
 * scheme: ADR-0012 governs public, externally-reachable REST surfaces; "internal/v1" carries no
 * external API commitment whatsoever -- only the Gateway (via commercial-catalog/platform.js)
 * ever reads these contracts. Named explicitly to avoid the exact "v1 label collision" ambiguity
 * ADR-0012 itself flags between intel-platform's and blog's unrelated `/api/v1/` surfaces.
 */

import { isContractForwardCompatible, checkContractCompatibility } from "../enterprise-gateway/service-contracts.js";

export { isContractForwardCompatible, checkContractCompatibility };

export const INTERNAL_V1_NAMESPACE = "internal/v1";

export const CommercialCatalogContract = Object.freeze({
  name: "CommercialCatalogContract",
  namespace: INTERNAL_V1_NAMESPACE,
  version: "1.0.0",
  source: "catalog.js",
  methods: Object.freeze(["getCatalogEntry", "listNewAdapterEntries", "listExistingCapabilityEntries"]),
  history: Object.freeze([
    Object.freeze({ version: "1.0.0", change: "Initial contract (Stage 21 Phase 1/3)", backwardCompatibleWithPrevious: null }),
  ]),
});

export const CommercialAdaptersContract = Object.freeze({
  name: "CommercialAdaptersContract",
  namespace: INTERNAL_V1_NAMESPACE,
  version: "1.0.0",
  source: "commercial-adapters.js",
  methods: Object.freeze([
    "createKnowledgeObjectAdapter",
    "createKnowledgeNavigationAdapter",
    "createKnowledgeExecutiveBriefingAdapter",
    "createEvidenceProvenanceSummaryAdapter",
    "createProductAssemblyAdapter",
    "createProductProfiledViewAdapter",
    "createProductPackageAdapter",
    "createMsspPartnerPackageAdapter",
    "createCommercialReadinessSummaryAdapter",
    "createCommercialExplanationAdapter",
  ]),
  history: Object.freeze([
    Object.freeze({ version: "1.0.0", change: "Initial contract (Stage 21 Phase 2/3)", backwardCompatibleWithPrevious: null }),
  ]),
});

export const CommercialMetricsContract = Object.freeze({
  name: "CommercialMetricsContract",
  namespace: INTERNAL_V1_NAMESPACE,
  version: "1.0.0",
  source: "commercial-metrics.js + enterprise-gateway/gateway-metrics.js (single shared ServicePlatformMetrics instance)",
  methods: Object.freeze([
    "CommercialMetrics.snapshot",
    "CommercialMetrics.recordInvocation",
    "CommercialMetrics.recordFailure",
    "CommercialMetrics.recordLatencySample",
  ]),
  history: Object.freeze([
    Object.freeze({
      version: "1.0.0",
      change:
        "Initial contract (Stage 21 Phase 5). No new ServicePlatformMetrics instance -- shares the " +
        "one instance reached via gateway.platform.metrics.sharedServiceMetrics.",
      backwardCompatibleWithPrevious: null,
    }),
  ]),
});

export const CommercialReadinessContract = Object.freeze({
  name: "CommercialReadinessContract",
  namespace: INTERNAL_V1_NAMESPACE,
  version: "1.0.0",
  source: "commercial-readiness.js",
  methods: Object.freeze(["buildCommercialReadinessReport", "buildCommercialReadinessEntry"]),
  history: Object.freeze([
    Object.freeze({ version: "1.0.0", change: "Initial contract (Stage 21 Phase 7)", backwardCompatibleWithPrevious: null }),
  ]),
});

export const ALL_COMMERCIAL_CATALOG_CONTRACTS = Object.freeze([
  CommercialCatalogContract,
  CommercialAdaptersContract,
  CommercialMetricsContract,
  CommercialReadinessContract,
]);
