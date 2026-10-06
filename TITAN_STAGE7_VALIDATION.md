# Project TITAN — Stage 7 Task 1: Validate Stage 6

**Status:** Complete. Both repositories' Stage 6 pull requests (intel-platform #109, blog #66)
had already merged to `main` before this stage began. Per this program's branch-reuse
protocol, `claude/titan-adrs-roadmap-oezwh5` was reset from each repo's current `main`
(`git checkout -B claude/titan-adrs-roadmap-oezwh5 origin/main`, force-with-lease pushed —
safe because the branch carried only already-merged history) before any Stage 7 work began.

---

## 1. Repository drift since Stage 6

Diffed every commit that landed on `main` between the Stage 6 push and the Stage 6 merge
(5 automated commits: AI Tracker, Guardian report, Observability Layer, governance-telemetry,
enterprise governance) plus the merge itself:

| Check | Method | Result |
|---|---|---|
| P-layer handler files (P16–P38) changed? | `git log --name-only` filtered to `workers/` | One line changed in `p38-handlers.js` (an em-dash replaced with a hyphen inside a code comment, by an automated `ci(governance-telemetry)` commit) — cosmetic, no functional or cited-reference impact |
| CI workflow changed? | Same, filtered to `.github/workflows/` | No changes beyond Stage 6's own additions |
| `docs/adr/*` changed? | Same | No changes beyond Stage 6's own additions |
| Regression suite | `scripts/regression_tests.py` | **21/21 PASS**, re-run on the reset branch |
| P33 certification | `scripts/p33_production_certification.py` | **WORLDWIDE_RELEASE, 0 blockers**, re-run on the reset branch |
| Stage 6's own advisory check | `scripts/titan_architecture_governance_check.py` | **Clean** — all 5 ADRs present, all cited references resolve, no unreviewed confidence/evidence/reliability functions, ownership matrix in sync |
| ADR references still valid? | Manual spot-check of ADR-0007–0011's cited file:line references against current file contents | Valid — the one changed line (P38 em-dash) is not inside any cited function |

**Conclusion: no repository change invalidates any Stage 6 ADR.** The migration roadmap,
technical debt register, and ownership matrix all remain technically sound against current
code. Nothing here required silently correcting a decision — there was nothing to correct.

---

## 2. New finding, not a Stage 6 invalidation: a third, live API surface Stage 6 never examined

While building Stage 7's interface inventory (Task 3), a materially important gap was found —
not because anything changed since Stage 6, but because Stage 6's confidence/evidence
discovery scoped its blog-repo search to `Sentinel-APEX/` (the Python engine) and, this stage,
`lib/` (the dormant TypeScript RC1 tree). **Neither discovery pass examined `api/_lib/`, a
third directory in the same repository, containing 120+ JavaScript files** — including
`confidence-scorer.js`, `confidence-exposure.js`, `evidence-manager.js`, `evidence-validator.js`,
`evidence-conflict-engine.js`, `source-reliability-engine.js`, `graph-engine.js`,
`threat-graph.js`, `campaign-engine.js`, and more.

