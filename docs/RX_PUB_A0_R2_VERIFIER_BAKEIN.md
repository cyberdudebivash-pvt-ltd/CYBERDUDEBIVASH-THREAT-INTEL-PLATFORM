# RX_PUB_A0_R2_VERIFIER_BAKEIN

RX-PUB-A0.4 Phase 1 (Sections 8-11) deliverable. Tracks real production
evidence for `scripts/r2_reports_verifier.py`'s two layers (R2-vs-LOCAL and
CUSTOMER-vs-LOCAL) before `--enforce` is authorized, per the mission's own
requirement: enforcement must be evidence-backed, not assumed correct from
code review alone.

## Status: bake-in evidence collection in progress. Not yet enforcement-safe.

**Update (2026-08-13, Run 1 below): the first real post-credential-fix run
surfaced a second, more fundamental gap than the one this doc originally
tracked.** The R2 layer (LOCAL-vs-R2) is now confirmed clean. The public-HTTP
layer (R2-vs-CUSTOMER) is not simply "clean" or "dirty" -- sample-based
investigation shows its 192/192 non-`LIVE_VERIFIED` result is explained by
**three distinct causes, none of which are LOCAL/R2 data corruption**, but
two of which mean the verifier itself is currently asserting the wrong thing.
See "Run 1" below before reading the exit criteria, which predate this
finding and are now known to be incomplete.

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
5. **(Added after Run 1, 2026-08-13.)** The public-HTTP layer's
   `LIVE_STALE_OR_DIVERGENT` / `LIVE_MISSING` classification must not fire
   for a report the platform's own publication gate (`evaluatePublicationGate`
   in `workers/intel-gateway/src/index.js`, surfaced at
   `/api/v1/reports/{id}/publication-status`) currently reports as
   `customer_ready: false`. As written today, `r2_reports_verifier.py`
   compares every in-window LOCAL artifact against the public HTTP response
   with no awareness of the gate's verdict -- so a report the gate is
   *correctly* refusing to serve (below certification threshold, or "do not
   publish") is indistinguishable, in the manifest, from a report that is
   wrongly stale or missing. Turning on `--enforce` against the verifier as
   it exists today would hard-fail STAGE 3.6a on every run that has even one
   gate-rejected in-window item -- which Run 1 shows is the common case, not
   an edge case.

## Evidence log

| Run ID | Date | R2 layer summary | Public HTTP layer summary | `run_deadline_exceeded` | Notes |
|---|---|---|---|---|---|
| [31713054946](https://github.com/cyberdudebivash-pvt-ltd/CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM/actions/runs/31713054946) | 2026-08-13 15:50-15:54 UTC | **INVALID -- tooling bug, not real evidence.** 314 in-window, 0 REMOTE_VERIFIED, 314 FAILED ("R2 object does not exist"), 0 UNKNOWN. | N/A (commit predates the public-HTTP layer, PR #184) | false | See "Run A: root-caused as a credential-wiring bug" below. Struck from consideration -- does not count toward the 2-3 clean runs required for `--enforce`. |
| [31727337104](https://github.com/cyberdudebivash-pvt-ltd/CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM/actions/runs/31727337104) (STAGE 3.6a: 18:29:31-18:39:34 UTC) | 2026-08-13 | **VALID, credential fix confirmed working.** 293 in-window, 192 REMOTE_VERIFIED, 0 STALE_OR_DIVERGENT/FAILED, 101 UNKNOWN (run-deadline remainder, not errors). | **VALID data, but not clean -- see Run 1 below.** 0 LIVE_VERIFIED, 125 LIVE_STALE_OR_DIVERGENT, 67 LIVE_MISSING, 101 UNKNOWN (same remainder). | **true** (600s budget exhausted at 192/293 reports) | First real post-#187 run. Disqualifies on criterion 4 (`run_deadline_exceeded`) by itself; deeper investigation also surfaced the new criterion 5 gap. Does not count toward the 2-3 clean runs required for `--enforce`. |

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

### Run 1: R2 layer clean; public-HTTP layer traced to three non-corruption causes

Run [31727337104](https://github.com/cyberdudebivash-pvt-ltd/CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM/actions/runs/31727337104)
(STAGE 3.6a, commit `3ce22c9d`) is the first real production run after the
PR #187 credential fix. Raw manifest, fetched live from
`GET /api/v1/rx-pub-a0/reports-identity?full=1`:

```text
R2 layer:          293 in-window, 192 REMOTE_VERIFIED, 0 STALE_OR_DIVERGENT/FAILED, 101 UNKNOWN
Public HTTP layer:  0 LIVE_VERIFIED, 125 LIVE_STALE_OR_DIVERGENT, 67 LIVE_MISSING, 101 UNKNOWN
run_deadline_exceeded: true (600s budget exhausted at 192/293 reports)
```

**R2 layer is clean and confirms the PR #187 fix.** Zero mismatches across
192 checked reports -- the credential-wiring bug from the earlier INVALID
run is genuinely fixed. The remaining 101 are the run-deadline remainder
(never reached within the 600s budget), not errors -- exactly the documented
`UNVERIFIED_DEADLINE` behavior, not a silent drop.

**Public HTTP layer: 0/192 `LIVE_VERIFIED` at first looked catastrophic.**
It is not. A stratified sample of 20 non-verified reports (7 `LIVE_MISSING`,
13 `LIVE_STALE_OR_DIVERGENT`, `random.seed(42)` over the full population)
was cross-referenced against each report's own
`/api/v1/reports/{id}/publication-status` -- the platform's live, independent
publication-gate verdict -- plus a direct re-fetch of one `LIVE_STALE_OR_DIVERGENT`
report about an hour after the run, to distinguish three causes:

| Cause | Evidence | Sample share | Real defect? |
|---|---|---|---|
| **Publication gate correctly rejects the report** (`customer_ready: false`, e.g. `P25_BELOW_THRESHOLD`, `P23_OPERATIONAL_READINESS_DO_NOT_PUBLISH`) | 7/7 sampled `LIVE_MISSING` + 2/13 sampled `LIVE_STALE_OR_DIVERGENT` were gate-rejected | 9/20 (45%) | **No.** The Worker is doing exactly what `workers/intel-gateway/src/index.js`'s "P0 CUSTOMER PUBLICATION AUTHORIZATION GATE" (line ~4130) is designed to do -- refuse to serve a below-threshold report. `generate_intel_reports.py`'s Zero-skip policy regenerates the LOCAL artifact for every in-window item regardless of certification score, so a gate-rejected item will *always* have a LOCAL/R2 artifact that the public endpoint correctly refuses to serve byte-for-byte (it 404s, or in a race with a still-cached older approved copy, serves stale bytes -- see next row). The verifier has no knowledge of `customer_ready` and flags both outcomes as "divergence." |
| **Item not resolvable by `findItemBySlug` in the Worker's current feed search window** (`reason_codes: ["ITEM_NOT_RESOLVABLE"]`) | 3/13 sampled `LIVE_STALE_OR_DIVERGENT` | 3/20 (15%) | **Possibly a real, separate gap** -- not investigated further in this pass. `findItemBySlug`'s search window is apparently narrower than the report generator's in-window set. Needs its own root-cause pass before it can be ruled non-blocking; flagged here, not fixed. |
| **Genuine CDN edge-cache staleness for a gate-approved report** (`customer_ready: true`, empty `reason_codes`, bytes still diverge) | 8/13 sampled `LIVE_STALE_OR_DIVERGENT` | 8/20 (40%) | **Yes, real -- and directly confirmed.** `intel--3e0d80c18f56f5ed`: manifest shows `remote_sha256` (R2, correct) == `artifact_sha256` (LOCAL) at `18:33:21Z`, but `public_sha256` (fetched one second later, `18:33:22Z`) was a *different* hash, served with `cache-control: public, max-age=86400, stale-while-revalidate=3600` from Cloudflare POP `ORD`. Re-fetching the same URL ~54 minutes later (this session, POP `IAD`) returned the *current, correct* bytes matching `artifact_sha256` exactly. `workers/intel-gateway/src/index.js`'s canonical `/reports/**` handler (line ~4212) sets `max-age=86400` on every 200 response and there is no corresponding purge: `scripts/bust_kv_cache.py`'s `CACHE_KEYS` list (`idx:reports`, `ai:*`, `reports:premium:*`, `checkout:*`) has no entry for the per-report `/reports/**` HTML cache. A report regenerated with new content (score/exec-summary/freshness fields; source records do get re-scored between runs) can be served stale to whichever Cloudflare POP cached the prior version, for up to 24h, with no active invalidation -- self-healing only via natural TTL expiry or an uncached POP. |

None of the three causes are LOCAL-vs-R2 corruption -- the canonical artifact
in R2 is correct in every sampled case. But two of the three
(publication-gate rejection, and -- pending its own investigation --
`ITEM_NOT_RESOLVABLE`) are the verifier asserting an identity requirement
that the platform never intended to hold, and the third (edge-cache
staleness) is a real, evidenced, currently-unmitigated gap between "R2 is
correct" and "every customer request gets the correct bytes immediately."
Turning on `--enforce` today would hard-fail on the common case, not the
exceptional one -- see new exit criterion 5 above.

**This run does not count toward the 2-3 clean runs required for `--enforce`**,
both because `run_deadline_exceeded: true` already disqualifies it under
criterion 4, and because it fails the newly-added criterion 5.

## Next update

Run 1 changed what "clean" needs to mean before further runs are worth
collecting toward the 2-3 required for `--enforce` -- collecting Run 2/3
against the verifier exactly as it exists today would keep reproducing the
same ~65% non-`LIVE_VERIFIED` rate for the same non-corruption reasons, not
converge toward zero. Before more bake-in runs are meaningful, the verifier
itself needs to close (at minimum) the criterion-5 gap:

1. Have `r2_reports_verifier.py` consult each report's
   `/api/v1/reports/{id}/publication-status` (or the same
   `evaluatePublicationGate` logic, called directly rather than duplicated)
   and classify a gate-rejected report as its own state -- e.g.
   `GATE_BLOCKED` -- distinct from `LIVE_STALE_OR_DIVERGENT` / `LIVE_MISSING`,
   so `--enforce` can exempt it correctly instead of hard-failing on expected
   behavior.
2. Investigate the `ITEM_NOT_RESOLVABLE` cause (15% of the sample) to confirm
   whether it is a second instance of the same gap or something new.
3. Decide, with the CDN-cache-staleness evidence in hand, whether the fix is
   (a) an active purge of the specific `/reports/**` key on every
   regeneration (extending `bust_kv_cache.py` or a dedicated step), (b) a
   grace-period exemption in the verifier (e.g. don't flag divergence for a
   report regenerated within the last N minutes, since propagation is
   expected, bounded latency, not corruption), or (c) both. This is a design
   decision, not yet made.

None of this is authorized to happen silently as part of routine bake-in
monitoring -- it changes the verifier's own classification logic and is
scoped as its own RX-PUB-A0.5C/D follow-up work, not folded into this
tracking document's routine evidence-log updates.

## RX-PUB-A0.6 update (6A-6D shipped)

The three items above were closed by the RX-PUB-A0.6 sub-mission, each as
its own PR: **6A** (#193) made the verifier publication-gate-aware,
directly addressing item 1 (gate-rejected reports now classify as
`LIVE_EXPECTED_DENIAL`, never folded into a failure count) and added the
`PUBLICATION_GATE_BYPASS` hard-defect class. **6B** (#194, bundled with 6C)
added a precise Cloudflare cache purge-and-reverify, addressing item 3(a).
**6C** (also #194) closed a confirmed resolver gap -- `findItemBySlug`
wasn't checking `data/stix/feed_manifest.json`, the broader in-window
population this verifier itself treats as authoritative -- answering item 2
(yes, `ITEM_NOT_RESOLVABLE` was a second, real instance of the same
root-shape gap, not something new). **6D** (#195) replaced the sequential
per-report loop with a bounded 8-worker pool, targeting the
`run_deadline_exceeded` disqualifier directly.

### Interim evidence: 6C confirmed on a real run, 6D not yet observed

Run [31773568022](https://github.com/cyberdudebivash-pvt-ltd/CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM/actions/runs/31773568022)
(STAGE 3.6a, commit `628a8da2` -- contains 6A+6B+6C, but predates 6D/#195)
was the first real production run to reach STAGE 3.6a after 6C merged:

```text
In-window manifest entries: 494
R2 summary:         494 in-window, 155 REMOTE_VERIFIED, 0 STALE_OR_DIVERGENT/FAILED, 339 UNKNOWN, 0 missing-local, 602.96s
Public HTTP summary: 0 LIVE_VERIFIED, 127 LIVE_EXPECTED_DENIAL, 5 LIVE_STALE_OR_DIVERGENT/MISSING_UNEXPECTED,
                     0 LIVE_RESOLUTION_FAILED, 5 LIVE_FETCH_FAILED, 339 LIVE_NOT_PROCESSED_DEADLINE, 18 UNKNOWN
gate-bypass: 0
run_deadline_exceeded: true (600s budget exhausted at 155/494 reports)
```

**6C confirmed, precisely**: `LIVE_RESOLUTION_FAILED = 0` across all 155
reports the run actually reached, versus the Phase 0 baseline
(`docs/RX_PUB_A0_6_PROOF_BEFORE_CHANGE.md`) where 4/4 sampled reports were
confirmed unresolvable before the fix -- zero reports fell into the specific
"the resolver couldn't find this item to evaluate its gate at all" class 6C
targets. This does **not** mean all 155 reached a gate verdict: 5 came back
`LIVE_FETCH_FAILED` and 18 `UNKNOWN` (the verifier's own public-HTTP fetch
or publication-status lookup failing, or an `UNKNOWN_EXPECTATION` case
distinct from a resolver miss) -- 23 reports with no gate verdict either
way, not evidence of a resolver failure. The remaining 132 did reach a real
verdict: 127 `LIVE_EXPECTED_DENIAL` + 5 `LIVE_STALE_OR_DIVERGENT/MISSING_UNEXPECTED`
(0 `LIVE_VERIFIED`, consistent with 6B's Section 13 finding that a
newly-approved report can still be mid-propagation to the edge at check
time). `gate-bypass: 0` also confirms no `PUBLICATION_GATE_BYPASS` in the
processed subset.

**6D not yet observed**: this run predates commit `73b3c341e` (#195), so it
still hit the sequential-loop deadline as expected -- 339/494 reports (69%)
`LIVE_NOT_PROCESSED_DEADLINE`, consistent with the pre-6D baseline
(170/518 in the original evidence run). This is the expected, unfixed
behavior for this specific commit, not a regression.

**This run does not count as Run 2 or Run 3 toward the `--enforce` bake-in
requirement** -- `run_deadline_exceeded: true` disqualifies it under
criterion 4, same as Run 1 above, and it does not include the 6D fix this
disqualification requires. It is recorded here as supplementary evidence
that 6C's fix is working, independent of 6D's still-pending validation.

The push that would have produced the first 6A-6D-inclusive run
(workflow run [31778226404](https://github.com/cyberdudebivash-pvt-ltd/CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM/actions/runs/31778226404),
commit `73b3c341e`, triggered directly by the #195 merge) was cancelled
before any job started -- no evidence obtained. `sentinel-blogger.yml`'s
schedule was deliberately cut to 3x/day (`0 0,8,16 * * *`) after a SEV-1
Actions-minutes cost audit (see the workflow file's own comment at the
`schedule:` block); per that explicit, founder-directed cost-conservation
decision, this mission does not manually trigger extra `workflow_dispatch`
runs solely to accelerate its own bake-in evidence collection. Run 2 and
Run 3 will be the next two runs (schedule or path-filtered push) that reach
STAGE 3.6a against a commit at or after `73b3c341e`.
