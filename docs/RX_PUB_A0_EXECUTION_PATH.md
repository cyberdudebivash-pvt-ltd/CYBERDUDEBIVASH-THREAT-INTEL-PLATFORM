# RX_PUB_A0_EXECUTION_PATH

RX-PUB-A0 Phase 0 deliverable. Reconstructs the exact, current-`main` production
path for a customer-facing HTML report, from source ingestion through to the
customer HTTP response — using only workflow YAML, orchestrator source code,
and live production evidence gathered this session. No claim below is inferred
from a comment alone; each stage was located by its actual invocation site.

Evidence gathered 2026-08-13. Superseded findings from prior sessions are
explicitly corrected where checked.

## 1. Exact stage ordering (verified against `.github/workflows/sentinel-blogger.yml` and `scripts/run_pipeline.py`)

```
GH Actions job step: "STAGE 1-3 - Master Pipeline Orchestrator"
  runs: python3 scripts/run_pipeline.py
  │
  ├─ [internal] file_integrity_guard, feed_guard, syntax_guard, bootstrap,
  │             jwt_secret, intel_engine, manifest_stabilisation,
  │             freshness_gate, anti_stale_hardening, schema_validation,
  │             dedup_enrich   (per _STAGE_REGISTRY, run_pipeline.py:3686)
  │
  ├─ [internal] stage_html_reports()   (run_pipeline.py:1575, called main():3885)
  │             → scripts/generate_intel_reports.py against
  │               data/stix/feed_manifest.json
  │             → "Zero-skip policy" (generate_intel_reports.py:32,2542):
  │               NO skip_existing / .exists() short-circuit found anywhere
  │               in main(). Every entry in the manifest window is
  │               unconditionally regenerated on every run. This claim was
  │               re-verified from scratch this session (prior-session
  │               conclusion CONFIRMED, not merely repeated).
  │
  ├─ [internal] manifest_integrity, pipeline_consistency (post-html_reports)
  │
  ├─ [internal] "Stage 3.9" block (run_pipeline.py:~3500-3661):
  │             confidence normalization ([3.9-CNORM])
  │             │
  │             └─ [3.9-RPT] SECOND, CONDITIONAL invocation of
  │                generate_intel_reports.py — run_pipeline.py:3626-3630:
  │                  python3 scripts/generate_intel_reports.py
  │                    --manifest api/feed.json
  │                Fires ONLY for items whose api/feed.json entry has an
  │                empty report_url at this point (run_pipeline.py:3617-3620).
  │                This is a genuinely distinct data source from the main
  │                pass (api/feed.json vs data/stix/feed_manifest.json) and
  │                is a real, confirmed second-writer pathway — see §3 below
  │                for why it was NOT implicated in the current incident.
  │
  │             feed.json sync from api/feed.json ([3.9-SYNC])
  │
  ├─ [internal] validate_repo, write_metrics, feed_json_final
  │
  └─ GH Actions job step ends

GH Actions job step: "STAGE 3.2 - Generate Internal HTML Reports (report_generator)"
  runs: python3 scripts/report_generator.py --manifest data/stix/feed_manifest.json
  → generate_reports_from_manifest() → per-item God Mode gate
    (report_generator.py:73-79, 1653-1718; see docs/REPORT_WRITER_OWNERSHIP_MATRIX.md
    for the full gate logic). For any file already >=60,000 bytes and <7 days
    old, this step SKIPS — i.e. leaves the file exactly as STAGE 1-3 wrote it.
    It only ever writes with ITS OWN separate render engine
    ("CDB-REPORT-ENGINE: report_generator.py v161.x") when the gate does NOT
    skip. This is a distinct rendering implementation from
    generate_intel_reports.py, not a copy of it.

GH Actions job step: "Stage 3.2.5 -- Encoding Remediation Pass"
  runs: python3 scripts/fix_report_encoding.py
  → VERIFIED this session (fix_report_encoding.py:87-99): reads each file's
    own text, applies a fixed mojibake substitution table to that SAME text,
    and writes back only `if text != original`. It is a closed transform on
    the file's own bytes — it cannot revert content to a prior/different
    version. RULED OUT as a mutation-after-generation risk for this incident.

GH Actions job step: "STAGE 3.2.6 - Advisory PDF Generator" — PDF only, does
  not touch reports/*.html.

GH Actions job step: "STAGE 3.3 - Report Validation Gate (HARD FAIL)"
  runs: python3 scripts/validate_reports.py — read-only existence/shape check.

GH Actions job step: "STAGE 3.3.5", "3.3.6", "3.3.7" — mutate
  data/stix/feed_manifest.json's/api/feed.json's report_url STRING fields and
  build read-only indexes (api/reports/index.json). None write reports/*.html
  content.

GH Actions job step: "STAGE 3.4 - Manifest Sanity Guard" — validates
  api/feed.json, does not touch reports/*.html.

GH Actions job step: "STAGE 3.4.5 - STABLE CONTRACT Schema Validation
  (--backfill --api-only)"
  runs: python3 scripts/validate_manifest_schema.py --backfill --api-only
  → VERIFIED this session: zero references to reports/, .html, report_generator,
    or generate_intel_reports anywhere in validate_manifest_schema.py. The
    --backfill flag restores apex_ai_summary/apex_ai_score/tags/severity
    fields on api/feed.json JSON records only. This IS a real data-mutation-
    after-generation step (confirming the mission's suspected failure class
    exists in this pipeline in general) but it cannot be the cause of THIS
    incident because it never touches HTML files — it would need a later
    HTML-regeneration step consuming its output, and none exists downstream
    of it in this job.

GH Actions job step: "STAGE 3.4.8", "3.4.9", "3.4.10" — api/feed.json,
  api/apex_v2/*, api/graph/* builders. Do not touch reports/*.html.

GH Actions job step: "STAGE 3.5 - Upload Intel to Cloudflare R2 (MANDATORY)"
  runs: python3 scripts/r2_upload.py
  → Uploads whatever currently exists under reports/ on the runner's
    filesystem to R2 bucket sentinel-apex-reports at key
    reports/{yyyy}/{mm}/{intel_id}.html. Per the above chain, that content is
    exactly what STAGE 1-3 wrote (report_generator.py and
    fix_report_encoding.py are both confirmed no-ops on an already-correct,
    already-large file).

GH Actions job steps: "STAGE 3.5.1", "3.6", "3.6.5" — R2 index/upload
  integrity gates and the report-engine consistency observability gate.

Cloudflare Worker (workers/intel-gateway/src/index.js), on customer GET
  /reports/{yyyy}/{mm}/{id}.html:
  → resolves item, checks publication-gate, then reads from R2
    (env.REPORTS_R2 binding) and serves the object if found. Falls back to
    generateIntelReport() (a THIRD, independent JS rendering path) only when
    no R2 object is found for a resolvable item — see
    docs/REPORT_WRITER_OWNERSHIP_MATRIX.md.
```

