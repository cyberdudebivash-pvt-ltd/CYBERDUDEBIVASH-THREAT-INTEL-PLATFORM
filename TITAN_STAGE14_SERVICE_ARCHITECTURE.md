# Project TITAN Stage 14, Phase 1 — Enterprise Intelligence Gateway (EIG) Service Architecture

## 1. Where this lives, and why

`workers/intel-gateway/src/enterprise-gateway/` — a new sibling directory to `evidence-registry/` (Stage 8/10/11/12) and `intelligence-platform/` (Stage 13), following the identical per-stage convention: not imported by `index.js` or any `pNN-handlers.js` file, its own `__tests__/` on Node's built-in test runner, its own `package.json` (`{"private":true,"type":"module"}`), its own `feature-flags.js`/`service-contracts.js`/`platform.js` composition root.

**Composes `intelligence-platform/` only — one hop, not two.** EIG depends on `IntelligenceService`, reaching `EvidenceService` transitively via `platform.evidenceService` rather than importing `evidence-registry/` directly in production code. This is deliberate: it keeps the new boundary to a single hop (stricter than Stage 13's own relationship to Stage 12), and was the reasoning behind the plan's (later revised — see the Completion Report §3) claim that `evidence-registry/`'s boundary test wouldn't need editing.

## 2. Dependency diagram

```
evidence-registry/   (Stage 8, 10, 11, 12 — EvidenceService, EvidenceRegistry, EvidenceQueryEngine,
                       EvidenceProvenanceEngine, RelationshipResolutionService, ServicePlatformMetrics)
        ^ composed by (existing, unchanged)
intelligence-platform/  (Stage 13 — IntelligenceService facade)
        ^ composed by (new, this stage)
enterprise-gateway/   (Stage 14 Phase 1 — EnterpriseGateway facade)
```

One-directional both hops, independently verified by three zero-blast-radius test suites (evidence-registry's, intelligence-platform's, and this stage's own) plus 12 new Python governance checks.

## 3. The "One X" principles this stage's modules satisfy

| Module | "One X" |
|---|---|
| `gateway-service.js` | **One Gateway** — `EnterpriseGateway`, the single aggregating facade. |
| `gateway-registry.js` | **One Service Registry** — `GatewayRegistry`, capability-name → handler, no hardcoded service wiring inside the registry itself (wiring lives in `gateway-service.js`'s composition). |
| `gateway-dispatcher.js` | **One dispatch path** — `GatewayDispatcher` is the only code that looks up the registry, checks authorization, and runs the middleware chain. |
| `gateway-context.js` | **One context shape** — `GatewayContext`, immutable, threaded through every stage. |
| `gateway-lifecycle.js` | **One lifecycle** — `GatewayLifecycle`, INIT → READY → STOPPED, one per gateway instance. |
| `gateway-metrics.js` | **One metrics instance** — `GatewayMetrics` never constructs its own `ServicePlatformMetrics`; see §5. |

## 4. `GatewayContext`

Immutable (frozen), matching this codebase's freeze-heavy convention. Fields: `correlationId` (auto-generated via `crypto.randomUUID()` if omitted), `caller` (`{id, kind}`), `capability`, `grantedCapabilities`, `environment`, `featureFlags`, `metadata`, `startedAt`. `with(patch)` returns a **new** frozen instance for a middleware stage to enrich context for downstream stages — `correlationId`/`startedAt` always carry forward unless explicitly overridden.

## 5. `GatewayRegistry` and capability handlers

`register(name, handler, {requiredCapabilities, version, description})` — `requiredCapabilities` defaults to `[name]` (secure by default). `createServiceMethodHandler(service, {allowedMethods})` is a generic adapter turning any multi-method service object into a `(context, method, ...args) => service[method](...args)` handler — this is the entire mechanism by which every EIG capability composes an existing `IntelligenceService` property with zero new business logic.

**The 8 pre-registered capabilities:**

| Capability | Delegates to |
|---|---|
| `evidence.lookup` | `platform.lookup` (`IntelligenceLookupService`) |
| `intelligence.query` | `platform.enterpriseQuery` (`EnterpriseQueryService`) |
| `intelligence.correlation` | `platform.correlation` (`IntelligenceCorrelationService`) |
| `intelligence.validation` | `platform.validation` (`IntelligenceValidationService`) |
| `intelligence.threatProfile` | `platform.threatIntelligence` (`ThreatIntelligenceService`) |
| `evidence.provenance` | `platform.provenance` (`EvidenceProvenanceEngine`) |
| `evidence.relationships` | `platform.relationshipResolution` — pass-through only, ADR-0010-gated |
| `platform.metrics` | `platform.metrics` (`IntelligenceMetricsService`) |

Authorization is capability-granular (8 names), not per-method (~40+) — a DI-boundary trust model (the caller is already-trusted in-process code), not a network ACL.

## 6. `GatewayDispatcher`

`dispatch({capability, method, args, caller, grantedCapabilities, environment, correlationId, metadata})`:
1. Registry lookup (`CapabilityNotRegisteredError` if unknown).
2. Build a `GatewayContext`.
3. Authorization check: `entry.requiredCapabilities` vs. `context.grantedCapabilities` (`CapabilityAuthorizationError`, naming what's missing, if unsatisfied).
4. Run the composed middleware chain around the resolved handler.
5. The whole call — steps 2-4 — is wrapped in the **shared** `ServicePlatformMetrics.timed("gateway.<capability>", ...)`.

## 7. `GatewayLifecycle`

Three states: `INIT → READY → STOPPED` (`STOPPED` terminal from either state). `EnterpriseGateway`'s constructor marks itself `READY` once capability registration completes; `dispatch()` is declared `async` specifically so its readiness check and its normal path are both uniformly promise-rejecting on failure (an inconsistency the test suite itself caught and this stage fixed — see the Completion Report).

## 8. Middleware pipeline

Six composable stages, onion-style (`composeGatewayMiddleware`), outermost first: **tracing** (correlation-id span logging — deliberately thin, no real exporter exists yet), **feature-flag evaluation** (resolves + records `EIG_ENABLED`, attaches flags to context — does **not** gate dispatch itself; see §9), **version compatibility** (no-ops unless the caller supplies `expectedContractVersion`/`targetContract`; reuses `checkContractCompatibility()` unchanged), **gateway-request validation** (structural only — `method` is a string, `args` is an array; evidence/intelligence *data* validation is out of scope here, see below), **audit logging** (bounded ring-buffer entry + one log line per call, always re-throws), **metrics-bridging** (innermost; for `intelligence.validation` specifically, bridges a non-throwing `{valid:false}` result into `ServicePlatformMetrics.recordValidationFailure()`, a method with zero prior callers before this bridge).

**Why gateway-request validation, not data validation:** all 8 Phase 1 capabilities are read-only. A generic middleware can't meaningfully schema-validate an evidence-shaped payload without the registry hardcoding per-capability knowledge (which would violate "no hardcoded service wiring"). Any future mutating capability inherits real evidence validation for free, transitively, the moment its handler calls through `EvidenceService`'s own mutating methods (which already validate before persisting).

## 9. In-process capability authorization — not network auth

`GatewayContext` carries caller-declared `grantedCapabilities`; the dispatcher checks them before invoking a handler. This is deliberately **not** a network-facing service-identity system: no scoped per-caller identity precedent exists anywhere in this codebase (confirmed by grep — only customer JWT/API-key auth and one blunt `ADMIN_SECRET` shared-secret admin gate exist), and since the gateway stays in-process (constructed directly by a caller in the same JS runtime, exactly like `scripts/intelligence_platform_snapshot.mjs` already does), there is no network hop and thus no auth gap for Phase 1 to fill. A real network-facing system is a separate, future, explicitly-authorized architectural event — `check_gateway_no_network_auth_scope_creep()` machine-enforces this boundary going forward, forbidding `fetch` handlers, `Request`/`Response` construction, `ADMIN_SECRET`, and JWT libraries anywhere in this directory.

**Correction found during this stage's own test run:** an earlier version of `featureFlagEvaluationMiddleware` also threw when `EIG_ENABLED` was false, as a "defense in depth" measure. This was inconsistent with `IntelligenceService`/`createIntelligencePlatform()`'s own precedent (flag-gated only at composition-root construction time, never re-checked per call) and made direct DI construction — an intentional, supported pattern this codebase uses throughout its own tests — surprising to use. Removed in favor of the one-gate precedent; the stage's own test suite caught this before it shipped.

## 10. Metrics — the property this brief calls out by name

See `TITAN_STAGE14_PERFORMANCE_BASELINE.md` and the Completion Report for the full "no duplicate metrics instance" enforcement (three independent layers: construction order, `metrics-sharing.test.js` identity assertions, `check_eig_metrics_no_duplicate_instance()`). `GatewayMetrics` wraps `platform.metrics` for `.sharedServiceMetrics` and owns exactly three genuinely-new counters (feature-flag evaluations, capability-authorization denials, middleware validation failures) plus a bounded audit-entry buffer — `snapshot()` returns `{registry, service, gateway}`.

## 11. Known gaps / deliberate Phase 1 scope limits

- Per-method (not just per-capability) authorization granularity — a real limitation of the DI-trust model chosen for Phase 1, not an oversight (~40+ registrations vs. 8 was judged too heavy a Phase 1 lift for a boundary where the caller is already-trusted in-process code).
- No `README.md` in this directory, following `intelligence-platform/`'s newer precedent (which also has none) rather than `evidence-registry/`'s older one (which does) — avoids creating a second "docstring says see README.md but none exists" instance of a pre-existing gap already present in `intelligence-platform/`.
- See `TITAN_STAGE14_COMPLETION_REPORT.md` §11 for the full list of what's deferred to a future phase.
