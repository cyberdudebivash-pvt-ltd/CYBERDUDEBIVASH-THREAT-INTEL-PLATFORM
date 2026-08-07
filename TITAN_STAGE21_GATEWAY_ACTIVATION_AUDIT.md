# Project TITAN — Stage 21 Gateway Activation Audit

## Enterprise Intelligence Gateway Commercial Activation — Pre-Implementation Audit

**Date:** 2026-08-07
**Status:** Complete — implementation proceeds under this plan.

---

## 0. Resume-state correction (repository evidence overrides assumptions)

The continuation prompt that opened this session described Stage 21 as already having a
completed architecture audit, catalog, adapters, contracts, registry extension, metrics,
readiness publisher, composition root, and governance extensions, with three governance bugs
already found and fixed, and asked this session to resume immediately after those fixes without
repeating discovery.

**Repository evidence contradicts that premise.** Verified directly before writing any code:

- `git ls-remote --heads origin` has no `claude/titan-stage-21-continuation-jv8689` branch — it
  does not exist on the remote at all.
- The local branch of that name (present in this container) sits exactly at the Stage 20A merge
  commit (`5377be49`, PR #132) plus routine automated bot commits (Bug Hunter, Guardian, SENTINEL
  APEX advisory runs) — nothing Stage-21-shaped.
- Repo-wide search (`git grep`, `find`) for `commercial-catalog`, `commercial-adapters`,
  `service-contracts` (new), `commercial-metrics`, and `TITAN_STAGE21_*` finds zero matches on
  every branch, including `main`.

The prior session's Stage 21 work was performed in an ephemeral container and never committed, so
it did not survive. Per this program's own standing rule ("repository evidence overrides
assumptions," restated in the Stage 21 brief's own First Principle and Critical Execution Rules),
this session treats Stage 21 as a fresh implementation rather than a checkpoint resume, and
commits incrementally as it proceeds so partial progress survives if this session is interrupted
too. This correction is recorded here rather than silently reconciled, per this program's standing
"document discrepancies rather than silently resolving them" rule (governance script `main()`
trailer, verbatim).

---

## 1. Method

Four parallel read-only research passes plus direct verification of every file this stage
touches or composes over:

1. Evidence Registry + Intelligence Platform service inventory (the 9 capabilities already
   registered on the Gateway, and what each delegates to underneath).
2. Knowledge Platform (Stage 18) + Product Platform (Stage 19) service inventory, wiring status,
   and the reported "Executive Intelligence" duplication risk.
3. Gateway contract pattern, test conventions, and the zero-blast-radius enforcement mechanism.
4. Governance script structure (87 existing checks), ADR status, and CI wiring.

All findings below are file:line-cited and were independently re-verified by direct file reads
before being relied on for implementation decisions.

---

## 2. What already exists (Reuse Before Build — do not duplicate any of this)

### 2.1 The Gateway itself (`workers/intel-gateway/src/enterprise-gateway/`, Stage 14)

Not imported by `index.js` or any production route (confirmed: `grep -c "enterprise-gateway" index.js` = 0;
`index.js` also has zero references to `intelligence-platform/` or `evidence-registry/` — the
entire Stage 8→20A lineage is parallel to, and disconnected from, the live P16–P39 handler stack).

