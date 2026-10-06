# Enterprise Intelligence Product & Delivery Platform (EIPDP) — Project TITAN Stage 19

**This directory is not imported by `index.js` or any other production route. It has zero runtime
effect on live Cloudflare Worker traffic.** It exists as an additive composition layer over the
Stage 8-18 lineage (`evidence-registry/`, `intelligence-platform/`, `enterprise-gateway/`,
`knowledge-platform/`), following that lineage's own unbroken "build it, test it, do not wire it
into `index.js` without separate authorization" convention (see `../evidence-registry/README.md`
for where that convention started, and `TITAN_STAGE18_KNOWLEDGE_PLATFORM_REPORT.md` Sec 5.3 for
its most recent restatement).

## What this is

An Intelligence Product Engine, reusable audience Profiles, deterministic Packaging, and a
Product Quality & Governance layer — all composing **exactly one** dependency:
`knowledge-platform/knowledge-platform.js`'s `KnowledgePlatform`, specifically its already-public
`object`, `analystViews`, and `executiveViews` properties (Stage 18).

This stage productizes existing platform capabilities into consistent, governed deliverables. It
does not create new intelligence engines.

## What this is not

- **Not** a second Evidence Registry, Gateway, Correlation Engine, Explainability Engine, or
  Knowledge Platform. Every Intelligence Product is assembled by calling those existing services
  and reshaping their output — no new storage, no new correlation/provenance/explanation logic.
- **Not** the Python dossier/report pipeline (`scripts/report_generator.py`,
  `agent/dynamic_dossier_engine.py`, `agent/dossier_quality_engine.py`,
  `scripts/generate_intel_reports.py`). That pipeline is CI-wired, independent, and unmodified by
  this stage — see `TITAN_STAGE19_READINESS_REPORT.md` Sec 2.3.
  `product-packaging.js`'s `"tactical_dossier"` package type is a structured JSON envelope over
  Knowledge Platform output, not the Python pipeline's HTML output; the two share no code, data
  model, or output format.
- **Not** an API. No route in `index.js` references any file in this directory.
- **Not** a source of new confidence values. ADR-0007 (Canonical Confidence Framework) is
  Proposed, not Accepted (`docs/adr/0007-canonical-confidence-framework.md`). Every
  confidence-adjacent field this directory surfaces (via `knowledgeObject.confidenceAsRecorded`)
  is read verbatim from Stage 18 — nothing here computes, weights, ranks, or propagates a
  confidence value.
- **Not** a public API, customer portal, SDK, or a place for authentication, authorization,
  billing, or multi-tenancy — all explicitly out of scope for this stage (Stage 20 preview only;
  not implemented here).

## Relationship to the Stage 8-18 lineage

```
evidence-registry/        (Stage 8, 10, 11, 12)  -- EvidenceRegistry, EvidenceService, Provenance, Query Engine
intelligence-platform/    (Stage 13, extended 17) -- IntelligenceService: .lookup .correlation .provenance .explainability
                                                       ├─ enterprise-gateway/    (Stage 14) -- EnterpriseGateway
                                                       └─ knowledge-platform/    (Stage 18) -- KnowledgePlatform: .object .navigation .analystViews .executiveViews .quality
                                                            └─ product-platform/    (Stage 19, THIS DIRECTORY) -- ProductPlatform: .engine .profiles .packaging .quality
```

`product-platform/` composes `KnowledgePlatform` via dependency injection, one hop down — the
same "one authorized hop into the layer directly below" rule every prior stage in this lineage
follows for itself. Nothing in `knowledge-platform/`, `intelligence-platform/`,
`evidence-registry/`, or `enterprise-gateway/` imports this directory back.

**One small, justified addition to `knowledge-platform/knowledge-platform.js`:** its constructor
now retains `this.metrics` (previously threaded into its five services but not exposed itself) so
this directory can share the exact same `ServicePlatformMetrics` instance rather than going
without metrics or constructing a second one — the same "exactly one shared instance" property
every layer below already guards. No existing property was renamed, removed, or changed shape; no
constructor signature changed. See `TITAN_STAGE19_READINESS_REPORT.md` Sec 3.1 for the before-change
verification that no test asserts a closed property set on `KnowledgePlatform`.

**Gateway integration (Phase 6) uses the Gateway's own existing, documented extension point
unchanged** — `EnterpriseGateway.registerCapability(name, handler, options)`, the same mechanism
Stage 18 used for itself. A caller that has both a `gateway` (`enterprise-gateway/`) and a
`productPlatform` (this directory) instance registers the Phase 6 capabilities itself:

```js
import { createServiceMethodHandler } from "../enterprise-gateway/gateway-registry.js";

gateway.registerCapability("product.engine", createServiceMethodHandler(productPlatform.engine), { description: "ProductEngineService" });
gateway.registerCapability("product.profiles", createServiceMethodHandler(productPlatform.profiles), { description: "ProductProfileService" });
gateway.registerCapability("product.packaging", createServiceMethodHandler(productPlatform.packaging), { description: "ProductPackagingService" });
gateway.registerCapability("product.quality", createServiceMethodHandler(productPlatform.quality), { description: "ProductQualityService" });
```

