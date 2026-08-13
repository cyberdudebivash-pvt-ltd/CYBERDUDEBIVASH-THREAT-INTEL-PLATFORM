# RX_PUB_A0_R2_VERIFIER_BAKEIN

RX-PUB-A0.4 Phase 1 (Sections 8-11) deliverable. Tracks real production
evidence for `scripts/r2_reports_verifier.py`'s two layers (R2-vs-LOCAL and
CUSTOMER-vs-LOCAL) before `--enforce` is authorized, per the mission's own
requirement: enforcement must be evidence-backed, not assumed correct from
code review alone.

## Status: bake-in evidence collection in progress. Not yet enforcement-safe.

This document is created as part of PR #184 (RX-PUB-A0.4B) to fix a dangling
reference: `docs/RX_PUB_A0_PUBLIC_HTTP_IDENTITY_SPEC.md` cited this file
before it existed. It is a stub, honestly reflecting that no real
STAGE 3.6a production run has been recorded here yet at the time this PR
merges. It exists to be filled in incrementally as real evidence arrives --
not to pre-declare a result before the evidence exists.

## What "enforcement-safe" requires (exit criteria for `--enforce`)

Per the mission's Section 27 and this session's own reasoning, `--enforce`
on STAGE 3.6a is not authorized until:

1. At least 2-3 independent real production pipeline runs have completed
   STAGE 3.6a and their `data/quality/rx_pub_a0_reports_artifact_manifest.json`
   output has been captured and reviewed here.
2. Those runs show **zero false-positive** `STALE_OR_DIVERGENT` /
   `LIVE_STALE_OR_DIVERGENT` classifications against genuinely in-window,
   actively-generated reports (a `HISTORICAL`/out-of-window divergence, as
   documented in `docs/RX_PUB_A0_PUBLIC_HTTP_IDENTITY_SPEC.md`'s "A note on
   a real (correctly non-alarming) finding" section, does not count against
   this -- it is the correct, expected classification for an aged-out item).
3. `UNKNOWN` / `LIVE_FETCH_FAILED` rates are low and explainable (e.g.
   transient network errors, not a systemic credential or connectivity
   problem) -- since RX-PUB-A0.4B's fail-open bug fix means any of these now
   correctly blocks `--enforce`, a persistently high rate would make
   `--enforce` unusable rather than unsafe, which is its own (different)
   problem to solve first.
4. `run_deadline_exceeded` is `false` across the recorded runs -- if the
   600-second run-level deadline (added in RX-PUB-A0.4B) is regularly being
   hit, the workflow's 15-minute STAGE 3.6a timeout needs revisiting before
   `--enforce` can be trusted to finish within it.

## Evidence log

| Run ID | Date | R2 layer summary | Public HTTP layer summary | `run_deadline_exceeded` | Notes |
|---|---|---|---|---|---|
| [31713054946](https://github.com/cyberdudebivash-pvt-ltd/CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM/actions/runs/31713054946) | 2026-08-13 15:50-15:54 UTC | **INVALID -- tooling bug, not real evidence.** 314 in-window, 0 REMOTE_VERIFIED, 314 FAILED ("R2 object does not exist"), 0 UNKNOWN. | N/A (commit predates the public-HTTP layer, PR #184) | false | See "Run A: root-caused as a credential-wiring bug" below. Struck from consideration -- does not count toward the 2-3 clean runs required for `--enforce`. |

### Run A: root-caused as a credential-wiring bug, not a production incident

Run 31713054946 (STAGE 3.6a at commit `51ff48f0`, PR #183's merge commit)
reported **100% of in-window reports as "R2 object does not exist."** Taken
at face value this would be a catastrophic finding -- but in the same job,
moments earlier, **STAGE 3.5.1 (R2 Reports Index Integrity Gate, a separate,
already-proven gate using the same bucket)** reported `500 clean` objects.
Two gates checking overlapping data in the same run cannot both be right --
this was correctly treated as a signal to investigate the newer, unproven
tool rather than accept it as a real incident (mission Section 30's
HISTORICAL-vs-ACTIVE-defect discipline, applied here to
tooling-bug-vs-real-defect instead).

**Root cause, confirmed by reading the actual code paths:**

- `scripts/r2_reports_verifier.py` supports an *optional* dedicated
  reports-bucket credential pair (`CF_R2_REPORTS_KEY_ID` /
  `CF_R2_REPORTS_SECRET_KEY`) that, when present, swaps in for the
  job-level data-bucket-scoped `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
  before every R2 call -- the same pattern `scripts/r2_upload.py` and
  `scripts/r2_reports_integrity.py` already use.
- `.github/workflows/sentinel-blogger.yml`'s STAGE 3.5 and STAGE 3.5.1 steps
  both explicitly set those two env vars. The STAGE 3.6a step this mission
  added (PR #183) did not -- it had no `env:` block at all.
- With both vars empty, `r2_reports_verifier.py`'s swap check
  (`if _reports_key_id and _reports_secret:`) is false, so it silently used
  the job-level DATA-bucket-scoped credentials against the REPORTS bucket
  instead.
- `r2_upload_verifier.py`'s reused `_s3api_head_object()` classifies *any*
  AWS CLI exit code `254` as "object not found" (`elif "NoSuchKey" in
  result.stderr or result.returncode == 254:`) without confirming the error
  was actually `NoSuchKey` -- awscli returns the same generic exit code for
  `AccessDenied`/`403` as it does for a real 404. A credential/permission
  mismatch is therefore indistinguishable from "genuinely missing" through
  this path.

**Fix applied**: added the missing `env:` block to STAGE 3.6a
(`.github/workflows/sentinel-blogger.yml`), mirroring STAGE 3.5 /
STAGE 3.5.1 exactly. New regression test
`tests/test_r2_reports_verifier.py::TestWorkflowStepHasReportsBucketCredentials`
parses the workflow YAML and asserts both env vars are present on the
STAGE 3.6a step; confirmed to fail against the pre-fix workflow via
`git stash`.

**Deliberately not touched in this same fix**: the `returncode == 254`
ambiguity in `r2_upload_verifier.py`'s `_s3api_head_object()` is pre-existing
shared code (also used successfully by STAGE 3.6, which has correct
credentials and has not exhibited this failure mode). Per this repo's
Zero Unnecessary Modification principle, changing shared/proven engine code
requires its own evidence of a defect in *its* actual usage, not just a
theoretical ambiguity exposed by a misconfiguration elsewhere. Flagged here
as a known latent risk worth a future dedicated look (it means a real R2
outage or expired credential would also currently misreport as
"content missing" rather than "unable to verify") -- not fixed in this pass.

## Next update

Awaiting a fresh real STAGE 3.6a run against the credential fix above (next
`main`-branch `sentinel-blogger.yml` run once this fix lands). That run is
"Run A" of the 2-3 required for `--enforce` sign-off. See
`docs/RX_PUB_A0_PRODUCTION_CERTIFICATION.md` (RX-PUB-A0.4's final
deliverable, not yet written) for the point-in-time enforcement-readiness
verdict once this evidence is gathered.
