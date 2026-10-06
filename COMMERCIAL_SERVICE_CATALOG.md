# Commercial Service Catalog

**Project TITAN Stage 21 — Enterprise Intelligence Gateway Commercial Activation**
**Source of truth:** `workers/intel-gateway/src/commercial-catalog/catalog.js` (`COMMERCIAL_SERVICE_CATALOG`, 16 frozen entries)
**Generated from:** live `describeAllCapabilities()`/`buildCommercialReadinessReport()` output, captured 2026-08-07

---

## 1. What this is

Every catalog entry is derived from a **currently-existing, verified method** — no aspirational
entries, and no entry duplicates another existing capability under a different name (Single
Source of Truth). 6 entries classify an already-registered Gateway capability in place
(`gatewayCapability` set, `newAdapter: false`); 10 entries register a brand-new capability
(`newAdapter: true`, implemented in `commercial-adapters.js`). See
`TITAN_STAGE21_GATEWAY_ACTIVATION_AUDIT.md` §4 for the full classification rationale and the
entries deliberately excluded (e.g. `intelligence.query`, whose read surface duplicates
`evidence.lookup`'s underlying engine).

| Metric | Count |
|---|---|
| Total catalog entries | 16 |
| GA lifecycle | 5 |
| Beta lifecycle | 10 |
| Blocked-pending-wiring | 1 |
| New adapters (Stage 21) | 10 |
| Existing-capability classifications | 6 |

## 2. Catalog

| # | ID | Name | Category | Lifecycle | Latency budget | Adapter type |
|---|---|---|---|---|---|---|
| 1 | `evidence.lookup` | Evidence Lookup | commercial, partner, ai-agent, mcp | ga | 250ms | existing capability |
| 2 | `intelligence.threatProfile` | Threat & Entity Profile | commercial, partner, soc, ai-agent, mcp | ga | 400ms | existing capability |
| 3 | `intelligence.correlation` | Correlation Summary | commercial, partner, soc, ai-agent, mcp | ga | 400ms | existing capability |
| 4 | `evidence.relationships` | Relationship Summary | commercial, partner, soc, ai-agent, mcp | blocked-pending-wiring | 400ms | existing capability |
| 5 | `intelligence.explainability` | Explainability Summary | commercial, partner, soc, ai-agent | ga | 400ms | existing capability |
| 6 | `commercial.evidenceProvenanceSummary` | Evidence Provenance Summary | commercial, partner | beta | 300ms | **new adapter** |
| 7 | `intelligence.validation` | Intelligence Validation Report | partner | ga | 300ms | existing capability |
| 8 | `commercial.knowledgeObject` | Knowledge Object Summary | ai-agent, mcp | beta | 500ms | **new adapter** |
| 9 | `commercial.knowledgeNavigation` | Knowledge Navigation | soc, mcp | beta | 500ms | **new adapter** |
| 10 | `commercial.knowledgeExecutiveBriefing` | Knowledge Platform Executive Briefing | commercial, portal | beta | 600ms | **new adapter** |
| 11 | `commercial.productAssembly` | Product Assembly | commercial | beta | 700ms | **new adapter** |
| 12 | `commercial.productProfiledView` | Audience-Profiled Product View | commercial, soc | beta | 700ms | **new adapter** |
| 13 | `commercial.productPackage` | Commercial Report Package | commercial, partner | beta | 900ms | **new adapter** |
| 14 | `commercial.msspPartnerPackage` | MSSP Partner Package | **partner** | beta | 900ms | **new adapter** |
| 15 | `commercial.readinessSummary` | Commercial Readiness Summary | commercial | beta | 200ms | **new adapter** |
| 16 | `commercial.explanationSummary` | Commercial Explanation | commercial | beta | 200ms | **new adapter** |

## 3. Per-entry detail

### 3.1 Existing-capability classifications (6)

These entries annotate an already-registered Gateway capability (via `gateway.annotateCapability()`,
Stage 21's registry addition) — they do not re-register or wrap it a second time.

**`evidence.lookup` — Evidence Lookup**
Unified single/multi-entity evidence lookup (`getEvidence`/`findEvidence` and 9 of 12 lookup
dimensions). `byVendor`/`byProduct`/`byMalware` are documented gaps (throw) and are excluded from
the commercial contract. Owner: Intelligence Platform (Stage 13). Dependency:
`intelligence-platform/intelligence-service.js`.

**`intelligence.threatProfile` — Threat & Entity Profile**
Single bounded call composing lookup + confidence aggregation + a 10-record provenance sample for
one dimension/value pair into one presentable business object. The strongest single-call
commercial/partner product in the catalog. Owner: Intelligence Platform (Stage 13).

**`intelligence.correlation` — Correlation Summary**
Cross-entity correlation and confidence/source aggregation. Owner: Intelligence Platform
(Stage 13). Internal consumer: `knowledge-platform/knowledge-navigation.js` (upstream, unmodified).

**`evidence.relationships` — Relationship Summary**
Entity-to-related-entity graph edges. `NullRelationshipProvider` throws `NOT_WIRED` by default —
real data requires composing with the relationship graph framework (Stage 16, ADR-0010 Accepted).
Catalogued for completeness; lifecycle is `blocked-pending-wiring`, **not** `ga` — do not market as
ready.

**`intelligence.explainability` — Explainability Summary**
Deterministic Analyst Reasoning Object (summary, supporting/contradictory evidence, provenance,
collection gaps, `confidenceAsRecorded` surfaced verbatim, policy). No LLM. ADR-0007 (Canonical
Confidence Framework) is Proposed, not Accepted — confidence fields are verbatim passthrough only,
never computed/weighted. Owner: Intelligence Platform (Stage 17).

**`intelligence.validation` — Intelligence Validation Report**
Schema and referential-integrity validation (`validateEvidence`, `validateBatch`,
`validateIntelligenceBundle`). Fits a future MSSP/data-contribution partner "submit intel, get a
validation report" flow. `documentationStatus: "partial"` — the only entry not fully documented.

### 3.2 New adapters (10) — `commercial-adapters.js`

Each is a real `GatewayCapabilityHandler` registered via the Gateway's existing, unmodified
`registerCapability()` — every one inherits `GatewayDispatcher`'s authorization check, middleware
chain, and shared-metrics-timed dispatch for free, exactly like the 9 pre-Stage-21 capabilities. No
new dispatch mechanism.

**`commercial.evidenceProvenanceSummary` — Evidence Provenance Summary**
5 of `evidence.provenance`'s 6 lineage views (evidence/version/confidence/source/relationship
lineage). A new, narrower adapter — not a reclassification of `evidence.provenance` itself, which
stays registered exactly as-is (all 6 methods) and is separately annotated internal-only.
`getAuditLineage` (carries internal actor identity) is excluded via `createServiceMethodHandler()`'s
existing `allowedMethods` option — real dispatch-boundary enforcement, not a documentation-only
caveat. `securityClassification: "restricted"`.

**`commercial.knowledgeObject` — Knowledge Object Summary**
Reshapes evidence lookup + explainability into a 7-field Knowledge Object
(`KnowledgeObjectService.build`). Deterministic, single-entity JSON in/out. Ideal AI-agent/MCP
tool-call shape.

**`commercial.knowledgeNavigation` — Knowledge Navigation**
6 analyst pivoting primitives (`relatedIntelligence`, `supportingEvidence`, `similarIntelligence`,
`contradictoryEvidence`, `historicalIntelligence`, `collectionGaps`).

**`commercial.knowledgeExecutiveBriefing` — Knowledge Platform Executive Briefing**
Business/operational impact narrative composed from a Knowledge Object — every statement
basis-tagged (`evidence` vs. `analyst_recommendation`), no computed score. Deliberately named
distinctly from the live P19/P20 "EXECUTIVE INTELLIGENCE BRIEF" heading (a pre-existing, unrelated
duplication noted in the audit doc §2.5, out of scope for this stage) — this is a different system,
not the same one under a new name.

**`commercial.productAssembly` — Product Assembly**
Bundles Knowledge Object + correlation view + executive briefing into one Product Assembly per
evidence record (`ProductEngineService.assemble`). The productization backbone every packaged
deliverable below is built from.

**`commercial.productProfiledView` — Audience-Profiled Product View**
Selects one of 6 named audience profiles (`soc_analyst`, `incident_response`,
`threat_intelligence_analyst`, `executive_leadership`, `mssp_operations`,
`vulnerability_management`) over an already-assembled product. Pure field selection — never
recomputes.

**`commercial.productPackage` — Commercial Report Package**
Deterministic packaging envelope, one of 4 package types
(`enterprise_threat_intelligence_report`, `tactical_dossier`, `executive_intelligence_briefing`,
`knowledge_summary`). Evidentiary backbone always read from the full assembly, never the narrowed
profiled view.

**`commercial.msspPartnerPackage` — MSSP Partner Package**
Commercial Report Package pinned to the `mssp_operations` profile — not caller-selectable. The
only catalog entry explicitly scoped to a reselling/managed-service partner
(`visibility: "partner"`).

**`commercial.readinessSummary` — Commercial Readiness Summary**
P39 Commercial Quality Orchestrator's applicability + quality view + readiness summary for one feed
item (`computeCommercialApplicability`, `buildCommercialQualityView`,
`buildCommercialReadinessSummary`) — the literal "Commercial Readiness" example this stage's brief
names. Operates on a flat feed-item shape (P16–P38's own data model), not a `CanonicalEvidence`
`evidenceUuid` — a different data model from every adapter above, called through P39's
already-exported pure functions unchanged.

**`commercial.explanationSummary` — Commercial Explanation**
P39's human-readable explanation and recommendation layer (`buildCommercialExplanation`,
`buildCommercialRecommendationLayer`).

## 4. Internal-only annotations (not catalog entries)

Three of the 9 pre-Stage-21 capabilities are neither a catalog entry nor superseded by a narrower
Stage 21 adapter of their own — still annotated for registry completeness
(`INTERNAL_ONLY_CAPABILITY_ANNOTATIONS` in `catalog.js`):

| Capability | Reason |
|---|---|
| `intelligence.query` | Read surface duplicates `evidence.lookup`'s underlying `EvidenceQueryEngine`; a second catalog entry would violate Single Source of Truth. |
| `evidence.provenance` | Superseded for commercial purposes by the narrower, `getAuditLineage`-excluding `commercial.evidenceProvenanceSummary`; the full 6-method capability remains internal-only. |
| `platform.metrics` | Ops telemetry, not business content. |

## 5. Deliberately excluded from the catalog

`ExecutiveViewService`'s quality/QA methods and both platforms' composition roots
(`KnowledgePlatform`, `ProductPlatform`) are internal plumbing/governance, not commercial products,
and are not catalog entries.

---
*Reuse note: this document describes data already defined in `catalog.js`; it does not introduce a second catalog. Regenerate the live sections (§1, live registry counts) from `describeAllCapabilities()`/`buildCommercialReadinessReport()` rather than hand-editing counts if the catalog changes.*
