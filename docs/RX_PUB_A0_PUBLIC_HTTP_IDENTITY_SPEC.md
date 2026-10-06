# RX_PUB_A0_PUBLIC_HTTP_IDENTITY_SPEC

RX-PUB-A0.4 Phase 2 (Sections 12-16) deliverable. Documents the public HTTP
byte-identity layer added to `scripts/r2_reports_verifier.py`, closing the
R2-vs-CUSTOMER half of the identity chain that `docs/RX_PUB_A0_ARTIFACT_IDENTITY_SPEC.md`
(PR #183) left explicitly open.

## Why an extension, not a new script

Per the mission's Section 4 reuse mandate: the public HTTP layer needs no R2
credentials, needs no new manifest, and needs no new per-report iteration
loop -- it is one more fact about the same report, computed in the same pass
that already fetches the R2 object. Building it as a separate script would
require re-loading the manifest, re-resolving local paths, and re-computing
`artifact_sha256` a second time for no reason. It is added directly to
`verify_one()` in `scripts/r2_reports_verifier.py`, and to the same output
manifest (`data/quality/rx_pub_a0_reports_artifact_manifest.json`, schema
version bumped `1` -> `2` for the additional fields).

## What "public" means here

`{PUBLIC_BASE_URL}/{r2_key}` -- by default `https://intel.cyberdudebivash.com/reports/{yyyy}/{mm}/{id}.html`,
the exact same path family a real customer's browser or the dashboard's
"FULL INTEL" link resolves to. `PUBLIC_BASE_URL` is overridable via the
`RX_PUB_A0_PUBLIC_BASE_URL` environment variable for non-production testing,
but defaults to the real production host.

## Independence from the R2 credential-gated layer

The R2 layer (`_s3api_head_object` / `_get_object_bytes`) requires
`CF_ACCOUNT_ID` + R2 access keys and returns `UNKNOWN` when they are absent
(this sandbox's exact situation -- no `CF_ACCOUNT_ID`, no `aws` CLI). The
public layer is an ordinary, unauthenticated HTTPS GET and runs regardless.
`tests/test_r2_reports_verifier.py::TestPublicHttpLayer::test_public_layer_runs_without_any_r2_credentials`
proves this directly: with both R2 helpers forced to their credential-absent
return value, the public layer still correctly classifies `LIVE_VERIFIED`.
This was also confirmed against real production from this sandbox (no R2
creds available, `_fetch_public` still returns real 200/404 responses with
real bytes) -- see the verification log in the PR.

## Classification (`live_state`)

| State | Meaning |
|---|---|
| `LIVE_VERIFIED` | `artifact_sha256 == public_sha256`. Customer receives exactly the certified bytes. |
| `LIVE_STALE_OR_DIVERGENT` | Public response fetched successfully but its SHA-256 does not match the local artifact -- R2-vs-CUSTOMER divergence (Section 12's Case B: "R2 correct, customer response stale" -- or, if R2 itself also diverges, Case A). |
| `LIVE_MISSING` | Public HTTP GET returned 404. |
| `LIVE_FETCH_FAILED` | Network error, timeout, or non-404 HTTP error after retries. Deliberately distinct from `LIVE_VERIFIED` -- a failed check is never silently treated as a passed one (`test_public_fetch_failure_is_live_fetch_failed_not_verified`). |
| `PENDING` | Not yet checked (only reached when `--skip-public` is set). |

`LIVE_BLOCKED_EXPECTED` (mission Section 16) is not yet implemented: the
current in-window verification set does not distinguish gated/premium
reports from ordinary ones, so a 403 on this path family would currently be
recorded as `LIVE_FETCH_FAILED`. Correctly classifying an *expected* 403 for
a gated fixture requires knowing the report's gating state going in, which
is exactly what the golden publication corpus (mission Section 21,
`docs/RX_PUB_A0_GOLDEN_PUBLICATION_CORPUS.md`, not yet built) is for -- not
duplicated here ahead of that work.

## Cache-awareness (Section 15) -- what was actually found

Captured safe response headers for every public fetch:
`cf-ray`, `cache-control`, `age`, `etag`, `last-modified`, `cf-cache-status`,
`content-length`, `content-type`. Live smoke tests against real production
this session (see `docs/RX_PUB_A0_EXECUTION_PATH.md` Section 4 for the
original finding, re-confirmed here) show **no `cf-cache-status` and no
`age` header on any response observed**, consistent with the earlier finding
that this Worker route has no Cache API usage and is not intercepted by
Cloudflare's zone-level HTTP cache -- each request appears to read R2
directly. This is evidence, not proof, that `LIVE_STALE_OR_DIVERGENT` on
this path family reflects the R2 object's actual content rather than a
stale edge-cache entry; the header capture exists specifically so a future
investigation isn't stuck re-deriving this by hand if that ever changes.

## A note on a real (correctly non-alarming) finding during smoke-testing

While validating this layer against real production, an ad-hoc test against
`reports/2026/08/intel--0003d531f5efa0058e3ef043.html` (picked arbitrarily,
not from the active window) showed `LIVE_STALE_OR_DIVERGENT`: local
(git-committed) bytes differ from the live public bytes. Before treating
this as a finding, it was checked against `data/stix/feed_manifest.json`
and confirmed **not in the active generation window** (last touched
2026-08-11, two days prior) -- exactly the `HISTORICAL` lifecycle case
mission Section 30 warns against misreading as an active-generation defect.
Both the local and live copies carry the identical
`generate_intel_reports.py` engine marker, ruling out a rogue writer; the
two copies simply reflect different points in that item's generation
history from before it aged out, with nothing currently keeping them in
sync since neither side is being actively regenerated anymore. This is
recorded here as a demonstration that the classification logic itself
correctly avoided a false "active defect" conclusion, and as a reminder
that **`verify_one()` must only be interpreted against genuinely in-window
entries** -- the `main()` loop already does this correctly (it iterates
`data/stix/feed_manifest.json`, not the `reports/` directory), this note
documents the hazard for any future ad-hoc/manual invocation.

## Cost (Section 37-38)

One additional HTTPS GET per in-window report (~150-305 reports observed
this session). `STAGE 3.6a`'s workflow timeout was raised from 10 to 15
minutes to accommodate this. `--skip-public` exists as a cost-governance
escape hatch (Section 37) if measured duration ever becomes a problem, but
is not used by default -- Section 14 prefers full in-window coverage over
sampling where operationally bounded, and this is bounded by the same
active-window scope PR #183 already established.

## Status: implemented, not yet enforced

Same bake-in posture as the R2 layer: `live_state` outcomes are recorded in
the manifest and logged, but do not affect the STAGE 3.6a step's exit code
unless `--enforce` is passed (not yet). See
`docs/RX_PUB_A0_R2_VERIFIER_BAKEIN.md` for the bake-in evidence this and the
R2 layer both need before `--enforce` activation.
