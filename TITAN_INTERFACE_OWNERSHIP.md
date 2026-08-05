# Project TITAN — Interface Ownership (Task 5)

**Status:** Derived from `TITAN_INTERFACE_REGISTRY.md`. Covers every interface with Single
Owner, Compatibility Layer, Migration Target, Consumer List, Deprecation Timeline — required
per Task 5. Only interfaces with something non-trivial to say in at least one of these five
columns are broken out individually; the ~30 uncontested-Canonical P-layer families (P16, P17,
P19, P21–P28, P32–P34, P36) share one summary row since their answer is identical across all of
them (per Task 5's own instruction to document decisions, not pad a table with repetition).

---

## Uncontested Canonical interfaces (summary row)

| Field | Value |
|---|---|
| **Interfaces** | P16, P17, P19, P21, P22, P23, P24 (referenced in prior discovery, not independently re-verified this stage), P26, P27, P28, P32, P33, P34, P36, plus admin/auth/payments/static-bundle surfaces |
| **Single Owner** | Intelligence Engineering (P-layers) / Platform SRE (admin, auth, payments, static bundles) |
| **Compatibility Layer** | None needed — no competing implementation exists for any of these |
| **Migration Target** | N/A — already canonical, no migration pending |
| **Consumer List** | See `TITAN_INTERFACE_REGISTRY.md` per-family; broadly: dashboards, customer-facing narrative, downstream P-layers, external partners per family |
| **Deprecation Timeline** | N/A |

---

## Contested or in-transition interfaces

### P25 Trust Score (`computeEnterpriseTrustScore`)

| Field | Value |
|---|---|
| Single Owner | Intelligence Engineering, designated canonical by ADR-0007 |
| Compatibility Layer | None required — already the most-consumed implementation; other systems migrate *to* it, it doesn't need an adapter *from* anything |
| Migration Target | N/A (is the target) |
| Consumer List | 13 files/functions: P26–P38 (9 handlers) + `p26_intelligence_excellence.py` + P37.3's `_confidenceAudit` + (post-migration) P18's `buildTrustIndicatorBlock` |
| Deprecation Timeline | N/A |

### P18 `buildEvidenceAttribution` / `computeTransparentConfidence`

| Field | Value |
|---|---|
| Single Owner | Intelligence Engineering — owns the migration, not permanent ownership of the deprecated logic |
| Compatibility Layer | `mapReliabilityCodeToDisplayGrade()` (ADR-0009, not yet built) bridges P20's A–F to P18's A–E display format |
| Migration Target | P20's `reliability_code` (source reliability) + P25's trust score (confidence) — per ADR-0009 and ADR-0007 respectively |
| Consumer List | `p19-handlers.js:561,651,700` (SOC/executive narrative) |
| Deprecation Timeline | Migration Roadmap Phase 4 (`TITAN_MIGRATION_ROADMAP.md`), gated on ADR-0009 approval + F→E mapping sign-off |

### P31 Relationship Graph

| Field | Value |
|---|---|
| Single Owner | Intelligence Engineering, designated target-canonical by ADR-0010 |
| Compatibility Layer | None built yet — required before blog's `api/_lib/threat-graph.js` or Python `KnowledgeGraph` can migrate to it |
| Migration Target | Persisted P31 (prerequisite work, DEBT-004, unestimated) |
| Consumer List | P31's own routes today; nothing currently migrates to it because it isn't persisted yet |
| Deprecation Timeline | Not started — blocked on persistence engineering estimate |

### `api-extensions.js` intel graph/relations (`data/ai/intel_graph.json`)

| Field | Value |
|---|---|
| Single Owner | **Undetermined — new finding this stage, not yet assigned.** Whatever pipeline generates `data/ai/intel_graph.json` was not identified in this stage's scope (candidate: one of the automated GENESIS/SOVEREIGN/OmniShield pipeline scripts visible in git history, not confirmed) |
| Compatibility Layer | None |
| Migration Target | Same as P31 above — once P31 is persisted and API-stable, this route should read from P31 rather than a separately-generated snapshot file, per ADR-0010's "collapse to one canonical relationship source" intent |
| Consumer List | Paid-tier customers via `/api/v1/intel/graph`, `/relations` |
| Deprecation Timeline | Not started — sequenced after P31 persistence, same as blog's graphs |

### Blog `api/_lib/threat-graph.js` + `campaign-engine.js`

| Field | Value |
|---|---|
| Single Owner | Blog/Vercel Engineering (de facto — no formal ownership document existed before this stage) |
| Compatibility Layer | None |
| Migration Target | Intel-platform's persisted P31, per ADR-0010's system-of-record precedent — **not decided as urgent**, since this is blog's only live relationship-graph capability and removing it before a replacement exists would remove live customer-facing functionality (`/api/v1/intel?action=graph` is a real, tier-gated, presumably revenue-relevant endpoint) |
| Consumer List | Blog's `/api/v1/intel` route, paid tiers |
| Deprecation Timeline | Not started — explicitly not recommended to start until P31's persisted replacement exists and is proven, given this is live revenue-adjacent functionality |

### Blog Python `KnowledgeGraph`

| Field | Value |
|---|---|
| Single Owner | Blog/EIOS Engineering |
| Compatibility Layer | None |
| Migration Target | Same as above, per ADR-0010 |
| Consumer List | Blog's report-generation pipeline (internal, not a live route) |
| Deprecation Timeline | Not started, same gating as above |

### TAXII dual path prefix (`/taxii/*` vs `/api/taxii/*`)

| Field | Value |
|---|---|
| Single Owner | Intelligence Engineering |
| Compatibility Layer | **Needed but not built** — if one path is to be canonical, the other needs a redirect/alias, not a silent removal |
| Migration Target | Undetermined — requires checking which path is documented for external TAXII partners today (not established this stage; flagged, not resolved) |
| Consumer List | External TAXII/STIX consumers — exact split between the two paths unknown, which is itself the risk (DEBT-014) |
| Deprecation Timeline | Not started — cannot start responsibly until consumer split is known, since this is an external-partner-facing surface where a wrong guess breaks real integrations |

### Archived `lib/api/*` (ADR-0013)

| Field | Value |
|---|---|
| Single Owner | Unassigned (DEBT-001) |
| Compatibility Layer | N/A — no live consumer to bridge from |
| Migration Target | N/A — Archive recommendation, not a migration |
| Consumer List | None |
| Deprecation Timeline | N/A (Archive, not Deprecate — see ADR-0013's terminology note) |

---

### The `api/v1/{intelligence,workbench,analysis,customer}/*` surface (DEBT-000)

| Field | Value |
|---|---|
| Single Owner | **None found — the single largest ownership gap in this report.** ~22 routes, ~18 engine files, real (likely) customer data, zero named owner anywhere in either repository's documentation |
| Compatibility Layer | None — no adapter exists between this surface and any of the P-layer-canonical systems ADR-0007/0008/0009/0010 designate |
| Migration Target | Undetermined — depends on whether this is retroactively legitimized as its own governed product surface or reconciled into the P-layer-canonical systems, a decision this report does not make |
| Consumer List | Unknown external consumer count — very likely real end users/customers given the customer-dashboard and purchase-history functionality found |
| Deprecation Timeline | **Not applicable and not recommended** — deprecating a live, revenue-adjacent customer-facing system without confirming impact first would itself be a production-stability risk, exactly the kind of hasty action this program's governing principles warn against |

## Interfaces with ownership genuinely undetermined by this stage

Per Task 5's requirement that "every API must have a single owner" — two items in this
registry do not yet have one, named explicitly rather than assigned arbitrarily:

1. **Whatever generates `data/ai/intel_graph.json`** — the pipeline was not identified this
   stage; assigning it an owner without knowing which script/team produces it would be a
   guess, not a decision. Flagged for Stage 8 to resolve as a prerequisite to acting on this
   interface's Migration Target.
2. **The TAXII dual-path question's canonical answer** — both paths have "Intelligence
   Engineering" as the team owner, but *which path is the one external partners should be told
   to use* is undetermined, which is the actually load-bearing ownership question here.

Both are logged in `TITAN_TECH_DEBT_REGISTER.md` (DEBT-013, DEBT-014) rather than resolved by
assumption.
