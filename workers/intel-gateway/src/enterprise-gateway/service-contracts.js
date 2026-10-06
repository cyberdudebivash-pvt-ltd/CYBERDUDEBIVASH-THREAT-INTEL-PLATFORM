/**
 * Enterprise Intelligence Gateway (EIG) -- Stage 14 Phase 1, Internal Contracts (Project TITAN).
 * Not imported by index.js or any production route. See TITAN_STAGE14_SERVICE_ARCHITECTURE.md.
 *
 * Four versioned internal contracts (GatewayServiceContract, MiddlewareContract,
 * CapabilityRegistryContract, GatewayMetricsContract) -- documentation-as-data describing this
 * stage's own public method surface, mirroring intelligence-platform/service-contracts.js
 * (Stage 13) and evidence-registry/service-contracts.js (Stage 12)'s pattern and format exactly.
 *
 * Reuses isContractForwardCompatible()/checkContractCompatibility() from Stage 13's
 * service-contracts.js UNCHANGED (which itself reuses Stage 12's, unchanged) -- both functions
 * are already generic over any {history, version} shape, nothing here to duplicate, only reuse.
 * Imported from intelligence-platform/, not evidence-registry/ directly, keeping this
 * directory's dependency to the one authorized hop.
 */

import { isContractForwardCompatible, checkContractCompatibility } from "../intelligence-platform/service-contracts.js";

export { isContractForwardCompatible, checkContractCompatibility };

export const GatewayServiceContract = Object.freeze({
  name: "GatewayServiceContract",
  version: "1.1.0",
  source: "gateway-service.js",
  methods: Object.freeze([
    "EnterpriseGateway.dispatch",
    "EnterpriseGateway.registerCapability",
    "EnterpriseGateway.listCapabilities",
    "EnterpriseGateway.healthCheck",
    "EnterpriseGateway.describeCapability",
    "EnterpriseGateway.describeAllCapabilities",
    "EnterpriseGateway.annotateCapability",
  ]),
  history: Object.freeze([
    Object.freeze({ version: "1.0.0", change: "Initial contract (Stage 14 Phase 1)", backwardCompatibleWithPrevious: null }),
    Object.freeze({
      version: "1.1.0",
      change:
        "Added describeCapability/describeAllCapabilities/annotateCapability (Stage 21 Phase 4) -- " +
        "thin passthroughs to the registry's Stage 21 additions, additive and backward compatible.",
      backwardCompatibleWithPrevious: true,
    }),
  ]),
});

export const MiddlewareContract = Object.freeze({
  name: "MiddlewareContract",
  version: "1.0.0",
  source: "gateway-middleware.js",
  methods: Object.freeze([
    "composeGatewayMiddleware",
    "tracingMiddleware",
    "featureFlagEvaluationMiddleware",
    "versionCompatibilityMiddleware",
    "capabilityValidationMiddleware",
    "auditLoggingMiddleware",
    "metricsMiddleware",
  ]),
  history: Object.freeze([
    Object.freeze({
      version: "1.0.0",
      change: "Initial contract (Stage 14 Phase 1): 6 default composable stages",
      backwardCompatibleWithPrevious: null,
    }),
  ]),
});

export const CapabilityRegistryContract = Object.freeze({
  name: "CapabilityRegistryContract",
  version: "1.2.0",
  source: "gateway-registry.js",
  methods: Object.freeze([
    "GatewayRegistry.register",
    "GatewayRegistry.has",
    "GatewayRegistry.get",
    "GatewayRegistry.list",
    "GatewayRegistry.unregister",
    "GatewayRegistry.describe",
    "GatewayRegistry.describeAll",
    "GatewayRegistry.annotate",
    "createServiceMethodHandler",
  ]),
  history: Object.freeze([
    Object.freeze({ version: "1.0.0", change: "Initial contract (Stage 14 Phase 1)", backwardCompatibleWithPrevious: null }),
    Object.freeze({
      version: "1.1.0",
      change:
        "Added GatewayRegistry.describe/.describeAll (Stage 14 Phase 2) -- read-only capability " +
        "metadata accessors that omit the handler function, additive and backward compatible.",
      backwardCompatibleWithPrevious: true,
    }),
    Object.freeze({
      version: "1.2.0",
      change:
        "Added GatewayRegistry.annotate and 5 optional commercial-classification fields to " +
        "register()/describe()/describeAll() -- owner, consumers, securityClassification, " +
        "visibility, lifecycle (Stage 21 Phase 4). All 5 fields are optional with secure-by-default " +
        "values; every pre-Stage-21 register() call site is unaffected. Additive and backward " +
        "compatible.",
      backwardCompatibleWithPrevious: true,
    }),
  ]),
});

export const GatewayMetricsContract = Object.freeze({
  name: "GatewayMetricsContract",
  version: "1.0.0",
  source: "gateway-metrics.js + evidence-registry/service-metrics.js (single shared ServicePlatformMetrics instance)",
  methods: Object.freeze([
    "GatewayMetrics.snapshot",
    "GatewayMetrics.sharedServiceMetrics",
    "GatewayMetrics.recordFeatureFlagEvaluation",
    "GatewayMetrics.recordCapabilityAuthorizationDenial",
    "GatewayMetrics.recordMiddlewareValidationFailure",
  ]),
  history: Object.freeze([
    Object.freeze({
      version: "1.0.0",
      change:
        "Initial contract (Stage 14 Phase 1). No new ServicePlatformMetrics instance -- shares " +
        "the one Stage 12 constructed, reached via platform.metrics.sharedServiceMetrics.",
      backwardCompatibleWithPrevious: null,
    }),
  ]),
});

export const ALL_EIG_CONTRACTS = Object.freeze([
  GatewayServiceContract,
  MiddlewareContract,
  CapabilityRegistryContract,
  GatewayMetricsContract,
]);