| File | Role |
|---|---|
| `gateway-service.js` | `EnterpriseGateway` facade. `_registerDefaultCapabilities()` pre-registers 9 capabilities (below) via `createServiceMethodHandler()` — a generic, zero-validation pass-through adapter. `registerCapability(name, handler, options)` is the existing, unmodified extension point. |
| `gateway-registry.js` | `GatewayRegistry`. `register(name, handler, {requiredCapabilities, version, description})` — **schema has no owner/consumers/securityClassification/visibility/lifecycle fields.** `describe()`/`describeAll()` (Stage 14 Phase 2) return safe metadata without the handler. |
| `gateway-dispatcher.js` | `GatewayDispatcher.dispatch()` — registry lookup → `GatewayContext` → authorization check → middleware chain → shared-metrics-timed handler call. The one dispatch path; new capabilities inherit it for free by registering into `GatewayRegistry`. |
| `gateway-context.js` | `GatewayContext` — immutable, frozen, `with(patch)` for enrichment. |
| `gateway-lifecycle.js` | `GatewayLifecycle` — INIT→READY→STOPPED. |
| `gateway-metrics.js` | `GatewayMetrics` — wraps `platform.metrics.sharedServiceMetrics` (no second `ServicePlatformMetrics` instance), owns 3 gateway-level counters + bounded audit ring buffer. |
| `gateway-middleware.js` | 6-stage onion pipeline: tracing, feature-flag eval, version compatibility, request validation, audit logging, metrics-bridging. |
| `service-contracts.js` | 4 frozen contracts (`GatewayServiceContract` v1.0.0, `MiddlewareContract` v1.0.0, `CapabilityRegistryContract` v1.1.0, `GatewayMetricsContract` v1.0.0), each `{name, version, source, methods, history}`. Reuses `isContractForwardCompatible()`/`checkContractCompatibility()` from `evidence-registry/service-contracts.js` unchanged (re-exported through `intelligence-platform/`). |
| `platform.js` | Composition root: `createEnterpriseGateway({environment, deps})` → `{enabled, gateway, environment, reason?}`. |
| `feature-flags.js` | `EIG_FLAGS` (dev/testing enabled, canary/production disabled), `resolveEigFlags()`. |

**The 9 pre-registered capabilities** (`gateway-service.js:59-90`), what each delegates to, and this
audit's classification recommendation:

| Capability | Delegates to (file:line) | Classification | Reasoning / caveats |
|---|---|---|---|
| `evidence.lookup` | `IntelligenceLookupService` → `evidence-registry/evidence-service.js:35` | Commercial + partner + AI-agent/MCP candidate | 9 of 12 lookup dimensions real; `byVendor`/`byProduct`/`byMalware` **throw** — exclude from any commercial contract until implemented. |
| `intelligence.query` | `EnterpriseQueryService` → `query-engine.js:22` | Internal (near-duplicate read surface) | Same underlying `EvidenceQueryEngine` as `evidence.lookup`; cataloging both as separate commercial products would violate Single Source of Truth. Not a separate catalog entry. |
| `intelligence.correlation` | `IntelligenceCorrelationService` → `correlation-engine.js:35` | Commercial + partner + SOC + AI-agent/MCP | `correlateByRelationship` inherits the NOT_WIRED caveat below. |
| `intelligence.validation` | `IntelligenceValidationService` → `evidence-service.js:168` | Internal-only, secondary partner candidate | Fits a future "submit intel, get a validation report" partner API; not a read product today. |
| `intelligence.threatProfile` | `ThreatIntelligenceService.getThreatProfile` | **Best commercial/partner candidate** + SOC + prime AI-agent/MCP tool | Single bounded call → one presentable business object. |
| `evidence.provenance` | `EvidenceProvenanceEngine` (6 lineage kinds) | Split | `getEvidenceLineage`/`getVersionLineage`/`getConfidenceLineage`/`getSourceLineage`/`getRelationshipLineage` = commercial candidate. **`getAuditLineage` = internal-only** (carries internal `actor` identity — must never reach a commercial adapter). |
| `evidence.relationships` | `RelationshipResolutionService` | Commercial/partner candidate **only once wired** | `NullRelationshipProvider` throws `NOT_WIRED` by default; real data requires composing with `relationship-framework/` (ADR-0010 Accepted, Stage 16). Catalog entry lifecycle = `blocked-pending-wiring`, not `ga`. |
| `platform.metrics` | `IntelligenceMetricsService` | Internal-only | Ops telemetry, not business content. |
| `intelligence.explainability` | `IntelligenceExplainabilityService` (Stage 17) | Flagship SOC + AI-agent + commercial/partner | No LLM, deterministic, bounded. **ADR-0007 (Canonical Confidence Framework) is Proposed, not Accepted** — confidence fields are surfaced verbatim only; must never be marketed as computed/weighted confidence scoring. |

**Not Gateway-exposed (correctly internal-only, unaffected by this stage):** `EvidenceService`'s
mutation/write path (`registerEvidence`, `updateEvidence`, `supersedeEvidence`, `archiveEvidence`,
`transitionLifecycle`) — the Gateway is read-only by construction; Stage 21 does not change that.

