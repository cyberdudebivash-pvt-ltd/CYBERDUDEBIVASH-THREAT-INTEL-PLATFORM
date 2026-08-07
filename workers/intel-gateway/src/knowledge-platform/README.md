# Enterprise Intelligence Knowledge Platform (EIKP) — Project TITAN Stage 18

**This directory is not imported by `index.js` or any other production route. It has zero runtime
effect on live Cloudflare Worker traffic.** It exists as an additive composition layer over the
Stage 12-17 lineage (`evidence-registry/`, `intelligence-platform/`, `enterprise-gateway/`),
following that lineage's own unbroken "build it, test it, do not wire it into `index.js` without
separate authorization" convention (see `../evidence-registry/README.md` for where that convention
started, and `TITAN_STAGE17_READINESS_REPORT.md` Sec 3 for its most recent restatement).

## What this is

A Knowledge Object Layer, Navigation Service, Analyst/Executive presentation views, and a
Knowledge Quality validation framework — all composing **exactly one** dependency:
`intelligence-platform/intelligence-service.js`'s `IntelligenceService`, specifically its already-
public `lookup`, `correlation`, `provenance`, and `explainability` properties (Stage 12/13/17).

## What this is not

- **Not** a second Evidence Registry, Gateway, Correlation Engine, or Explainability Engine. Every
  Knowledge Object is built by calling those existing services and reshaping their output — no
  new storage, no new indexing, no re-derivation of anything those services already compute.
- **Not** wired into `item.evidence_chain` (P20) or any file in the architecturally separate
  P16-P38 handler stack. That stack has zero shared code with this lineage (established Stage 15,
  re-confirmed Stage 17/18) and is out of scope here.
- **Not** an API. No route in `index.js` references any file in this directory.
- **Not** a source of new confidence values. ADR-0007 (Canonical Confidence Framework) is
  Proposed, not Accepted (`docs/adr/0007-canonical-confidence-framework.md`). Every
  confidence-adjacent field this directory surfaces is read verbatim from
  `IntelligenceExplainabilityService`'s own verbatim passthrough — nothing here computes, weights,
  ranks, or propagates a confidence value. `check_no_confidence_computation_introduced_stage18()`
  (governance script) enforces this mechanically, mirroring Stage 17's identical check.

## Relationship to the Stage 8-17 lineage

```
evidence-registry/        (Stage 8, 10, 11, 12)  -- EvidenceRegistry, EvidenceService, Provenance, Query Engine
intelligence-platform/    (Stage 13, extended 17) -- IntelligenceService: .lookup .correlation .provenance .explainability
                                                       ├─ enterprise-gateway/    (Stage 14) -- EnterpriseGateway
                                                       └─ knowledge-platform/    (Stage 18, THIS DIRECTORY) -- KnowledgePlatform
```

