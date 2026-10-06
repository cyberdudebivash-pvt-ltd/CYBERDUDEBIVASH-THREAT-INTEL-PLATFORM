# Commercial Gateway Readiness Report

**Project TITAN Stage 21 — Enterprise Intelligence Gateway Commercial Activation**
**Source of truth:** `commercial-catalog/commercial-readiness.js` (`buildCommercialReadinessReport()`)
**This document reports a live capture of that function's actual output** (`createCommercialGateway({environment:"testing"})`, 2026-08-07T13:20:05.790Z) — it is not hand-maintained data.

---

## 1. What this is

`buildCommercialReadinessReport({gateway, metrics})` reads `catalog.js` + live registry state (via
`gateway.describeAllCapabilities()`) + live metrics, and produces the structured readiness data
behind this document. It is the Phase 7 deliverable named in the audit doc §5. Calling it again at
any time reproduces (modulo `generatedAt` and any `observed` metrics accumulated since) the same
structure reported here — this document is a snapshot, not a duplicate of the underlying engine.

## 2. Top-level summary (live)

```json
{
  "catalogSize": 16,
  "gaCount": 5,
  "betaCount": 10,
  "blockedCount": 1
}
```

| Lifecycle | Count | Entries |
|---|---:|---|
| `ga` | 5 | Evidence Lookup, Threat & Entity Profile, Correlation Summary, Explainability Summary, Intelligence Validation Report |
| `beta` | 10 | all 10 new adapters (Evidence Provenance Summary, Knowledge Object/Navigation/Executive Briefing, Product Assembly/Profiled View/Package, MSSP Partner Package, Commercial Readiness/Explanation Summary) |
| `blocked-pending-wiring` | 1 | Relationship Summary (`evidence.relationships`) — real data requires composing with `relationship-framework/`; not activatable as-is |

## 3. Service health (19 entries, all registered)

Every one of the 16 catalog entries maps to a registry entry, and every mapped entry reports
`registered: true` — zero drift between catalog and live registry at the time of this snapshot.
(19 total registered capabilities vs. 16 catalog entries: the 3-entry gap is
`INTERNAL_ONLY_CAPABILITY_ANNOTATIONS` — `intelligence.query`, `evidence.provenance`,
`platform.metrics` — deliberately excluded from the catalog itself; see
`COMMERCIAL_SERVICE_CATALOG.md` §4.)

| ID | Lifecycle | Registered |
|---|---|---|
| evidence.lookup | ga | ✓ |
| intelligence.threatProfile | ga | ✓ |
| intelligence.correlation | ga | ✓ |
| evidence.relationships | blocked-pending-wiring | ✓ |
| intelligence.explainability | ga | ✓ |
| commercial.evidenceProvenanceSummary | beta | ✓ |
| intelligence.validation | ga | ✓ |
| commercial.knowledgeObject | beta | ✓ |
| commercial.knowledgeNavigation | beta | ✓ |
| commercial.knowledgeExecutiveBriefing | beta | ✓ |
| commercial.productAssembly | beta | ✓ |
| commercial.productProfiledView | beta | ✓ |
| commercial.productPackage | beta | ✓ |
| commercial.msspPartnerPackage | beta | ✓ |
| commercial.readinessSummary | beta | ✓ |
| commercial.explanationSummary | beta | ✓ |

## 4. Readiness by entry (full detail)

Each catalog entry's full readiness record — description, owner, dependencies, commercial value,
internal consumers, security level, visibility, lifecycle, expected latency budget, documentation
status, and classification tags — is reproduced verbatim in `COMMERCIAL_SERVICE_CATALOG.md` §3
(source-identical: both are read from the same `catalog.js`). This report's `entries[]` array adds
one field beyond the catalog's own shape: `observed` (metrics-derived latency/failure data once the
gateway has served live traffic — `null` in this snapshot, since it was captured immediately after
composition with no prior dispatch history).

## 5. Not yet commercially ready — explicit call-out

Per this document's own "no speculative wording" mandate:

- **`evidence.relationships` (Relationship Summary)** is the only catalog entry with lifecycle
  `blocked-pending-wiring`, not `ga`/`beta`. It must not be marketed or sold until composed with a
  real `relationship-framework/`-backed provider (ADR-0010, Stage 16). The catalog and this report
  both surface this status explicitly rather than omitting the entry or rounding it up to `beta`.
- **10 of 16 entries are `beta`** — appropriate for a first commercial activation; none have
  accumulated production traffic yet (`observed: null` throughout this snapshot).
- **`intelligence.validation`** has `documentationStatus: "partial"` — the only entry not fully
  documented; flagged here rather than silently left inconsistent with the other 15.

## 6. Reproducing this report

```js
import { createCommercialGateway } from "./workers/intel-gateway/src/commercial-catalog/platform.js";
import { buildCommercialReadinessReport } from "./workers/intel-gateway/src/commercial-catalog/commercial-readiness.js";

const result = createCommercialGateway({ environment: "testing" });
const report = buildCommercialReadinessReport({ gateway: result.gateway, metrics: result.commercialMetrics });
```

`commercial-catalog/__tests__/commercial-readiness.test.js` (7 tests, part of the 84-test
`commercial-catalog` suite — see `COMMERCIAL_GATEWAY_VALIDATION.md` §6) exercises this function
directly and is the CI-visible (via `node --test`) regression guard for its shape.