## 2. Answer to the Phase 0 mandate question: does mutation occur between generation and R2 publication?

**Yes, in general** — STAGE 3.4.5's `--backfill` is a real, confirmed example of
data mutation occurring after the HTML generation stages and before R2
upload. **But it mutates `api/feed.json` JSON fields only; it does not
regenerate or rewrite any `reports/*.html` file.** No stage between
`stage_html_reports()` (or the STAGE 3.2 secondary pass) and STAGE 3.5 was
found to rewrite HTML content with a different render than what STAGE 1-3
produced, other than the mechanical, content-preserving encoding-fix pass.

This means: for the current incident fixture, the on-disk HTML file consumed
by STAGE 3.5's `r2_upload.py` should have been byte-identical to whatever
`generate_intel_reports.py`'s main pass (or the 3.9-RPT gap-fill pass, if it
fired for this item) wrote earlier in the same job.

## 3. Why the "3.9-RPT" second-writer pathway was checked and not implicated

`intel--20282e88b1f49bf2` was queried against the repository's current
`api/feed.json` (137 items) this session: **not present**. Since the 3.9-RPT
gap-fill loop (`run_pipeline.py:3611-3640`) only acts on items actually
present in `api/feed.json`'s own item list, an item absent from that file
cannot have been touched by this pathway in the run that produced that
committed `api/feed.json`. This does not prove it was absent from
`api/feed.json` at the moment the *specific failing* pipeline run executed
(that state was not preserved), so this is recorded as a checked-but-not-
fully-closed line of inquiry, not a definitive exclusion.