`knowledge-platform/` is a **peer** of `enterprise-gateway/`, not a consumer of it and not a
dependency of it either. Both compose `IntelligenceService` independently via dependency
injection, one hop down. **`IntelligenceService` itself is not modified by this stage** —
attaching a `.knowledge` property to it the way Stage 17 attached `.explainability` was
considered and rejected: `knowledge-navigation.js` needs `intelligence-platform/
correlation-policy.js`'s `detectConflicts()`, so `intelligence-platform/intelligence-service.js`
importing this directory back would be a circular dependency (`intelligence-platform ->
knowledge-platform -> intelligence-platform`). Composing downward from `intelligence-platform/`
is fine (the same one-hop rule `enterprise-gateway/` already follows); composing upward from
`intelligence-platform/intelligence-service.js` into this directory is not, so this stage keeps
`KnowledgePlatform` external and constructs it from an already-built `IntelligenceService`
supplied by the caller (see `platform.js`'s `createKnowledgePlatform()`).

**Gateway integration (Phase 7) uses the Gateway's own existing, documented extension point
unchanged** — `EnterpriseGateway.registerCapability(name, handler, options)`, described in
`gateway-service.js` as "an extension point for a future capability beyond the 8 pre-registered."
A caller that has both a `gateway` (`enterprise-gateway/`) and a `knowledgePlatform`
(this directory) instance registers the five Phase 7 capabilities itself:

```js
import { createServiceMethodHandler } from "../enterprise-gateway/gateway-registry.js";

gateway.registerCapability("knowledge.object", createServiceMethodHandler(knowledgePlatform.object), { description: "KnowledgeObjectService" });
gateway.registerCapability("knowledge.navigation", createServiceMethodHandler(knowledgePlatform.navigation), { description: "KnowledgeNavigationService" });
gateway.registerCapability("knowledge.analystViews", createServiceMethodHandler(knowledgePlatform.analystViews), { description: "AnalystViewService" });
gateway.registerCapability("knowledge.executiveViews", createServiceMethodHandler(knowledgePlatform.executiveViews), { description: "ExecutiveViewService" });
gateway.registerCapability("knowledge.quality", createServiceMethodHandler(knowledgePlatform.quality), { description: "KnowledgeQualityService" });
```

This means **zero lines of `gateway-service.js` or `intelligence-service.js` are modified by
Stage 18** — both files, and every capability that existed before this stage, are completely
unaffected whether or not a caller chooses to register Knowledge Platform capabilities. See
`__tests__/gateway-integration.test.js` for this pattern exercised end to end through a real
`gateway.dispatch()` call.

## File layout

```
feature-flags.js        KP_FLAGS (Stage 18) -- same per-environment shape as EIG_FLAGS/EIPS_FLAGS
service-contracts.js     5 versioned internal contracts, mirrors intelligence-platform's pattern
knowledge-object.js      KnowledgeObjectService (Phase 2)
knowledge-navigation.js  KnowledgeNavigationService (Phase 3)
analyst-views.js         AnalystViewService (Phase 4)
executive-views.js       ExecutiveViewService (Phase 5)
knowledge-quality.js     Knowledge Quality Framework (Phase 6) -- pure functions, versioned
knowledge-platform.js    KnowledgePlatform facade -- composes the five above
__tests__/               node:test suite
```

## Running the tests

```
cd workers/intel-gateway/src/knowledge-platform
node --test
```

Zero new dependencies — uses Node's built-in `node:test`/`node:assert`, matching this platform's
established convention.

## The design rule that keeps this directory low-risk to extend

Same rule `evidence-registry/README.md` states for itself: every file here operates on the
documented public surface of `IntelligenceService` and its four composed properties — none of them
`import` a `pNN-handlers.js` file or `index.js`, and none of them reach into any lower layer's
private fields. Three mechanisms guard this:

1. `__tests__/zero-blast-radius.test.js` — nothing outside this directory references it (except
   the one documented Gateway hop, mirroring `intelligence-platform/`'s own `enterprise-gateway/`
   exception), and this directory never imports a `pNN-handlers.js` file or `index.js`.
2. `check_kp_files_present_and_isolated()` (governance, advisory).
3. `check_no_confidence_computation_introduced_stage18()` (governance, advisory) — the ADR-0007
   boundary, enforced the same way Stage 17 enforces its own.

## Extending this directory further

1. Read `TITAN_STAGE18_KNOWLEDGE_PLATFORM_REPORT.md` first — most extensions are additive to an
   existing view or navigation method, not a new top-level concept.
2. Add tests in `__tests__/` before considering a change done.
3. Never surface a NEW confidence-shaped computation. If a future stage genuinely needs one, that
   is gated on ADR-0007 Acceptance, not a decision this directory (or the stage that adds to it)
   can make unilaterally — see `TITAN_STAGE17_CORRELATION_EXPLAINABILITY_REPORT.md` Sec 12's
   Deferred Capability Register for the precedent.