**Unresolved data-level gap, flagged not fixed (out of scope for this stage):**
`CanonicalEvidence` (`evidence-registry/entity.js:176-201`) already carries `visibility`
(`INTERNAL`/`CUSTOMER_FACING`/`RESTRICTED`) and `tlp_classification` fields, but **zero enforcement
of either exists** anywhere in `evidence-registry/*.js` or `intelligence-platform/*.js` outside
`entity.js`/`validation.js`/`serialization.js` — every lookup/query/correlation/provenance method
returns raw records regardless of these flags. This does not block Stage 21 (the Gateway stays
internal-only and unrouted; nothing built here becomes reachable by an actual external customer),
but it is a hard precondition for any *future* stage that would expose Gateway capabilities on a
live, customer-reachable route. Recorded here and in the Architecture Compliance Report as a
carried-forward risk, not silently worked around.

### 2.2 Knowledge Platform (`workers/intel-gateway/src/knowledge-platform/`, Stage 18) — unwired

Composes `IntelligenceService`'s already-public `lookup`/`correlation`/`provenance`/`explainability`
properties. Not imported by `index.js`, `gateway-service.js`, or `intelligence-service.js` (confirmed
by direct grep — zero matches in all three).

| Service : file:line | Key methods | Classification |
|---|---|---|
| `KnowledgeObjectService` `knowledge-object.js:30` | `build(uuid)` — reshapes `getEvidence()`+`explainEvidence()` into a 7-field Knowledge Object | MCP / AI-agent-capability |
| `KnowledgeNavigationService` `knowledge-navigation.js:31` | `relatedIntelligence`, `supportingEvidence`, `similarIntelligence`, `contradictoryEvidence`, `historicalIntelligence`, `collectionGaps` | SOC + MCP-capability |
| `AnalystViewService` `analyst-views.js:15` | `investigationView`, `correlationView`, `evidenceTimeline`, `confidenceContext`, `intelligenceGapView`, `collectionPriorityView` | SOC / portal-capability |
| `ExecutiveViewService` `executive-views.js:22` | `executiveBriefing(uuid)` — business/operational impact narrative, explicitly no score, every claim tagged `basis: "evidence"` or `"analyst_recommendation"` | Commercial-service candidate / portal |
| `KnowledgeQualityService` `knowledge-quality.js:116` | 6-rule structural QA over a Knowledge Object | Internal-only (governance/QA) |
| `KnowledgePlatform` / `createKnowledgePlatform()` `platform.js:24` | Composition root, flag-gated (`KP_FLAGS`) | Internal-only (plumbing) |

### 2.3 Product Platform (`workers/intel-gateway/src/product-platform/`, Stage 19) — unwired

Composes an already-constructed `KnowledgePlatform` only (one hop down). Not imported by `index.js`,
`gateway-service.js`, `intelligence-service.js`, or `knowledge-platform.js` (confirmed by direct grep).

| Service : file:line | Key methods (verified signatures) | Classification |
|---|---|---|
| `ProductEngineService` `product-engine.js:17` | `async assemble(evidenceUuid)` → `{found, evidenceUuid, knowledgeObject, correlation, briefing}` | Commercial-service candidate (productization backbone) |
| `ProductProfileService` `product-profiles.js` | `applyProfile(assembly, profileKey)` — **synchronous**, pure field selection over 6 named audience profiles (`PRODUCT_AUDIENCE_PROFILES`), no recompute | Spans SOC/commercial/partner — see profile table below |
| `ProductPackagingService` `product-packaging.js:27` | `async package(assembly, profiledView, packageType)` — **asynchronous**, one of 4 `PRODUCT_PACKAGE_TYPES`; evidentiary backbone always read from `assembly` (never the narrowed `profiledView`) | Commercial + partner-service candidate — the literal deliverable |
| `ProductQualityService` `product-quality.js:123` | Package-level governance, delegates to KP checks | Internal-only |
| `ProductPlatform` `product-platform.js:17` (`.engine`/`.profiles`/`.packaging`/`.quality`) / `createProductPlatform()` `platform.js:25` | Composition root, flag-gated (`PP_FLAGS`) | Internal-only (plumbing) |

**Existing profile → Stage 21 category mapping** (`product-profiles.js:17-56` — reused as-is, not
reinvented, per Reuse Before Build):