Unlike `lib/` (confirmed zero production consumers in Stage 6), this directory backs the
repository's **actual deployed API** — `vercel.json` declares 8 live serverless functions
(`api/v1/intel.js`, `api/v1/auth.js`, `api/v1/billing.js`, `api/v1/admin.js`, two webhook
handlers, a cron job, and `api/og.js`), and direct inspection already confirmed one concrete
case: `api/v1/intel.js` requires `../_lib/intel`, which itself requires `./threat-graph`
(`getGraphForTier`, `getTopActors`, `loadGraph`) — reachable from the live
`/api/v1/intel?action=graph` and `?action=top-actors` endpoints (per `vercel.json`'s rewrites).

This is not entirely undocumented territory: `platform/open-issues.md` Issue 15 already
independently confirmed `api/_lib/threat-graph.js` ("8 fully-attributed real actors") and
`api/_lib/campaign-engine.js` ("a full 573-line weighted-clustering engine, live, with a
persisted `campaigns.json`") are real and live, found during an earlier audit unrelated to
Project TITAN. What Stage 6 missed is **cross-referencing that existing finding against
ADR-0010's relationship-graph ownership decision** — ADR-0010 compared intel-platform's P31
graph against blog's Python `KnowledgeGraph` only, never against this third, already-documented,
live JavaScript graph.

A full transitive-reachability trace was dispatched to a research pass and has completed. Its
finding supersedes everything written above in this section — see §2A immediately below, which
replaces the "does not retroactively invalidate" conclusion this section originally drew before
the trace returned. That conclusion was wrong, and is preserved in git history rather than
silently edited out, consistent with this program's own documented-not-corrected discipline.

---

## 2A. MAJOR FINDING — a second, undocumented, very-likely-live CTI platform inside the blog repository, directly contradicting its own CLAUDE.md

The reachability trace was scoped to the 8 functions `vercel.json`'s `"functions"` block
explicitly configures memory/duration for. **That scoping assumption was wrong.** `vercel.json`
has no `"builds"` key — the `"functions"` block only tunes resource limits for the 8 named
files, it does not restrict what Vercel deploys. Vercel's standard behavior is to deploy every
file under `/api` as a route unless `.vercelignore` excludes it. Direct verification:

```
find api/v1 -type f -name "*.js" | wc -l   → 30
```

Only 8 of those 30 are in `vercel.json`'s `"functions"` block. `.vercelignore` (read in full)
excludes `Sentinel-APEX/`, `eito/`, `platform/`, `prompts/`, `scripts/`, `docs/`, `marketing/`,
`backups/`, and specific root `.md` files — **it does not exclude any path under `api/v1/`**.
The other 22 files are, per Vercel's documented default routing convention, very likely live,
independently-deployed serverless functions:

```
api/v1/analysis/assessments.js       api/v1/intelligence/similarity.js
api/v1/analysis/findings.js          api/v1/ioc/[id].js
api/v1/customer/dashboard.js         api/v1/ioc/search.js
api/v1/customer/download.js          api/v1/newsletter.js
api/v1/detections/rules.js           api/v1/products/approvals.js
api/v1/detections/rules/[id].js      api/v1/products/export.js
api/v1/intelligence/confidence.js    api/v1/products/index.js
api/v1/intelligence/correlations.js  api/v1/quality/index.js
api/v1/intelligence/graph.js         api/v1/reports/index.js
api/v1/intelligence/objects.js       api/v1/workbench/cases.js
api/v1/intelligence/publish.js       api/v1/workbench/dashboard.js
                                      api/v1/workbench/investigations.js
                                      api/v1/workbench/search.js
```

These routes require — and per the trace, are the *only* callers of — a large cluster of
`api/_lib/*.js` files that neither Stage 6 nor this stage's earlier work had examined:
`confidence-scorer.js`, `confidence-exposure.js`, `evidence-manager.js`, `evidence-validator.js`,
`evidence-conflict-engine.js`, `evidence-traceability-engine.js`, `source-reliability-engine.js`,
`graph-engine.js`, `graph-traversal.js`, `relationship-engine.js`, `correlation-engine.js`,
`campaign-engine.js`, `governance-engine.js`, `quality-gates-engine.js`, `quality-scorer.js`,
`quality-validators.js`, `threat-scorer.js`, `consistency-engine.js`, and more.

**This is not a separate product domain from what ADR-0007–0010 already govern.** Direct
verification, not inference:

```
GET /api/v1/intelligence/confidence
"Query intelligence with confidence filtering. Returns articles, reports, and CVEs
enriched with confidence scores." Example item: id "CVE-2024-001", confidence.level
(HIGH/MEDIUM/LOW), confidence.aggregate (0-100), confidence.multidimensional
{source_reliability, evidence_quality, analyst_assessment, temporal_relevance, corroboration},
governance {status: PUBLISHED, version, reviewed_by, reviewed_at}.
```

This scores the same kind of object (CVEs, threat articles) ADR-0007 already governs, with a
documented example response — better externally documented, in fact, than P25 (A1) itself,
which has no equivalent worked example anywhere in this repository. `api/v1/customer/dashboard.js`
is a real, working "Customer Self-Service Dashboard" (purchase history, subscription status,
download links, API key/tier status) — directly relevant to
`TITAN_IMPLEMENTATION_AUTHORIZATION.md`'s "Customer Portal" row, which this stage originally
assessed as Blocked with no ADR and no existing implementation. Both of those claims were wrong
and are corrected in that document.

**This directly contradicts blog's own CLAUDE.md**, which names `intel.cyberdudebivash.com`
(intel-platform) as the sole owner of "Live APIs and intelligence feeds... Customer-facing API
portal" and states in writing: "DO NOT duplicate Sentinel APEX functionality on the blog." No
architecture document in either repository — not `docs/architecture/*`, not
`ARCHITECTURE_DECISIONS.md`, not `platform/open-issues.md`'s extensive fragmentation
tracking — mentions this system exists. It has no ADRs, no ownership record, and (unlike the
dormant `lib/` tree, which at least documents itself accurately as unintegrated) no
documentation acknowledging its own existence at all.

**Confidence in "live" assessment:** High but not certain. Based on: (a) Vercel's well-
documented default file-based routing behavior, (b) the absence of any found exclusion
mechanism (`.vercelignore`, a restrictive `"builds"` key) that would prevent deployment,
(c) the code's own internal documentation reads as production-intended (worked examples,
customer-facing language, CORS headers, method validation) rather than experimental. Not
independently confirmed via live HTTP request or Vercel dashboard/build-log access, which this
environment does not have. **Recommended first action for whoever has deployment access:
confirm via `vercel ls` / dashboard / a live `curl` whether these 22 routes actually serve
traffic**, before any of this stage's revised ADR sections are treated as fully settled.

This finding is incorporated into ADR-0007, ADR-0008, ADR-0009, and ADR-0010 as dated Revision
sections (added, not silently rewritten into the original Decision text), into
`TITAN_INTERFACE_REGISTRY.md`, `TITAN_API_TAXONOMY.md`, `TITAN_INTERFACE_OWNERSHIP.md`, and as
the top entry in `TITAN_TECH_DEBT_REGISTER.md`.

---

## 3. What this validation does not do

- Does not modify any Stage 6 ADR's Decision section based on assumption — ADR-0010's revision
  (if warranted) happens after the reachability trace completes with actual evidence, not before.
- Does not treat the `api/_lib/` finding as a Stage 6 failure — Stage 6's scope was explicitly
  confidence/evidence discovery; a live relationship-graph implementation in a third,
  unexamined directory is a gap in cumulative repository knowledge, not a defect in Stage 6's
  own stated scope.
- Does not touch `api/_lib/` or any file within it.

---

*Project TITAN Stage 7 — Task 1: Validate Stage 6*
