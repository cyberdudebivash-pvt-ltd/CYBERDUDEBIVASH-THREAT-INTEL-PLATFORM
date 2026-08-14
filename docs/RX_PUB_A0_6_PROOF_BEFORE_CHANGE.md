# RX-PUB-A0.6 — Proof Before Change

Per `CLAUDE.md`'s Proof Before Change requirement and the RX-PUB-A0.6 mission
brief's Section 3 ("do not begin by coding"). This document, plus the Reuse
Plan at the end, precede any code change in this mission.

## Proof Before Change table

| Field | Entry |
|---|---|
| **Objective** | Make the customer-facing (public HTTP) half of `scripts/r2_reports_verifier.py`'s identity check semantically correct: distinguish a publication-gate's *intended* denial from a genuine customer-delivery defect, close the resolver gap that produces `ITEM_NOT_RESOLVABLE`, fix the edge-cache staleness that lets gate-approved reports serve stale bytes, and fix the run-deadline exhaustion that has disqualified every real bake-in run so far -- all as prerequisites for `--enforce` being safe to authorize later (not in this mission). |
| **Affected Files** | `scripts/r2_reports_verifier.py` (extend, no new verifier); `workers/intel-gateway/src/index.js` (`/reports/**` handler, publication-gate check, resolver, cache headers -- extend existing code, no new route family); `scripts/bust_kv_cache.py` (extend `CACHE_KEYS` / add a per-URL purge path, or a new small dedicated script if a cleanly separable purge concern -- decided per-PR, not here); `data/quality/rx_pub_a0_reports_artifact_manifest.json` schema (version bump, additive fields); `workers/intel-gateway/src/rx-pub-a0-handlers.js` (surface new fields, same 2 routes); `scripts/ci_stats_extract.py` (`rx_pub_a0` key, new semantic classes); `tests/test_r2_reports_verifier.py` and `workers/intel-gateway/src/__tests__/*.test.js` (new tests per PR); `docs/RX_PUB_A0_R2_VERIFIER_BAKEIN.md` (evidence log, updated per bake-in run); `docs/RX_PUB_A0_6_PRODUCTION_CERTIFICATION.md` (final deliverable, written at mission close). |
| **Existing Engine Reused** | `GET /api/v1/reports/{id}/publication-status` (already-live, already-authoritative endpoint wrapping `evaluatePublicationGate` -- called, not reimplemented, from Python via HTTP the same way `r2_reports_verifier.py` already calls the public report URLs); `r2_upload_verifier.py`'s `_s3api_head_object`/`_boto3_head_object` (R2 layer, unchanged); `r2_upload.py`'s `BUCKET_REPORTS`/`s3_cp` (unchanged); `workers/intel-gateway/src/publication-gate.js`'s `evaluatePublicationGate` (Worker side, called where it already is -- not reimplemented in Python, per mission Section 5's explicit prohibition); `findItemBySlug` (Worker side, traced not rewritten from scratch, extended only if the trace proves a fixable gap). |
| **Evidence Modification Is Required** | Documented in `docs/RX_PUB_A0_R2_VERIFIER_BAKEIN.md`'s Run 1 entry (PR #192) and reconfirmed with fresh live evidence below (Phase 0). Two production runs (31727337104 on 2026-08-13, 31761997953 on 2026-08-14) both show the identical pattern: R2 layer clean, public-HTTP layer 0% `LIVE_VERIFIED`, `run_deadline_exceeded: true` in both. This is reproducible, not a one-off. |
| **Risk Classification** | **HIGH** for the resolver/gate-bypass finding below (customer-facing access-control correctness); **MEDIUM** for cache coherency (customer sees stale-but-not-wrong-tier content, self-heals within 24h today); **LOW** for verifier classification and deadline/concurrency changes (Python-side, `STAGE 3.6a` only, `enforced: false` throughout, per mission Section 33). |
| **Expected Regression Risk** | `workers/intel-gateway/src/index.js`'s `/reports/**` handler is the single highest-traffic customer-facing route in the platform (every report URL). Any change here risks breaking legitimate report access. Mitigated by: additive-only changes (Architecture Preservation Rule), full resolution test matrix (mission Section 22) before any behavior change ships, and sequencing the gate-bypass fix strictly after the resolver-population fix (mission Section 21) so denial-by-default is never introduced before the underlying resolvability gap is actually closed -- doing it in the other order would newly 404 legitimate reports. |
| **Rollback Plan** | Each of 6A-6D ships as its own small, revertible PR (mission Section 44). `STAGE 3.6a` remains non-blocking (`|| true`, no `--enforce`) throughout this entire mission (Section 49) -- a bad verifier-classification change cannot break production CI or block deploys, only misreport observability. Worker changes (6B cache purge, 6C resolver/gate-fail-closed) are the only changes with real customer-facing blast radius; each ships behind its own PR with the resolution test matrix as a merge gate, and `git revert` on the merge commit is sufficient since no schema/data migration is involved (additive manifest fields only, no destructive writes). |

