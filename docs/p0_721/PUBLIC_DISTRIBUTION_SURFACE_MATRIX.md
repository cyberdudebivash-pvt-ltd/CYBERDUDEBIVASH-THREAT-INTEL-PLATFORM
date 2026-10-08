# Public distribution surface matrix (P0 #721 / #725 / #720)

Evidence date: 2026-10-08, base `main` = `40315f6a3` (#727 merged). Statuses use the release vocabulary:
**FIXED IN SOURCE** → **CI VERIFIED** → **MERGED** → **DEPLOYED** → **LIVE VERIFIED** → **CUSTOMER CERTIFIED**.
Nothing below is above FIXED IN SOURCE / CI VERIFIED; no row is LIVE VERIFIED or CUSTOMER CERTIFIED.

Single authority: `scripts/tlp_policy.py::publication_decision()` (FIRST TLP v2.0; deny-first; no bypass flag).
Last-mile applier for finished bytes: `scripts/tlp_public_boundary.py` (JSON documents, staged folders, workspace,
dist/). Producer-side gates remain in place; the boundary exists because producers are many and not all are gated.

| # | Surface | Producer (file) | Public entry point | Storage | Access | Classification authority | Fail-closed behaviour | Cache / stale behaviour | Negative control | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Report HTML | `generate_intel_reports.py` | `/reports/YYYY/MM/<id>.html` | Pages (dist) + R2 `sentinel-apex-reports` | anonymous | `tlp_policy` in generator (`PublicationDenied`); `r2_report_publisher.apply_tlp_gate`; dist boundary removes denied ids and pages that state a restricted TLP | denied → not rendered / not PUT / not in dist | **R2 object and CDN copy of an already-published page are NOT deleted by any gate** (operator retraction) | `tests/test_p0_721_publication_enforcement.py`, `tests/test_p0_721_public_boundary.py::TestSanitizeDist` | FIXED IN SOURCE (new part: dist) |
| 2 | Immutable API manifests | `generate_api_manifests.py` | `/api/v1/intel/{latest,latest_pro,top10,apex,manifest}.json` | R2 data bucket + Pages | anonymous (`latest`), tier-gated by Worker (`*_pro`) | `partition_publishable` before build; `s3_cp_public` boundary; dist boundary | all-withheld or missing policy → exit 1 before writing | `Cache-Control` per object; Worker KV bust at STAGE 3.7 | `tests/test_manifest_sanitizer_fail_closed.py` | FIXED IN SOURCE; **a restricted record was still present in the live anonymous `latest.json` at 16:48Z (pre-#727 run) — not live verified** |
| 3 | `api/feed.json` | pipeline + `commercial_readiness_governor.py` | `/api/feed.json` | R2 + Pages | anonymous | governor gate; `r2_upload.tlp_safe_public_feed_source`; resync; workspace + dist boundary | unparseable/unexpected shape → exit 1; empty set → `[]` overwrites stale bytes | R2 `no-store`; Worker KV | `TestR2TlpPublicFeedBoundary` (#727), `TestSanitizeWorkspace` | FIXED IN SOURCE |
| 4 | Other `api/**/*.json` (tier feeds, `iocs/`, `graph/`, `apex_v2/`, `reports/index.json`, detections, …) | various writers, **ungated at producer** | `/api/...` | Pages (dist) and R2 via `r2_upload` pairs | anonymous (file name such as `pro`/`mssp`/`enterprise` is **not** access control: `feed_mssp.json`/`feed_enterprise.json` are static files) | boundary: workspace pass (before dist build) + dist backstop + `s3_cp` | per-document: tombstone / record removal; unverifiable `api/` JSON fails the dist build | stale R2 object overwritten by tombstone/sanitized copy at next upload | `TestSanitizeDocument`, `TestSanitizeWorkspace`, `TestS3CpIsTheStructuralChoke` | FIXED IN SOURCE |
| 5 | `ai/*.json` | `r2_upload._generate_ai_endpoints` | Worker `index.js` (`INTEL_R2.get("ai/<file>")`) | R2 | per Worker route | boundary (`apex_report.json` states `TLP:AMBER` at document level → tombstone) | unverifiable → not uploaded | R2 object overwritten | `test_main_puts_only_sanitized_bytes_for_every_json_key…` | FIXED IN SOURCE |
| 6 | Weekly threat brief | `weekly_threat_brief.py`, `weekly-threat-brief.yml` | `/weekly-brief.html`, `/api/v1/intel/weekly_brief.json` | R2 (`s3_cp_public`) + gh-pages | anonymous | `s3_cp_public` boundary; staged-folder `--tree` pass. **Before this change `STEP 8` published `folder: .` — the whole checkout (raw `api/`, `reports/`, `data/`) — to gh-pages** | unverifiable staged JSON fails the job | gh-pages `clean:false` keeps history | `TestOtherPublicWritersUseTheBoundary` | FIXED IN SOURCE |
| 7 | Weekly analyst briefing | `generate_weekly_briefing.py`, `weekly-analyst-briefing.yml` | `/data/weekly_briefings/*.json` | gh-pages | anonymous | `--tree .publish` pass | unverifiable fails the job | `clean:false` | same | FIXED IN SOURCE |
| 8 | Dashboard feeds | `generate_dashboard_feeds.py`, `dashboard-feeds-sync.yml` (push + schedule) | `/api/v1/intel/{stats,campaigns,…}.json` | R2 | anonymous | `--sanitize-file` before every `aws s3 cp` | `set -e`: unverifiable stops the publication | `max-age=120` | `TestOtherPublicWritersUseTheBoundary` | FIXED IN SOURCE |
| 9 | Manual R2 sync | `r2-data-sync.yml` (workflow_dispatch) | `intel/…`, `apex_v2/…` keys | R2 | per Worker | `--sanitize-file` before every `aws s3 cp` | same | — | same | FIXED IN SOURCE |
| 10 | Fast frontend publish | `pages-fast-publish.yml` → `build_dist_artifact.py` | Pages | gh-pages | anonymous | inherits the dist builder (workspace + dist boundary) | build exits 1 if the boundary cannot be applied | — | `TestWiring` | FIXED IN SOURCE |
| 11 | Status monitor | `status-monitor.yml` | `/data/status/*` | gh-pages | anonymous | none — platform status JSON, no advisory records expected | — | — | none | **NOT VERIFIED** (content not inspected for advisory records) |
| 12 | R2 report publisher | `r2_report_publisher.py` (STAGE 3.5a, 5.4.0c) | R2 reports + `reports/pdf/` | R2 | via Worker | `apply_tlp_gate` (#724) | denied never planned; nothing auto-deleted | stale objects remain until retracted | `test_p0_721_publication_enforcement.py` | MERGED (#724) |
| 13 | Publishing verdict before Pages | `sentinel-blogger.yml` `p0-publisher-verdict` (#726) | all Pages write steps in the main pipeline | — | — | outcome-based (`steps.<id>.outcome`) | failed/skipped/cancelled/missing publisher → exit 1; kill switch → explicit PASS-WITH-PUBLISHER-DISABLED | — | `TestPublishingVerdictBehavior` (executes the real script) | FIXED IN SOURCE (kill-switch visibility new); #726 core MERGED |
| 14 | Worker `/reports/**`, `/api/v1/intel/*`, KV/edge cache | `workers/intel-gateway/src/index.js`, `publication-gate.js`, `r2-edge-cache.js` | live site | R2 + KV + edge | anonymous / tiered | `publication-gate.js` = quality/certification gate; **no TLP decision anywhere in the Worker** (`TLP` appears only as display text) | n/a | Worker serves whatever R2 holds; `r2Get` is a plain reader | none (JS) | **FAIL — not fixed.** Safe only if R2 holds nothing restricted; a tier-aware JS port needs shared policy vectors and a product decision on entitled access to restricted content |
| 15 | Worker static proxy fallback | `intel-static-proxy.js` | `/api/v1/intel/{nexus,genesis,cortex,quantum,sovereign}_output.json` | falls back to `raw.githubusercontent.com/.../main/data/...` when R2 misses | anonymous | none | falls back to **unsanitized repository content** | `max-age=300` | none | **FAIL — not fixed** (R2-miss bypass; files not inventoried for records) |
| 16 | TAXII / STIX | Worker TAXII route (`stix/bundle-<id>.json` from R2 else inline bundle) | `/taxii/…` | R2 | authenticated tier | inline bundle uses `isCustomerReady` (quality), not TLP; **no Python writer of `stix/bundle-*.json` found in the repo** | — | — | none | **NOT VERIFIED** |
| 17 | MISP / other STIX/PDF exporters | `agent/export_stix.py`, `product_factory/*` | not traced to a public route | — | — | none | — | — | none | **NOT VERIFIED** |
| 18 | Sitemaps / report catalogs | `sitemap-reports.xml`, `reports/index` builders | `/sitemap-reports.xml` | Pages | anonymous | not gated; lists URLs (ids) of withheld reports | — | crawler caches | none | **NOT VERIFIED** (ids only, no bodies) |
| 19 | Public git repository | tracked `api/**`, `reports/**` (22,433 pages) | github.com | git history, forks | anonymous | n/a | — | permanent in history | n/a | **OPEN** — history rewrite needs separate explicit authorization |

## Findings that drove the changes (file-level root causes)

* `scripts/r2_upload.py` (#727) guarded only the destination key `api/feed.json`. Measured on the checkout: 23 upload
  pairs, of which `apex_v2/priority.json` (100/100 records restricted), `apex_v2/critical.json` (6/6),
  `ai/apex_report.json` (document states `TLP:AMBER`, 8 items `TLP:RED`) and `intel/apex_v2_strategic_report.json`
  (`TLP:AMBER`) carried restricted content and were uploaded raw. Five more upload modes
  (`--p40-only`, `--ai-tracker-only`, `--governance-telemetry-only`, `--weekly-brief-only`, `--reports-index-only`)
  call the same plain `s3_cp` primitive. **Fix:** the guard now lives in `s3_cp_public` (used by every anonymous upload mode; the plain `s3_cp` is kept raw because `r2_state_sync.py` round-trips internal state through it) and in the
  pre-budget plan; `r2_resync_manifests.py` (its own `s3_cp`) guards every `.json` key.
* `build_dist_artifact.py` copies all of `api/` and `reports/` to Pages verbatim. Measured: 16 of 257 `api/**/*.json`
  files carry restricted records or a document-level restricted classification (e.g. `api/iocs/feed.json` 100 records
  `TLP:WHITE` not migrated, `api/graph/nodes.json` 497, `api/feed.baseline.json` 193).
* Pages is an independent anonymous channel and the Worker's static origin; R2 sanitization alone never closed it.
* Four workflows wrote to R2/Pages outside every Python gate (rows 6–9).

## Consistency invariant (why the workspace pass exists)
`dist_artifact_verifier`, regression `T21`, the `report_url` validation and the canaries compare the repository feed
with `dist/`. Sanitizing only `dist/` made them fail ("11 report_url path(s) … MISSING from dist"). The dist builder
therefore sanitizes the CI-runner copy of `api/**` and the root feed files first (most-restrictive-wins **across
documents**, contradicting report pages included), so publishing and verification agree. `data/` (internal manifests,
state) is never modified.

## Known behaviour changes the operator must accept or adjust (all fail closed)
* `api/iocs/feed.json` (100 records, `TLP:WHITE`) is withheld until `legacy_white_treated_as_clear` is reviewed.
* Unlabelled per-advisory documents without a verified parent (`api/v1/detections/*.json`: 162 files, `_tier` field
  present) are replaced by tombstones; with `data/feed_manifest.json` present in CI, those whose parent is
  `TLP:CLEAR` are kept.
* The platform's own backfill (`scripts/apex_quality_field_backfill.py::_TLP_MAP`) assigns `TLP:GREEN` to every
  CRITICAL/HIGH record and `TLP:CLEAR` to the rest — a **severity-derived** label, not an originator label. That is consistent with
  643 of 706 restricted advisories being `TLP:GREEN` and `apex_v2/priority.json` being 100 % restricted (not proven
  causal — the checkout carries no label provenance). The gate treats
  them as restricted (safe); whether they are genuinely third-party restricted is an operator determination that needs
  label provenance (`tlp_source`) at ingestion.
