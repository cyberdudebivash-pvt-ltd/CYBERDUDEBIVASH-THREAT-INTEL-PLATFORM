# Project TITAN Stage 14, Phase 1 — Enterprise Intelligence Gateway (EIG) Contract Documentation

Four versioned internal contracts in `workers/intel-gateway/src/enterprise-gateway/service-contracts.js`, mirroring `intelligence-platform/service-contracts.js` (Stage 13) and `evidence-registry/service-contracts.js` (Stage 12)'s pattern exactly — documentation-as-data, not a runtime-enforced interface (this codebase's "interface" pattern is an abstract class with `NOT_IMPLEMENTED` methods; these contracts describe services that already concretely exist). `isContractForwardCompatible()`/`checkContractCompatibility()` are reused unchanged from Stage 12/13, not reimplemented — both are already generic over any `{history, version}` shape.

## GatewayServiceContract (v1.0.0)

Source: `gateway-service.js`. Methods: `EnterpriseGateway.dispatch`, `.registerCapability`, `.listCapabilities`, `.healthCheck`.

## MiddlewareContract (v1.0.0)

Source: `gateway-middleware.js`. Methods: `composeGatewayMiddleware`, `tracingMiddleware`, `featureFlagEvaluationMiddleware`, `versionCompatibilityMiddleware`, `capabilityValidationMiddleware`, `auditLoggingMiddleware`, `metricsMiddleware`. 6 default composable stages (see the Service Architecture doc §8).

## CapabilityRegistryContract (v1.1.0)

Source: `gateway-registry.js`. Methods: `GatewayRegistry.register`, `.has`, `.get`, `.list`, `.unregister`, `.describe`, `.describeAll`, `createServiceMethodHandler`.

**v1.1.0 (Stage 14 Phase 2, additive, `backwardCompatibleWithPrevious: true`):** added `.describe(name)`/`.describeAll()` — read-only capability metadata (`{name, version, description, requiredCapabilities}`) with the raw `handler` function omitted, for diagnostic/observability callers that shouldn't be able to invoke capabilities directly via `.get()`'s full internal entry. A caller still on v1.0.0 is unaffected — `.get()`/`.has()`/`.list()`/`.register()`/`.unregister()` are all unchanged.

## GatewayMetricsContract (v1.0.0)

Source: `gateway-metrics.js` + `evidence-registry/service-metrics.js` (single shared `ServicePlatformMetrics` instance). Methods: `GatewayMetrics.snapshot`, `.sharedServiceMetrics`, `.recordFeatureFlagEvaluation`, `.recordCapabilityAuthorizationDenial`, `.recordMiddlewareValidationFailure`. No new `ServicePlatformMetrics` instance — shares the one Stage 12 constructed, reached via `platform.metrics.sharedServiceMetrics`.

## Consuming a contract

A caller that wants version-compatibility enforcement on a specific capability call can pass `metadata: {expectedContractVersion, targetContract}` in a `dispatch()` request — the `versionCompatibilityMiddleware` stage will reject an incompatible version via `ContractVersionIncompatibleError` before the handler runs (see the Service Architecture doc §8). This is opt-in per call; Phase 1's own internal adoption script (`scripts/enterprise_gateway_snapshot.mjs`) does not use it, since it always calls against the current version.

## ADR-0012 applicability

ADR-0012 (API Versioning & Interface Governance, Accepted) governs `/api/v1/*` path-prefix versioning for HTTP surfaces. Since this stage stays purely in-process/DI with no HTTP surface (per its own Non-Goals), ADR-0012 does not apply to it yet — stated here explicitly rather than left ambiguous, per that ADR's own text.