| Profile key | Category |
|---|---|
| `soc_analyst`, `incident_response` | SOC-capability |
| `threat_intelligence_analyst` | SOC + AI-agent-capability |
| `executive_leadership` | Commercial-service candidate / portal |
| `mssp_operations` | **Partner-service candidate** — profile description literally says "for a managed service provider operating on behalf of a client" |
| `vulnerability_management` | Internal-only / SOC-capability |

### 2.4 Commercial Quality Orchestrator (`p39-handlers.js` + `commercial_quality_orchestrator.py`, Stage 20A) — unwired, fully independent

`p39-handlers.js:64-67` imports only `p20/p21/p25/p26-handlers.js` — confirmed zero import of
`evidence-registry/`, `intelligence-platform/`, or `enterprise-gateway/` (its one textual match for
"intelligence-platform" is a documentation analogy in a comment, not an import).
`commercial_quality_orchestrator.py` reads only local JSON report files. **Two parallel,
non-composing commercial lineages exist in this repo today** — Stage 21 is the first work to bridge
them, and does so only through P39's already-exported pure functions (Reuse Before Build), never by
modifying P39 itself.

Relevant exports (`p39-handlers.js`, JS side; mirrored in `commercial_quality_orchestrator.py`):
`computeCommercialApplicability(item)`, `buildCommercialQualityView(item, feedContext)`,
`buildCommercialReadinessSummary(view)`, `buildCommercialExplanation(view)`,
`buildCommercialRecommendationLayer(view)`, `buildCommercialPublicationDecision(item, view, feedContext)`,
`buildCommercialReleaseDecision(view, publicationDecision)`.

Classification: **commercial-service candidate** — this is the literal "Commercial Readiness"
catalog entry the Stage 21 brief names by example.

**Distinct from, not a duplicate of:** `scripts/commercial_readiness_auditor.py` (feed-tier 0-100
scoring), `scripts/commercial_readiness_governor.py` (10 publication-mandate enforcement over feed
items), `scripts/p24_commercial_certification.py` (platform-wide release certification). All three
score/govern **data items or the release as a whole**; Stage 21's catalog/readiness concept
describes **Gateway services** (owner, dependencies, commercial value, consumers, security level,
latency, documentation status) — a different axis, verified by reading each script's header and
scoring dimensions. No duplication; both are cited in the Reuse Report as adjacent-but-distinct.

### 2.5 Pre-existing, unrelated defect noticed during this audit (out of scope, not fixed here)

`p19-handlers.js:452 buildExecutiveBlock()` and `p20-handlers.js:445 buildP20ExecutiveBlock()` are
both live (`index.js:913,979`), both render a section with the identical heading `EXECUTIVE
INTELLIGENCE BRIEF`, and both independently compute business/financial/regulatory impact from the
same fields with different numbers ($4M+ vs $4.45M) — a real, pre-existing duplication in the live
P16–P39 stack, unrelated to the Gateway lineage this stage touches. Recorded here per this
program's "surface issues, don't silently fix out-of-scope ones" convention; not remediated in this
stage (would violate Minimal Change Surface / Zero Unnecessary Modification against a system Stage
21 has no mandate to touch). Recommended as a future stage candidate.

To avoid adding to the confusion, this stage's catalog entry for `ExecutiveViewService.executiveBriefing()`
is named **"Knowledge Platform Executive Briefing"**, not "Executive Intelligence [Brief/Summary]" —
explicitly disambiguated from the live P19/P20 heading.

### 2.6 Contracts, tests, and governance conventions to mirror exactly

- **Contract shape** (`enterprise-gateway/service-contracts.js:21-111`): frozen plain object
  `{name, version, source, methods: [...], history: [{version, change, backwardCompatibleWithPrevious}]}`.
  No JSON Schema, no per-contract `validate()`. `checkContractCompatibility()`/`isContractForwardCompatible()`
  (defined once in `evidence-registry/service-contracts.js:40-62`, generic over any `{history, version}`
  shape) are reused unchanged — never reimplemented.
- **Test framework**: `node:test` + `node:assert/strict`, zero external deps. Run via
  `cd workers/intel-gateway/src/enterprise-gateway && node --test` (not wired into CI; CI runs only
  the Python governance script).
