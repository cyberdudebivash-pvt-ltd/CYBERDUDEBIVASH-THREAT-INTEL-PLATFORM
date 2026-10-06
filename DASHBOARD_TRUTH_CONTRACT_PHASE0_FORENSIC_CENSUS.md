# SENTINEL APEX — Dashboard Truth Contract: Phase 0 Forensic Census

**Mission:** One authoritative data contract → one normalization path → one canonical view model → one rendering system → explicit state machine → observability → production SLOs.

**This document covers Phase 0 (forensic inventory) and Phase 1 (canonical contract definition) only.** No production rendering, scoring, or gating behavior is changed by this document or its companion code (`js/dashboard-state.js`, `js/__tests__/dashboard-state.test.js`). Phases 2+ (normalization migration, renderer consolidation, state-machine wiring, removal of duplicate logic) are **not started** and require separate, individually-reviewed PRs per the migration plan in §7.

Evidence gathered by five parallel forensic passes over `workers/intel-gateway/src/`, `js/`, `scripts/`, `index.html`, `dashboard/*.html`, and live production data (`api/feed.json`, `https://intel.cyberdudebivash.com/api/v1/intel/apex.json`). Every claim below is `file:line`-cited in the underlying domain reports; this document synthesizes and ranks them.

---

## 1. Architecture Map

```
Python pipeline (scripts/)
  true_intel_ingestor.py           -- ingest, coarse per-source risk_score defaults
       |
  enrich_cvss_epss_batch.py        -- real NVD CVSS + FIRST.org EPSS; narrow risk_score
       |                              reconciliation (only overwrites on 3 magic values)
  severity_governance_engine.py    -- KEV/ransomware/zero-day-aware severity floors
       |
  confidence_corroboration_engine.py -- sla_priority P0-P4, confidence_label/_v2
       |
  enrich_feed_apex.py              -- predictive_risk (weighted), ttp_density, confidence_score
       |
  run_pipeline.py STAGE 3.9        -- re-applies severity governance (post-write)
       |
  [STAGE 3.1.2, LATER] enrich_cvss_epss_batch.py Pass 4.7
       -- reassigns severity from CVSS ALONE, can silently undo governance floors
       |
  generate_api_manifests.py / generate_dashboard_feeds.py / build_reports_index.py
       -- writes api/feed.json, api/v1/intel/latest.json, api/reports/*.json
       v
Cloudflare Worker  (workers/intel-gateway/src/index.js)
  publication-gate.js  evaluatePublicationGate()
       composes: p20 (quality) + p21 (certification tier) + p23 (actionability)
                 + p25 (trust score) + p26 (grade/cert flags)
       -- correctly computes CUSTOMER_READY / WITHHELD / REJECTED / PENDING_ENRICHMENT
       -- but this classification is COMPUTED then DISCARDED before most responses
          (index.js:656 computes it, :701 serves the raw catalog entry instead)
       |
  revenue-enforcement.js  applyTierGateV2() / computeApexAIGated()
       -- tier-gates iocs/stix/actor-attribution/detection-rules/full apex block
       -- ttp_density fix (this session, PR #165) now correct & tier-uniform
       v
Public API  (/api/v1/intel/latest.json, /api/feed.json, /api/v1/intel/apex.json, ...)
       v
Frontend — NOT a single pipeline. At least 8 independent consumers of the same feed:
  js/api_adapter.js  (SentinelApexAdapter.normalizeIntelItem)
       -- the ONLY real normalization boundary, but feeds ONLY #sapx-card-grid
       -- has its own bug: normalizeSocPriority() whitelists P1-P4, silently
          collapses P0 (the pipeline's most urgent tier) to P4
       |
       +--> js/card_renderer.js + card_renderer_integration.js --> #sapx-card-grid
       |     (canonical surface; correctly adapter-first; but never auto-refreshes)
       |
  index.html (13,000+ lines) independently reads raw feed fields for 7 more surfaces:
       +--> renderCards()            --> #threat-grid       (hidden, still executes)
       +--> cdbGodModeRender()       --> #threat-grid        (own severity fn)
       +--> renderTopThreats()       --> #top-threats-section (3 internal template
       |                                  copies, 1 dead, own sevInfo()/prio())
       +--> cdbRenderSOC()           --> #cdb-panel-soc      (own risk_score thresholds)
       +--> reports tab _renderCard()--> #cdb-reports-grid   (own SEV_COLORS map)
       +--> openThreatModal()        --> modal                (2 more independent
       |                                  apex_ai soc_priority computations)
       +--> computeMetrics()/fillMetrics() --> header counters (races with the
                                              canonical _injectHeaderStats() writer)

  dashboard/enterprise_dashboard.html, enterprise_dashboard_v2.html
       -- separate HTML files, still live in CI, still show browser-clock as
          "Last Sync" (the exact bug class already fixed 5x inside index.html)
```

