# Global Intelligence Source Fabric — Architecture (P40.0)

## 1. What this is

The Global Intelligence Source Fabric is the canonical representation of every
intelligence source Sentinel APEX integrates, has code for, requires
credentials/licensing for, or has evaluated and deliberately deferred. It
turns "which feeds does the platform pull from" from tribal knowledge and
scattered constants into one structured, machine-readable, honestly-governed
registry — consumed by the live ingestion pipeline, the Cloudflare Workers
API, and a dashboard.

It does **not** replace any existing ingestion mechanism. It documents them,
extends the one proven to be safe to extend, and gives the whole platform a
single place to answer "is source X live, and can I trust what it's telling
me right now."

## 2. Reconnaissance findings that shaped this design

Before writing any code, this change traced every ingestion code path in the
repository. Four independent, overlapping mechanisms already exist:

| Path | What it does | Status found |
|---|---|---|
| `core/ingestion/` (`ingestion_engine.py`, `sources/*.py`) | A well-formed `BaseSource` adapter framework (retry/backoff/rate-limit/health/structured-errors) with NVD, KEV, MalwareBazaar, AbuseIPDB adapters. Mounted into the Railway FastAPI app (`api/main.py:294-296`, `ingestion_router`). | **Dormant.** `get_engine()` is instantiated but `.start()` is never called anywhere in the live path — its scheduler/worker threads never run. |
| `agent/sentinel_blogger.py` + `agent/content/source_fetcher.py` | Inline `urllib`/`requests` fetching, invoked as Stage 2 of `scripts/run_pipeline.py` (the `sentinel-blogger.yml` master orchestrator). | **Live.** Writes the root `feed.json` via `stage_sync_root_feed_json()`. |
| `scripts/multi_source_collector.py` | Hardcoded 8-source fetcher (MSRC, GHSA, abuse.ch, Cisco, CISA, OTX, BleepingComputer), writes `api/feed.json`. | **Live**, invoked from `sentinel-blogger.yml`. |
| `scripts/true_intel_ingestor.py` | Function-per-source design (`ingest_cisa_kev`, `ingest_nvd_cves`, `ingest_github_advisories`, `ingest_ransomware_live`, `ingest_urlhaus`, `ingest_rss_feeds`) with real checkpointing (`FeedState`), real dedup (`dedup_state.py`), and atomic, integrity-verified, backed-up manifest writes. | **Live**, scheduled via `.github/workflows/multi-source-intel.yml` (cron `45 1,5,9,13,17,21 * * *`). |

`scripts/r2_upload.py` (Stage 3.5 of `sentinel-blogger.yml`) bridges the
Python-side output into Cloudflare R2 (bucket `sentinel-apex-data`), which
`workers/intel-gateway/src/index.js` reads (`env.INTEL_R2.get(key)`) to serve
the P16-P39 API surface.

**A verified, live defect was found during this reconnaissance**: abuse.ch
now requires an `Auth-Key` on URLhaus (confirmed via an unauthenticated live
request returning HTTP 401 on 2026-08-08). `ingest_urlhaus()` had been
silently returning zero items every scheduled run since abuse.ch's policy
changed — `urlhaus` does not appear anywhere in the committed
`data/cache/feed_state.json`, meaning it has never once recorded a
successful fetch. This is fixed in this change (see §5).

## 3. Design decision: which pipeline to extend

