# Production Performance Certification — v200

**Project TITAN Stage 22 Phase 4**
**Measured, not estimated — with an explicit boundary on what "measured" means in this session.**
This session runs in an isolated container with no production credentials and no live Cloudflare
bindings. Three measurement sources are used, each labeled by provenance, and nothing below is a
guess dressed up as a number:

1. **Fresh local benchmarks** of the platform's pure, standalone-importable computation functions
   (no network, no live bindings) — measured just now, in this session.
2. **The platform's own recent production telemetry** (`data/health/sla_status.json`,
   generated ~1 hour before this document, by the platform's existing automated SLA probe hitting
   the real deployed API) — real production measurement, not self-generated, cited with its own
   timestamp.
3. **Stage 21's Gateway performance smoke test results** (`COMMERCIAL_GATEWAY_PERFORMANCE.md`) —
   real, already-measured, still valid (no code in that path has changed since).

Where a requested dimension could not be measured by any of the three (search, correlation, and
IOC-lookup as full HTTP round trips; live dashboard rendering against real data), this is stated
explicitly in §6 rather than filled in with an invented figure.

---

## 1. Report generation (JS compute layer) — measured, this session

Benchmarked the pure P18/P20 report-quality/attribution functions directly against all 159 real
items in `data/feed.json` (not synthetic fixtures) — `computeP20QualityScore`,
`buildEvidenceChainBlock`, `buildIOCQualityBlock`, `buildAttributionRationaleBlock`,
`buildP20ExecutiveBlock`, `buildP20QualityGateBlock`, `buildEvidenceAttribution`,
`computeTransparentConfidence`. These are pure functions (no imports, no I/O) — this measures true
CPU cost with zero network/binding overhead.

| Function | Avg | Median | p95 | Worst |
|---|---:|---:|---:|---:|
| `computeP20QualityScore` | 0.0211ms | 0.0096ms | 0.0500ms | 0.8653ms |
| `buildEvidenceChainBlock` | 0.0013ms | 0.0003ms | 0.0006ms | 0.1480ms |
| `buildIOCQualityBlock` | 0.0025ms | 0.0005ms | 0.0024ms | 0.1989ms |
| `buildAttributionRationaleBlock` | 0.0022ms | 0.0006ms | 0.0059ms | 0.1134ms |
| `buildP20ExecutiveBlock` | 0.0188ms | 0.0092ms | 0.0378ms | 0.9546ms |
| `buildP20QualityGateBlock` | 0.0380ms | 0.0212ms | 0.0680ms | 0.8872ms |
| `buildEvidenceAttribution` (P18) | 0.0114ms | 0.0043ms | 0.0138ms | 0.7910ms |
| `computeTransparentConfidence` (P18) | 0.0071ms | 0.0032ms | 0.0131ms | 0.2747ms |
| **Composite (all 8, sequential, per item)** | **0.0598ms** | **0.0552ms** | **0.1022ms** | **0.4297ms** |

n=159 for every row (every real feed item). **This computation layer is not a performance
bottleneck at any realistic scale** — the composite cost of building every report-quality block for
one item is under 0.1ms at p95. Whatever dominates the real, end-to-end per-advisory report
generation time (10,040 files exist under `reports/`) is elsewhere: `scripts/report_generator.py`'s
own I/O (STIX bundle read, file write, PDF generation) or upstream enrichment steps — none of which
were re-measured in this session (see §6).

## 2. Gateway latency — reused from Stage 21, unchanged code path, still valid

| Category | n | Average | Median | p95 | Worst |
|---|---:|---:|---:|---:|---:|
| Full-stack composition (cold, x1) | 1 | 2.18–2.23ms | — | — | — |
| Registry lookup (`describeCapability`) | 200 | 0.001ms | 0.000ms | 0.003ms | 0.045–0.053ms |
| New-adapter dispatch (`commercial.knowledgeObject/build`) | 200 | 1.04–1.11ms | 0.58–0.60ms | 3.4–4.8ms | 8.4–9.9ms |
| Pre-existing capability dispatch (`evidence.lookup/byCVE`) | 200 | 0.06–0.07ms | 0.042–0.044ms | 0.08–0.12ms | 2.1–4.1ms |
| Contract validation | 200 | 0.001–0.002ms | 0.000–0.001ms | 0.002ms | 0.14–0.16ms |
| Readiness generation | 50 | 0.032–0.037ms | 0.017–0.018ms | 0.051–0.053ms | 0.59–0.72ms |

Full detail, methodology, and both independent runs: `COMMERCIAL_GATEWAY_PERFORMANCE.md`. Re-verified
today that no file in this dispatch path has changed since that measurement (`workers/intel-gateway/src/enterprise-gateway/`
and `commercial-catalog/` are byte-identical to the Stage 21 commit). **Note**: this lineage is not
customer-reachable (`TITAN_V200_RELEASE_AUDIT.md` §1) — these numbers characterize an internal,
unrouted capability surface, not the live customer-facing API.

## 3. Live production API response times — real, external measurement (not self-generated)

From `data/health/sla_status.json`, generated `2026-08-07T14:40:09Z` by the platform's own
`scripts/sla_engine.py` probe against `https://intel.cyberdudebivash.com` — real network round
trips to the actual deployed edge, roughly one hour before this document, not reproduced by this
session (this session does not probe production itself — see §6 for why).