## 4. Live production ground truth captured this session

Direct HTTPS GET, no cache-defeating tricks needed to reproduce (public,
unauthenticated, production endpoint):

```
GET https://intel.cyberdudebivash.com/reports/2026/08/intel--20282e88b1f49bf2.html
HTTP/2 200
content-length: 91893
etag: "8dcb7138618e953395fbc22ddc28fe24"
cache-control: public, max-age=86400, stale-while-revalidate=3600
server: cloudflare
(no cf-cache-status header, no age header — on repeat request with
 Cache-Control: no-cache / Pragma: no-cache, both still absent)

PUBLIC_HTTP_SHA256 = e3373fd035e388a37bdee9b80b8d74609035ec0986ed9ca79ff30b37d99df26c
PUBLIC_HTTP_MD5    = 8dcb7138618e953395fbc22ddc28fe24  (matches ETag exactly)
Body contains:      "CDB-REPORT-ENGINE: generate_intel_reports.py vv184.0 --"
Body contains:      "WHAT TO DO TODAY?" / "PATCH WITHIN 14 DAYS — ..." (the
                     confirmed pre-fix stale text pattern)
```

Three findings from this capture:

1. **ETag == MD5 of the exact served body.** For a non-multipart R2 PUT this
   is the expected relationship for an S3-compatible object store, and it
   confirms the Worker is serving the literal R2 object body, not a
   transformed/cached copy with a different checksum relationship.
2. **The engine marker proves authorship**: this content was written by
   `generate_intel_reports.py` at platform version `v184.0` (the *current*
   platform version, not a stale pre-184.0 artifact) — not
   `report_generator.py`, and not the Worker's `generateIntelReport()`
   fallback (which carries no engine marker at all — confirmed by grep, zero
   matches for "PATCH WITHIN" / "WHAT TO DO TODAY" anywhere in
   `workers/intel-gateway/src/index.js`). **This rules out Writers B and C as
   the source of the currently-live content for this incident.**
3. **No observable caching layer.** `cf-cache-status` and `age` are absent
   from the response even under `Cache-Control: no-cache`, and
   `workers/intel-gateway/src/index.js` was grepped for `caches.default`,
   `caches.open`, `cache.match`, `cache.put` — zero matches. There is no
   Worker-side Cache API usage on this path at all. This is evidence against
   (not proof against) a CDN/edge-cache explanation for the staleness — see
   `docs/R2_RUNTIME_BINDING_CERTIFICATION.md` for the fuller Phase 6/7 writeup.

## 5. What remains unproven at end of Phase 0

This sandbox environment has `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
present but **no `CF_ACCOUNT_ID`** (required to construct the R2
S3-compatible endpoint `https://<account_id>.r2.cloudflarestorage.com`) and
**no `aws` CLI installed**. `scripts/r2_upload.py` additionally shows the
reports bucket may be uploaded under a distinct scoped credential pair
(`CF_R2_REPORTS_KEY_ID` / `CF_R2_REPORTS_SECRET_KEY`, swapped in temporarily
around the reports-upload phase) that is not present here either. **Direct
R2 HEAD/GET against the real bucket, and the direct-object control
experiment (Phase 5), cannot be performed from this environment.** Those
credentials exist only inside the repository's GitHub Actions secrets. Phases
1-5's remaining hash-level evidence requires a CI-executed diagnostic (see
`docs/RX_PUB_A0_INCIDENT_ROOT_CAUSE.md`, in progress) rather than direct
sandbox access.

Per Section 43/44 of the mission: until that evidence is captured, the
incident root cause remains **ROOT_CAUSE_NOT_FULLY_PROVEN**. What Phase 0
narrows it to: the divergence is not explained by any known HTML-mutating
stage between generation and upload, is not explained by Writer B or Writer
C authorship of the live artifact, and is not well-explained by an
observable caching layer. The remaining candidate classes are
`AWS_SYNC_DECISION_DEFECT`, `R2_KEY_MAPPING_DEFECT`, `PIPELINE_RACE`, and
"the pipeline simply has not successfully completed `stage_html_reports()`
for this item since the RX-PR1 fix merged" (a `GENERATION_ORDER_DEFECT`-
adjacent explanation requiring CI run-history evidence, not yet gathered).