Given four pre-existing mechanisms, the mission's explicit instructions
("do not replace working production components unnecessarily," "prefer
incremental architectural improvements") ruled out consolidation. The choice
of *which one to extend* came down to:

- **`core/ingestion`** has the architecturally closest match to the mission's
  requested `IntelSourceAdapter` contract (retry/backoff/circuit-breaker-like
  disable-after-failures/health/structured errors), but activating it means
  starting a previously-never-run background thread pool inside the shared
  Railway web dyno, and would independently re-fetch NVD/KEV — sources
  already live through a different path. That is a genuine architectural
  event (new always-on background workload, a second live producer for data
  the platform already has) requiring its own blast-radius sign-off. **Not
  done in this change** — see ADR-P40-001 in
  `data/quality/p40_certification_report.json`.
- **`scripts/true_intel_ingestor.py`** is the cleanest of the three live
  scripts: single-responsibility functions, real incremental cursors, real
  dedup, and hardened manifest I/O (temp-write → verify → backup → atomic
  replace, with a 5-backup retention window). It already satisfies mission
  Section 20 (Ingestion Resilience) almost entirely. **This is what was
  extended.**

## 4. What was built

```
SOURCE
  ↓
SOURCE REGISTRY            data/registry/source_registry.json (104 sources,
  │                         all Section-4 fields, honest status per source)
  ↓
CONNECTOR / ADAPTER         scripts/true_intel_ingestor.py:
  │                           ingest_openphish()   (new, EVENT_STREAM)
  │                           enrich_with_epss()   (new, ENRICHMENT)
  │                           sync_mitre_attack()  (new, REFERENCE_SYNC)
  │                           ingest_urlhaus()     (fixed: Auth-Key regression)
  │                           + 5 pre-existing, unmodified sources
  ↓
INGESTION GATEWAY           scripts/true_intel_ingestor.py:run_ingestion()
  ↓
CHECKPOINT / DEDUP          FeedState (data/cache/feed_state.json),
  │                         dedup_state.DedupState (data/processed_intel.json)
  ↓
NORMALIZATION               _normalize_item() → canonical manifest schema
  ↓
INTELLIGENCE STORE          data/stix/feed_manifest.json (event items)
  │                         data/attck/enterprise-attack.json (ATT&CK reference)
  ↓
OBSERVABILITY                scripts/source_fabric_health.py →
  │                          data/quality/source_fabric_health.json
  ↓
CERTIFICATION                scripts/p40_production_certification.py →
  │                          data/quality/p40_certification_report.json
  ↓
R2 BRIDGE                    scripts/r2_upload.py (additive tuples)
  ↓
API / UI                     workers/intel-gateway/src/p40-handlers.js
                              (10 routes under /api/v1/p40/*)
                              dashboard/source_fabric_dashboard.html
```

## 5. What changed in `true_intel_ingestor.py`, precisely

Zero lines changed in the 6 existing sources' *logic*. One evidence-based fix
and three additive functions:

- **`ingest_urlhaus()` fix**: sends `Auth-Key` from the `ABUSECH_AUTH_KEY` env
  var when present; when absent, logs an explicit "requires credentials"
  state and returns `[]` *without attempting the network call* (previously it
  would attempt the doomed request every run and log a generic failure). No
  behavior change once the key is provisioned as a GitHub Actions secret —
  it starts working automatically.
- **`enrich_with_epss(items)`** (new): batch-enriches CVE IDs already present
  in the current run's candidate items with FIRST.org EPSS scores. Not a
  standalone source — FIRST re-scores its entire ~280k-CVE corpus daily, so
  treating that as an event stream would misrepresent a daily re-score as
  280k new intelligence events.
- **`ingest_openphish(feed_state)`** (new): free plaintext phishing-URL feed,
  no auth. Its "new-ness" is determined by the existing `_merge_into_manifest`
  id/`stix_id` dedup (a stable hash of `source_url + title`), not a
  `FeedState` cursor — OpenPhish's feed carries no per-URL date to cursor
  against.
- **`sync_mitre_attack(dry_run=False)`** (new): fetches the MITRE ATT&CK
  Enterprise STIX 2.1 bundle and writes a curated reference file
  (`data/attck/enterprise-attack.json`) — techniques, groups, software,
  mitigations, tactics — content-hash gated to avoid needless rewrites.
  **Deliberately never merged into `feed_manifest.json`**: ATT&CK objects are
  taxonomy data, not discrete threat events. Original STIX object IDs are
  preserved verbatim.

All three were verified against the real live APIs during development (not
just unit-tested against mocks) — see the final deliverables report for the
actual request/response evidence.

## 6. Why P40, not P39

`workers/intel-gateway/src/p39-handlers.js` already exists (Commercial
Quality Orchestrator) and is deliberately unwired from `index.js` per its own
file header. P40 is the next free layer number; its certification chains
from P38 (the last certified, wired layer) rather than P39.

## 7. Known limitations

- `core/ingestion`'s dormant adapter engine (NVD/KEV/MalwareBazaar/AbuseIPDB)
  is documented in the registry (`core_ingestion_engine`, status
  `IMPLEMENTED`) but not activated — see §3.
- `data/registry/source_registry.json` covers 104 sources across the
  mission's full taxonomy; 9 are `ACTIVE`, 1 is `IMPLEMENTED`-but-dormant, 25
  `REQUIRES_CREDENTIALS`, 21 `REQUIRES_LICENSE`, 48 `PLANNED`. No source
  claims a status this environment cannot substantiate — see
  `docs/SOURCE_REGISTRY.md`.
- P40's Worker API (`/api/v1/p40/*`) reads its data from R2, which is
  populated by `scripts/r2_upload.py` during the *next* scheduled
  `sentinel-blogger.yml` run after this change merges (R2 upload runs before
  the P40 certification stage within a single pipeline run, so the very
  first run only commits the artifacts to git; the following run's Stage 3.5
  picks them up). Until then, the P40 endpoints correctly return `503` with
  an explanatory hint rather than fabricated data.
