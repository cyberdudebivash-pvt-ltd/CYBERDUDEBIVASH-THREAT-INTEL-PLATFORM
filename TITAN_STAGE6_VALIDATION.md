# Project TITAN — Stage 6 Task 1: Discovery Validation

**Status:** Complete. This document validates `CONFIDENCE_FRAMEWORK_DISCOVERY.md` (Stage 4)
and `EVIDENCE_ENGINE_DISCOVERY.md` (Stage 5) against the repository state as of this stage,
per this continuation task's instruction to verify before writing ADRs, and to document —
not silently correct — any discrepancy found. Two genuine discrepancies were found. Neither
invalidates Stage 4/5's conclusions; both extend them. They are carried into ADR-0007 through
ADR-0011 (`docs/adr/`) rather than corrected here.

---

## 1. What was re-verified and confirmed accurate

| Claim (Stage 4/5) | Re-verification method | Result |
|---|---|---|
| `computeEnterpriseTrustScore()` (P25) imported by 12 files | Re-read Stage 4's Part A1 citation list against current `workers/intel-gateway/src/` | Still accurate — no new imports removed, no consumers lost |
| `evidence_chain.reliability_code` (P20) not read by P25 | Re-read P20/P25 handler bodies | Still accurate — the two remain disjoint |
| `buildEvidenceAttribution` (P18) independently computed, A–E scale, substring-matched | Re-read `p18-handlers.js` | Still accurate |
| P23 gate `!!(ec && ec.source_reliability)` | Re-read `p23-handlers.js` | Still accurate |
| Regression suite 21/21 | Ran `scripts/regression_tests.py` | **21 PASS, 0 FAIL of 21** — confirmed live |
| P33 certification WORLDWIDE_RELEASE, 0 blockers | Ran `scripts/p33_production_certification.py` | **TIER: WORLDWIDE_RELEASE, PASSED 21/26, BLOCKERS: 0** — confirmed live |
| No merged code since PR #108 has touched P20/P25/P18/P23/P30/P31's cited functions | `git log --oneline` on `p18-handlers.js`, `p20-handlers.js`, `p25-handlers.js` since `6b3bd273` | No commits touch these files since Stage 4/5 merged |
| PR #106/#107/#108 all merged, branch clean | `git status`, `git log` | Confirmed — working tree clean on `claude/titan-adrs-roadmap-oezwh5`, matches `origin` |

CI still reflects the architecture the discovery docs describe. No duplicate P-layer
implementations were introduced by merged code since PR #108. Discovery findings for the
intel-platform repo's P16–P33 stack remain accurate as written.

---

## 2. Discrepancy 1 — Stage 4/5's blog-repo search was scoped, not repo-wide, and missed a second confidence/evidence system

### What Stage 4 actually searched

`CONFIDENCE_FRAMEWORK_DISCOVERY.md` §"Scope and method" states the search covered "this
repo's `workers/`, `agent/`, and `scripts/` directories, **plus 2 in the blog repo's
`engine/sentinel_engine/`**." `EVIDENCE_ENGINE_DISCOVERY.md` §5 states explicitly: "Does not
touch the blog repository — all blog-side findings (EIOS layers 3, 8, 9) are cited by path
from read-only inspection." Both searches were, by their own design, scoped to the blog
repo's `Sentinel-APEX/` tree (the Python EIOS engine). Neither searched the blog repo's `lib/`
directory.

### What actually exists in `lib/` (cyberdudebivash-blog repo)

`lib/` is a second, complete, self-contained TypeScript implementation of substantially the
same domain the P-layer stack and the EIOS engine both already cover — malware intelligence
modeling, IOC processing, detection rule generation, report generation, and a publication
governance control plane — verified by direct read, not inferred:

| Module | Verified content |
|---|---|
| `lib/intelligence/schema.ts` | `interface Evidence { source, date, attribution: 'observed_fact'\|'analyst_assessment'\|'hypothesis', confidence, notes }`, plus `MalwareFamily`, `IOC`, `ThreatActor`, `Campaign`, `KnowledgeGraph` types |
| `lib/ioc/*` (8 files) | `IOCIntelligenceEngine`, normalizers for 18 IOC types, `aggregateConfidence()`, `scoreEvidence()`, `RelationshipGraph` |
| `lib/reporting/*` (8 files) | `ReportEngine`, `ReportBuilder`, `calculateReportConfidence()`, `aggregateIOCConfidence()`, Markdown/HTML/JSON renderers |
| `lib/detection/*` (10 files) | Sigma/YARA/Suricata/Splunk/Sentinel/Elastic/ArcSight rule generators |
| `lib/governance/*` (12 files) | `WorkflowEngine` (15-state FSM), `ApprovalManager`, `ConfidenceEngine` (`MultidimensionalConfidence`: sourceReliability, observationQuality, technicalValidation, analystVerification, independentCorroboration), `AuditEngine`, `VersioningEngine`, `RollbackEngine`, `PolicyEngine` |
| `lib/api/*` | HTTP endpoint definitions for the above (`/api/v1/reports/*`, `/api/v1/detections/*`) |
| `docs/adr/0001-phase-2a-isolation.md`, `docs/adr/0002-multidimensional-confidence.md` | Both marked **Status: Accepted**, sign-off recorded from "Governance Team," "Intelligence Team," "Security Review," "API Team" |
| `docs/architecture/README.md` | Self-describes as "Sentinel APEX, a production-grade enterprise cybersecurity threat intelligence platform," **"RC1 Certification — Workstream 1 Complete ✓"**, "43 production modules," "~12,600 lines," "300+ tests" |

