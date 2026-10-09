# P0 R22 — Canonical manifest loss through persistent deduplication

**Verified root-cause evidence:** Sentinel Blogger run [#2534](https://github.com/cyberdudebivash/CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM/actions/runs/37947837450) reported `[3.2] COMPLETE: 45 -> 0 items | dupes removed=45`. Stage 3.9 recovered only 9 entries from historical STIX bundles and previous disk state. Eight entries carried no verifiable public TLP label/collector authority and were properly withheld; the ninth was outside the 24-hour report window. `api/feed.json` later contained zero records, so APEX enrichment, regression T04 and feed freshness failed.

## Defect

`scripts/safe_io.py::dedup_items` included a default **persistent** `IntelDedupEngine.dedup_batch` layer intended to detect previously seen advisories across runs. `scripts/run_pipeline.py::stage_dedup_and_enrich` called this function when **rewriting the canonical retained manifest**. A previously seen advisory is not a new ingest event, but can still be a legitimate stored report record. The persistent filter therefore erased canonical inventory and could feed downstream dashboards/report generation an empty manifest.

## Narrow correction

- Add `use_persistent_history: bool = True` as an optional, keyword-only parameter to `dedup_items`; the original default remains unchanged for incremental ingestion callers.
- Stage 3.2 invokes `dedup_items(items, use_persistent_history=False)` when rebuilding the canonical snapshot. The in-memory exact-content, title and bundle dedup layers and final uniqueness guard still run.
- No timestamp refresh, TLP declassification, confidence inflation, R2 migration, Cloudflare mutation, report release or authentication change.
- R22 regression validates retention of distinct prior records, preservation of a TLP:AMBER record as restricted, continued default persistent suppression, and in-batch duplicate removal.

## Exact release acceptance

Run the full Python/Worker/security CI on the PR HEAD, then confirm on an approved publisher dry run that Stage 3.2 no longer shrinks **all** 45 known records merely because they appeared on previous runs. The mere presence of a record in the canonical manifest does not make it eligible for public release: `scripts/tlp_policy.py`, provenance checks, original publication timestamps, CVE/reference integrity, report materialization and the R18 private eight-dossier gate all remain mandatory.

Do not call a successful R22 CI run Enterprise GO. Live freshness, source HEALTHY telemetry, public report routes/bytes, historical TLP retractions (#725), commercial revocation (#596), independent eight-dossier truth (#721), and deployed SHA parity must be verified separately.
