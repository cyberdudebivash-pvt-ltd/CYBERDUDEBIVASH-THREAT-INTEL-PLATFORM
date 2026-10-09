# P0 R16 — ingestion timeout and early release fence

## Production incident (source of truth)

- Repository main: `36a08fad5170c398269a4706e636b1729092a743`.
- Failed Actions run: [sentinel-blogger #2522, run 37873832668](https://github.com/cyberdudebivash/CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM/actions/runs/37873832668), terminal failure on 2026-10-09 03:21 UTC.
- Stage 2.0: `agent.sentinel_blogger` ran for **1,200 seconds**, timed out and returned `-1`. Feed source logs show many locally rejected duplicates printed approximately three seconds apart.
- Stage 2.6: quarantined 7 stale entries from 10; only 3 remained versus minimum 5. This **must stay a hard failure** until genuine fresh source content meets it.
- Stage 3.2 HTML/PDF generation continued after the stage 1–3 outcome failed, despite recording `PIPELINE_HEALTH=DEGRADED`. Stage 3.3 failed for a missing in-window report. Subsequent publishing was not authorized.
- Independent later read-only checks showed the worker liveness endpoint returned 200 and identified live deployed commit `f6bce04597892179876243a9f6345db8a29e8108` (`deploy_run_id: 37873261215`), while `/api/health` returned 503 after expiry of its six-hour intelligence freshness window. The homepage and preview remained reachable.

## Code changes in this draft PR

1. In `agent/sentinel_blogger.py`, perform *all existing local reject controls* before the unchanged `RATE_LIMIT_DELAY=3` second sleep. The sleep still occurs immediately before any accepted `process_entry` call.
2. In `.github/workflows/sentinel-blogger.yml`, add `p0-ingestion-health-fence` **before Stage 3.1 enrichment**. It fails if `steps.pipeline_stage_1_3.outcome != success` **or** `PIPELINE_HEALTH != HEALTHY`, even when the prior orchestrator was configured with `continue-on-error: true`.
3. Seven focused static negative/positive controls in `tests/test_p0_r16_dedup_before_throttle.py`, explicitly included in the mandatory Gateway Python suite.

## Explicit boundary: this is NOT customer certification

- A successful pipeline run with genuinely new source data, a durable, valid HTML report and origin/edge integrity still must be demonstrated. The existing anti-stale minimum, quality thresholds, TLP publication policy, R2 read/write budget, and terminal health gate remain mandatory.
- Report URL-only `PASS` in Stage 3.3 is a separate issue fixed in draft PR #738, not this PR.
- Legacy regression T19 is separately fixed by parent draft PR #734. This PR is stacked onto #734 **for integration testing only**, not approved for merge.
- This branch is SOURCE ONLY. No production deployment, data write, cache purge, release promotion, customer credential mutation, or object deletion occurred as part of the review.

## CI acceptance

Every relevant workflow must report a completed conclusion for the **exact current PR head** and its current base. No earlier green SHA, workflow-level success with security scanners skipped, or green tests not listed by the runner count as certification.

## Rollback

If an operator later approves deployment, preserve the prior deployed Worker commit and Pages artifact ID before promotion. For a regression, revert the new merge commit in source and redeploy the previously verified artifact under the organization's existing release/rollback procedure. Do **not** roll back by blindly deleting R2 objects or removing the freshness or TLP gate. Verify `/api/health/live`, `/api/health`, preview and customer entitlement boundaries after rollback.