This is not a stub or a design doc — it is ~12,600 lines of implemented, tested TypeScript
with its own accepted ADRs, its own module-ownership map, and its own dependency-graph and
public-API audits, using the same "Sentinel APEX" name as the platform's actual production
brand.

### Verified: it has zero production consumers

```
grep -rl "from.*governance"  --include="*.ts" --include="*.tsx" .   → types/index.ts, tests/governance.test.ts only
grep -rl "lib/(intelligence|reporting|ioc|detection|governance)" app/ pages/ src/  → no such directories exist in this repo
```

The repo has no `app/`, `pages/`, or `src/` directory — it is not a Next.js application.
`package.json`'s `scripts` block confirms the actual live site runs on
`"start": "node fetch-live-intel.js"` plus the Python `Sentinel-APEX/engine/sentinel_engine/`
pipeline that produces the auto-published posts visible in `git log` (the `SENTINEL APEX
AI-SEC:`, `syndication: auto-published`, `🛰 [SENTINEL APEX] Auto-generate intelligence hub`
commits). `lib/`'s own `tsconfig.json` compiles it as an independent package
(`rootDir: "./"`, `outDir: "./dist"`), consumed by nothing outside itself and its own test
suite (`tests/governance.test.ts`, run via `npm run test:governance`).

`docs/architecture/README.md` also claims "Enforced in CI" via
`.github/workflows/architecture.yml` running `npx madge --circular lib/` and a Phase 2A
isolation grep check. **That workflow file does not exist** in `.github/workflows/` — 51
workflow files are present, `architecture.yml` is not one of them. The claim of CI enforcement
is itself inaccurate, in the same "documentation wrong, not just stale" category
`platform/open-issues.md` Issue 15 already named as worse than ordinary staleness.

### Why this wasn't already known

