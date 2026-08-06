# Project TITAN — Technical Debt Register

**Status:** Canonical TITAN backlog, per this task's Task 5. Items are drawn from this stage's
validation (`TITAN_STAGE6_VALIDATION.md`), the five ADRs' own Risks sections, and prior-stage
discovery documents' unresolved findings. This register does not duplicate items already fully
closed (e.g., Stage 4's `ai_confidence` fixes) — only open items appear.

Priority is ordered within each severity band by blast radius and how many other items depend
on it, not strictly by discovery date.

---

## CRITICAL

### DEBT-000 / AR-000 — RESOLVED (downgraded from Critical to Low) — second CTI platform surface in the blog repo confirmed NOT live

**Status: Resolved 2026-08-05, Stage 8.** Originally raised in Stage 7 as "undocumented,
very-likely-live second CTI platform." Renamed AR-000 by Stage 8's task framing. Direct HTTP
verification against production (`TITAN_STAGE8_VERIFICATION_REPORT.md`,
`TITAN_AR000_RESOLUTION.md`) found 21 of the 22 flagged routes return Vercel's platform-level
`NOT_FOUND`, byte-identical to a deliberately-nonexistent baseline path — **not deployed, not
reachable, not a production competitor to the canonical confidence/evidence/relationship
systems.** Only `api/v1/newsletter.js` is confirmed live, and it is an unrelated, low-stakes
email-signup endpoint.

| Field | Value |
|---|---|
| Severity | **Downgraded: Critical → Low.** The blocking fear (live, undocumented, traffic-serving duplicate architecture) did not materialize. What remains is documentation hygiene, not an active risk |
| Risk (residual) | Repository contains ~21 files' worth of substantially-engineered, unreachable code overlapping confidence/evidence/relationship territory. Low risk today (nothing calls it); moderate risk if someone later makes it reachable (a Vercel config change, a new route file re-exposing it) without first checking this register |
| Owner | Still unknown — the code's existence is unexplained (WIP never promoted? config accident? something else?). Recommended: blog engineering confirms via Vercel dashboard/build logs per `TITAN_AR000_RESOLUTION.md`'s three candidate explanations, none confirmable from outside |
| Affected Systems | `api/v1/{intelligence,workbench,analysis,customer,products,quality,reports,detections,ioc}/*` (21 files), the `api/_lib/` engine cluster they alone import |
| Blocking Status | **No longer blocking.** ADR-0007, ADR-0008, ADR-0009 all carry a Stage 8 "Revision 2" marking them ready for human Acceptance review |
| Recommended Resolution | Due-diligence follow-up, not urgent: confirm root cause via Vercel dashboard access; either wire the code up properly with its own ADR, or archive it with a correction note (same pattern as ADR-0013 for `lib/`) |
| Implementation Priority | Low — downgraded from Highest. See DEBT-000B below for the one genuinely new high-priority item this verification pass produced |

### DEBT-000B — R1 vs. R6 (retitled Stage 9 Phase 1, was "R1 vs. R3"): two live-or-live-adjacent, independently-computed relationship graphs in the same intel-platform repository

**Update, Stage 9 Phase 1:** Retitled from "R1 vs. R3" — DEBT-013's producer trace found R3
(`api-extensions.js`) is a thin reader with no independent graph-computation logic of its own;
the actual second implementation competing with P31/R1 is **R6**
(`core/intelligence/enrichment_graph.py`), which R3 merely exposes via a Cloudflare R2 storage
snapshot. The reconciliation question this item tracks is unchanged in spirit (two
same-repository, same-team, uncoordinated "what's related to this" computations) but the
technical target moves from "converge two JS files" to "decide R1 vs. a substantially more
capable Python engine, and resolve whether that engine even runs in production" — see DEBT-017.

| Field | Value |
|---|---|
| Severity | **Critical** — the highest-priority actionable item this register now contains, promoted here specifically because AR-000's resolution freed up attention for it |
| Risk | `p31-handlers.js` (`_buildGraph`, rebuilt per-request, no persistence) and `core/intelligence/enrichment_graph.py` (`IOCEnrichmentGraph` — persisted, OSINT-enriched, STIX-exporting, functionally more capable than P31) are **both real implementations in the same repository, same team**, answering the same "what's related to this item" question from two different, uncoordinated code paths. R6's output reaches customers via R3 (`/api/v1/intel/graph` → 403, confirmed live, tier-gated) — but R6's own production execution is unconfirmed (DEBT-017), so the "two live graphs" framing needs that caveat: P31 is confirmed live end-to-end, R6's live-ness is confirmed only up to "code exists and would work," not "definitely executes on a schedule" |
| Owner | Intelligence Engineering (owns both — this is the same team failing to coordinate with itself, not a cross-team or cross-repo issue) |
| Affected Systems | `p31-handlers.js`, `api-extensions.js`, `core/intelligence/enrichment_graph.py`, `core/orchestrator.py`, `core/pipeline/stages.py` |
| Blocking Status | Blocking ADR-0010's full resolution (Revision 3 names this explicitly) — but unlike the cross-repo R1-vs-R2/R4 question, this one requires no negotiation with another team, only internal prioritization |
| Recommended Resolution | Resolve DEBT-017 first (confirm R6's actual execution status); then make an explicit R1-vs-R6 call — either adopt R6 as R1's long-sought persistence layer (it already exports a Worker-compatible snapshot shape) or formally deprecate R6 in favor of building persistence natively into R1, rather than leaving both running uncoordinated |
| Implementation Priority | **Highest actionable item in this register** — same-repo, same-team, no external dependency, but the DEBT-017 prerequisite must close first or any decision here risks being made on stale assumptions about what actually runs |

**Update, Stage 9 Phase 2:** Re-reading `scripts/threat_graph_engine.py` (one of Phase 1's 16
long-tail files, previously classified only as "production long-tail," not weighted for its
architectural significance) in this phase's ownership-decision context found it feeds
**`/api/graph/{nodes,edges,pivot}`** — a live, Free/Pro/Enterprise/MSSP-tiered, monetized public
API surface, confirmed via its own preceding comment block in `sentinel-blogger.yml` ("uploaded
to R2 by Stage 3.5 and served by the Worker"). This is a **fourth** independent "give me the
graph" implementation with real commercial exposure that Phase 1's per-file table did not flag
as competing with R1/R6 for ownership. Elevated to **R8** in
`TITAN_STAGE9_PHASE2_ARCHITECTURE_PLAN.md` Task 2B. **This item's title and scope are updated
accordingly: the reconciliation question is R1 vs. R6 vs. R8, not a two-way question.** R8 is
explicitly the highest-commercial-risk item of the three (real paying traffic today) and is
deliberately excluded from `TITAN_GRAPH_MIGRATION_BLUEPRINT.md`'s first authorized migration
phase for exactly that reason — see that document's "Deferred, not forgotten" table.

### DEBT-001 — `lib/` RC1 initiative: disposition undecided |

### DEBT-001 — `lib/` RC1 initiative: disposition undecided

| Field | Value |
|---|---|
| Severity | Critical (not because it's causing active harm — it isn't, having zero consumers — but because ~12,600 lines of self-certified, "Accepted"-ADR-backed code with no owner decision is the largest single ungoverned surface found in this program) |
| Risk | A future engineer discovers `lib/` and reasonably assumes "Accepted" ADRs and "RC1 Certification: ARCHITECTURE COMPLETE ✓" mean this is live or load-bearing, and either builds on it (creating a real dependency on unintegrated code) or duplicates it a third time without realizing two implementations already exist |
| Owner | Unassigned — requires blog repo's architecture-review authority to claim |
| Affected Systems | `cyberdudebivash-blog`: `lib/intelligence`, `lib/reporting`, `lib/ioc`, `lib/detection`, `lib/governance`, `lib/api`, `docs/adr/0001-0002`, `docs/architecture/*` |
| Blocking Status | Not blocking any TITAN Stage 6 ADR (all five exclude it explicitly on zero-consumer grounds) — but blocking a clean answer to "what is this platform's architecture" for any future contributor who encounters it |
| Recommended Resolution | Architecture-review decision among three options: (a) integrate — assign it a real deployment target and connect it to at least one production consumer; (b) formally shelve — mark its ADRs and README with a "Status: Shelved, not integrated" notice so future readers aren't misled by "Accepted"/"RC1 Complete" language, without deleting the code; (c) delete, after confirming no other internal work references it. This register does not recommend which. |
| Implementation Priority | High — not for code changes (there are none to make yet), but for the decision itself, since every month undecided increases the chance someone builds on it by mistake |

### DEBT-002 — `.github/workflows/architecture.yml` is documented as existing and enforcing, but does not exist

| Field | Value |
|---|---|
| Severity | Critical (documentation making a false claim about CI enforcement is worse than the underlying gap, per this program's own standing precedent) |
| Risk | Anyone trusting `docs/architecture/README.md`'s "Enforced in CI" claim believes circular-dependency and Phase 2A isolation checks are running on every change to `lib/`. None are. |
| Owner | Same as DEBT-001 (same subsystem) |
| Affected Systems | `cyberdudebivash-blog`, `lib/` tree |
| Blocking Status | Not blocking any TITAN deliverable |
| Recommended Resolution | Either implement the workflow as documented, or correct `docs/architecture/README.md` to state the checks are not currently enforced — tied to DEBT-001's resolution, since building CI for code nobody has decided to keep is premature |
| Implementation Priority | Tied to DEBT-001 |

---

## HIGH

### DEBT-003 — Three-way (now four/five-way) source-reliability and evidence-presence fragmentation

| Field | Value |
|---|---|
| Severity | High |
| Risk | Same item can present different reliability/evidence signals to different audiences (SOC narrative vs. trust score vs. fleet audits) with no cross-check — the concrete example `EVIDENCE_ENGINE_DISCOVERY.md` §3 and `TITAN_STAGE6_VALIDATION.md` §3 both document |
| Owner | Intelligence Engineering (P18/P20/P25/P35/P37 owner) |
| Affected Systems | `p18-handlers.js`, `p20-handlers.js`, `p25-handlers.js`, `p35-handlers.js`, `p37-handlers.js` |
| Blocking Status | Not blocking — ADR-0008/0009 define the target state; this item tracks the actual migration work (`TITAN_MIGRATION_ROADMAP.md` Phase 4) plus the still-unaddressed P37/P35 heuristic consolidation those ADRs flagged but didn't schedule |
| Recommended Resolution | Ship Migration Roadmap Phase 4 (P18→P20), then a follow-up (not yet phased) consolidating P23's gate, P37's `_hasEvidence`, and P35's `handleP35Evidence` onto one shared evidence-presence check reading the extended P20 schema |
| Implementation Priority | High — scheduled as Phase 4; the P23/P37/P35 consolidation follow-up is unscheduled and should be picked up in Stage 7 planning |

### DEBT-004 — P31 relationship graph has no persistence layer

| Field | Value |
|---|---|
| Severity | High |
| Risk | Blocks ADR-0010's target state entirely; blocks any future Evidence-node-in-graph work; blocks Knowledge Graph readiness (see `TITAN_IMPLEMENTATION_READINESS.md`) |
| Owner | Intelligence Engineering (P31 owner) |
| Affected Systems | `p31-handlers.js` |
| Blocking Status | **Blocking** — Knowledge Graph implementation readiness is marked Blocked specifically on this item |
| Recommended Resolution | Scope and estimate a persistence approach (JSON-backed, matching R2's proven no-DB-dependency pattern per ADR-0010, or an alternative if Cloudflare Workers constraints favor one) as a dedicated Stage 7+ work item |
| Implementation Priority | High — required before ADR-0010's migration can proceed past its current "target decided, not yet actionable" state |

### DEBT-005 — A–F to A–E letter-scale mismatch (P20 vs. P18) has no reviewed resolution yet

| Field | Value |
|---|---|
| Severity | High (customer-visible narrative text risk, per ADR-0009's own Risks table) |
| Risk | The proposed F→E collapse could understate severity for the worst-graded sources in customer-facing SOC/executive narrative if adopted without explicit review |
| Owner | Platform Governance Lead + Chief Threat Intelligence Architect (joint sign-off required per ADR-0009) |
| Affected Systems | `p18-handlers.js`, `p19-handlers.js` (narrative rendering) |
| Blocking Status | Blocking ADR-0009 Migration Strategy Phase 4 specifically (not the ADR's approval as a whole) |
| Recommended Resolution | Explicit reviewer decision between the proposed F→E collapse and the six-grade S2 display alternative, coordinated with commercial/CS per the customer-visible-change risk |
| Implementation Priority | High, gates Migration Roadmap Phase 4 |

---

## MEDIUM

### DEBT-006 — `evidence_uuid` / `content_hash` backfill coverage for pre-existing items

| Field | Value |
|---|---|
| Severity | Medium |
| Risk | Two classes of Evidence records (with and without Integrity fields) persist indefinitely if backfill is never scheduled |
| Owner | Intelligence Engineering (P20 owner) |
| Affected Systems | `p20-handlers.js`, ingestion pipeline |
| Blocking Status | Not blocking — Phase 3 ships without requiring backfill |
| Recommended Resolution | Track backfill coverage as a named metric, same pattern as P38 gate G19's existing "Evidence Chain Coverage" | 
| Implementation Priority | Medium — revisit once Phase 3 ships and real coverage numbers exist |

### DEBT-007 — Two independent 6-role "operational intelligence by role" systems (pre-existing, blog repo)

| Field | Value |
|---|---|
| Severity | Medium |
| Risk | `authority_transformer.py`'s Executive Decision Center and EIOS Layer 5's audience templates don't match each other or any external proposed role list — named in `platform/open-issues.md` Issue 15, not a TITAN Stage 6 finding, included here because it's structurally the same fragmentation category this program tracks |
| Owner | Blog/EIOS Engineering |
| Affected Systems | `authority_transformer.py`, `Sentinel-APEX/eios/layer-05*` |
| Blocking Status | Not blocking any TITAN ADR |
| Recommended Resolution | Out of Project TITAN's current scope (confidence/evidence specifically) — logged here for cross-program visibility, ownership remains with whoever picks up Issue 15's "explicitly staged for a future sprint" item |
| Implementation Priority | Medium, not a TITAN Stage 6/7 dependency |

### DEBT-008 — Confidence: 3-level enum vs. 5-level prose vs. 4-tag convention vs. 9-category Provenance model (pre-existing, blog repo, `Sentinel-APEX/eios/`)

| Field | Value |
|---|---|
| Severity | Medium |
| Risk | Named in `platform/open-issues.md` Issue 15 as "not yet consolidated" | 
| Owner | Blog/EIOS Engineering |
| Affected Systems | `Sentinel-APEX/eios/layer-02*`, quality gate code |
| Blocking Status | Not blocking any TITAN Stage 6 ADR — this is internal to the blog's EIOS layer, distinct from the cross-repo A1–A8 fragmentation ADR-0007 resolves |
| Recommended Resolution | Blog-repo-internal consolidation, out of this stage's cross-repo scope; candidate for a future ADR-0012+ if it's judged to need one |
| Implementation Priority | Low-Medium, tracked for visibility only |

---

## LOW

### DEBT-009 — Marketing `ai_confidence` constant (99.9) never reconciled with engineering values

| Field | Value |
|---|---|
| Severity | Low (deliberate scope exclusion, not a defect) |
| Risk | Minimal — customer-facing marketing copy, not an engineering signal path; risk is reputational/consistency, not correctness |
| Owner | Marketing/Commercial, not Engineering |
| Affected Systems | `apex_marketing_matrix.py`, `.github/workflows/syndicate.yml` |
| Blocking Status | Not blocking |
| Recommended Resolution | A business decision on whether 99.9% should track any real engineering signal — explicitly not an engineering-consolidation task, per Stage 4's own finding |
| Implementation Priority | Low |

### DEBT-010 — P37/P35 "has evidence" heuristics not yet consolidated onto canonical schema

Cross-reference: this is the unscheduled half of DEBT-003, split out because its priority is
lower (fleet-level reporting accuracy, not per-item customer-facing output) than the P18/P20
migration.

| Field | Value |
|---|---|
| Severity | Low |
| Risk | Fleet-level enrichment/evidence-density reporting may undercount evidence for items whose evidence lives in fields these two heuristics don't check (they already disagree with each other on field sets — see `TITAN_STAGE6_VALIDATION.md` §3) |
| Owner | Intelligence Engineering (P35/P37 owner) |
| Affected Systems | `p35-handlers.js`, `p37-handlers.js` |
| Blocking Status | Not blocking |
| Recommended Resolution | Fold into the DEBT-003 follow-up once P20's schema extension (Phase 3) ships |
| Implementation Priority | Low, sequenced behind Phase 3 |

---

### DEBT-011 — CLAUDE.md's "CI STAGE NUMBERING" table is stale (documentation drift, not code drift)

| Field | Value |
|---|---|
| Severity | Low-Medium (governance-file accuracy, not a production defect) |
| Risk | CLAUDE.md states P34–P38's CI stage mapping "was not located... at time of writing" and suggests "Next available: STAGE 3.99." Direct inspection of `.github/workflows/sentinel-blogger.yml` (this stage, while placing the CI governance advisory check) found P35–P38 already mapped as **STAGE 4.00–4.03**, plus STAGE 4.04 (schema mirror drift check), STAGE 4.1, STAGE 5.8.5, and STAGE 5.9–5.9.3 (the true terminal gates, `if: always()`, hard-fail). STAGE 3.99 is not actually the next available slot — it would land chronologically before stages that already exist past it in file order. This CI governance advisory check was placed after the true last stage (5.9.3) instead, and this discrepancy is logged here rather than silently used or silently corrected in CLAUDE.md itself. |
| Owner | Whoever holds edit authority over CLAUDE.md (governance-file owner, not a Project TITAN decision) |
| Affected Systems | `CLAUDE.md` (documentation only — no code path affected) |
| Blocking Status | Not blocking — did not block placement of `TITAN_CI_GOVERNANCE.md`'s new stage, which used the empirically-verified slot instead of the documented one |
| Recommended Resolution | Update CLAUDE.md's CI STAGE NUMBERING table to reflect STAGE 4.00–4.04, 4.1, 5.8.5, 5.9–5.9.3 as they actually exist, and correct "Next available" accordingly. Out of this stage's authority to do unilaterally — CLAUDE.md is this repository's own supreme-authority governance document; changing it is deliberately not bundled into a Stage 6 documentation pass. |
| Implementation Priority | Low — cosmetic/accuracy fix, not schedule-critical, but cheap to fix once someone with the right authority reviews it |

### DEBT-012 — `_computeConfidenceGraph` (P29) partially reinvents dimensions ADR-0007 already assigns elsewhere

| Field | Value |
|---|---|
| Severity | Medium (found via this stage's own CI governance tooling, after ADR-0007's first draft — see `TITAN_STAGE6_VALIDATION.md` §4) |
| Risk | `p29-handlers.js:155`'s confidence-graph visualization correctly delegates 2 of 7 dimensions to canonical engines (P20, P26) but independently computes Source, Detection, IOC, Attribution, and Executive Confidence from raw fields with their own thresholds — plausibly overlapping P25's existing "IOC Operational Quality" and "MITRE ATT&CK Coverage" dimensions, among others, without reading them |
| Owner | Intelligence Engineering (P29 owner) |
| Affected Systems | `p29-handlers.js` (`_computeConfidenceGraph`, `buildP29ConfidenceGraphBlock`) |
| Blocking Status | Not blocking — this function has real production use (an API/dashboard visualization), unlike A8/A9; consolidating it requires care not to change what the graph visually shows without review |
| Recommended Resolution | Dimension-by-dimension comparison against A1 (P25)'s twelve dimensions; replace matches with reads from A1, keep any genuinely novel dimension (e.g., "Detection Confidence" from `detection_bundle` format coverage has no obvious A1 equivalent and may be legitimately new) |
| Implementation Priority | Medium — not scheduled in `TITAN_MIGRATION_ROADMAP.md`'s six phases; candidate for Stage 7+ planning once someone does the dimension-by-dimension read |

### DEBT-013 — Relationship-graph fragmentation (superseded in part by DEBT-000B; `intel_graph.json` producer now identified, execution trigger unconfirmed)

**Update, Stage 8:** Live verification confirmed 3 of the 4 candidates named here are actually
live (P31, `api-extensions.js`'s R2-snapshot reader, blog's `threat-graph.js`); the 4th
(blog's Python `KnowledgeGraph`) has no HTTP surface to verify (pipeline-internal, as
originally noted). The same-repository P31-vs-`api-extensions.js` conflict is now tracked as
**DEBT-000B** (promoted to Critical, since it's the most actionable). This entry remains open
specifically for the still-unidentified `data/ai/intel_graph.json` producer.

**Update, Stage 9 Phase 1:** Producer identified with high confidence by tracing actual
execution paths, not comments: `core/intelligence/enrichment_graph.py` (`IOCEnrichmentGraph`,
newly catalogued as ADR-0010 R6 — not the blog's `KnowledgeGraph` at all, correcting a factual
error in ADR-0010 Revision 2) → `core/orchestrator.py`'s `R2AIExportStage` → Cloudflare R2
storage, key `data/ai/intel_graph.json` → `api-extensions.js`. See
`TITAN_STAGE9_PHASE1_GRAPH_DISCOVERY_REPORT.md` Task 4 and ADR-0010 Revision 3 for the full
trace. **This does not fully close the item**: no `.github/workflows/*.yml` file was found to
invoke `core/orchestrator.py`, so while the producer's *identity* is now certain, its
*execution* in production is not — tracked separately as DEBT-017 given the distinct
commercial-risk shape (a live, tier-gated, paying-customer route with unconfirmed data
freshness). DEBT-000B is retitled below to reflect the corrected target (R1-vs-R6, not
R1-vs-R3 — R3 is a thin, non-computing reader over R6's output).

| Field | Value |
|---|---|
| Severity | High (found Stage 7 — ADR-0010, written Stage 6, only compared 2 of these 4) |
| Risk | P31 (`p31-handlers.js`, per-request-built, intel-platform), blog's Python `KnowledgeGraph`, blog's live `api/_lib/threat-graph.js` (Vercel, real actor data per `platform/open-issues.md` Issue 15), and intel-platform's own `api-extensions.js` `handleIntelGraph`/`handleIntelRelations` (reads a snapshot of R6, `core/intelligence/enrichment_graph.py`, exported via Cloudflare R2 storage) are four independent relationship-graph data sources. The most concerning is still R6 vs. P31: both **inside the same repository and the same Worker deployment surface**, uncoordinated |
| Owner | Intelligence Engineering (P31 + `enrichment_graph.py`/`core/orchestrator.py` owner — same team, two uncoordinated implementations) |
| Affected Systems | `p31-handlers.js`, `api-extensions.js`, `core/intelligence/enrichment_graph.py`, `core/orchestrator.py`, `core/pipeline/stages.py` (`R2AIExportStage`), `api/_lib/threat-graph.js` (blog), `knowledge_graph.py` (blog) |
| Blocking Status | Blocking ADR-0010's full resolution — Revision 3 (Stage 9 Phase 1) corrects the producer identity but does not resolve R1-vs-R6 ownership |
| Recommended Resolution | Resolve DEBT-017 (confirm whether `core/orchestrator.py` runs anywhere) before treating R6's output as trustworthy input to any migration decision; then converge `handleIntelGraph`/`handleIntelRelations` onto P31 (or adopt R6 as P31's persistence layer — an option Stage 9 Phase 1 surfaced but did not decide) per ADR-0010 |
| Implementation Priority | High — same-repository, same-team fragmentation is lower-friction to fix than cross-repo fragmentation and should not wait behind the cross-repo pieces |

### DEBT-014 — Two TAXII path prefixes, both confirmed live, unknown external-partner split

**Update, Stage 8:** Live-verified. `/taxii/` → HTTP 200 (public, no auth). `/api/taxii/` → HTTP
403 (exists, tier-gated, distinct behavior — not a dead duplicate). This is not "one path might
be dead code" as Stage 7 left it; it's **two genuinely different, differently-gated live
surfaces**, which makes the "which one do partners actually use" question more important, not
less, since they may not be interchangeable.

| Field | Value |
|---|---|
| Severity | Medium-High (external-partner-facing, wrong action risks breaking real integrations) |
| Risk | `/taxii/*` (public discovery tier) and `/api/taxii/*` (`enterprise-endpoints.js`, tier-gated 403) are both confirmed live with **different access levels**, not equivalent paths. No document found this stage states which one external TAXII/STIX partners are actually told to integrate against, or whether `/api/taxii/*` is meant to be a superset (more data, paid tier) rather than a duplicate |
| Owner | Intelligence Engineering, Partner/Customer-facing documentation owner (whoever publishes API docs to TAXII partners — not identified this stage) |
| Affected Systems | `index.js`, `enterprise-endpoints.js` |
| Blocking Status | Not blocking any ADR, but blocking a confident answer in the Interface Registry's "which TAXII path is canonical" question |
| Recommended Resolution | Check partner-facing documentation/onboarding materials (outside this codebase, not searched this stage) to determine actual external usage and whether the two paths are intentionally differentiated by tier (in which case this may not be "fragmentation" at all, just an undocumented product tier) |
| Implementation Priority | Medium — confirmed both live and distinctly gated, so no immediate action-forcing risk, but the documentation gap should close before it causes partner confusion |

### DEBT-015 — No discoverable monitoring/alerting/structured-logging story for any verified live route, including canonical ones

| Field | Value |
|---|---|
| Severity | Medium — not urgent (nothing is observed broken), but real: this platform cannot currently say with confidence whether any given route silently started failing |
| Risk | Found while live-verifying routes for Phase 4 (Stage 8): `/api/health` and per-P-layer `/observability` endpoints exist as monitoring *targets*, but no in-repo evidence of anything polling/alerting on them, and no structured request logging was found for any tested route, canonical or not (P25's trust-score included) |
| Owner | Platform SRE |
| Affected Systems | All verified-live routes, both repos |
| Blocking Status | Not blocking any ADR — orthogonal concern |
| Recommended Resolution | Confirm whether monitoring exists outside the repository (a third-party APM, Cloudflare Analytics, Vercel Analytics dashboard) before assuming a gap exists — this register only reflects what's discoverable from repository contents, and monitoring infra often lives entirely outside the codebase |
| Implementation Priority | Medium — worth a quick confirmation, not worth engineering effort until confirmed absent |

### DEBT-016 — `sentinel-apex-api`: a substantial, uncatalogued parallel backend with a non-functional deploy path

*Found Stage 9 Phase 1.*

| Field | Value |
|---|---|
| Severity | **Critical** — the largest single new-ungoverned-surface finding this stage, same category as DEBT-001's `lib/` tree: real, substantial engineering investment (auth system, Supabase schema migration, 11 API routers, test suite, three deployment configs) that no prior TITAN stage found |
| Risk | A separate FastAPI application implementing its own auth, its own graph computation (ADR-0010 R7), SIEM dispatch, MSSP multi-tenancy, and compliance endpoints — entirely disconnected from the Cloudflare Worker and the Python ingestion pipeline. Its Railway-deploy CI workflow is misplaced (`sentinel-apex-api/.github/workflows/sentinel-apex-api`, nested inside the subdirectory and missing the `.yml` extension — GitHub Actions never discovers it), so it has likely never auto-deployed. `app.cyberdudebivash.com` (the domain its own CORS config names) failed to connect in a direct probe. A future engineer could reasonably assume this is either live (Fortune-500-grade code) or safe to delete (never deploys) — both assumptions are currently unverifiable from repository contents alone |
| Owner | Unassigned — requires a human product/architecture decision on intent, same as DEBT-001 |
| Affected Systems | `sentinel-apex-api/` (entire subtree) |
| Blocking Status | Not blocking any currently-Proposed ADR directly, but blocking ADR-0010 from being called complete (R7 is now a named candidate — see ADR-0010 Revision 3) |
| Recommended Resolution | Architecture-review decision, same three options DEBT-001 already established: (a) fix the CI placement and finish deploying it as real product surface; (b) formally shelve with a "Status: Shelved" notice; (c) delete after confirming zero external dependency on `app.cyberdudebivash.com` ever having been live. This register does not recommend which |
| Implementation Priority | High — not for code changes yet, but the decision itself, since every month undecided increases the chance someone builds on it (or deletes it) by mistake |

### DEBT-017 — R6's production execution is unconfirmed, feeding a live, tier-gated, paying-customer route

*Found Stage 9 Phase 1, split out from DEBT-013 for its distinct commercial-risk shape.*

| Field | Value |
|---|---|
| Severity | **High** — not proven broken, but a real gap in confidence about data freshness on a route customers are paying tier-gated access to use |
| Risk | R3 (`api-extensions.js`'s `handleIntelGraph`/`handleIntelRelations`, confirmed live at `/api/v1/intel/graph` → 403) serves data written by R6 (`core/intelligence/enrichment_graph.py`) via `core/orchestrator.py`'s `R2AIExportStage`. No `.github/workflows/*.yml` file was found to invoke `core/orchestrator.py` — a precise search distinguishing real invocations from the many workflow files that merely contain the English word "orchestrator" in their own names/descriptions (`master-deployment-orchestrator.yml`, `revenue-orchestrator.yml`, etc.) confirmed zero real invocations. The confirmed-live master pipeline (`scripts/run_pipeline.py`) does not import `core.orchestrator` either. If this chain genuinely never runs, ENTERPRISE/MSSP-tier customers hitting this route may be served a stale, one-time, or manually-generated snapshot indefinitely without any indication of staleness |
| Owner | Intelligence Engineering (R6/`core/orchestrator.py` owner) |
| Affected Systems | `core/orchestrator.py`, `core/pipeline/stages.py`, `core/intelligence/enrichment_graph.py`, `api-extensions.js` |
| Blocking Status | Blocking confident resolution of DEBT-000B/DEBT-013 — any decision to adopt R6 as R1's persistence layer must first confirm R6 actually runs |
| Recommended Resolution | Engineering confirmation: does anything outside this repository (a separate scheduler, a manual runbook, a one-time backfill) invoke `core/orchestrator.py`? If not, either wire it into a real schedule or treat R3's current data as a known-stale snapshot until it is |
| Implementation Priority | High — commercial-trust-adjacent, same category as DEBT-015 but for a specific tier-gated route rather than general observability |

### DEBT-018 — Long-tail graph-file sprawl under `agent/` and `scripts/` (16 files, fully characterized)

*Found and closed out Stage 9 Phase 1.*

**Update, Stage 9 Phase 1 (same session):** Full per-file characterization complete — see
`TITAN_STAGE9_PHASE1_GRAPH_DISCOVERY_REPORT.md` Task 1C. Result: **9 of 16 are genuinely
production (imported and/or scheduled), 6 are complete-but-dormant (zero importers, zero CI),
1 is paused-since-2026-07-29.** No literal duplicates found, but four separate files
independently implement "build a threat graph from advisories" without any awareness of each
other — a coordination failure distinct from (and in addition to) DEBT-000B/DEBT-013's R1-vs-R6
question. One of the 9 "production" files (`scripts/intelligence_knowledge_graph.py`) is
scheduled with `continue-on-error: true` and shows no observed output — a possible silent
no-op. Two of the 9 (`agent/graph_correlation_engine.py` writing,
`agent/graph_integrity_validator.py` reading, both 6x/day scheduled) form the write/validate
loop now tracked separately as **DEBT-020** given its distinct severity. A 17th implementation
(`ocios_campaign_correlation_engine`, source: `scripts/ocios_campaign_correlation_engine.py`)
was located and characterized this same session — real, documented, imported by 3 sibling
`ocios_*` scripts. **That resolution immediately surfaced 5 more previously-uncatalogued files**
via the same mechanism (the new CI governance check, run for the first time), none of which
have been characterized: `agent/threat_graph/correlation_engine.py`,
`agent/v70_apex_upgrade/engines/correlation_engine.py`, `agent/v26/ioc_correlation.py`,
`scripts/cve_correlation_engine.py`, `scripts/adversary_correlation_engine.py`. Deliberately
left off the governance check's allowlist so they continue to surface as findings rather than
being assumed benign.

| Field | Value |
|---|---|
| Severity | **High** — not because any single file is individually dangerous, but because 9 confirmed-live, uncoordinated graph implementations (on top of R1/R6/R3) is a materially larger fragmentation surface than ADR-0010 has ever been scoped to address |
| Risk | Four independent, non-communicating "build a threat graph" engines (`agent/threat_graph/graph_engine.py`, `agent/threat_graph_engine.py` [dormant], `scripts/threat_graph_engine.py`, `agent/v44_threat_graph/threat_graph_engine.py` [dormant]) exist because nobody could see the others existed — the exact failure mode this entire TITAN program exists to close, now found one layer deeper than R1-R7 |
| Owner | Intelligence Engineering (spans multiple named sub-owners per file — see the discovery report's Task 1C table for specifics) |
| Affected Systems | `agent/graph/`, `agent/graph_operations_engine.py`, `agent/graph_integrity_validator.py`, `agent/graph_correlation_engine.py`, `agent/threat_graph/`, `agent/threat_graph_engine.py`, `agent/v44_threat_graph/`, `scripts/adversary_graph_engine.py`, `scripts/graph_integrity_validator.py`, `scripts/graph_intelligence_validator.py`, `scripts/graph_intelligence_engine.py`, `scripts/intelligence_knowledge_graph.py`, `scripts/omega_ioc_graph_layer.py`, `scripts/persistent_campaign_graph_engine.py`, `scripts/threat_graph_engine.py` |
| Blocking Status | Blocking ADR-0010 from being called a complete picture of the platform's graph landscape — the ADR's R1-R7 taxonomy does not yet incorporate any of these 16 |
| Recommended Resolution | Not decided this stage (no ownership decisions per Task 6's explicit instruction). Candidate next step: extend ADR-0010's candidate matrix formally to include the 9 confirmed-production long-tail files before any Phase 4 work, since several (`scripts/threat_graph_engine.py` especially, which feeds a live customer-facing API) may need explicit canonical/legacy dispositions of their own, not just a footnote |
| Implementation Priority | High — discovery is now complete for this item; the remaining work is an ownership/architecture decision, which is explicitly out of Phase 1's scope (see Task 7's BLOCKED determination) |

### DEBT-019 — ADR-0010's R2 (`knowledge_graph.py`) characterized as a live pipeline; evidence supports manual-only execution

*Found Stage 9 Phase 1.*

| Field | Value |
|---|---|
| Severity | Medium — documentation/ADR-accuracy item, not an active production risk (the underlying code is correct and tested) |
| Risk | ADR-0010's Existing Implementations table lists R2's consumer as "Report generation pipeline," reading as active automation. Direct tracing this stage found `KnowledgeGraph()` is constructed only via manual `cli.py run`/`score` invocation and the repository's own test suite; `intelligence-engine-ci.yml` (the only blog workflow referencing `sentinel_engine`) runs only `pytest` and a compile check, never real ingestion; the repository's actual high-frequency auto-publish automation (`ai-security-intel.yml`) does not reference `sentinel_engine` at all. `platform/open-issues.md` Issue 9 independently confirms this in the repository's own words |
| Owner | Blog/EIOS Engineering (`knowledge_graph.py`/`cli.py` owner) |
| Affected Systems | `Sentinel-APEX/engine/sentinel_engine/knowledge_graph.py`, `cli.py`, `pipeline.py`, `report_ingest.py` |
| Blocking Status | Not blocking any code change — informs migration-urgency judgment only (a manually-run tool has a different deprecation posture than a live pipeline) |
| Recommended Resolution | Either schedule real ingestion (closing the gap `report_ingest.py`/GIKEP-GTIEP v1 already narrowed for hand-authored reports) or correct ADR-0010's "Report generation pipeline" framing to "manually-invoked tool" — a decision for whoever owns R2's roadmap, not decided by this register |
| Implementation Priority | Low-Medium — accuracy fix, not schedule-critical |

### DEBT-020 — "Zombie pipeline": scheduled, CI-wired graph scripts report clean while their data flow appears to have never worked

*Found Stage 9 Phase 1, split out from DEBT-018 for its distinct severity.*

| Field | Value |
|---|---|
| Severity | **Critical** — this is a materially worse failure mode than an undiscovered dormant file (DEBT-018's other findings): CI is actively green on a schedule for a data flow that, per this repository's own git history, has never once persisted its target output |
| Risk | `agent/graph_correlation_engine.py` (writer, 6x/day cron, `enterprise-intel-quality.yml`) and `agent/graph_integrity_validator.py` (reader, 6x/day cron, `enterprise-observability.yml`) form a complete write/validate loop against `data/threat_graph/{graph_nodes,graph_edges}.json` — a path with **zero commits in this repository's entire git history.** The validator's own logic does not flag `nodes:0, edges:0` as anomalous, so every scheduled run reports a clean, structurally-valid result. `scripts/intelligence_knowledge_graph.py` (scheduled 4x/day, `continue-on-error: true`, no observed output) shows the same shape. This is a concrete instance of a risk this register had previously only described in the abstract (DEBT-015: "no discoverable monitoring/alerting story") — here, specific named jobs are demonstrably running green while accomplishing nothing observable, which is a stronger claim than "no monitoring exists" |
| Owner | Intelligence Engineering (owner of `agent/graph_correlation_engine.py`, `agent/graph_integrity_validator.py`, `scripts/intelligence_knowledge_graph.py`) |
| Affected Systems | `agent/graph_correlation_engine.py`, `agent/graph_integrity_validator.py`, `scripts/intelligence_knowledge_graph.py`, `.github/workflows/enterprise-intel-quality.yml`, `.github/workflows/enterprise-observability.yml`, `.github/workflows/generate-and-sync.yml` |
| Blocking Status | Not blocking any ADR directly, but blocking confidence in this register's own DEBT-018 characterization of these files as "production" in any meaningful sense beyond "scheduled to execute" |
| Recommended Resolution | Engineering investigation into root cause: is `data/threat_graph/` written but gitignored (real output, just untracked — lower severity, re-classify if confirmed)? Is the write silently failing (higher severity — the "zero-failure design" pattern noted in `agent/threat_graph_engine.py`'s docstring may be actively hiding real errors across this file family)? Is the path itself wrong on one side of the write/read pair? Do not assume an answer without checking — this register only states what was observed, not why |
| Implementation Priority | **Critical** — resolving *why* CI is green here is a precondition for trusting any other "confirmed production" claim in this register that relies on scheduled-workflow evidence alone, not just this specific pipeline |

### DEBT-021 — Evidence Registry service built (Stage 10–11) ahead of its gating ADRs' Acceptance

**Status: RESOLVED, 2026-08-06.** ADR-0008, ADR-0011, and ADR-0012 all now show `Status:
Accepted` (executive architecture authority — see `TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md`).
The gap this item tracked — implementation ahead of Acceptance — is closed for these three going
forward from Stage 12. Left below for the record, per this register's own
document-don't-delete discipline; the history is still true, it's just no longer open.

*Found Stage 11 post-implementation validation (resumed session, PR #115 pre-merge review).*
**Correction, Stage 11.5 (2026-08-06):** the Recommended Resolution field below originally
claimed ADR-0012 was "not-yet-drafted... never written." That was wrong — verified against
`docs/adr/0012-api-versioning-interface-governance.md` directly, ADR-0012 was drafted in Stage 7
(PR #110) specifically to fill this gap. It carries the same `Status: Proposed, not Accepted` as
ADR-0008/0011. The error traced back to reading `docs/adr/README.md`'s index (stale — never
updated to list ADR-0012/0013, now fixed) and `TITAN_IMPLEMENTATION_READINESS.md`'s Stage-6-era
claim (accurate when written, since annotated) without checking `docs/adr/` directly. The
underlying blocker is unchanged — absence of *Acceptance*, not absence of the ADR — but the text
below is now corrected to say that accurately.

| Field | Value |
|---|---|
| Severity | Medium — no active harm (zero blast radius, independently re-verified this review: zero imports of `evidence-registry/` outside its own directory, zero routes, `index.js`/`p32-handlers.js`/`p38-handlers.js` untouched, `EER_FLAGS` off by default in canary/production), but a governance-process gap that compounds if the same pattern repeats into Stage 12 |
| Risk | Stage 8's own authorization memo (`TITAN_EVIDENCE_REGISTRY_AUTHORIZATION.md`) explicitly reserved "Evidence Registry service (actual persistence)" as `No — Blocked`, requiring ADR-0008 formal Acceptance first. Stage 10 built the authorized half (schema/entity/serialization). Stage 11 built the blocked half — `registry-service.js`, `in-memory-repository.js`, `lifecycle.js` (a 9-state machine, ADR-0011's exact subject), `versioning.js` — under a narrower reading that ADR-0008 blocks only *wiring into a live route*, not construction of the service itself. ADR-0008, ADR-0011, **and ADR-0012** (API Versioning & Interface Governance — the policy Stage 12's Phase 7 "Internal API Contracts" would need) all remain `Status: Proposed`, confirmed by direct inspection of each ADR file. Each stage has disclosed the unmet precondition transparently in its own completion report — nothing was hidden — but the scope built under "it's inert, so it's fine" has grown every stage, from type definitions (Stage 8) to a full service/lifecycle/versioning/indexing layer (Stage 11) |
| Owner | Platform Governance Lead (ADR-0008 / ADR-0011 / ADR-0012 Acceptance decision) |
| Affected Systems | `workers/intel-gateway/src/evidence-registry/*`, `docs/adr/0008-canonical-evidence-framework.md`, `docs/adr/0011-evidence-lifecycle-ownership.md`, `docs/adr/0012-api-versioning-interface-governance.md` |
| Blocking Status | Blocking Stage 12 (Enterprise Evidence Service Platform — the first stage that would touch real consumer/API surface, per its own Phase 3/Phase 7 scope). **Not** blocking PR #115's merge itself, which stayed inert and reversible regardless of ADR status — confirmed by independent re-run of the full test/regression/certification/governance gate set, merged 2026-08-06 |
| Recommended Resolution | Human Acceptance review of ADR-0008, ADR-0011, and ADR-0012 before Stage 12 implementation begins — all three are drafted and ready for review, none require further authoring. See `TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md` (Stage 11.5) for the formal disposition record awaiting each ADR's named Deciders |
| Implementation Priority | High — not for code changes, for the decision itself, before Stage 12 implementation begins |

## Register maintenance

New items should be added, not silently folded into existing ones, per this program's
documented-not-corrected discipline. Close an item by changing its status inline (add
`**Status: CLOSED (date, reference)**` under its heading) rather than deleting the row — this
register is itself subject to the Deprecation Instead of Deletion policy.
