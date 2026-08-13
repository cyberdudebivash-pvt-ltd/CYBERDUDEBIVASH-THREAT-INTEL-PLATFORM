# RX_PUB_A0_ARTIFACT_IDENTITY_SPEC

RX-PUB-A0 Phase 9 / Sections 19-25 deliverable. Defines the artifact-identity
manifest produced by `scripts/r2_reports_verifier.py` and the two distinct
hash concepts this mission requires kept separate.

## Two hash concepts (Section 19) -- not conflated

**Source/certification identity** (`source_content_fingerprint` in the
mission's suggested schema): detects drift in the *input* data feeding a
report's certification decision (P20/P21/P23/P25/P26). This already exists
in `workers/intel-gateway/src/publication-gate.js`'s `content_hash` /
fingerprint logic. **Not touched by this work.**

**Rendered artifact identity** (`artifact_sha256`): identifies the exact
customer-facing HTML bytes. This is what was missing, and what this work
adds. It answers a different question entirely: not "has the input changed"
but "are the bytes R2 is serving the exact bytes the certified generator
produced."

## Manifest schema (`data/quality/rx_pub_a0_reports_artifact_manifest.json`)

Reuses the mission's suggested shape, scoped to the fields
`scripts/r2_reports_verifier.py` actually populates:

```json
{
  "schema_version": "1",
  "generated_at": "2026-08-13T...Z",
  "pipeline_run_id": "<GITHUB_RUN_ID>",
  "release_sha": "<GITHUB_SHA>",
  "bucket": "sentinel-apex-reports",
  "reports": {
    "<intel_id>": {
      "source_record_id": "<intel_id>",
      "source_updated_at": "<processed_at or timestamp>",
      "path": "reports/YYYY/MM/<intel_id>.html",
      "r2_key": "reports/YYYY/MM/<intel_id>.html",
      "generator": "generate_intel_reports.py",
      "size_bytes": 0,
      "artifact_sha256": "<sha256 of the local file>",
      "remote_sha256": "<sha256 of the fetched R2 object, or null>",
      "remote_verified_at": "<timestamp, or null>",
      "publication_state": "REMOTE_VERIFIED | STALE_OR_DIVERGENT | FAILED | UNKNOWN | PENDING"
    }
  },
  "summary": {
    "total_in_window": 0,
    "remote_verified": 0,
    "stale_or_divergent_or_failed": 0,
    "unknown": 0,
    "missing_local": 0,
    "elapsed_seconds": 0.0
  }
}
```

`certification_version` / `certification_state` from the mission's original
suggested schema are intentionally omitted here -- they belong to the
publication-gate's certification decision (P20/P21/P23/P25/P26), a separate,
pre-existing, unmodified system (see `workers/intel-gateway/src/
publication-gate.js`). Duplicating those fields into this manifest would
create a second, driftable copy of a value that already has one authoritative
source -- the exact Single-Source-of-Truth violation this whole mission
exists to close. If a future consumer needs both facts together, it should
join on `source_record_id`, not duplicate the certification fields here.

## Publication state values actually implemented

| State | Meaning |
|---|---|
| `REMOTE_VERIFIED` | `artifact_sha256 == remote_sha256`. The only state that should ever be treated as "customer-ready" from this manifest's perspective. |
| `STALE_OR_DIVERGENT` | R2 object exists but its SHA-256 does not match the local artifact. This is the exact incident class `docs/RX_PUB_A0_INCIDENT_ROOT_CAUSE.md` documents. |
| `FAILED` | R2 object does not exist at the expected key, or no local artifact exists for an in-window manifest entry. |
| `UNKNOWN` | R2 could not be reached (HEAD or GET failed after retries) -- deliberately distinct from `REMOTE_VERIFIED`. A failed check must never be silently treated as a passed one (see `test_get_object_failure_after_successful_head_is_unknown_not_verified` in `tests/test_r2_reports_verifier.py`). |
| `PENDING` | Default/unset -- not reached by the current implementation (every report ends in one of the above), retained for schema forward-compatibility with a future pre-upload manifest-write step. |

## Scope: in-window only, not the full historical corpus

Verifies every report currently in `data/stix/feed_manifest.json` --
the same set `generate_intel_reports.py`'s "Zero-skip" policy unconditionally
regenerates every pipeline run (~150-250 reports at time of writing). This
is deliberately the "changed this run" set the mission's Section 22 requires
full, non-sampled verification for, without triggering the "unbounded
per-object GET validation" Section 36 warns against against the full
15,000+ report historical corpus. Historical reports outside the active
window are out of scope per Section 26 (a separate, later, bounded
correction task).

## Rollout status: observability bake-in, not yet a HARD FAIL gate

Wired into the pipeline as **STAGE 3.6a**, immediately after the existing
STAGE 3.6 (data-bucket verifier) and before cache bust (STAGE 3.7), running
with `|| true` and without `--enforce` -- it currently only observes and
records. This mirrors the exact rollout pattern this repository already
established for STAGE 3.6.5 (`report_engine_consistency_gate.py`): a new
gate on customer-facing keyspace ships observability-first, and is switched
to hard-fail (`--enforce`) only after a bake-in period shows zero false
positives against real production R2 traffic.

**This is a deliberate, documented gap against the mission's Section 48
rejection condition** ("changed certified artifact is not remotely verified"
must not remain non-blocking for commercial certification). It is not yet
closed. Closing it requires: (1) a run history from real CI executions
(this sandbox has no R2 credentials to generate that history --
`docs/RX_PUB_A0_EXECUTION_PATH.md` Section 5), and (2) a follow-up PR adding
`--enforce` to the STAGE 3.6a workflow step once that history exists.

## What this does NOT yet do

- Does not verify `PUBLIC_HTTP_SHA256` (the customer-facing HTTP response) --
  only `R2_SHA256` (the object store). Section 23's four-layer chain
  (SOURCE → GENERATED → CERTIFIED → LIVE) is only partially closed: this
  closes GENERATED-vs-R2, not R2-vs-LIVE. Given `docs/RX_PUB_A0_EXECUTION_PATH.md`
  §4 already established the Worker serves R2 objects directly with no
  observed caching layer, R2-vs-LIVE divergence is a lower-probability gap
  than GENERATED-vs-R2 was, but it remains unverified by automation.
- Does not implement the golden-fixture corpus (A0-1..A0-8, Section 27) --
  it verifies whatever is actually in the active window on a given run, not
  a fixed, curated regression set.
- Does not yet run the Phase 5 direct-object-upload control experiment
  (Section 11-12) against the live incident fixture, since that fixture has
  aged out of the active window (`docs/RX_PUB_A0_INCIDENT_ROOT_CAUSE.md`) and
  is therefore out of this script's in-window scope by design.
