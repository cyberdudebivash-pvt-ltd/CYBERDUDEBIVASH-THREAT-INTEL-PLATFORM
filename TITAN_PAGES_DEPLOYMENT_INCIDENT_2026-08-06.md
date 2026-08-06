# Incident: GitHub Pages Deployment Silently Stalled — 2026-08-06

## 0. Summary

Three consecutive GitHub-managed `pages build and deployment` runs (11:14:27Z, 12:08:28Z, 12:52:15Z) got stuck in `deployment_queued` and timed out after ~8 minutes without publishing. **The live site (`intel.cyberdudebivash.com`) went stale**: `Last-Modified` was still `Thu, 06 Aug 2026 08:23:57 GMT` when checked at 14:18 UTC — nearly 6 hours and 3 subsequent deploy attempts behind. This went undetected in-pipeline: `sentinel-blogger.yml`'s own deploy step (JamesIves' action) reports success on `git push` alone, and its post-deploy smoke test checks HTTP status/size only, running with `continue-on-error: true`. The only signal was the Actions tab UI.

**This is a real production issue, not a CI annoyance** — verified by directly checking the live site's response headers, not assumed from the Actions UI alone.

## 1. Root cause

GitHub Pages is currently configured as **"Deploy from a branch"** (`gh-pages`), confirmed by direct inspection of the failing dynamic workflow's own job structure: run 31103285719 has a `build` job that performs `Checkout` + `Upload artifact` internally (the signature of branch-based deployment — in Actions-based deployment, the artifact is already uploaded by the *calling* workflow, so no separate `Checkout`+`Upload` job exists inside `pages-build-deployment`).

Branch-based Pages deployment is being force-pushed at a frequency and pattern that overwhelms GitHub's internal Pages processor:

1. **`sentinel-blogger.yml`** pushes to `gh-pages` via `JamesIves/github-pages-deploy-action` with `clean: true, single-commit: true` — every deploy **force-pushes** a single new commit, discarding history. It runs on a 3x/day schedule *plus* on every `push` to `main` touching `scripts/**.py`/`agent/**.py`. On 2026-08-06, three separate PR merges (Project TITAN Stage 14/15, all modifying `scripts/*.py` governance files) each independently triggered a full run, landing close together and amplifying the normal push frequency.
2. **`weekly-threat-brief.yml`** *also* pushes directly to `gh-pages` via the same action, but with **opposite settings** (`clean: false, single-commit: false`) and under a **separate, uncoordinated concurrency group** (`sentinel-weekly-brief`, not `sentinel-data-writer`). This is a genuine, distinct architectural defect — two independent writers to the same branch with no coordination between them — even though it did not directly trigger *this* incident (its last run was 2026-08-03, three days prior).

Each force-push to `gh-pages` triggers a new `pages-build-deployment` run. If a new push lands while GitHub's backend hasn't finished processing the prior one, the new deployment can get stuck in `deployment_queued` indefinitely and eventually time out. The observed failure timestamps line up closely with each `sentinel-blogger.yml` run's own completion time, consistent with this mechanism.

## 2. What was fixed (this PR)

### 2.1 Cross-workflow concurrency unification
`weekly-threat-brief.yml`'s concurrency group changed from `sentinel-weekly-brief` to `sentinel-data-writer` — the same group `sentinel-blogger.yml` already uses, and per that file's own comment, "the shared concurrency group used by all data-writing workflows." This is the **exact same fix pattern** this repository already applied once before, for a near-identical bug class (see `sentinel-blogger.yml`'s own "P0 RACE CONDITION FIX" comment, which fixed *sentinel-blogger.yml* joining this group — this PR extends that same discipline to a workflow that was missed). Eliminates the possibility of these two workflows ever racing to write `gh-pages` concurrently. `cancel-in-progress: false` preserved, so `weekly-threat-brief.yml` queues (rather than fails or races) behind any in-progress data-writing pipeline — a multi-hour worst-case delay is immaterial for a weekly digest.

### 2.2 Deployment freshness gate (turns silent failures into loud ones)
New `scripts/pages_deploy_freshness_gate.py`, wired into `sentinel-blogger.yml` as **STAGE 5.4.9.1**, immediately after the Pages deploy step:

- Captures a timestamp immediately before STAGE 5 pushes (`STAGE 4.9.9`).
- Polls the live site's `Last-Modified` header (mirroring `post_deploy_smoke_test.py`'s existing fetch-with-retries idiom) until it advances past that timestamp, or a 12-minute budget expires (comfortably clears both GitHub's own ~8-minute internal Pages timeout and the platform's observed 600s CDN `max-age`).
- Uses a cache-busting query parameter on each poll, since the platform's CDN layer was observed serving `cache-control: max-age=600` with `x-cache: HIT` — a plain repeated request could return a cached response and never reflect true origin freshness within the budget.
- **Hard fails** (no `continue-on-error`) if freshness is never confirmed — deliberately different from the existing STAGE 5.5.0 smoke test, because "we don't know if this deploy is actually live" is itself the actionable signal this step exists to surface. STAGE 5.5.0 itself is unchanged (still `continue-on-error: true`, still checks status/size only) — this is a new, additive, narrowly-scoped step, not a modification of existing passing behavior.

