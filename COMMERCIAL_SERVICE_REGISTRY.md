# Commercial Service Registry

**Project TITAN Stage 21 — Enterprise Intelligence Gateway Commercial Activation**
**Source of truth:** `enterprise-gateway/gateway-registry.js` (`GatewayRegistry`, the one and only
capability registry) + `commercial-catalog/platform.js` (`wireCommercialCapabilities()`)
**Registry snapshot below captured from a live `describeAllCapabilities()` call, 2026-08-07**

---

## 1. The registry is not duplicated

Stage 21 introduces **zero new registry classes**. `commercial-catalog/` has no `GatewayRegistry`
of its own — every commercial capability is registered into the same, single
`enterprise-gateway/gateway-registry.js` `GatewayRegistry` instance the 9 Stage 14–17 capabilities
already use, through the same unmodified `registerCapability()` extension point. Confirmed by
direct repository search: `class GatewayRegistry` appears in exactly one file
(`enterprise-gateway/gateway-registry.js`), and `governance check_no_duplicate_enterprise_gateway`
(pre-existing, unmodified) re-verifies this on every governance run.

## 2. What Stage 21 added to the registry (additive only)

Two small, justified additions to existing Gateway files — the *only* production files this stage
modifies outside its own new `commercial-catalog/` directory:

| File | Addition | Compatibility |
|---|---|---|
| `gateway-registry.js` | `register()`'s `options` gains 5 new optional fields (`owner`, `consumers`, `securityClassification`, `visibility`, `lifecycle`), all defaulted so the 9 existing registrations are byte-for-byte unaffected. `describe()`/`describeAll()` now surface them. New `annotate(name, patch)` method attaches this metadata to an *already-registered* capability without re-registering it (`register()` throws `DuplicateCapabilityError` on a second call for the same name). `CapabilityRegistryContract` bumps `1.1.0` → `1.2.0`, new history entry. | Additive; `backwardCompatibleWithPrevious: true` |
| `gateway-service.js` | `EnterpriseGateway` gains `describeCapability(name)`, `describeAllCapabilities()`, `annotateCapability(name, patch)` — thin passthroughs to the registry additions above, mirroring the existing `registerCapability()` passthrough exactly. `GatewayServiceContract` bumps `1.0.0` → `1.1.0`. | Additive; `backwardCompatibleWithPrevious: true` |

Both mirror the exact precedent Stage 14 Phase 2 already set for itself (the original
`describe()`/`describeAll()` addition). No other file in `enterprise-gateway/`,
`knowledge-platform/`, `product-platform/`, or `p39-handlers.js` is modified.

## 3. Registry contents (19 capabilities, live snapshot)

9 pre-Stage-21 registrations (unchanged shape, now annotated) + 10 Stage 21 registrations = **19**,
confirmed by a live `createCommercialGateway({environment:"testing"}).gateway.describeAllCapabilities().length`
call.

| Capability | Registered (stage) | Visibility | Security | Lifecycle |
|---|---|---|---|---|
| `evidence.lookup` | pre-existing (14), annotated | commercial | standard | ga |
| `intelligence.query` | pre-existing (14), annotated | **internal** | **internal** | internal-only |
| `intelligence.correlation` | pre-existing (14), annotated | commercial | standard | ga |
| `intelligence.validation` | pre-existing (14), annotated | internal | standard | ga |
| `intelligence.threatProfile` | pre-existing (14), annotated | commercial | standard | ga |
| `evidence.provenance` | pre-existing (14), annotated | **internal** | **restricted** | internal-only |
| `evidence.relationships` | pre-existing (14), annotated | commercial | standard | blocked-pending-wiring |
| `platform.metrics` | pre-existing (14), annotated | **internal** | **internal** | internal-only |
| `intelligence.explainability` | pre-existing (17), annotated | commercial | standard | ga |
| `commercial.evidenceProvenanceSummary` | **new (21)** | commercial | **restricted** | beta |
| `commercial.knowledgeObject` | **new (21)** | commercial | standard | beta |
| `commercial.knowledgeNavigation` | **new (21)** | commercial | standard | beta |
| `commercial.knowledgeExecutiveBriefing` | **new (21)** | commercial | standard | beta |
| `commercial.productAssembly` | **new (21)** | commercial | standard | beta |
| `commercial.productProfiledView` | **new (21)** | commercial | standard | beta |
| `commercial.productPackage` | **new (21)** | commercial | standard | beta |
| `commercial.msspPartnerPackage` | **new (21)** | **partner** | standard | beta |
| `commercial.readinessSummary` | **new (21)** | commercial | standard | beta |
| `commercial.explanationSummary` | **new (21)** | commercial | standard | beta |

All 19 entries report `registered: true` in `buildCommercialReadinessReport()`'s `serviceHealth`
array — zero drift between the catalog and the live registry.

## 4. Registration path (single, verified)

`wireCommercialCapabilities({gateway, knowledgePlatform, productPlatform, commercialMetrics})` in
`commercial-catalog/platform.js` is the **only** call site in the repository that registers a
`commercial.*` capability — confirmed by a repository-wide grep for
`registerCapability(` outside `__tests__/`, and mechanically re-verified on every governance run by
the new `check_commercial_catalog_no_adapter_bypass` check. It:

1. Iterates `listNewAdapterEntries()` (the 10 `newAdapter: true` catalog rows).
2. Looks up the matching factory in `ADAPTER_FACTORIES` (throws loudly — "catalog.js and
   commercial-adapters.js/platform.js have drifted" — if catalog and factories ever fall out of
   sync, rather than silently skipping).
3. Wraps the handler with `CommercialMetrics.wrapWithFailureClassification()` for failure-reason
   observability.
4. Registers via `gateway.registerCapability(entry.id, handler, {description, owner, consumers,
   securityClassification, visibility, lifecycle})`.
5. Annotates the 6 existing-capability catalog entries + 3 internal-only capabilities via
   `gateway.annotateCapability()` — no re-registration, no duplication.

Partial wiring is supported by design: if `knowledgePlatform`/`productPlatform` is not supplied,
their adapters are skipped (not thrown) — `result.wiring.skipped` lists them. In the live snapshot
above (both platforms composed), `skipped` is empty and all 10 register successfully.

## 5. Not registered, not routed

`gateway-service.js`'s `_registerDefaultCapabilities()` is never modified to know about
`commercial-catalog/` — wiring happens one level up, exactly as the governance script's own
pre-existing docstrings for `check_knowledge_platform_still_unwired()`/
`check_product_platform_still_unwired()` anticipate ("wired via `registerCapability()` from a
composition script"). `index.js` is unmodified (byte-identical to `origin/main`, confirmed by direct
diff) and has zero references to `commercial-catalog`, `wireCommercialCapabilities`, or
`createCommercialGateway` — mechanically re-verified by `check_commercial_catalog_still_unwired`.
The Gateway remains the sole, internal-only commercial entry point.