## Production Blast Radius

| Dimension | Assessment |
|---|---|
| **Files** | See Affected Files above. |
| **Imports** | `r2_reports_verifier.py` already imports `r2_upload_verifier`, `r2_upload` -- adding an HTTP call to the already-live `/api/v1/reports/{id}/publication-status` endpoint adds no new import, only a `urllib.request` call reusing the existing `_fetch_public`-style helper. `index.js` changes stay within the existing `/reports/**` handler function; no new imports. |
| **Routes** | No new routes. `/reports/**`, `/api/v1/reports/{id}/publication-status`, `/api/v1/rx-pub-a0/reports-identity`, `/api/v1/rx-pub-a0/observability` are all extended, not duplicated. |
| **Dashboards** | None render this data today; no dashboard blast radius. |
| **CI Stages** | `STAGE 3.6a` only (`sentinel-blogger.yml`). Remains non-blocking throughout. |
| **Certification Reports** | `data/quality/rx_pub_a0_reports_artifact_manifest.json` gains additive fields (schema version bump); does not participate in the `p33 -> p32 -> ... -> p25` certification chain and does not alter it. |
| **APIs** | `/api/v1/rx-pub-a0/reports-identity` response gains new summary counters (additive); `enforced: false` preserved verbatim per mission Section 33. `/reports/**`'s *response shape* for already-authorized requests does not change; only its behavior for the specific fail-open-on-unresolvable case changes, and only after the resolver fix makes that case rare/genuine. |
| **Data Schema** | No D1/KV/R2 structural changes. Manifest JSON gains fields; existing consumers (`ci_stats_extract.py`, the Worker observability handlers) are updated in the same PRs that add the fields, per Deprecation Instead of Deletion (no field removed). |
| **Workflows** | `sentinel-blogger.yml` STAGE 3.6a step only; possibly a new/extended cache-purge step (6B), added after STAGE 3.5/3.6a, before nothing currently depends on its timing except the public-HTTP verification itself. |
| **Expected Risk** | **MEDIUM overall** (HIGH-risk resolver/gate item is real but tightly scoped and test-gated; everything else is LOW/observability-only). Not re-scoped further -- the mission's own Section 44 PR split already bounds each individual change's surface area. |

## Cache implications

`/reports/**`'s `Cache-Control: public, max-age=86400, stale-while-revalidate=3600`
(set in `index.js`, canonical-URL 200 branch) is the confirmed root cause of
the edge-cache-staleness class (Phase 0 evidence below). Any purge mechanism
added in 6B must target the exact changed URL only (mission Section 14) and
must never fire before R2 verification succeeds (mission Section 15) --
purging toward an unverified/potentially-corrupt object would make the
customer experience worse, not better.

## API implications