`platform/open-issues.md` Issue 15 ("Stale governance docs and scattered parallel systems")
is the blog repo's own tracker for exactly this class of finding, and its confidence-related
entry ("a 3-level code enum vs. a 5-level prose scale... plus a real, practiced 4-tag
evidentiary convention vs. a richer, fully-specified-but-never-used 9-category Provenance
model") is scoped entirely within `Sentinel-APEX/eios/`. It does not mention `lib/` at all.
Issue 1 ("Independently-evolved parallel implementations") is titled specifically "Python
offline engine vs. live JS product" — `lib/` is neither the Python offline engine nor the
live JS product; it is a third, unshipped thing. This finding does not overlap any existing
tracked issue.

### Disposition

Not decided here. `lib/`'s `ConfidenceEngine` and `Evidence` type are catalogued as additional
existing implementations in ADR-0007 and ADR-0008 respectively, and excluded from canonical
candidacy on the same evidentiary basis Stage 4 used to exclude nothing arbitrarily — zero
production consumers is a fact about current state, not a judgment about the code's quality
(RC1 sign-off and 300+ tests suggest it isn't casual scaffolding). The disposition question
("integrate it, formally shelve it, or delete it, and who decides") is logged as the top entry
in `TITAN_TECH_DEBT_REGISTER.md` because it is a different question in kind from "which system
computes confidence today" — it's "why does a fully-built, self-certified parallel platform
exist with nothing pointing at it," which this stage's ADRs are not scoped to answer.

---

## 3. Discrepancy 2 — three additional fleet-level audit functions exist that neither discovery doc catalogued

`p37-handlers.js` (P37, "Platform hardening, source diversity, enrichment excellence,
confidence calibration" per this repo's own CLAUDE.md P-layer table) and `p35-handlers.js`
were in scope for Stage 4's repo-wide grep (unlike the blog's `lib/`), but neither discovery
doc's comparison tables mention them by name. Read directly, not inferred:

| Function | File:line | What it actually does (verified) |
|---|---|---|
| `_confidenceAudit(feed)` | `p37-handlers.js:152` | Reads existing `item.confidence` across a sample, computes coverage % and a distribution histogram. **Calls `computeEnterpriseTrustScore(item)` (P25/A1) directly** for its "calibration signal" — an organic, already-existing consumer of A1 beyond the 12+1 files Stage 4 counted, and itself evidence that P25 is already the de facto reference implementation newer layers reach for. Not a competing scorer. |
| `_evidenceAudit(feed)` | `p37-handlers.js:202` | Defines its own local `_hasEvidence(item)` — presence of `cvss_score` OR `cve_ids` OR `iocs` OR `kev_present` OR `epss_score` OR `ttps`. This is a **fourth independent "does this item have evidence" heuristic**, alongside P20's `evidence_chain`, P18's `buildEvidenceAttribution`, and P23's certification-gate check (`!!(ec && ec.source_reliability)`) — none of which it calls. Concrete reinforcement of `EVIDENCE_ENGINE_DISCOVERY.md` §3's fragmentation finding, one signal wider than that document counted. |
| `handleP35Evidence` | `p35-handlers.js:371` | A fifth such heuristic: `evidence_density_pct` from CVSS/EPSS/KEV/CVE/IOC coverage (no TTPs, unlike P37's version) against `data/governance/evidence_score_enforcement.json`. Different field set than P37's own heuristic — the two newest evidence-adjacent P-layers don't even agree with each other. |
| `_reliabilityAudit(feed, ...)` | `p37-handlers.js:375` | **Not part of the source-reliability fragmentation** — despite the name, this measures feed-pipeline health (duplicate IDs, freshness, certification-chain intactness across P34–P36), not source or evidence reliability. Named adjacently to, but conceptually distinct from, P20/P18/P25's source-reliability signals. Included here only to rule it out explicitly rather than have a reader do the same check independently. |

None of these are per-item scoring engines competing for canonical ownership — they are
fleet-level auditors reading whatever field already exists. But `_evidenceAudit` and
`handleP35Evidence` are additional, independently-invented "has evidence" heuristics that
belong in ADR-0008's and ADR-0009's "Existing Implementations" inventory, and all three
functions are additional consumers that migration planning in `TITAN_MIGRATION_ROADMAP.md`
must account for.

---

## 4. Discrepancy 3 — found while building this stage's own CI governance tooling (Task 6), after ADR-0007 was drafted

Writing `scripts/titan_architecture_governance_check.py` (`TITAN_CI_GOVERNANCE.md`) and running
it against the live tree surfaced two more independent confidence-computing sites in
`workers/intel-gateway/src/`, neither in Stage 4's original catalogue nor in §2–3 above. Both
are folded into `docs/adr/0007-canonical-confidence-framework.md` directly (as A9 and a flagged,
undecided item respectively) rather than left only in this document, since ADR-0007 is the
document a future reader will actually consult. Logged here too so the discovery trail is
complete and the validation record doesn't silently go stale the moment a later tool finds more.

- **`computeTransparentConfidence()`** (`p18-handlers.js:173`) — a fully independent, 7-factor,
  0–100 confidence score (source_quality, evidence_count, cross_validation, data_freshness,
  consistency, ioc_quality, mitre_completeness), calling neither P20 nor P25 nor P26. The same
  file (`p18-handlers.js`) already independently computes `buildEvidenceAttribution()`'s A–E
  letter grade — meaning P18 alone runs *two* independent confidence/reliability computations,
  neither reading the other or any canonical source. Catalogued as **A9** in ADR-0007, treated
  the same as A4 (Deprecated — Pending Migration, same rationale).
- **`_computeConfidenceGraph()`** (`p29-handlers.js:155`, rendered by
  `buildP29ConfidenceGraphBlock`) — a 7-dimension "confidence graph" for a visualization
  feature. Two of its seven dimensions correctly delegate to canonical engines
  (`computeP20QualityScore` for "Evidence Confidence," `computeP26Grade` for "Overall
  Confidence"). The other five — Source, Detection, IOC, Attribution, and Executive Confidence —
  are freshly, independently computed inline with their own thresholds and weights, several of
  which look like they should be reading equivalent, already-existing dimensions inside P25's
  twelve (e.g., its own "IOC Operational Quality" and "MITRE ATT&CK Coverage"). This is a
  partial case — not a clean duplicate like A9 — logged as **DEBT-012** in
  `TITAN_TECH_DEBT_REGISTER.md` rather than force-fit into ADR-0007's binary
  canonical/deprecated framing, since it needs its own read-through of what each of the five
  dimensions is actually for before a consolidation call is made.

Both findings are consistent with, not a contradiction of, ADR-0007's core decision — they are
additional evidence for exactly the pattern (P-layer authors reaching for a fresh inline
computation instead of the canonical A1) the ADR's Decision section already addresses. They
arrived after the ADR's first draft and are incorporated into it directly; this section exists
so the "how was this found" trail isn't lost.

---

## 5. What this validation does not do

- Does not modify `CONFIDENCE_FRAMEWORK_DISCOVERY.md` or `EVIDENCE_ENGINE_DISCOVERY.md` —
  both stand as-written; this document extends their inventory rather than editing already-
  committed, marked-complete discovery artifacts.
- Does not modify, deprecate, or delete `lib/` or any file under it.
- Does not modify P35, P36, or P37.
- Does not decide any of the five ADR questions — see `docs/adr/0007`–`0011`.

---

*Project TITAN Stage 6 — Task 1: Validate Discovery*