**Two separate "contract validator" implementations already exist and disagree with each other** (found during this census, not previously documented):

| | `js/dashboard_contract_validator.js` | `scripts/api_dashboard_contract_validator.py` + `dashboard_contract.json` |
|---|---|---|
| Wired into CI? | **No** — zero references anywhere outside itself (`grep` confirmed) | **Yes** — `sentinel-blogger.yml:1605`, `deploy-worker.yml:119`, `sync-dashboard.yml:120` |
| Checks | Field presence + a few value enums (severity, action_rec, `soc_priority ∈ {P1,P2,P3,P4}`) | Field presence by the 9 card zones only, no value-domain checks |
| Bug | `VALID_SOC_PRIORITIES` (line 41) **excludes `P0`** — the same defect independently present in `js/api_adapter.js`'s `normalizeSocPriority()` | N/A (doesn't check values) |
| Consequence | Dead code — even if it were wired in, it would flag a legitimate `P0` value as `INVALID_SOC_PRIORITY` rather than catch the adapter dropping it | Would not catch the P0→P4 collapse either way (doesn't inspect values) |

This is itself a microcosm of the whole mission: even "the contract" has two independent, silently-diverging implementations.

---

## 2. Rendering-Path Census (summary — full detail in agent reports, retained in session scratchpad)

At least **8 independent card/metric rendering implementations** read the same underlying feed today:

| Surface | Adapter-first? | Independent severity/priority logic? |
|---|---|---|
| `#sapx-card-grid` (canonical, `card_renderer.js`) | Yes | No — pure presentation |
| `#threat-grid` legacy (`renderCards()`) | Partial (`item.__norm` optional) | Yes |
| GOD MODE fallback (`cdbGodModeRender()`) | No | Yes, own `_sv()`/`_sc()` |
| TOP10 (`renderTopThreats()`) | Partial | Yes — **3 internal template copies**, 1 provably dead |
| SOC VIEW tab (`cdbRenderSOC()`) | No | Yes, raw `risk_score` thresholds |
| Reports tab (`_renderCard()`) | No | Yes, own `SEV_COLORS`/`SEV_BG` |
| Intelligence detail modal (`openThreatModal()`) | Partial | Yes — 2 independent `apex_ai` panels |
| Header/summary counters | Split | `computeMetrics()` (legacy) and `_injectHeaderStats()` (canonical) **both target the same DOM IDs** |

Git history (`ec218a76`, `190fc9cb`) confirms this has already caused two prior production incidents (CRITICAL/HIGH items rendering as P4), each requiring 3-4 hand-synchronized edits across the duplicated templates because no shared render function exists.

**Most severe operational finding:** the one canonical, adapter-first grid (`#sapx-card-grid`) **never refreshes after initial page load** — `window.SAPX.refresh` is exposed but never called anywhere in `index.html`; its own auto-refresh timer is hard-disabled (`AUTO_REFRESH_MS = 0`). All visible refresh controls (30-min countdown, 5-min EICC loop, manual `r` key) only re-render the *hidden* legacy grid and TOP10/SOC paths. A user who leaves the tab open sees the canonical grid frozen at page-load state indefinitely.

---

## 3. Consolidated Field Ownership Matrix (condensed — see full per-field detail in the five domain census reports retained this session)

| Field | Canonical backend owner | # duplicate calculators found | Worst confirmed live conflict | Risk |
|---|---|---|---|---|
| `severity` | `severity_governance_engine.py` (KEV/ransomware/zero-day floors) | 1 (Pass 4.7 `cvss_to_severity()` can silently undo governance floors, ordering bug) | Governance-floored CRITICAL items can be CVSS-realigned lower later in the same CI run | HIGH |
| `sla_priority`/`priority` | `confidence_corroboration_engine.py build_sla_recommendation()` (P0-P4) | 2 (`api_adapter.js fallbackSocPriorityForSeverity()`, `p23-handlers.js _computePatchPriority()` — different taxonomy) | **`P0` silently collapses to `P4` in `js/api_adapter.js normalizeSocPriority()`** — confirmed live on item `intel--d49e384ea385135d` (CRITICAL, KEV=true) | **HIGH — confirmed live, violates mission's own "CRITICAL cannot display P4" acceptance criterion** |
| `risk_score` | None — contested; ingestion default patched by narrow reconciliation | N/A (single field, but authorship is the bug) | 28/116 live items diverge ≥1.0 from `cvss_score` on the same item; worst case CVSS 9.8 vs `risk_score` 0.89 | HIGH |
| `cvss_score` | `enrich_cvss_epss_batch.py` NVD fetch | 1 (`severity_governance_engine.py._get_cvss()` treats `risk_score` as an equally-valid CVSS source) | Corroborates the `risk_score` conflict above | MEDIUM |
| `confidence` (4 scales) | None — 3 independent producers + a 4th client-side formula | 4 | `confidence_score:20.0` vs `confidence_score_v2:0` on the same live item | HIGH |
| `predictive_risk` | `enrich_feed_apex.py compute_predictive_risk()` (weighted, KEV-aware) | 2 (`revenue-enforcement.js` simple clamp; `alert-engine.js` raw passthrough) | KEV items get the canonical formula's +3.0 bonus only when served through the enrichment path, not the Worker's own gateway path | MEDIUM |
| `ttp_density` | `enrich_feed_apex.py compute_ttp_density()` mirrored exactly in `revenue-enforcement.js` (this session's PR #165 fix) | **0 remaining** | None — resolved | **LOW (resolved)** |
| `ioc_count` | `agent/ioc_engine.py enforce_ioc_integrity()` at write time; preserved correctly through tier-gating | 0 on the primary path; policy inconsistency between `/api/cves` (nulls count) and `/api/feed` (preserves count) | Policy divergence only, not a numeric bug | MEDIUM |
| `iocs`/IOC-type composition | `revenue-enforcement.js applyTierGateV2` | 1 — **`/api/actors` bypasses the IOC entitlement gate entirely**, leaking IOC-type composition to FREE tier | Confirmed via code path (`api-extensions.js:269-410` never calls `applyTierGateV2`) | MEDIUM |
| MITRE `ttps` rendering | `js/api_adapter.js` normalizer | 1 (shape mismatch) | 61% of live items store `ttps` as plain strings; adapter drops non-object entries; `card_renderer.js` renders blank MITRE chips for the majority of cards | MEDIUM (display-only) |
| `publication_status`/`customer_ready` | `publication-gate.js evaluatePublicationGate()` — computed correctly | 1 architectural gap (not a duplicate, an *omission*) | **Computed per-item at `index.js:656`, then discarded — never serialized onto any public feed manifest** | HIGH — root cause of the report-URL state-collapse below |
| `report_url`/report state | No backend `publication_status` reaches the client at all | Frontend infers state from **URL presence alone** across **6 divergent call sites** | `cdbBuildReportUrl()` collapses "not yet synced" and "permanently rejected" identically by design; the 6 call sites also disagree with each other in how they render the empty result | HIGH |
| "processing" state | N/A | 0 remaining literal instances (fixed by PR #165, this session) | Residual: the fix changed the *label* only — `PENDING_ENRICHMENT` and permanent `REJECTED` both now silently read "UNAVAILABLE," a different but still-collapsed state | MEDIUM |
| `validation_status` (item-level) | None — **≥4 incompatible value-domains share one field name** across report-outcome, IOC-verification, trust-score-input, and UI-badge uses | 4 | Live production value `"enriched"` satisfies none of the client's 3-bucket badge logic → fully-enriched items render **"? PENDING"** trust badges | HIGH |
| Freshness / "Last Sync" | No canonical source | **≥9 independent reducers** in `index.html` alone, each with a different field-priority fallback order, plus a computed-but-**never-read** canonical `freshnessIndicator()` in `api_adapter.js` | `dashboard/enterprise_dashboard.html:721` and `enterprise_dashboard_v2.html:597` (both live, CI-referenced) still write **raw browser `new Date().toLocaleTimeString()`** as "Last Sync" — the exact bug class already fixed 5× inside `index.html` but never propagated to these two files | HIGH |
| Freshness *state* (LIVE/STALE/etc.) | No canonical function exists anywhere | **≥6 independently-thresholded definitions** across `p18/p29/p30/p35/p40-handlers.js` (1h–720h ranges) plus 3 more inline in `index.html` | A card could be "LIVE" per one engine and "AGING" per another simultaneously; the one client-side canonical function (`freshnessIndicator()`) is computed and attached but **never read anywhere** (dead code) | HIGH |
| Header summary counters | Split ownership | `computeMetrics()` (legacy, unconditional) vs. `_injectHeaderStats()` (canonical, self-guarded once) — **both target the identical DOM element IDs** | Canonical adapter-derived numbers are deterministically clobbered by legacy raw-threshold numbers on the very first refresh cycle and never restored | HIGH |

---

## 4. Duplicate-Calculation Matrix (every file implementing logic that should have exactly one owner)

| Concept | Canonical implementation | Duplicate implementations (all must migrate or be formally deprecated in Phase 8, not now) |
|---|---|---|
| Severity | `severity_governance_engine.py` | `enrich_cvss_epss_batch.py cvss_to_severity()` (Pass 4.7); `index.html getSeverity()` (9692); `cdbGodModeRender()._sv()` (11206); `cdbRenderSOC()` inline thresholds; Reports-tab `SEV_COLORS` map |
| SLA priority | `confidence_corroboration_engine.py build_sla_recommendation()` | `js/api_adapter.js fallbackSocPriorityForSeverity()` (86-90, disagreeing CRITICAL mapping); `p23-handlers.js _computePatchPriority()` (different taxonomy); `index.html renderTopThreats()`'s `prio()` (×3 internal copies) |
| `predictive_risk` | `enrich_feed_apex.py compute_predictive_risk()` | `revenue-enforcement.js computeApexAIGated()` (simple clamp, no KEV/EPSS bonuses); `alert-engine.js` (raw `risk_score` passthrough) |
| Confidence | Contested (see §3) | `enrich_feed_apex.py compute_ai_confidence()`; `confidence_corroboration_engine.py score_item_evidence()`; `p18-handlers.js computeTransparentConfidence()`; `revenue-enforcement.js computeApexAIGated()` |
| Report-URL / state | None (URL-presence proxy) | 6 divergent call sites in `index.html` (main card CTA, TOP10, TOP3, godmode footer, modal source-links, modal dossier button) |
| Tier/entitlement check ("am I PRO?") | `revenue-enforcement.js applyTierGateV2` (server) | 3 hand-copied inline IIFEs in `index.html` (`_currentTierLvl`, `_mTier/_mPro`, `_mdTier/_mdPro`) |
| Relative-time ("Xm ago") formatting | None | 5 near-identical formatters: `index.html timeSince()`, `api_adapter.js relativeTime()`, `card_renderer.js relativeTime()`, `sentinel-live-feeds.js fmtRelTime()`, `sla-monitor.js _time_ago()` |
| "Newest timestamp in dataset" (Last Sync) | None | ≥9 independent `reduce()`/`Math.max()` blocks in `index.html`, each with different field-priority fallback |
| Freshness state (LIVE/STALE/...) | None | 6 backend definitions (p18/p29/p30/p35/p40) + `api_adapter.js freshnessIndicator()` (unused) + 3 inline `index.html` per-card thresholds |
| "Contract validator" itself | Neither is canonical (see §1 table) | `js/dashboard_contract_validator.js` (unwired, has the P0 bug) vs. `scripts/api_dashboard_contract_validator.py` (wired, structural-only) |

---

## 5. Ranked Truth-Divergence Risks

1. **[CONFIRMED LIVE, HIGH] KEV-confirmed CRITICAL items with pipeline priority `P0` render as `P4 — INFORMATIONAL`.** `js/api_adapter.js:57-62 normalizeSocPriority()` whitelists only `P1`-`P4`. Reproduced against live `api/feed.json` item `intel--d49e384ea385135d`. This directly violates the mission's own stated acceptance bar ("CRITICAL cannot display P4"). The dead, unwired `js/dashboard_contract_validator.js` has the identical `P0`-exclusion bug in its own enum whitelist, so even if it were wired in it would not catch this — it would instead incorrectly flag legitimate `P0` values.
2. **[HIGH] The one canonical, adapter-normalized card grid never refreshes.** `#sapx-card-grid`'s auto-refresh is hard-disabled and unreachable from any visible refresh control. Customers viewing the dashboard for an extended session see frozen data indefinitely with no visual indication.
3. **[HIGH] `publication_status` is computed correctly server-side and then discarded before the response is built.** The entire report-URL/"processing" state-collapse (item §3, §5.5 below) stems from this one omission, not from any frontend logic defect — the fix belongs on the backend response-shape side (additive field), not in renderer logic.
4. **[HIGH] Header summary counters have two writers targeting identical DOM IDs.** Canonical, adapter-derived numbers shown momentarily at page load are unconditionally overwritten by legacy raw-threshold numbers on the first refresh cycle (30 min) and never restored.
5. **[HIGH] Two live, CI-referenced dashboard HTML files still show browser-clock as "Last Sync."** `dashboard/enterprise_dashboard.html` and `enterprise_dashboard_v2.html` were missed by the 5 prior fixes applied inside `index.html`. A customer viewing either during a real multi-hour data outage sees "Synced just now."
6. **[HIGH] `risk_score` and `cvss_score` diverge ≥1.0 on 28/116 live items**, corroborating a defect already identified and deliberately left unfixed earlier this session pending explicit authorization (enrichment-ordering + narrow reconciliation-allowlist issue in `enrich_cvss_epss_batch.py`/`severity_governance_engine.py`).
7. **[HIGH] `validation_status` serves ≥4 incompatible purposes under one field name.** Live production items carry `validation_status:"enriched"`, which satisfies none of the client's 3-bucket trust-badge logic, so fully-enriched items display **"? PENDING"** — the opposite of their true state.
8. **[HIGH] No canonical freshness-state definition exists anywhere; 6+ backend engines and 3+ frontend sites use different thresholds** (1h to 720h) for what counts as "fresh." The one client-side function that IS correctly canonical (`api_adapter.js freshnessIndicator()`) is computed and attached to every item but literally never read by any renderer — dead code sitting next to the exact problem it was built to solve.
9. **[MEDIUM] `/api/actors` bypasses the IOC entitlement gate** that `/api/feed` and `/api/search` correctly enforce, leaking IOC-type composition (not raw values) to FREE tier.
10. **[MEDIUM] Six-plus independent card/severity-rendering implementations, one provably dead code** (`renderTopThreats()`'s unused `cards` template). Git history shows two prior production incidents from exactly this pattern, each requiring 3-4 hand-synchronized edits because no shared render function exists — nothing structurally prevents a third recurrence.
11. **[MEDIUM] MITRE TTP chips render blank for the majority of live cards** due to a `ttps` shape mismatch (61% plain-string vs. 39% object) between what the pipeline writes and what `api_adapter.js`/`card_renderer.js` assume. Numeric TTP-density and TTP-count fields are unaffected (they read a separate, correct field).
12. **[LOW/architecturally MEDIUM] `p32-handlers.js`'s `_computeReleaseGate()` remains live and imported despite `publication-gate.js`'s own comments explicitly disqualifying it as non-authoritative** — a standing landmine if a future change ever wires it back into a serving decision.

---

## 6. Phase 1 — Canonical Contract (this PR's code deliverable)

Given the existing `js/dashboard_contract_validator.js` (unwired, renderer-output-shape validator) and `scripts/api_dashboard_contract_validator.py` + `dashboard_contract.json` (wired, structural zone-presence validator), **Phase 1 does not introduce a third, competing "DashboardRecord" implementation.** Per Level 4 (Reuse) and Principle 3 (Single Source of Truth), the correct additive step is the one piece the census confirmed **does not exist anywhere in the codebase yet**: an explicit, versioned **state-machine vocabulary** (mission Phase 5) that a future canonical normalizer can target, and that both existing validators can eventually be extended to check.

**New file, purely additive, not imported or wired into anything: `js/dashboard-state.js`.**

It defines:
- The 12 canonical states from the mission spec (`LIVE, FRESH, STALE, DEGRADED, PROCESSING, PUBLISHED, WITHHELD, BLOCKED, REJECTED, UNAVAILABLE, ERROR, UNKNOWN`), each with a machine value, customer-visible label, explanation, severity, and telemetry event name — matching mission §6's required shape exactly.
- A `mapPublicationGateResult()` helper documenting (but not calling — the endpoint isn't wired to any manifest yet, per §5.3 above) how a future `publication_status` field would map onto this vocabulary once the backend gap is closed.
- Explicit `UNKNOWN`/`UNAVAILABLE` sentinel constants for the zero-fabrication policy (mission Phase 10), so a future normalizer has one place to import them from instead of ad hoc `''`/`null`/`'—'` strings.

This module exports pure data and pure functions. It has zero side effects, is not `<script src>`-included in `index.html`, is not `require()`d by `api_adapter.js` or `card_renderer.js`, and is not referenced by any CI workflow. Blast radius: **zero** — it cannot affect production behavior because nothing consumes it yet.

**Companion test file:** `js/__tests__/dashboard-state.test.js` — validates the module's own internal consistency (every state has all required properties, no duplicate machine values, label/severity domains are valid) using this repo's existing `node --test` convention. It does not test any renderer or adapter, since none consume the module yet.

---

## 7. Migration Plan (unstarted — for review before any PR beyond this one)

| PR | Scope | Files (indicative, subject to review at PR time) |
|---|---|---|
| **PR-A (this PR)** | Phase 0 census (this doc) + Phase 1 state contract | `DASHBOARD_TRUTH_CONTRACT_PHASE0_FORENSIC_CENSUS.md`, `js/dashboard-state.js`, `js/__tests__/dashboard-state.test.js` — zero existing files touched |
| PR-B | Backend: add `publication_status` field to feed manifests (closes §5.3); fix `js/api_adapter.js normalizeSocPriority()`'s P0 exclusion (closes §5.1); fix the same bug in `js/dashboard_contract_validator.js`'s enum | `scripts/generate_api_manifests.py` or `buildCertifiedReportsFeed` (index.js:641-702), `js/api_adapter.js`, `js/dashboard_contract_validator.js` |
| PR-C | Wire `#sapx-card-grid` to an actual refresh cycle (closes §5.2); resolve the header-counter dual-writer collision (closes §5.4) | `js/card_renderer_integration.js`, `index.html` (remove/redirect the `computeMetrics()` writes that collide) |
| PR-D | Fix the two stale `dashboard/*.html` browser-clock instances (closes §5.5) | `dashboard/enterprise_dashboard.html`, `dashboard/enterprise_dashboard_v2.html` |
| PR-E | Consolidate TOP10's 3 template copies into 1 (closes part of §5.10); remove the confirmed-dead `cards` template | `index.html` |
| PR-F | Single freshness-state implementation; wire the already-correct-but-unused `freshnessIndicator()` into every surface (closes §5.8) | `js/api_adapter.js`, `index.html`, and a decision on which of the 6 backend threshold sets becomes canonical |
| PR-G | `validation_status` field-name disambiguation — likely requires a backend rename/split, not a frontend fix (closes §5.7) | TBD pending backend design review — this is a schema-shape decision, not a rendering fix |
| PR-H | Legacy-path deprecation: `renderCards()`/`#threat-grid`, `cdbGodModeRender()`, `cdbRenderSOC()`'s independent logic, migrated to consume the canonical adapter/state contract; synthetic Playwright production gate | `index.html`, new Playwright spec |

Each PR above is independently reviewable, independently revertible, and — per the mission's own non-negotiable rule — none of them proceed without their own Proof Before Change table, live reproduction, and regression coverage at PR time. **This document does not authorize PR-B through PR-H; it only establishes the evidence base they require.**

---

## 8. Rollback

This PR (PR-A) adds two new files and one new markdown document. Rollback is `git revert` of a single commit; nothing else in the repository imports, requires, or executes any of the new code, so reverting has zero effect on any running system.

---

## 9. Reuse Report

| Metric | Result |
|---|---|
| Existing engines reused | `evaluatePublicationGate()`, `computeP20QualityScore`, `getP21CertificationLevel`, `computeOperationalReadiness`, `computeEnterpriseTrustScore`, `computeP26Grade` (read/cited, not modified); `js/dashboard_contract_validator.js` and `scripts/api_dashboard_contract_validator.py` (inspected and referenced as prior art, not duplicated) |
| Existing API routes extended | 0 (none — Phase 0/1 is forensic + additive-only, no route touched) |
| Existing dashboards extended | 0 |
| New engines introduced | 1 — `js/dashboard-state.js` (state-vocabulary constants + pure helpers), justified by the census confirming **no such vocabulary exists anywhere in the codebase today** despite being required by mission Phase 5 |
| Duplicate engines introduced | **0** |
| Duplicate routes introduced | **0** |
| Backward compatibility preserved | PASS — no existing file modified |
| Certification chain intact | PASS — untouched |
| Regression suite result | Not applicable to this PR (no behavior changed); existing suite to be run and reported in the PR itself |

---

*Evidence for every row above was gathered via five parallel, read-only forensic passes plus direct inspection of `js/dashboard_contract_validator.js`, `scripts/api_dashboard_contract_validator.py`, and `dashboard_contract.json`. Full per-domain matrices (severity/priority/risk/CVSS/confidence; IOC/TTP; publication/state/entitlement; freshness/timestamps; rendering-surface architecture) are preserved in this session's working notes and available on request — this document is the synthesized, ranked, cross-referenced version intended for review and PR planning.*
