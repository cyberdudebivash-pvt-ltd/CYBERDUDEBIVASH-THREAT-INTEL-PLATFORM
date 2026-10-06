# RX_PUB_A0_INCIDENT_ROOT_CAUSE

Status: **HIGH-CONFIDENCE MECHANISM IDENTIFIED, EMPIRICALLY REPRODUCED, AND
FIXED. Not yet elevated to fully proven** because that would require direct
R2/CI-run evidence tying this exact mechanism to this exact incident, which
is still blocked on credentials this environment does not have (§5). This
document will be finalized once Phases 1-5's credentialed R2 evidence closes
that last gap.

## §0 — Root-cause mechanism found via code forensics, not speculation

`scripts/safe_git_commit.py`'s conflict-recovery path (`git stash push` →
`git reset --hard origin/main` → `git stash pop`, fired whenever a
concurrent push to `main` causes `git merge origin/main -X ours` to fail —
this pipeline runs long enough to routinely overlap with other automation
that also commits to `main`) discards the run's own locally-committed
changes and replaces them with `origin/main`'s state. A pre-existing safety
net ("reports-guard", P0-FIX v154.0.0) already protects against this
wiping HTML reports that don't exist yet on `origin/main` — but it detects
loss with a **path-set difference only** (`pre_reset_paths - post_reset_paths`).
For any report whose path already exists on `origin/main` (i.e. essentially
every report after its first run, since reports/ retains recent history),
`git reset --hard origin/main` does not remove the file — it silently
overwrites its *content* back to whatever `origin/main` had. The path
survives, so the guard's set-difference is empty, it logs "intact", and the
freshly regenerated (correct) bytes are gone with zero warning anywhere in
the pipeline. The exact same failure class was already found and fixed for
several JSON artifacts (`[artifact-guard]`, P0-FIX v184.2 — before/after
item-count comparison, restore from `ORIG_HEAD` on mismatch) but that fix
was never extended to `reports/*.html`.

**This was verified empirically, not just read from the code**: a new test,
`tests/test_safe_git_commit_artifact_recovery.py::TestHtmlReportContentReversionSurvivesConflictRecovery`,
builds a real two-repo git scenario (bare "origin" + a "runner" clone) that
forces this exact conflict/recovery path, with an HTML report present in
both the stale ancestor commit and the runner's fresh local commit under
the same path. Run against the pre-fix code, it reproduces the live
incident's exact symptom — the test's stale fixture text
(`"PATCH WITHIN 14 DAYS"`, chosen to match the real incident's observed
text) survives in `origin/main` after the script runs, and the freshly
regenerated content is gone, silently, with no error and exit code 0. Run
against the fix (see §0.1), the fresh content survives and the guard logs
`[reports-guard] ... CONTENT-REVERTED ...` making the event visible.

## §0.1 — Fix applied

`scripts/safe_git_commit.py`'s reports-guard now hashes every HTML report
(SHA-256) before the reset, and after `stash pop` treats a same-path/
different-hash report exactly like a lost one (both trigger the existing
whole-tree `git checkout ORIG_HEAD -- reports/` restore, and both are logged
by name). This closes the silent-divergence gap using the same restore
mechanism already proven correct for the lost-file case, extended with the
same before/after comparison pattern the `[artifact-guard]` block already
uses for JSON artifacts — no new recovery mechanism was introduced.
Regression tests: `tests/test_safe_git_commit_artifact_recovery.py`, all 8
cases (5 pre-existing + 3 new) pass; the 2 new negative-control assertions
were confirmed to fail against the pre-fix code before the fix was applied,
proving the tests actually exercise the bug rather than passing trivially.

## §0.2 — What this does and does not prove for this specific incident

**Proven:** this exact mechanism exists in the current (pre-fix) codebase,
is reachable via a documented, previously-hit trigger condition (concurrent
pushes to `main`, which the file's own comments document as a recurring
production occurrence, not a hypothetical), and is capable of producing
byte-for-byte the class of symptom observed live (a report whose engine
marker and text pattern match a pre-fix generation, persisting after the
generator was fixed and re-verified, with zero missing-file signal anywhere
in the pipeline).

**Not yet proven:** that this specific mechanism (rather than, e.g., a
distinct `AWS_SYNC_DECISION_DEFECT`) is what actually happened to
`intel--20282e88b1f49bf2` on the real CI runners, since this environment
cannot inspect real GitHub Actions run logs for "Merge failed -- stash
recovery" / "[reports-guard]" lines from the runs that touched this fixture,
nor real R2 object history. Both would make this conclusive. Per the
mission's own standard, this is recorded as **the leading, evidenced
hypothesis with a shipped fix**, not as a certified closure.

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