- **Zero-blast-radius mechanism** (`enterprise-gateway/__tests__/zero-blast-radius.test.js:50,94-108`):
  a filesystem sweep asserting the literal string `"enterprise-gateway"` appears nowhere under `src/`
  except inside `EIG_DIR` itself or a named `AUTHORIZED_CONSUMER_DIRS` entry (currently
  `relationship-framework/`, `knowledge-platform/`, `product-platform/`). A second assertion confirms
  `index.js` never references any `gateway-*.js` filename. A third confirms EIG production files
  never import a `pNN-handlers.js`/`index.js` file directly, and reach `evidence-registry/` only
  through `intelligence-platform/` (the "one authorized hop" rule).
- **Composition pattern, already precedented and explicitly anticipated by the governance script's
  own docstrings** (`check_knowledge_platform_still_unwired()`, `check_product_platform_still_unwired()`):
  each new platform-level layer gets its own sibling directory under `workers/intel-gateway/src/`,
  depends on an *already-constructed* upstream instance via dependency injection (never importing
  its upstream's own composition-root module from production code — only from `__tests__/`
  integration tests, which is why `AUTHORIZED_CONSUMER_DIRS` needed each new sibling added), and is
  wired into the Gateway "via `registerCapability()` from a composition script" — `gateway-service.js`
  itself is never modified to know about the new layer.
- **Governance script** (`scripts/titan_architecture_governance_check.py`, 3,577 lines, 87 checks):
  every check is `def check_X() -> list[str]` (empty = clean), all called from `main()` in file
  order into one `all_findings` list, advisory-only (CI step `STAGE 5.9.4` always exits 0). Existing
  idioms this stage's Phase 6 checks must instance, not reinvent: `*_files_present_and_isolated`,
  `check_no_duplicate_*`, duplicate-contract + version-drift pairs, `*_still_unwired` (the
  "unauthorized routing" idiom), `check_gateway_bypass_new_direct_composition_consumers` (the
  adapter-bypass-adjacent idiom). No CI YAML change is needed — the single existing step already
  runs the whole script unconditionally.
- **ADRs** (`docs/adr/`): 0008 (Evidence Framework), 0010 (Relationship Graph Ownership), 0011
  (Evidence Lifecycle), 0012 (API Versioning & Interface Governance) are **Accepted**. 0007
  (Canonical Confidence Framework) and 0009 (Source Reliability) are **Proposed, not binding** — no
  new compute/score/weight/rank-confidence function may be introduced by this stage. ADR-0012
  governs *public, path-prefixed* (`/api/v1/`) API versioning and explicitly does not apply to an
  internal-only surface with "no external API commitment" — this stage's `internal/v1` contract
  namespace is a deliberately distinct concept, named to avoid exactly the label-collision hazard
  ADR-0012 itself flags between intel-platform's and blog's unrelated `/api/v1/` surfaces.

---

## 3. Stage 21 architectural placement decision

Following the unbroken Stage 14/16/18/19 precedent, Stage 21 introduces
**`workers/intel-gateway/src/commercial-catalog/`** as a new sibling directory. It differs from
every prior stage in one structural respect, stated explicitly rather than left implicit: prior
stages each added exactly one hop below the previous single-file lineage
(evidence-registry → intelligence-platform → enterprise-gateway → knowledge-platform → product-platform).
Stage 21's own charter is to compose **across** that entire lineage plus the independent P39
lineage simultaneously (its Pre-Implementation Audit explicitly names Evidence Registry, Evidence
Services, Knowledge Platform, Product Platform, P39, and Gateway as joint inputs) — a deliberate,
charter-justified cross-cutting layer, not an accidental violation of the one-hop convention.

Zero-blast-radius is preserved by construction:

- `commercial-catalog/` production files depend on **already-constructed** `EnterpriseGateway`,
  `KnowledgePlatform`, and `ProductPlatform` instances via dependency injection — mirroring
  knowledge-platform/product-platform's own pattern exactly — and import P39's already-exported
  pure functions directly (P39 has no composition-root class to inject).
