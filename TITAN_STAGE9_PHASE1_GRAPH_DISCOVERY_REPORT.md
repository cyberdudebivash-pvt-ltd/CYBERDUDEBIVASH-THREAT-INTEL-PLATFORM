# Project TITAN — Stage 9 Phase 1: Graph Discovery Report (Continuation)

**Date:** 2026-08-05
**Status:** Phase 1 (Graph Discovery Validation) — **extended, not closed**. This continuation
picked up mid-triage after a usage-limit interruption and found the inventory materially
larger than Stage 6-8 assumed. Per Stage 9's own charter ("If new graph implementations are
discovered: Stop implementation. Document."), **Phase 4 (Graph Ownership ADR Implementation)
has not begun and does not begin from this report.**
**Scope:** Both repositories (`CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM`, `cyberdudebivash-blog`).
**Supersedes:** Nothing — this is additive to `TITAN_TECH_DEBT_REGISTER.md`, ADR-0010, and
`TITAN_STAGE9_READINESS.md`, all of which are updated separately (see companion edits in this
same commit) rather than silently rewritten.

---

## Continuation context

The prior Stage 9 session stopped mid-investigation after discovering (a) an uncatalogued
FastAPI service (`sentinel-apex-api/`), (b) roughly two dozen previously-unseen graph-related
files, and (c) a comment in `report_ingest.py` appearing to contradict ADR-0010's description
of R2. A subagent spawned to triage the file list failed to run; the last completed step was
launching a second subagent to verify the `report_ingest.py` finding, which did not return
before the limit was reached.

This report re-derives everything from current repository state per this continuation's
instructions ("repository evidence wins"), rather than assuming the prior session's
in-progress conclusions. Where this report's findings differ from what the prior session
appeared to be converging on, that is noted inline.

---

## TASK 1 — Complete Graph Discovery

### 1A. Previously-catalogued implementations (ADR-0010 R1–R5) — re-verified, status changes noted