This means **zero lines of `gateway-service.js`, `intelligence-service.js`, or
`knowledge-platform.js`'s own service files are modified by Stage 19's Gateway integration** — see
`__tests__/gateway-integration.test.js` for this pattern exercised end to end through a real
`gateway.dispatch()` call.

## The product pipeline

```
ProductEngineService.assemble(evidenceUuid)
  -> { knowledgeObject, correlation, briefing }        (Phase 2 -- audience-agnostic assembly)

ProductProfileService.applyProfile(assembly, profileKey)
  -> { profileKey, profileName, <selected sections> }  (Phase 3 -- audience-shaped view, values unchanged)

ProductPackagingService.package(assembly, profiledView, packageType)
  -> { packageId, metadata, evidenceReferences, provenance,
       correlationSummary, explainability, intelligenceGaps, content }
                                                        (Phase 4 -- deterministic deliverable envelope)

ProductQualityService.evaluate(assembly, pkg, profileKey)
  -> { knowledgeObjectQuality, provenancePreservedInPackage,
       explainabilityIncludedInPackage, profileCompliance, packagingConsistency }
                                                        (Phase 5 -- governance validation)
```

Every package — regardless of which audience profile shaped its `content` — always carries the
full evidentiary backbone (`evidenceReferences`, `provenance`, `correlationSummary`,
`explainability`, `intelligenceGaps`) read from the unabridged `assembly`, never from the
(possibly narrower) `profiledView`. A profile like `executive_leadership`, which surfaces only the
`briefing` section as content, still ships with complete provenance and evidence references.

## Six audience profiles (Phase 3)

| Profile key | Sections included |
|---|---|
| `soc_analyst` | `knowledgeObject`, `correlation` |
| `threat_intelligence_analyst` | `knowledgeObject`, `correlation`, `briefing` |
| `executive_leadership` | `briefing` |
| `mssp_operations` | `knowledgeObject`, `correlation`, `briefing` |
| `vulnerability_management` | `knowledgeObject` |
| `incident_response` | `knowledgeObject`, `correlation`, `briefing` |

## Four package types (Phase 4)

`enterprise_threat_intelligence_report`, `tactical_dossier`, `executive_intelligence_briefing`,
`knowledge_summary` — see `product-packaging.js`'s `PRODUCT_PACKAGE_TYPES`. All four share the
identical envelope shape; the type is metadata (`packageId`/`packageType`), not a structural fork.

## File layout

```
feature-flags.js        PP_FLAGS (Stage 19) -- same per-environment shape as KP_FLAGS
service-contracts.js     4 versioned internal contracts, mirrors knowledge-platform's pattern
product-engine.js        ProductEngineService (Phase 2)
product-profiles.js      ProductProfileService (Phase 3)
product-packaging.js     ProductPackagingService (Phase 4)
product-quality.js       Product Quality & Governance framework (Phase 5) -- composes knowledge-quality.js
product-platform.js      ProductPlatform facade -- composes the four above
platform.js              createProductPlatform() -- feature-flagged factory
__tests__/               node:test suite
```

## Running the tests

```
cd workers/intel-gateway/src/product-platform
node --test
```

Zero new dependencies — uses Node's built-in `node:test`/`node:assert`, matching this platform's
established convention.

## The design rule that keeps this directory low-risk to extend

Same rule `evidence-registry/README.md` and `knowledge-platform/README.md` state for themselves:
every file here operates on the documented public surface of `KnowledgePlatform` and its three
composed properties (`object`, `analystViews`, `executiveViews`) — none of them `import` a
`pNN-handlers.js` file or `index.js`, and none of them reach past `knowledge-platform/` into
`intelligence-platform/`, `evidence-registry/`, or `enterprise-gateway/` directly. Three
mechanisms guard this:

1. `__tests__/zero-blast-radius.test.js` — nothing outside this directory references it (except
   the one documented Gateway hop, mirroring `knowledge-platform/`'s own `enterprise-gateway/`
   exception), and this directory never imports a `pNN-handlers.js` file or `index.js`.
2. `check_stage19_files_present_and_isolated()` (governance, advisory).
3. `check_no_confidence_computation_introduced_stage19()` (governance, advisory) — the ADR-0007
   boundary, enforced the same way Stage 17/18 enforce it.
4. `check_product_platform_no_python_pipeline_coupling()` (governance, advisory) — the Python
   pipeline boundary from `TITAN_STAGE19_READINESS_REPORT.md` Sec 2.3, made mechanically
   enforceable.

## Extending this directory further

1. Read `TITAN_STAGE19_PRODUCT_PLATFORM_REPORT.md` first — most extensions are additive to an
   existing profile or package type, not a new top-level concept.
2. Add tests in `__tests__/` before considering a change done.
3. Never surface a NEW confidence-shaped computation. If a future stage genuinely needs one, that
   is gated on ADR-0007 Acceptance, not a decision this directory (or the stage that adds to it)
   can make unilaterally.
4. Never import the Python dossier/report pipeline, and never shape this directory's output to
   require it — the two systems stay independent.