`/api/v1/reports/{id}/publication-status` becomes a dependency of
`r2_reports_verifier.py` (an HTTP call per in-window report, same pattern
already used for the public artifact fetch). This roughly doubles the
per-report public-layer request count, which directly informs the
deadline/concurrency work (6D) -- covered there, not solved by ad hoc timeout
increases (mission Section 24).

## Workflow implications

No new CI stage. `STAGE 3.6a`'s per-report work increases (one more HTTP call
per report); 6D's bounded-concurrency design must account for this from the
start rather than being retrofitted after 6A ships.

## Security impact

The confirmed fail-open-on-unresolvable finding (below) is a genuine
customer-facing access-control gap in `index.js`'s `/reports/**` handler --
not merely a verifier classification problem. Fixing it is in scope for 6C.
No secrets, credentials, or new attack surface are introduced by any planned
change; the cache-purge design (6B) must restrict its target host to
`intel.cyberdudebivash.com` and canonicalize purge URLs per mission Section 36.

## Availability impact

`/reports/**` is the platform's primary customer-facing surface. All planned
changes there are additive/corrective, gated by the resolution test matrix,
and shipped as an isolated, revertible PR (6C) separate from the
lower-risk verifier/observability work (6A) and cache work (6B).

---

## Phase 0 — Fresh live evidence (2026-08-14), not a re-citation of Run 1

Reproduced independently against the current production system, per mission
Section 4's explicit instruction not to rely only on previously recorded
percentages.

### Current manifest state (`GET /api/v1/rx-pub-a0/reports-identity`, run `31761997953`, 2026-08-14T02:38:32Z)

```text
R2 layer:          518 in-window, 170 REMOTE_VERIFIED, 0 STALE_OR_DIVERGENT/FAILED, 348 UNKNOWN (deadline remainder)
Public HTTP layer: 0 LIVE_VERIFIED, 166 LIVE_STALE_OR_DIVERGENT, 4 LIVE_MISSING, 348 UNKNOWN
run_deadline_exceeded: true
```

Same pattern as Run 1 (PR #192), on a larger population (518 vs 293
in-window) -- confirms the finding is systemic and worsening as report
volume grows, not a one-off artifact of a single run.

### Stratified sample (n=25, `random.seed(7)` over the full non-`LIVE_VERIFIED` population), cross-referenced against live `/api/v1/reports/{id}/publication-status`

| Publication-status result | Count | Share |
|---|---|---|
| `REJECTED` (P20/P21/P23/P25/P26 reason codes, `customer_ready: false`) | 14 | 56% |
| `BLOCKED` (`P23_OPERATIONAL_READINESS_DO_NOT_PUBLISH` only, `customer_ready: false`) | 3 | 12% |
| `UNKNOWN` / `ITEM_NOT_RESOLVABLE` (`customer_ready: false`) | 4 | 16% |
| `CUSTOMER_READY` (`customer_ready: true`, genuine divergence) | 4 | 16% |

Consistent with Run 1's three-category model (publication-gate denial,
resolver failure, genuine cache staleness) -- gate-related denial is the
majority cause (68% combined) in both runs.

### New finding: fail-open publication-gate bypass on resolver miss (HIGH severity)

All 4 sampled `ITEM_NOT_RESOLVABLE` reports were independently re-fetched
from `/reports/2026/08/{id}.html` and their SHA-256 compared against the
manifest's `artifact_sha256` (the canonical, R2-verified LOCAL artifact):

| Report ID | `publication-status` | Served bytes match canonical artifact? |
|---|---|---|
| `intel--f5ff8edef07fa32b` | `UNKNOWN` / `ITEM_NOT_RESOLVABLE`, `customer_ready: false` | **Yes -- exact match** |
| `intel--514b4ec0f18b7fda` | `UNKNOWN` / `ITEM_NOT_RESOLVABLE`, `customer_ready: false` | **Yes -- exact match** |
| `intel--ebe79a2e5c68e982` | `UNKNOWN` / `ITEM_NOT_RESOLVABLE`, `customer_ready: false` | **Yes -- exact match** |
| `intel--0f5b01fa64d0cc45` | `UNKNOWN` / `ITEM_NOT_RESOLVABLE`, `customer_ready: false` | **Yes -- exact match** |

