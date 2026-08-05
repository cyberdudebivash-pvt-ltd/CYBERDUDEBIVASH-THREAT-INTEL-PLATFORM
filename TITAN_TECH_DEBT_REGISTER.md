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

### DEBT-000B — R1 vs. R3: two live, independently-computed relationship graphs in the same intel-platform repository

| Field | Value |
|---|---|
| Severity | **Critical** — the highest-priority actionable item this register now contains, promoted here specifically because AR-000's resolution freed up attention for it |
| Risk | `p31-handlers.js` (`_buildGraph`, rebuilt per-request) and `api-extensions.js`'s `handleIntelGraph`/`handleIntelRelations` (reads a separately-generated `data/ai/intel_graph.json` snapshot from R2) are **both confirmed live** (`/api/v1/p31/graph` → 402; `/api/v1/intel/graph` → 403 — both real, tier-gated, working routes), in the **same repository, same team, same Worker**, answering the same "what's related to this item" question from two different, uncoordinated code paths and data sources |
| Owner | Intelligence Engineering (owns both — this is the same team failing to coordinate with itself, not a cross-team or cross-repo issue) |
| Affected Systems | `p31-handlers.js`, `api-extensions.js`, whatever pipeline produces `data/ai/intel_graph.json` (still unidentified — see DEBT-013) |
| Blocking Status | Blocking ADR-0010's full resolution (Revision 2 names this explicitly) — but unlike the cross-repo R1-vs-R2/R4 question, this one requires no negotiation with another team, only internal prioritization |
| Recommended Resolution | Identify the `data/ai/intel_graph.json` producer (DEBT-013) first, then converge `handleIntelGraph`/`handleIntelRelations` to call P31 directly (or vice versa) rather than maintaining two data paths |
| Implementation Priority | **Highest actionable item in this register** — same-repo, same-team, no external dependency, clear technical path once the producer is identified |

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

### DEBT-013 — Relationship-graph fragmentation (superseded in part by DEBT-000B; `intel_graph.json` producer still unidentified)

**Update, Stage 8:** Live verification confirmed 3 of the 4 candidates named here are actually
live (P31, `api-extensions.js`'s R2-snapshot reader, blog's `threat-graph.js`); the 4th
(blog's Python `KnowledgeGraph`) has no HTTP surface to verify (pipeline-internal, as
originally noted). The same-repository P31-vs-`api-extensions.js` conflict is now tracked as
**DEBT-000B** (promoted to Critical, since it's the most actionable). This entry remains open
specifically for the still-unidentified `data/ai/intel_graph.json` producer.

| Field | Value |
|---|---|
| Severity | High (found Stage 7 — ADR-0010, written Stage 6, only compared 2 of these 4) |
| Risk | P31 (`p31-handlers.js`, per-request-built, intel-platform), blog's Python `KnowledgeGraph`, blog's live `api/_lib/threat-graph.js` (Vercel, real actor data per `platform/open-issues.md` Issue 15), and intel-platform's own `api-extensions.js` `handleIntelGraph`/`handleIntelRelations` (reads a separately-generated `data/ai/intel_graph.json` snapshot from R2) are four independent relationship-graph data sources. The last one is the most concerning: it is **inside the same repository and the same Worker** as P31 yet reads an entirely different, separately-generated data source for what a customer would reasonably assume is "the" intelligence graph |
| Owner | Intelligence Engineering (P31 + `api-extensions.js` owner — same team, two uncoordinated implementations) |
| Affected Systems | `p31-handlers.js`, `api-extensions.js`, `api/_lib/threat-graph.js` (blog), `knowledge_graph.py` (blog), whatever pipeline produces `data/ai/intel_graph.json` (unidentified this stage) |
| Blocking Status | Blocking ADR-0010's full resolution — the ADR as revised this stage names P31 as target-canonical, but cannot address the `intel_graph.json` source until its producing pipeline is identified |
| Recommended Resolution | Identify the `data/ai/intel_graph.json` producer first (prerequisite to any further action); then converge `handleIntelGraph`/`handleIntelRelations` onto P31 once persisted, per ADR-0010 |
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

## Register maintenance

New items should be added, not silently folded into existing ones, per this program's
documented-not-corrected discipline. Close an item by changing its status inline (add
`**Status: CLOSED (date, reference)**` under its heading) rather than deleting the row — this
register is itself subject to the Deprecation Instead of Deletion policy.