| ID | System | Repo | Language | Re-verification result |
|---|---|---|---|---|
| R1 | `p31-handlers.js` (`_buildGraph`, `buildP31RelationshipBlock`) | intel-platform | JS (Cloudflare Worker) | Present, unchanged. No persistence layer added since Stage 8 (DEBT-004 still open). |
| R2 | `knowledge_graph.py` (`KnowledgeGraph`) | blog | Python | Present, unchanged code. **Runtime status materially clarified this stage — see Task 4/5.** |
| R3 | `api-extensions.js` (`handleIntelGraph`/`handleIntelRelations`) | intel-platform | JS (Cloudflare Worker) | Present, unchanged. **Producer fully identified this stage — see Task 4 (corrects ADR-0010 Revision 2).** |
| R4 | `api/_lib/threat-graph.js` | blog | JS (Vercel) | Present, unchanged, last touched by the same bulk commit (`5bcccee`, 2026-08-03) as the rest of `api/_lib/`. |
| R5 | `api/_lib/graph-engine.js` + `graph-traversal.js` + `relationship-engine.js` + `correlation-engine.js` | blog | JS (Vercel) | Present, unchanged. Still not deployed (Stage 8 finding stands — see Task 2). **One additional consumer file found this stage: `api/_lib/investigation-graph.js` (constructed with R5's `graphEngine`/`graphTraversal` as dependencies, consumed by `api/v1/workbench/investigations.js`) — falls under the already-confirmed-dead `api/v1/workbench/*` umbrella, not a new live surface. Folded into R5's file list, not given a separate ID.** |

### 1B. Newly-discovered implementations this stage

| ID | System | Repo | Language | Summary |
|---|---|---|---|---|
| **R6** | `core/intelligence/enrichment_graph.py` (`IOCEnrichmentGraph`, module singleton `graph`) | intel-platform | Python | Real, substantial IOC relationship graph engine: pure-Python adjacency graph, thread-safe (RLock), 6-source OSINT enrichment (VirusTotal/AbuseIPDB/Shodan/URLhaus/ThreatFox/OTX), PageRank-like authority scoring, BFS traversal, campaign correlation, actor attribution, STIX 2.1 export, JSON save/load persistence, and a "Phase 6" community-feed merge/export/import capability. **This is functionally the most capable single graph implementation found across either repository.** Not mentioned anywhere in ADR-0010 or the tech debt register before this stage. |
| **R7** | `sentinel-apex-api/app/api/v1/endpoints/intel_graph.py` (`get_correlation_graph`, `get_actor_graph`, `get_campaigns`) | intel-platform | Python (FastAPI) | A fourth, fully independent graph computation, in a **third backend stack** (FastAPI on Railway/Render + Supabase — not Cloudflare Workers, not the Python ingestion pipeline). Reads `data/graph/graph_relationships.stix.json`, `data/intelligence/actor_profiles.json`, `data/intelligence/campaigns_db.json`, `data/apex_enriched_manifest.json`, with a Supabase query fallback. Full detail under Task 3. |
| **Long-tail** | 16 files under `agent/` and `scripts/` with "graph" in the name (`agent/graph/graph_intel.py`, `agent/graph_operations_engine.py`, `agent/graph_integrity_validator.py`, `agent/graph_correlation_engine.py`, `agent/threat_graph/graph_engine.py`, `agent/threat_graph_engine.py`, `agent/v44_threat_graph/graph_models.py`, `agent/v44_threat_graph/threat_graph_engine.py`, `scripts/adversary_graph_engine.py`, `scripts/graph_integrity_validator.py`, `scripts/graph_intelligence_validator.py`, `scripts/graph_intelligence_engine.py`, `scripts/intelligence_knowledge_graph.py`, `scripts/omega_ioc_graph_layer.py`, `scripts/persistent_campaign_graph_engine.py`, `scripts/threat_graph_engine.py`) | intel-platform | Python | **Per-file characterization delegated to a parallel investigation to keep this pass tractable; see Task 1C below for the completed table.** Discovered via `**/*graph*` glob; not individually named by any prior TITAN stage. Two pairs of near-identical filenames across `agent/` and `scripts/` were flagged for duplicate-content verification. |

**Correlation graph note (Task 1's explicit category):** `core/correlation/threat_correlator.py` was checked directly — it is a threat-correlation module but does not implement or reference a graph data structure (no node/edge/adjacency concepts); it is **not** a graph implementation and is excluded from the candidate matrix on that basis, not omitted by oversight.

### 1C. Long-tail file characterization

Completed. Each of the 16 files was read individually and cross-referenced against imports,
`.github/workflows/*.yml`, and git history of its claimed output artifacts.

**Headline result: 9 of 16 are genuinely wired into production (imported and/or scheduled),
6 are complete, well-engineered, but entirely dormant (zero importers, zero CI), and 1
(`agent/graph_operations_engine.py`) is dormant in a way the repository's *own* internal audit
tooling (`demo_truth_audit.json`, `production_gap_registry.json`) already knows about and has
not acted on.** No two files are literal duplicates of each other, including the pairs sharing
a filename — but that is a narrower finding than it sounds: several are independently-written,
non-overlapping implementations of the same concept (four separate "build a threat graph from
advisories" engines that do not know about each other), which is a coordination failure even
without code duplication.

| File | Status | Evidence |
|---|---|---|
| `agent/graph/graph_intel.py` | Dormant (Shadow vs. R6) | Zero importers; demo-only entrypoint; its own output path (`data/graph/intel_graph.json`) does not exist |
| `agent/graph_operations_engine.py` | Dormant | Zero Python importers; the repo's own `demo_truth_audit.json`/`production_gap_registry.json` already flag it "CODE_EXISTS" but never run |
| `agent/graph_integrity_validator.py` | **Production** (6x/day cron, `enterprise-observability.yml`) — but validates an empty target | Imported by `apex_engine.py`, `saas_scale_hardening_engine.py`; fresh telemetry today — but every recorded run shows `nodes:0, edges:0` because its read target (`data/threat_graph/`) has **zero git history ever** |
| `agent/graph_correlation_engine.py` | **Production** (6x/day cron, `enterprise-intel-quality.yml`) — output never observed persisted | Double-imported by 2 orchestrators + direct scheduled CI execution; writes to the same never-committed `data/threat_graph/` |
| `agent/threat_graph/graph_engine.py` | **Production** | Real call site in `apex_engine.py:216`'s main per-advisory `process_advisory()` method (soft import, degrades gracefully if missing) |
| `agent/threat_graph_engine.py` | Dormant (Shadow) | Complete 827-line engine; zero importers; zero CI reference |
| `agent/v44_threat_graph/graph_models.py` + `threat_graph_engine.py` | Dormant/Archived | v44-era versioned scaffolding; only the two files import each other; no CI |
| `scripts/adversary_graph_engine.py` | **Production, currently paused** | `telemetry-fabric.yml` wired it, but the schedule trigger is commented out since 2026-07-29 ("EMERGENCY PAUSE... to conserve GitHub Actions minutes"); manual-dispatch only now. Real past output artifacts exist, timestamped the pause date |
| `scripts/graph_integrity_validator.py` (**different code** from the `agent/` file of the same name) | **Production — most concretely proven of all 16** | 12x/day cron (`enterprise-governance.yml`); output timestamped today; sequential auto-commit history ("governance run #844→#848") |
| `scripts/graph_intelligence_validator.py` | Dormant | Real logic; sole caller (`apex_sovereign_trust_orchestrator.py`) is itself unwired anywhere in the repo |
| `scripts/graph_intelligence_engine.py` | Dormant | Same pattern; sole caller (`apex_sovereign_orchestrator.py`) is itself unwired anywhere |
| `scripts/intelligence_knowledge_graph.py` | **Production (scheduled 4x/day) — possible silent no-op** | Wired in `generate-and-sync.yml` with `continue-on-error: true`; its claimed output files do not exist in `data/graph/` — the schedule may be masking a failure every run |
| `scripts/omega_ioc_graph_layer.py` | **Production — strongest chain in the batch** | Explicitly documented and confirmed as wired at a named step in `agent/sentinel_blogger.py`, reached via the confirmed-live master pipeline (`scripts/run_pipeline.py`) |
| `scripts/persistent_campaign_graph_engine.py` | **Production** | Real active import and per-advisory calls in `sentinel_blogger.py`. **Surfaced a 17th, still-uncatalogued implementation in passing:** `data/ocios/campaign_graph.json` self-identifies as engine `"ocios_campaign_correlation_engine"` — a different component from this file, whose source has not yet been located |
| `scripts/threat_graph_engine.py` | **Production — best-proven file in the batch** | Fresh output today matching its own version banner exactly; explicitly documented as feeding the live `/api/graph/{nodes,edges,pivot}` endpoints via R2 upload |

**`api/graph/graph.json`** (distinct from the live `api/graph/{nodes,edges,stats}.json` produced
today by `scripts/threat_graph_engine.py`): confirmed a **stale, static fixture** — `generated_at`
frozen at `2026-05-29`, over two months old, touched by exactly one broad unrelated maintenance
commit in its entire git history, schema matching none of the 16 files' output formats.

**New finding this stage, elevated as its own tech-debt item (DEBT-020): a "zombie pipeline"
pattern.** Two separately-scheduled, separately-imported production scripts
(`agent/graph_correlation_engine.py`, writing; `agent/graph_integrity_validator.py`, reading —
both 6x/day, both real production wiring) form a complete write/validate loop against
`data/threat_graph/` — a directory with **zero commits in this repository's entire git
history.** The validator reports clean, structurally-valid runs every time (`nodes:0, edges:0`
is not flagged as anomalous by its own logic) — the CI signal is green, but the underlying data
flow has, as far as this repository's history shows, never once worked. `scripts/
intelligence_knowledge_graph.py` shows the same shape (scheduled 4x/day, `continue-on-error:
true`, no observed output). This is a stronger, more concrete instance of the general concern
`TITAN_TECH_DEBT_REGISTER.md`'s pre-existing DEBT-015 already raised in the abstract ("no
discoverable monitoring/alerting story") — here, specific scheduled jobs are demonstrably
running green while accomplishing nothing observable.

**Residual gap update — closed, then reopened one layer deeper.** The newly-extended CI
governance check (Task 9) was run immediately after being written, and on its first execution
located the previously-missing `"ocios_campaign_correlation_engine"` source:
`scripts/ocios_campaign_correlation_engine.py` — a real, documented engine ("OCIOS Phase 1 —
Campaign Correlation Engine"), whose own docstring explicitly differentiates itself from
`ai_brain_publisher.py`, `threat_actor_profiler.py`, and `enterprise_scoring_engine` ("WHAT
THIS ENGINE DOES that nothing else in the stack does") — itself acknowledging the platform's
fragmentation pattern in its own header. Imported by three sibling scripts
(`ocios_soc_prioritization_engine.py`, `ocios_coordinator.py`,
`ocios_operational_reasoning_engine.py`) plus `kev_feed_marker.py`, consistent with genuine
production use within a coordinated `ocios_*` subsystem family (CI-scheduling not
independently re-verified this pass).

**The same check run also surfaced five more previously-uncatalogued files** that this stage's
original `**/*graph*` glob missed entirely, because they are named for "correlation" without
the word "graph": `agent/threat_graph/correlation_engine.py` (sibling of the already-confirmed-
production `agent/threat_graph/graph_engine.py`), `agent/v70_apex_upgrade/engines/
correlation_engine.py` (notable: `scripts/run_pipeline.py` does invoke
`agent.v70_apex_upgrade.orchestrator` as a subprocess — this file may sit in a live-adjacent
versioned subsystem, unlike the confirmed-archived v26/v44 trees), `agent/v26/ioc_correlation.py`
(likely archived, matching the v26/v44 versioned-legacy pattern), `scripts/
cve_correlation_engine.py`, and `scripts/adversary_correlation_engine.py`. **None of these five
are characterized in this report** — deliberately left as open governance-check findings (see
`titan_architecture_governance_check.py`'s updated allowlist comment) rather than assumed
benign, consistent with this stage's own discipline. This is presented as evidence the
discovery process itself is now self-sustaining (the tooling built this stage immediately found
gaps the manual pass left), not as a failure of this pass — see Task 10.

---

## TASK 2 — Runtime Reachability

| ID | System | Runtime status | Evidence |
|---|---|---|---|
| R1 | `p31-handlers.js` | **Production** | `/api/v1/p31/graph` → HTTP 402 (Stage 8 live verification) — real, tier-gated route, part of the standard P-layer chain in `workers/intel-gateway/src/index.js`. |
| R2 | `knowledge_graph.py` | **Internal / manual tool — not scheduled automation** (revised this stage) | `KnowledgeGraph()` is constructed only at `Sentinel-APEX/engine/cli.py:156` and in the repo's own test suite. `pipeline.py:61` calls `.ingest()` as part of the automated `SourceDocument → NormalizedDoc` path, but **no blog workflow invokes `cli.py`, `pipeline.py`, or anything under `sentinel_engine/`** — `intelligence-engine-ci.yml` (the only workflow referencing this tree) only runs `pytest tests/` and a `py_compile` check on push, never real ingestion. The real, high-frequency auto-publish automation (`ai-security-intel.yml`, source of the frequent "SENTINEL APEX AI-SEC: pub=N" commits) does not reference `sentinel_engine` at all. `platform/open-issues.md` Issue 9 independently confirms this in the repo's own words: *"`KnowledgeGraph()` was never constructed anywhere except `cli.py run`/`score`"* — and that issue's title describes the one known real ingestion (`SA-2026-0001`) as discovered by **running it for the first time**. `Sentinel-APEX/knowledge-graph.json` (the persisted output) is static at the same bulk-commit timestamp as everything else, corroborating no ongoing automated refresh. |
| R3 | `api-extensions.js` | **Production** | `/api/v1/intel/graph` → HTTP 403 (Stage 8 live verification) — real, tier-gated route. **Its data source's own production status is separately unconfirmed — see R6 below and Task 4.** |
| R4 | `api/_lib/threat-graph.js` | **Production** | Reconfirmed live via `api/v1/intel.js`, per Stage 7/8 (unchanged this stage; not independently re-curled since no code changed). |
| R5 | `graph-engine.js`/`graph-traversal.js`/`relationship-engine.js`/`correlation-engine.js` (+ `investigation-graph.js`) | **Dormant (not deployed)** | Stage 8 confirmed all named consumers (`api/v1/intelligence/{graph,correlations}.js`, `api/v1/workbench/*`) return Vercel's platform-level `NOT_FOUND`. `investigation-graph.js`'s consumer (`api/v1/workbench/investigations.js`) falls under that same dead `workbench/*` umbrella. |
| **R6** | `enrichment_graph.py` | **Code is production-quality; execution trigger unconfirmed** | The engine itself is well-built and is imported successfully by `core/orchestrator.py` (`R2AIExportStage`, which calls `intel_graph.export_snapshot()` and writes it to Cloudflare R2 storage). **No file under `.github/workflows/` invokes `core/orchestrator.py`** — a precise grep for `core.orchestrator`/`core/orchestrator.py`-style invocations across all 9 workflow files that merely contain the English word "orchestrator" (`master-deployment-orchestrator.yml`, `sovereign-platform.yml`, `post-deploy-validation.yml`, `revenue-orchestrator.yml`, `platform-build-deploy.yml`, `enterprise-intel-quality.yml`, `sentinel-blogger.yml`, `precognition-engine.yml`, `omnishield.yml`) returned zero matches. The repo's confirmed-live master pipeline (`scripts/run_pipeline.py`, invoked at `sentinel-blogger.yml:604`, triggered on every push to `main`) does **not** import `core.pipeline` or `core.orchestrator` at all — it is a separate, monolithic implementation. R6's only other consumer is R7 (`sentinel-apex-api`), which has no confirmed deployment (below). **This is a materially different and more concerning finding than "producer identified" — the producer is identified, but its execution is not confirmed to happen at all**, which bears directly on the freshness of the data R3's live, tier-gated, paying-customer route serves. Caveat, consistent with this program's standing practice (cf. DEBT-015): absence of in-repo scheduling evidence is not proof no external scheduler exists; it is proof none was found in this repository. |
| **R7** | `sentinel-apex-api/.../intel_graph.py` | **No confirmed live deployment** | See Task 3 in full. Summary: deploy-to-Railway CI workflow is misplaced (`sentinel-apex-api/.github/workflows/sentinel-apex-api`, no `.yml` extension — GitHub Actions only discovers workflows under the repo-root `.github/workflows/`, so this can never have triggered). `app.cyberdudebivash.com` (the domain named in the app's own CORS config and root-endpoint links) failed to resolve/connect via direct HTTPS probe (baseline domains `blog.cyberdudebivash.in` and `intel.cyberdudebivash.com` both returned clean HTTP 200 in the same test batch, so this is not a proxy-wide failure). `intel.cyberdudebivash.com/api/v1/intel/graph/correlations` (sentinel-apex-api's own route shape, tested against the Worker's real domain) → HTTP 404, confirming these routes are not merged into the Worker either. |
| Long-tail (16 files) | various | **9 Production (scheduled and/or imported), 6 Dormant, 1 paused-since-2026-07-29** | See Task 1C — full per-file table with evidence. Two of the "Production" scripts write to a directory (`data/threat_graph/`) with zero git history despite a third script validating it 6x/day and reporting clean — see the "zombie pipeline" finding (DEBT-020). |

---

## TASK 3 — FastAPI Assessment (`sentinel-apex-api/`)

**Purpose.** A complete, separately-versioned, production-grade FastAPI application
("SENTINEL APEX API", independently versioned from the Worker's v184.0 line) implementing what
its own OpenAPI description calls the commercial API surface: Feed, Search, SOC/threat-hunting,
CSV/STIX/Sigma/YARA export, MISP export, SIEM dispatch (Splunk/Sentinel/QRadar/Elastic),
**Intel Graph** (`intel_graph.py` — correlation graph across advisories/IOCs/actors/TTPs),
MSSP multi-tenancy, and GDPR/CCPA compliance endpoints.

**Routes (registered in `app/main.py`):** `auth`, `feed`, `keys`, `usage`, `soc`,
`enterprise_ai`, `payment`, `export`, `compliance`, `intel_graph`, `mssp` — 11 routers, a
materially larger surface than a stub or prototype.

**Authentication.** Its own, separate auth system (`app/auth/dependencies.py`,
`get_current_user`/`require_tier`), backed by Supabase (`app/db/client.py`, JWT via
`SUPABASE_JWT_SECRET`) — **entirely independent of the Cloudflare Worker's auth.** Two
parallel, non-shared authentication systems for what is nominally the same platform.

**Graph ownership.** `intel_graph.py` computes its own correlation graph at request time from
static JSON files (`data/graph/graph_relationships.stix.json`, `data/intelligence/
actor_profiles.json`, `data/intelligence/campaigns_db.json`, `data/apex_enriched_manifest.json`)
with a Supabase-query fallback. This is a **fourth independent "give me the relationship graph"
code path** (after R1, R3, R6), sharing no code with any of them, in a language/runtime that is
shared with R6 (Python) but not with R1/R3 (JS/Worker), and a storage backend (Supabase/Postgres)
shared with nothing else in this inventory.

**Dependencies.** `requirements.txt` (Supabase client, FastAPI, uvicorn — standard,
production-shaped Python web stack), `migrations/001_foundation_schema.sql` (a real Postgres
schema migration exists), `tests/test_api.py` (a test suite exists).

**Deployment.** Three deployment configs exist simultaneously — `railway.toml`, `render.yaml`,
`Procfile`, `Dockerfile` — all pointing at the same `uvicorn app.main:app` entrypoint, suggesting
either genuine multi-target flexibility or unresolved indecision between hosting providers.
**The CI/CD workflow that would deploy it to Railway on push (`sentinel-apex-api/.github/
workflows/sentinel-apex-api`) is misplaced**: GitHub Actions requires workflow files under the
repository root's `.github/workflows/`, not a subdirectory's own `.github/workflows/`. This file
additionally lacks the `.yml`/`.yaml` extension GitHub requires. **Both defects independently
prevent this workflow from ever having been discovered or triggered by GitHub.** No other
evidence of deployment (no reachable custom domain, no matching route on the Worker's domain)
was found.

**Current usage.** No confirmed live traffic. `render.yaml`'s CORS config allows
`https://app.cyberdudebivash.com` as an origin, and `app/main.py`'s root endpoint links to that
same domain as `"app"` — a domain not mentioned in any prior TITAN stage. Direct HTTPS probe
against `app.cyberdudebivash.com` failed to establish a connection (proxy CONNECT tunnel
failure), while baseline probes against both known-live platform domains
(`blog.cyberdudebivash.in`, `intel.cyberdudebivash.com`) succeeded cleanly in the same test
batch — evidence, not proof, that this domain is not currently provisioned.

**Relationship to Sentinel APEX / P31 / ADR-0010.** No code-level relationship at all — no
shared imports with `workers/intel-gateway`, no shared imports with `core/pipeline` or
`core/orchestrator` (R6's producer chain), no reference to P31. It is architecturally adjacent
only in subject matter (it computes "a relationship graph" for the same conceptual entities),
not in implementation. ADR-0010 does not mention it because no prior stage had found it.

**Classification: this is a legacy/parked subsystem, not a canonical, secondary, experimental,
compatibility-layer, or future-platform candidate in the sense ADR-0010's framework
anticipated.** It is too complete and too deliberately engineered to read as abandoned
scaffolding (real auth, real Supabase schema, real tests, real multi-provider deploy configs),
but its deploy path has never functioned and no evidence of live traffic exists. The most
defensible reading: **a real, substantial build-out that stalled before its CI was wired up
correctly**, sitting fully outside this program's prior visibility. It cannot be assessed as
"the canonical graph," "a compatibility adapter," or "safely archived" without a human
confirming intent — see Task 7.

---

## TASK 4 — Graph Producer Trace

Traced by reading actual execution paths (imports, instantiation sites, CI invocations), not
comments, per this task's explicit instruction.

```
core/intelligence/enrichment_graph.py
  └─ class IOCEnrichmentGraph, module singleton `graph`
  └─ .export_snapshot() — docstring: "Worker-consumable snapshot... expected by
     handleIntelGraph and handleIntelRelations in the Cloudflare Worker"
        │
        ▼ (imported by)
core/orchestrator.py:164  — from core.pipeline.stages import R2AIExportStage
core/orchestrator.py:199  — "r2_ai_export": R2AIExportStage()
        │
        ▼ (R2AIExportStage, core/pipeline/stages.py:1373-1526, calls intel_graph.export_snapshot())
boto3 S3-compatible client → Cloudflare R2 bucket (env R2_BUCKET_NAME, default
  "sentinel-apex-intel") → r2.put_object(Key="data/ai/intel_graph.json", ...)
        │
        ▼ (read by)
workers/intel-gateway/src/api-extensions.js — handleIntelGraph / handleIntelRelations (R3)
        │
        ▼ (served at)
GET /api/v1/intel/graph → HTTP 403 (tier-gated, confirmed live, Stage 8)
```

**This corrects ADR-0010 Revision 2's factual claim.** Revision 2 states R3 "reads a
separately-generated `data/ai/intel_graph.json` snapshot **from R2**" — using "R2" to mean
ADR-0010's own graph-implementation label for the blog's `knowledge_graph.py`. That is
incorrect. **The actual producer is `core/intelligence/enrichment_graph.py` — a same-repository,
intel-platform-native Python module with no relationship whatsoever to the blog's
`KnowledgeGraph`.** The word "R2" in this codebase's own comments (`core/pipeline/stages.py`'s
section header "R2 Export Snapshot," its log line `"[{self.name}] R2 AI exports:"`) refers to
**Cloudflare R2 object storage**, not to ADR-0010's R2 graph-implementation ID. This is a
genuine terminology collision between this program's own ADR-0010 vocabulary and Cloudflare's
product name, and it appears to have caused a real factual error in Revision 2, written under
time pressure without reading `core/pipeline/stages.py`'s actual body. Flagged per this
continuation's instruction to document discrepancies explicitly rather than silently correct
governance documents — see the dated revision appended to ADR-0010 itself.

**Second-order finding:** having corrected the producer's identity, its production execution
status is *itself* unconfirmed — see Task 2 (R6) above. The chain is code-correct end to end
but no confirmed trigger exists in-repo for the `core/orchestrator.py` step.

**R7 (sentinel-apex-api)'s producer trace** is short by comparison: `intel_graph.py` reads
static files directly (no intermediate producer script found) or falls back to a live Supabase
query. `data/graph/graph_relationships.stix.json` (the primary file it reads) has no
in-repo writer found — it is either populated by a process outside this repository, or is a
stale/manually-placed fixture. Not resolved this stage; flagged as a new tech-debt item (see
`TITAN_TECH_DEBT_REGISTER.md`).

---

## TASK 5 — ADR Validation (ADR-0010)

**Determination: Major Revision required.** Not a replacement (the core Decision — R1
target-canonical, contingent on persistence — is not contradicted by anything found this
stage), but the evidentiary basis for two of the ADR's specific claims is wrong or incomplete
in ways that matter to anyone relying on this document:

1. **Factual correction (high confidence):** Revision 2's claim that R3 reads a snapshot "from
   R2" conflates Cloudflare R2 storage with ADR-0010's own R2 label. The real producer (R6,
   `core/intelligence/enrichment_graph.py`) is uncatalogued in the ADR entirely.
2. **New candidate requiring a decision, not just a footnote:** R6 is, on functional merit, the
   most capable graph engine found in this inventory (persistence, OSINT enrichment, STIX
   export, authority scoring) and sits in the *same repository* as R1 — the same
   low-friction, no-cross-repo-negotiation situation Revision 2 already identified as the
   highest-priority reconciliation target for R1-vs-R3. That reconciliation question is now
   more accurately "R1 vs. R6" (R3 is a thin reader over R6, not an independent computation).
3. **New candidate requiring a decision:** R7 (`sentinel-apex-api`) is a fourth, architecturally
   distinct implementation (third backend stack, third auth system, third storage backend) that
   the ADR's "five-way fragmentation" framing (even at its most expansive, Stage 7's Revision 1)
   never anticipated. Whether R7 is in scope for this ADR at all — given no confirmed
   deployment — is itself a question the ADR does not yet answer.
4. **R2's runtime characterization needs qualification, not replacement.** ADR-0010's "Existing
   Implementations" table lists R2's consumer as "Report generation pipeline," which reads as
   an active, running system. This stage's evidence (Task 2) supports "correct, tested,
   real code, exercised only manually" more than "production pipeline." This changes the
   ADR's migration-urgency calculus (a manually-run tool has a different deprecation
   posture than a live pipeline) without changing the ownership Decision itself.

A dated "Revision 3" section has been appended to `docs/adr/0010-relationship-graph-ownership.md`
in this same commit, following the exact pattern of Revisions 1 and 2 — prior sections are
unmodified.

---

## TASK 6 — Canonical Graph Candidate Matrix

*No ownership decisions are made in this table — descriptive only, per this task's explicit
instruction.*

| ID | Name | Repo | Lang | Consumers | Runtime | Traffic evidence | Strengths | Weaknesses | Migration risk | Canonical candidate? | Compat. candidate? | Archive candidate? | Deprecation candidate? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 | `p31-handlers.js` | intel-platform | JS | P31 routes | Production | `/api/v1/p31/graph` → 402 | System-of-record precedent; live; part of governed P-layer chain | No persistence (DEBT-004); no OSINT enrichment | Low (already canonical-designate) | **Yes** (ADR-0010 target, unchanged) | — | — | — |
| R2 | `knowledge_graph.py` | blog | Python | `cli.py` (manual) | Internal/manual | None found (Task 2) | Persistent JSON; richer edge vocabulary than R1; well-tested | Not automated; cross-repo from intel-platform's perspective | Medium (deprecation posture depends on whether any human process still relies on manual runs) | No | Possibly (edge vocabulary reuse, per ADR-0010's existing Future Considerations) | No | Candidate — but only after confirming no manual-workflow dependency |
| R3 | `api-extensions.js` | intel-platform | JS | `/api/v1/intel/graph` | Production (route); data freshness unconfirmed | 403, tier-gated, real | Live, paying-tier route | Thin reader with no independent logic; entirely dependent on R6's unconfirmed pipeline | Medium — any resolution must account for R6, not just R3's own code | No (thin layer, not a real independent implementation) | **Yes** — could become R1's or R6's read path | No | No — but its data-freshness gap needs a decision, not silent trust |
| R4 | `api/_lib/threat-graph.js` | blog | JS | `api/v1/intel.js` | Production | Live per Stage 7/8 | Real curated actor data (8 actors, per Issue 15) | Cross-repo from intel-platform's perspective; blog's own CLAUDE.md "STRICT SEPARATION" rule arguably applies | Medium-High (cross-repo, live traffic) | No | Possible | No | Candidate, cross-repo negotiation required |
| R5 | `graph-engine.js` + cluster | blog | JS | none live | Dormant | Confirmed not deployed (Stage 8) | Most capable *design* on paper (34 entity types, 31 relationship types, Redis-backed) | Zero live consumers; violates blog CLAUDE.md separation rule by existing at all | Low (nothing depends on it) | No (no live consumer to migrate) | No | **Yes** | Yes — no traffic, lowest-friction item in this table |
| **R6** | `enrichment_graph.py` | intel-platform | Python | R3 (via R2 storage), potentially R7 | Code-correct; execution unconfirmed | None found in-repo (Task 2) | Most functionally complete engine in the inventory; already same-repo as R1; already exports a Worker-compatible snapshot shape | Different language/runtime than R1 (Python vs. JS/Worker) — a real integration cost even if adopted; execution trigger missing | **High** — any decision here inherits both "is this even running" and "how does Python-engine output reach a Cloudflare Worker" | **Plausible strong candidate** — functionally ahead of R1, but needs the execution-trigger question resolved first | Yes — natural persistence donor for R1 per ADR-0010's existing Future Considerations, now with a concrete implementation to point at | No | No |
| **R7** | `sentinel-apex-api/intel_graph.py` | intel-platform | Python (FastAPI) | none confirmed live | No confirmed deployment | `app.cyberdudebivash.com` unreachable; CI never triggered; no matching route on Worker domain | Real auth, real Supabase schema, real tests — substantial engineering investment | Entirely separate backend/auth/storage stack; broken CI; unclear product intent | **High** — deciding this touches a whole parallel platform, not just a graph algorithm | No (too disconnected from the rest of the stack as currently found) | Unclear — depends on whether `app.cyberdudebivash.com` is real product intent | Possible | Possible — but archiving a substantial unlaunched service needs a human product decision, not an engineering default |
| Long-tail: 9 production files (`agent/graph_integrity_validator.py`, `agent/graph_correlation_engine.py`, `agent/threat_graph/graph_engine.py`, `scripts/adversary_graph_engine.py` [paused], `scripts/graph_integrity_validator.py`, `scripts/intelligence_knowledge_graph.py` [possible silent no-op], `scripts/omega_ioc_graph_layer.py`, `scripts/persistent_campaign_graph_engine.py`, `scripts/threat_graph_engine.py`) | various | intel-platform | Python | Mostly each other (orchestrators: `apex_engine.py`, `sentinel_blogger.py`) + scheduled CI | Production (see Task 1C for per-file nuance — several write to data never observed persisted) | Fresh timestamps/commits on most; `data/threat_graph/` has zero history despite 2 scheduled scripts targeting it | `threat_graph_engine.py` demonstrably feeds a live API; `omega_ioc_graph_layer.py` has the cleanest proven chain | Four independent "build a threat graph" engines unaware of each other; at least 2 scheduled jobs appear to run against data that never lands | High — none of these were in ADR-0010's scope before this stage, and several have real scheduled executions that could conflict with any future R1/R6 consolidation | No individually — none show the system-of-record precedent or persistence-plus-API-surface combination R1/R6 have | Some (`omega_ioc_graph_layer.py`'s per-advisory enrichment could feed a canonical graph rather than embedding directly in STIX metadata) | No — several have real, current scheduled executions | Not without a human decision — "paused," "possibly silently failing," and "genuinely live" are three different states mixed in this set |
| Long-tail: 6 dormant files (`agent/graph/graph_intel.py`, `agent/graph_operations_engine.py`, `agent/threat_graph_engine.py`, `agent/v44_threat_graph/graph_models.py`+`threat_graph_engine.py`, `scripts/graph_intelligence_validator.py`, `scripts/graph_intelligence_engine.py`) | various | intel-platform | Python | None (zero importers each) | Dormant | None found | Some are well-engineered (e.g. `agent/threat_graph_engine.py` is a complete 827-line "zero-failure" orchestrator) | Zero live consumers each; one is versioned-legacy (v44) | Low (nothing depends on them) | No | No | **Yes, all 6** — no traffic, no importers, lowest-friction items in this entire matrix | Yes — same low-friction profile as R5 |
| **Residual/unresolved:** `ocios_campaign_correlation_engine` | Unknown — source file not located | intel-platform | Python (inferred) | Unknown | Unknown | `data/ocios/campaign_graph.json` self-identifies with this engine name | Unknown | Cannot assess — not yet located | Unknown until located | Unknown | Unknown | Unknown | Unknown — flagged as open, not resolved, per this stage's discipline |

---

## TASK 7 — Implementation Authorization Check

## Decision: **BLOCKED**

More blocked than Stage 8's own Stage 9 readiness assessment anticipated, not less. Every
precondition that assessment named is still open, and this stage added new ones.

| # | Blocker | Reason | Required before Phase 4 |
|---|---|---|---|
| 1 | ADR-0010 not Accepted | All three sign-off boxes remain unchecked on current `main` (re-verified this stage) | Human Acceptance review — unchanged from Stage 8/9-readiness, still nobody's action item has been completed |
| 2 | ADR-0010's factual basis just changed | Revision 2's R3-producer claim is corrected this stage (Task 4/5) | Reviewer sign-off must happen against the corrected ADR text, not the pre-correction version — re-review, not just review |
| 3 | R6 uncatalogued until this stage | The most functionally capable graph engine found across both repos was not part of any ownership discussion before now | ADR-0010 needs an explicit R6 disposition before any canonical decision can be called complete |
| 4 | R7 (`sentinel-apex-api`) uncatalogued until this stage | An entire parallel backend/auth/storage stack with its own graph computation was not part of any prior TITAN inventory | Requires a human product/architecture decision (is this real, parked, or should-be-archived?) that this program cannot make unilaterally |
| 5 | R6's production execution is unconfirmed | The producer for a live, tier-gated, paying-customer route (R3) has no confirmed trigger in this repository | Requires engineering confirmation (external scheduler? one-time manual run? genuinely never run?) before any migration work could safely assume "R6 keeps running as it does today" |
| 6 | Long-tail inventory (16 files) — **now closed out this session** | Task 1C complete: 9 Production, 6 Dormant, 1 paused | No further action to unblock this specific item, but its findings (below) add new blockers |
| 7 | DEBT-000B's original framing (R1 vs. R3) is now known to be imprecise | The real question is R1 vs. R6, which changes what "reconciling them" would even mean | Tech debt register updated this stage (see below); no code changes follow from a register update alone |
| 8 | "Zombie pipeline" pattern found in the long tail | Two scheduled, production-wired scripts (`agent/graph_correlation_engine.py` writing, `agent/graph_integrity_validator.py` reading, both 6x/day) form a write/validate loop against `data/threat_graph/`, a directory with zero git history — the CI signal is green while the underlying data flow appears to have never worked | Requires engineering investigation into why persistence never lands (path mismatch? write failure swallowed by the "zero-failure" design pattern? gitignored output that's real but untracked?) before any claim about "what data these production scripts actually produce" can be trusted |
| 9 | A 17th implementation surfaced but not located (`ocios_campaign_correlation_engine`) | Evidenced only by its output file's self-identification; source not found in this pass | Locate and characterize before Phase 1 can be called genuinely complete |

**No conditions exist under which Phase 4 could reasonably begin from this state.** This is not
a "GO WITH CONDITIONS" situation — the newly-discovered items are large enough (a second graph
engine that's arguably better than the ADR's target-canonical choice, and an entire uncatalogued
backend) that proceeding to Phase 4 planning around the pre-this-stage picture would mean
designing shared interfaces (Phase 5) and a migration layer (Phase 6) around an incomplete
model of what exists. Phase 5-6's own instruction — "do not introduce vendor-specific
implementations" / "must be transparent" — cannot be honored with confidence while two major
implementations were unknown an hour ago.

---

## TASK 8 — Technical Debt Update

Applied directly to `TITAN_TECH_DEBT_REGISTER.md` in this same commit (register maintenance
discipline: close-by-status-change, never delete). Summary of changes — full text in the
register itself:

- **DEBT-013** — status updated from "producer unidentified" to **producer fully identified
  (R6, `core/intelligence/enrichment_graph.py` via `core/orchestrator.py`'s `R2AIExportStage`)**,
  with a new sub-finding that the identified producer's execution trigger is itself unconfirmed.
- **DEBT-000B** — reframed from "R1 vs. R3" to **"R1 vs. R6"** (R3 is a thin reader, not an
  independently-computing implementation) — same Critical severity, corrected technical target.
- **New: DEBT-016** — `sentinel-apex-api` is a substantial, uncatalogued, non-functionally-deployed
  parallel backend (Critical — largest single new-ungoverned-surface finding this stage, same
  category as DEBT-001's `lib/` tree).
- **New: DEBT-017** — R3's live, tier-gated route has no confirmed automated data-refresh
  mechanism (High — commercial/customer-trust risk, paying-tier customers).
- **New: DEBT-018** — long-tail graph file sprawl in `agent/`/`scripts/`, now fully
  characterized: 9 Production, 6 Dormant, 1 paused, plus one unlocated 17th implementation
  (`ocios_campaign_correlation_engine`) — High, four uncoordinated "build a threat graph"
  engines is a coordination failure independent of the zombie-pipeline finding below.
- **New: DEBT-019** — R2 (`knowledge_graph.py`) confirmed manual-only, not automated (Medium —
  documentation/ADR-accuracy item, not an active production risk).
- **New: DEBT-020** — "zombie pipeline" pattern: scheduled, CI-wired graph scripts writing to
  and validating a directory (`data/threat_graph/`) with zero git history, reporting clean
  every run (Critical — CI signal is actively misleading, not merely absent, a materially
  worse failure mode than DEBT-015's general observability gap).

---

## TASK 9 — CI Governance Extension

Extended `scripts/titan_architecture_governance_check.py` with new advisory (report-only, non-
blocking, matching the script's existing rollout convention) checks — full detail in that file's
own updated module docstring. New checks added this stage:

1. A hand-maintained allowlist of every graph implementation now known (R1-R7 plus the Task 1C
   long-tail once finalized) — flags any *new* graph/relationship/correlation-shaped top-level
   Python class or function appearing under `core/`, `agent/`, `scripts/`, or `sentinel-apex-api/`
   that isn't already accounted for, mirroring the existing JS scorer-drift check's design.
2. A producer-chain sentinel — confirms `core/orchestrator.py` still imports `R2AIExportStage`
   and that `api-extensions.js` still references `data/ai/intel_graph.json`, so if this chain is
   silently changed or removed, the next governance run surfaces it rather than letting the
   documented trace go stale unnoticed.
3. An ADR-0010 sync check — confirms the ADR file still exists and still mentions each tracked
   graph-implementation ID.

No automatic fixes; report-only, per this task's explicit instruction.

---

## TASK 10 — Stage 9 Readiness Report

**Current status:** Stage 9 Phase 1 (Graph Discovery Validation) is **substantially extended
and, for the first time, believed near-complete for this repository pair** — with one explicit
exception (below). This continuation closed several specific open threads (DEBT-013's producer,
the `report_ingest.py`/GIKEP-GTIEP concern, the FastAPI subsystem's classification, and the full
16-file long tail) but in the process surfaced findings at least as consequential as what it
closed: R6, R7, and a "zombie pipeline" pattern affecting live CI signal integrity.

**Completed this stage:**
- Full re-verification of R1-R5 against current repository state (no drift found beyond the
  R5-cluster file-count addition).
- R6 discovered, fully traced end-to-end (code path), and functionally characterized.
- R7 (`sentinel-apex-api`) discovered and fully assessed (Task 3).
- The 16-file long tail fully characterized (Task 1C): 9 confirmed Production, 6 confirmed
  Dormant, 1 confirmed paused-since-2026-07-29.
- DEBT-013 resolved to a specific, named, same-repo Python module — with an important caveat
  (execution trigger unconfirmed) that keeps it from being a clean close.
- The `report_ingest.py`/"GIKEP" thread resolved: real, already-merged remediation code
  (`report_ingest.py`, tied to a pre-TITAN initiative called GIKEP/GTIEP v1, documented in
  `platform/open-issues.md` Issues 9 and 15) that correctly narrows — but does not eliminate —
  a real gap in R2's production reach.
- A previously-unknown "zombie pipeline" pattern found: scheduled, CI-wired production scripts
  writing to and validating a directory with zero git history, reporting clean every run — a
  concrete instance of a class of risk this program had only discussed abstractly before
  (DEBT-015).
- ADR-0010 validated against all of the above; Major Revision applied as a dated, additive
  section (Revision 3), consistent with this program's non-silent-rewrite discipline.

**Remaining work (blocking Phase 1 closure, in priority order):**
1. Characterize the 5 files the new governance check surfaced on its first run
   (`agent/threat_graph/correlation_engine.py`, `agent/v70_apex_upgrade/engines/
   correlation_engine.py`, `agent/v26/ioc_correlation.py`, `scripts/cve_correlation_engine.py`,
   `scripts/adversary_correlation_engine.py`) — the 17th implementation
   (`ocios_campaign_correlation_engine`) that was this report's original residual gap **was**
   located and characterized this session, via that same check.
2. Investigate the zombie-pipeline finding's root cause (DEBT-020) — without knowing *why*
   `data/threat_graph/` never persists despite two scheduled writers/validators, no claim about
   what these production scripts actually accomplish can be fully trusted.
3. Human confirmation of `sentinel-apex-api`'s actual status/intent (parked build-out vs.
   should-be-archived vs. should-be-finished) — an organizational decision, not an engineering
   one, matching this program's precedent for similar findings (cf. `lib/` tree, DEBT-001).
4. Engineering confirmation of whether `core/orchestrator.py` executes anywhere outside this
   repository (external scheduler, one-time manual run, or genuinely never) before R3's data
   freshness can be trusted at face value.
5. Human Acceptance review of ADR-0010 (Revision 3) and the other four ADRs still sitting
   Proposed since Stage 6 — unchanged, still nobody's completed action item.

**Risks:** The pattern across Stages 7, 8, and this continuation is consistent — each discovery
pass has found the true inventory larger than the previous pass assumed. This continuation
found the largest single-session addition yet (R6, R7, plus 16 long-tail files — 9 of them
genuinely live), which is the *opposite* of the program's stated "trending down" success metric
(`TITAN_STAGE9_READINESS.md`'s own framing). The zombie-pipeline finding is a new risk category
for this program specifically: prior stages found *undiscovered* systems; this one found
*actively running, CI-green* systems that appear to accomplish nothing, which is arguably a
higher-trust-cost failure mode than an undiscovered dormant file, because green CI is actively
relied upon elsewhere in this program's own certification chain.

**Authorization recommendation:** **BLOCKED** (Task 7, full reasoning above). Do not begin
Phase 4. Do not build shared interfaces (Phase 5) or a migration layer (Phase 6) against the
pre-this-stage model of the graph landscape.

**Next implementation milestone (once unblocked):** Resolve R1-vs-R6 (not R1-vs-R3) as DEBT-000B's
corrected target — same-repo, same-team, no cross-repo negotiation, the same low-friction
rationale Stage 8 already established for prioritizing this over the cross-repo R1-vs-R2/R4
question. This remains the highest-confidence path to an actual canonical decision once ADR-0010
is Accepted and the long tail is closed out.