4/4. Traced to `workers/intel-gateway/src/index.js`'s `/reports/**` handler:
the P0 publication-authorization gate (line ~4147) only executes when
`gateItem = await findItemBySlug(env, gateSlug)` returns non-null; when
`findItemBySlug` cannot resolve the item (`gateItem` is `null`), the guard
condition `if (gateItem && gateResult && !gateResult.customer_ready)` is
false by construction, so the gate is silently skipped and execution falls
through to `env.REPORTS_R2.get(key)` (line ~4212), which serves whatever is
in R2 **unconditionally, with no authorization check at all**.

This matches the RX-PUB-A0.6 mission's own Section 9 hard-defect test
verbatim: `customer_ready=false` + public route serves canonical body
`-> HARD DEFECT: PUBLICATION_GATE_BYPASS`. In all 4 sampled cases the served
content happened to be legitimate (matches the canonical artifact exactly),
because `generate_intel_reports.py`'s Zero-skip policy regenerates every
in-window item's HTML regardless of its certification score and uploads it
to R2 unconditionally -- so R2 already contains full content for
certification-failing reports too. Nothing currently prevents a report whose
*true* gate verdict would be `REJECTED`/`BLOCKED` from also being
`ITEM_NOT_RESOLVABLE` and being served through this exact same fall-through
path, undetected. This pass did not catch a live instance of that specific
combination -- the 4 samples happened to be legitimate content -- but the
code path itself is unconditional and was exercised by 100% of the sampled
resolver-miss cases, so the mechanism is proven, not hypothetical.

**Sequencing implication for 6C** (already reflected in task #160): fix the
resolver's population/window gap first (so `findItemBySlug` succeeds for
essentially all active in-window items and the gate is evaluated for real),
then convert the residual fail-open branch to fail-closed. Doing it in the
reverse order would newly 404 legitimate reports whose only problem is a
resolver gap, not a certification failure -- mission Section 21 explicitly
requires resolution and authorization to be fixed as separate, ordered
concerns.

### Cache-staleness re-confirmation

Re-checked `intel--fa3f81f2935965fe` (fresh sample, run `31761997953`):
`remote_sha256` (R2) == `artifact_sha256` (LOCAL) at `2026-08-14T02:48:25Z`;
`public_sha256` fetched one second later was a *different* hash, served from
Cloudflare POP `ORD` with `cache-control: public, max-age=86400,
stale-while-revalidate=3600`. A fresh re-fetch during this investigation
(POP `IAD`) returned `content-length: 92251`, matching the manifest's
`size_bytes` for the correct current version. Identical mechanism to the
Run 1 finding (PR #192) -- reconfirmed on a different report, different run,
different day.

## Reuse Plan

1. `r2_reports_verifier.py` gains one new HTTP call per in-window report, to
   the already-live `/api/v1/reports/{id}/publication-status` endpoint --
   reusing the Worker's existing `evaluatePublicationGate` result exactly as
   the platform's other consumers already do, per mission Section 5's
   explicit "do not duplicate P20/P21/P23/P25/P26 logic in Python."
2. `index.js`'s resolver fix extends `findItemBySlug` (traced first, per
   Section 19, not widened blindly) and the existing gate-check block --
   no new gate implementation, no second publication-authorization path.
3. Cache purge (6B) reuses Cloudflare's existing purge-by-URL API and the
   existing R2-upload-then-verify sequencing already present in
   `scripts/r2_upload.py` / `scripts/r2_reports_verifier.py` -- ordered
   strictly after R2 verification succeeds (Section 15), not a new pipeline
   stage with its own independent trigger.
4. Manifest schema evolves additively (Section 31) -- no second manifest,
   no second observability endpoint family (Section 33).

**Zero new engines planned.** Every fix in this mission extends an existing,
already-canonical implementation.
