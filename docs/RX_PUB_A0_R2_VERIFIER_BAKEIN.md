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
| _(none recorded yet)_ | | | | | Awaiting the next real STAGE 3.6a run's output after PR #183/#184 land on `main`. |

## Next update

This table is updated as real runs complete -- see
`docs/RX_PUB_A0_PRODUCTION_CERTIFICATION.md` (RX-PUB-A0.4's final
deliverable, not yet written) for the point-in-time enforcement-readiness
verdict once this evidence is gathered.