This does not prevent the underlying GitHub Pages backend contention — it makes it **immediately visible in the pipeline** the next time it happens, instead of requiring someone to notice a red X in the Actions tab hours later.

## 3. What was considered but NOT done, and why

**Migrating to GitHub Actions-based Pages deployment** (`actions/upload-pages-artifact` + `actions/deploy-pages`, replacing JamesIves' branch-push action) is the officially-recommended, durable fix for this failure class — Actions-based deployments have built-in concurrency management (newer deployments supersede older queued ones automatically; nothing gets permanently stuck) and would eliminate this problem structurally, not just make it observable.

**This was not implemented in this PR** because it requires the repository's Pages source setting to first be switched from "Deploy from a branch" to "GitHub Actions" (Settings → Pages → Build and deployment → Source) — a one-time change outside of any git commit, and one this session has no tool access to make or verify. Shipping the code change without confirming that prerequisite would trade today's *occasional, self-recovering* stuck-deployment failure for an *immediate, every-time* hard failure of the deploy step (the `deploy-pages` action errors out if the repo isn't configured for Actions-based deployment) — a strictly worse outcome, and a direct violation of this repository's own Level 2 priority ("never reduce production stability"). Per the Architecture Preservation Rule ("when in doubt, add, don't replace"), this PR ships the safe, additive observability and coordination fixes now, and documents the durable migration as a clearly-scoped follow-up requiring one manual step.

**If/when the Pages source is switched to "GitHub Actions"**, the migration itself is a small, well-understood change (replace STAGE 5's single `uses:` block with `actions/upload-pages-artifact@v3` — passing `include_hidden_files: true` to preserve `.nojekyll`/`_headers`, both of which the pipeline's own Stage 5 comments confirm are required in `dist/` — followed by `actions/deploy-pages@v4`); the workflow's `permissions: pages: write, id-token: write` are already present at the workflow level and require no further change.

## 4. Verification

- Both modified workflow files parse as valid YAML (`python3 -c "import yaml; yaml.safe_load(...)"`).
- New script's timestamp-parsing logic sanity-checked against the actual `Last-Modified` header format observed on the live site today (`Thu, 06 Aug 2026 08:23:57 GMT`) — correctly classifies it as stale relative to a later reference timestamp, and a later timestamp as fresh.
- Cannot be end-to-end tested without triggering a real `sentinel-blogger.yml` run (a ~45-90 minute pipeline) — the next scheduled or push-triggered run will exercise this gate for real. If the freshness gate proves too strict in practice (e.g., CDN timing assumptions don't hold), the retry budget (`FRESHNESS_TIMEOUT_MIN`) and poll interval (`FRESHNESS_POLL_SEC`) are both tunable via workflow env vars without further code changes.

## 5. Immediate operational note

As of this PR, the live site remains stale from the last successful deploy (08:23:57 UTC) until the next `sentinel-blogger.yml` run completes successfully — which the concurrency fix (§2.1) and the ordinary passage of time (GitHub's Pages backend catching up) should allow. This PR does not itself trigger a new deploy; the next scheduled run (00:00/08:00/16:00 UTC) or the next qualifying push will.