- `enterprise-gateway/gateway-service.js`, `index.js`, `knowledge-platform/knowledge-platform.js`,
  and `product-platform/product-platform.js` are **not modified** to know about
  `commercial-catalog/` — wiring happens one level up, via the existing `registerCapability()`
  extension point, exactly as the governance script's own docstrings anticipate.
- `commercial-catalog/__tests__/` integration/smoke tests (not production files) import the
  upstream composition roots (`enterprise-gateway/platform.js`, `knowledge-platform/platform.js`,
  `product-platform/platform.js`) to prove end-to-end wiring — the same reason
  `AUTHORIZED_CONSUMER_DIRS` needed `knowledge-platform`/`product-platform`/`relationship-framework`
  added when each was built. `commercial-catalog/` needs the identical addition, for the identical
  reason (Phase 4/6 implementation detail, not a new pattern).
- Nothing in `enterprise-gateway/`, `knowledge-platform/`, `product-platform/`, or `p39-handlers.js`
  is modified to import `commercial-catalog/` back — verified by a new zero-blast-radius test
  mirroring the existing mechanism, and by new governance checks (Phase 6).
- Not wired into `index.js` or any live route. The Gateway remains the sole (internal-only)
  commercial entry point, per this stage's own acceptance criteria.

### 3.1 Two small, justified additions to existing Gateway files (the only production files this stage modifies outside the new directory)

Both mirror the exact precedent Stage 14 Phase 2 set for itself (the `describe()`/`describeAll()`
addition, `CapabilityRegistryContract` 1.0.0→1.1.0, additive, `backwardCompatibleWithPrevious: true`)
and both are compatible per ADR-0012's own Compatibility Rules table ("Add a new field to a
response → Yes … `version_introduced` tag recommended").

1. **`gateway-registry.js`**: `register()`'s `options` gains 5 new optional fields (`owner`,
   `consumers`, `securityClassification`, `visibility`, `lifecycle`), defaulted so all 9 existing
   registrations are byte-for-byte unaffected; `describe()`/`describeAll()` surface them; a new
   `annotate(name, patch)` method allows attaching this metadata to an *already-registered*
   capability without re-registering (needed to classify the 9 existing capabilities, since
   `register()` throws `DuplicateCapabilityError` on a second call for the same name).
   `CapabilityRegistryContract` bumps 1.1.0→1.2.0 with a new history entry.
2. **`gateway-service.js`**: `EnterpriseGateway` gains `describeCapability(name)`,
   `describeAllCapabilities()`, and `annotateCapability(name, patch)` — thin passthroughs to the
   registry additions above, mirroring the existing `registerCapability()` passthrough exactly.
   `GatewayServiceContract` bumps 1.0.0→1.1.0.

No other existing file in `enterprise-gateway/`, `knowledge-platform/`, `product-platform/`, or
`p39-handlers.js` is modified by this stage.

---

## 4. Commercial Service Catalog — classification summary

16 catalog entries (Phase 1 deliverable, full detail in `COMMERCIAL_SERVICE_CATALOG.md`), derived
only from verified, currently-existing methods — no aspirational entries. Deliberately narrower
than the Stage 21 brief's illustrative example list where an example (e.g. "IOC Lookup", "CVE
Intelligence", "Campaign Summary") turns out to be a parameter value of an existing bounded call
(`getThreatProfile(dimension, value)`, `findEvidence().byCVE/byThreatActor/byCampaign/byIOC`) rather
than a distinct method — cataloging each parameter as its own "service" would duplicate a single
canonical implementation under multiple names, violating Single Source of Truth.

