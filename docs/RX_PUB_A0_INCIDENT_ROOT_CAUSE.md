# RX_PUB_A0_INCIDENT_ROOT_CAUSE

Status: **IN PROGRESS — ROOT_CAUSE_NOT_FULLY_PROVEN.** This document will be
completed once Phases 1-5's credentialed R2 evidence (see §5 below) has been
captured. It is published now, incomplete, because Phase 0 forensics produced
a material correction to the incident's classification that changes what the
remaining evidence-gathering should target.

## Section 43 — Incident fixture acceptance, answered to the extent evidence allows

Fixture: `intel--20282e88b1f49bf2`

**Q1. Was the report regenerated in the actual production pipeline?**
Yes, at least once, by `generate_intel_reports.py` — proven by the live
engine marker `CDB-REPORT-ENGINE: generate_intel_reports.py vv184.0`
(current platform version, not a stale pre-184.0 artifact). What is not yet
proven is *which specific pipeline run* wrote the currently-live bytes, or
whether that run's checkout of `generate_intel_reports.py` already contained
the RX-PR1 fix.

**Q2. What was its SHA-256 immediately before publication?**
Not yet known — this requires either (a) re-entering the active generation
window and observing a real pipeline run, or (b) CI-side instrumentation
capturing this at generation time (Phase 1, in progress).

**Q3. What exact R2 key was targeted?**
`reports/2026/08/intel--20282e88b1f49bf2.html` (derived from
`internal_report_url`/`report_url` field convention; confirmed against the
live, resolving public URL).

**Q4. Did normal sync transfer it?**
Not yet provable from this environment — no R2 credentials available (see §5).
Previously reported "STAGE 3.5 completed successfully" is a pipeline-exit-code
fact, not a proof this specific object was transferred; per the mission's own
Section 3, a successful `aws s3 sync` must never be treated as content-identity
proof, and no per-object transfer log was previously captured.

**Q5-Q8.** Blocked on the same credential gap as Q4.

**Q9. What was the proven root cause?**
**A material correction supersedes the prior "confirmed inside the active
~250-item generation window" classification.** Traced directly against git
history of `data/stix/feed_manifest.json` this session:

| Commit | Timestamp (UTC) | Manifest size | Fixture present? |
|---|---|---|---|
| `00db0bf2` | 2026-08-12T18:54:15Z | 250 | **PRESENT** |
| `519178dc` | 2026-08-12T22:31:08Z | 372 | **PRESENT** |
| `d1498576` | 2026-08-13T03:59:24Z | 188 | **ABSENT** |

The fixture exited the active generation window sometime between
2026-08-12T22:31Z and 2026-08-13T03:59Z — i.e., in the hours immediately
preceding this investigation, via the pipeline's own normal window-rotation
behavior (unrelated to any defect). The prior session's two local
reproductions ("isolated regeneration" and "full manifest generation") were
performed while the fixture was still genuinely in-window (consistent with
the 250-item snapshot at `00db0bf2`) and were valid at the time — they are
not contradicted, they are simply now describing a state that no longer
applies to this fixture's *current* pipeline eligibility.

**Practical consequence:** `stage_html_reports()`'s "Zero-skip" pass (see
`docs/RX_PUB_A0_EXECUTION_PATH.md`) no longer attempts to regenerate this
item on any current or recent pipeline run, and will not until/unless the
item re-enters the window. This reclassifies the fixture, per the mission's
own Section 26 taxonomy, as a **HISTORICAL_IMMUTABLE** candidate rather than
proof of an active, ongoing sync defect — with the caveat that this is
distinguishable from a genuine one-time `AWS_SYNC_DECISION_DEFECT` (a sync
that should have transferred it during the window in which it *was* eligible,
and silently didn't) only by direct R2 object history, which is not
available from this environment.

Both explanations remain open and are not mutually exclusive:
- **HISTORICAL_IMMUTABLE**: the fixture was correctly synced at some point
  pre-fix, then exited the window before any post-fix run could regenerate
  and re-sync it. The live staleness is real but is a closed, one-off
  artifact of timing, not an active bug.
- **AWS_SYNC_DECISION_DEFECT / PIPELINE_RACE**: during the window in which
  the fixture *was* eligible (2026-08-12T18:54Z through some point before
  03:59Z on 08-13), at least one pipeline run should have regenerated it
  correctly (post-fix) and synced the corrected bytes to R2, and did not.

**Per Section 43: `ROOT_CAUSE_NOT_FULLY_PROVEN`. Certification remains
blocked** pending either direct R2 object version/history evidence, or a
CI-run-log audit distinguishing these two explanations.

## What this changes about the remaining plan

Because this specific fixture is no longer in the active window, it is no
longer the most representative target for Phase 1-5's live diagnostic
instrumentation (which is meant to observe a *real, in-flight* generate→
sync→verify cycle). The diagnostic instrumentation set (Phase 1) should
target:
1. `intel--20282e88b1f49bf2` itself — read-only R2 HEAD/GET history check
   only (it won't be regenerated by a normal run), to close Q2/Q4/Q5/Q9
   above.
2. A **currently in-window** fixture, to observe a live, provable
   generate → pre-sync-hash → sync → post-sync-hash cycle end-to-end — this
   is the test that actually exercises Phases 2-5 as designed.

Per RX-PUB-A0 Section 26, mass-regeneration or special-casing of this specific
historical fixture is explicitly out of scope for this mission; a bounded
historical-correction policy is deferred, as instructed.