| Endpoint | Status | Latency |
|---|---|---:|
| `/api/health` | 200 | 532ms |
| `/api/v1/intel/latest.json` | 200 | 2,142ms |
| `/api/v1/intel/top10.json` | 200 | 560ms |
| `/api/feed.json` | 200 | 536ms |
| `/api/v1/intel/apex.json` | 200 | 656ms |

Computed across these 5 real, simultaneous endpoint probes (n=5, a single snapshot, not a repeated
time series — `data/health/sla_history.json` contains only one historical entry, from
2026-05-06, so a longitudinal percentile series is not available in this repository):
**avg 885ms, median 560ms, worst 2,142ms** (`latest_json`). The platform's own SLA evaluation
(`sla_status.json`) reports **p95_latency_ms: 560** and grades this **Grade A, 100 SLA score,
compliant** against its own committed threshold of ≤1,000ms p95 (`sla_commitments.latency_p95_ms`).
**One number needs a caveat, not silent omission**: `latest_json` at 2,142ms would itself breach the
1,000ms p95 commitment if it recurred at p95 rather than as a single outlier — flagged as a
watch item, not a certified failure, given n=1 for that specific endpoint.

## 4. Dashboard rendering — partially measurable

The frozen dashboard (`dashboard/enterprise_dashboard.html`, per `UI_FREEZE_POLICY.md`) is a static
file that fetches live data client-side (45 `fetch()` call sites). Static-shell parse/load time is
measurable locally without touching production; the 45 live data fetches are not (they would either
fail against no backend or require hitting the real production API, which this session does not do
— see §6). Not benchmarked in this pass given the partial, potentially misleading picture a
shell-only measurement would give; recommended as a live-environment (staging or production,
authorized) measurement for Phase 9/10 follow-up rather than an incomplete number here.

## 5. Certification against CLAUDE.md's performance baseline

| Baseline (non-negotiable) | Measured value | Status |
|---|---|---|
| API response < 500ms p95 (cached) / < 2s p95 (computed) | Live API p95 560ms (§3); 4/5 probed endpoints ≤656ms, 1/5 (`latest_json`) at 2,142ms | **Borderline** — platform's own SLA grade is A/compliant against its own (looser, 1000ms) commitment, but CLAUDE.md's own stricter 500ms-cached bar is exceeded by every probed endpoint except `/api/health` |
| Cold start < 50ms (Cloudflare Worker) | Not measured this session (requires live CF infrastructure) | **Not certified** — see §6 |
| Dashboard load: Lighthouse Performance ≥ 90 | Not measured this session | **Not certified** — see §6 |
| Bundle size: no regression | Not measured this session (no prior baseline bundle size on record found in this repo) | **Not certified** — see §6 |
| Report generation compute layer | 0.06ms avg composite per item (§1) | **Pass, wide margin** |
| Gateway dispatch | p95 well under 30ms budget on every category (§2) | **Pass, wide margin** |

## 6. What could not be measured in this session, and why

Reported explicitly per this program's "measured, not estimated" standard — an absent number here
is safer than an invented one:

- **Live Cloudflare Worker cold start**: requires actual Cloudflare edge infrastructure. This
  session has no production/staging credentials.
- **`wrangler dev --local` (Miniflare) was attempted and failed**: `node_modules/miniflare/dist/`
  is missing its build output in this container's dependency install (`MODULE_NOT_FOUND` on
  `miniflare/dist/src/index.js`) — an environment/install issue, not a code defect. A working local
  Miniflare environment would let a future session measure `/api/search`, `/api/v1/p18/correlation`,
  and IOC-lookup end-to-end safely (no production traffic). Recommended as a fix-forward item.
- **Search, correlation, and IOC-lookup as full HTTP operations**: their route handlers
  (`handleSearch`, `handleCorrelate`, `handleP18Correlation`) require a `Request` object and a
  Cloudflare `env` with live KV/R2 bindings. Constructing a synthetic mock `env` would measure this
  session's own mock latency (near-zero, meaningless) rather than anything real — reported as not
  measured rather than substituted with a misleading number.
- **This session did not probe `https://intel.cyberdudebivash.com` directly** — load-testing or
  even light-probing a live production system without explicit authorization is exactly the kind of
  action this program's own risk posture reserves for deliberate, authorized operations, not an
  audit script. §3's numbers come from the platform's own existing, already-scheduled automation,
  not from this session initiating new production requests.
- **Lighthouse / bundle size**: no existing recorded baseline was found in this repository to
  compare against, and running Lighthouse against a page whose 45 live fetches would fail locally
  would produce a partial, uninformative score.

## 7. Summary

The parts of the platform this session could safely and honestly measure — the report-generation
compute layer and the already-measured Gateway lineage — perform well within budget, with wide
margins. The live customer-facing API is SLA-compliant against the platform's own commitments but
sits at or above CLAUDE.md's own stricter baseline on 4 of 5 probed endpoints, with one real,
unrepeated 2.1-second outlier worth monitoring. Several requested dimensions (cold start, dashboard
Lighthouse score, end-to-end search/correlation/IOC-lookup) are **not certified in this document**
because they cannot be measured honestly without either production access this session does not
have, or a local dev environment that is currently broken in this container. This is reported as an
open item for Phase 9/10, not silently dropped.