| # | Catalog entry | Source capability/method | Category | Lifecycle |
|---|---|---|---|---|
| 1 | Evidence Lookup | `evidence.lookup` (existing) | Commercial, partner, AI-agent/MCP | ga (9/12 dimensions) |
| 2 | Threat & Entity Profile | `intelligence.threatProfile` (existing) | Commercial, partner, SOC, AI-agent/MCP | ga |
| 3 | Correlation Summary | `intelligence.correlation` (existing) | Commercial, partner, SOC, AI-agent/MCP | ga |
| 4 | Relationship Summary | `evidence.relationships` (existing) | Commercial, partner (pending) | blocked-pending-wiring |
| 5 | Explainability Summary | `intelligence.explainability` (existing) | Commercial, partner, SOC, AI-agent | ga (ADR-0007-limited) |
| 6 | Evidence Provenance Summary | `evidence.provenance` (existing, minus audit lineage) | Commercial, partner | ga |
| 7 | Intelligence Validation Report | `intelligence.validation` (existing) | Partner (secondary), internal | ga |
| 8 | Knowledge Object Summary | `knowledgePlatform.object.build` (new adapter) | AI-agent/MCP | beta |
| 9 | Knowledge Navigation | `knowledgePlatform.navigation.*` (new adapter) | SOC, MCP | beta |
| 10 | Knowledge Platform Executive Briefing | `knowledgePlatform.executiveViews.executiveBriefing` (new adapter) | Commercial, portal | beta |
| 11 | Product Assembly | `productPlatform.engine.assemble` (new adapter) | Commercial | beta |
| 12 | Audience-Profiled Product View | `productPlatform.profiles.applyProfile` (new adapter) | Commercial, SOC | beta |
| 13 | Commercial Report Package | `productPlatform.packaging.package` (new adapter) | Commercial, partner | beta |
| 14 | MSSP Partner Package | `productPlatform.profiles`+`packaging` with `mssp_operations` profile (new adapter) | **Partner** | beta |
| 15 | Commercial Readiness Summary | P39 `buildCommercialQualityView`/`buildCommercialReadinessSummary` (new adapter) | Commercial | beta |
| 16 | Commercial Explanation | P39 `buildCommercialExplanation`/`buildCommercialRecommendationLayer` (new adapter) | Commercial | beta |

Internal-only capabilities (`intelligence.query`, `platform.metrics`, `evidence.provenance`'s audit
lineage, `KnowledgeQualityService`, `ProductQualityService`) are annotated in the registry
(`visibility: "internal"`) but deliberately **excluded** from the catalog — the catalog is a list of
commercial/partner/portal/SOC/AI-agent/MCP candidates, not a list of every registry entry.

---

## 5. Phase-by-phase implementation plan

1. **Catalog** (`commercial-catalog/catalog.js`) — the 16-entry table above as frozen data.
2. **Adapters** (`commercial-catalog/commercial-adapters.js`) — one real `GatewayCapabilityHandler`
   per new (non-existing-capability) catalog entry: validates `method`/`args`, calls through the
   correct platform method(s) via DI, maps output into a stable envelope, excludes/redacts
   internal-only fields (audit-lineage `actor`, etc.). Registered via the existing
   `gateway.registerCapability()` — never a new dispatch mechanism.
3. **Contracts** (`commercial-catalog/service-contracts.js`) — `internal/v1`-namespaced, mirroring
   `enterprise-gateway/service-contracts.js`'s exact shape, reusing the same compatibility
   functions.
4. **Registry extension** — the two additive changes in §3.1.
5. **Observability** (`commercial-catalog/commercial-metrics.js`) — wraps the existing shared
   `ServicePlatformMetrics` (via `gateway.platform.metrics.sharedServiceMetrics`, reached through
   the Gateway instance already injected) plus `GatewayMetrics`; adds adapter invocation counts,
   latency, and failure classification. No second metrics instance.
6. **Governance** — new Stage 21 checks in `titan_architecture_governance_check.py`, instancing the
   existing idioms (`*_files_present_and_isolated`, `check_no_duplicate_*`, contract version drift,
   `*_still_unwired`/unauthorized-routing) rather than inventing new idioms.
7. **Commercial readiness publisher** (`commercial-catalog/commercial-readiness.js`) — reads
   `catalog.js` + live metrics, produces the structured readiness data behind
   `COMMERCIAL_GATEWAY_READINESS.md`.
8. **Tests** — `node:test` suite mirroring the established per-file convention, plus a new
   `zero-blast-radius.test.js` for `commercial-catalog/` and the one-line addition to
   `enterprise-gateway/__tests__/zero-blast-radius.test.js`'s `AUTHORIZED_CONSUMER_DIRS`.
9. **Validation** — governance, full `node --test` runs, Python regression, P33 certification,
   measured (not estimated) performance.

No changes to `index.js`, any `pNN-handlers.js` engine (other than reading P39's already-exported
pure functions), any CI workflow YAML, or any D1/KV/R2 schema.
