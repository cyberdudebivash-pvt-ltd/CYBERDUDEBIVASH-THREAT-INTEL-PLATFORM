# CYBERDUDEBIVASH SENTINEL APEX — Main Branch Protection Requirements (v185)

**Status: `BLOCKED_BRANCH_PROTECTION`**

This document is the required fallback deliverable for Mission v185.0 Phase 13
("Main-Branch Release Governance"). The Claude Code session executing this
mission does not have a GitHub tool capable of reading or writing branch
protection rules / repository rulesets (confirmed via `ToolSearch` against the
full GitHub MCP tool surface available in this session — no
`branch_protection_*` or `repository_ruleset_*` tool exists). Per the
mission's own explicit instruction, this session cannot verify or enable
branch protection, so this document exists in place of a live change, and the
final release verdict for this mission MUST be marked
`BLOCKED_BRANCH_PROTECTION` until a human operator applies the configuration
below and it is independently verified.

**This document does not itself change any repository setting.** It is a
specification an operator (or a future session with `admin:repo`-scoped
GitHub API/App credentials) must apply manually via the GitHub UI or API.

---

## 1. Required protection target

- **Repository:** `cyberdudebivash-pvt-ltd/CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM`
- **Branch:** `main`
- **Mechanism:** GitHub repository ruleset (preferred, `Settings -> Rules ->
  Rulesets -> New branch ruleset`) or classic branch protection
  (`Settings -> Branches -> Add rule`). A ruleset is preferred because it is
  independently auditable via `GET /repos/{owner}/{repo}/rulesets` and applies
  even to repository admins unless explicitly bypassed.

## 2. Required ruleset configuration

| Setting | Required value | Rationale |
|---|---|---|
| Target branches | `main` (exact match, not a pattern that could accidentally include release branches) | Only the canonical production branch needs to be locked |
| Restrict deletions | ON | Prevents accidental or malicious deletion of the production history |
| Require linear history | ON | Keeps `git bisect` / rollback tractable; matches this repo's existing squash-merge convention |
| Block force pushes | ON | The single highest-value control — prevents history rewrite on `main`, which every deploy workflow and every consumer branch is based on |
| Require a pull request before merging | ON | No direct pushes to `main` |
| Required approving review count | ≥ 1 (2 recommended once a second maintainer exists) | Human review gate on every change reaching production |
| Dismiss stale approvals on new commits | ON | An approval must reflect the code actually being merged |
| Require status checks to pass before merging | ON — required checks: the `sentinel-blogger.yml` CI job(s) that run `scripts/p33_production_certification.py`, `scripts/regression_tests.py`, `scripts/worker_js_integrity_gate.py`, and the `deploy-worker.yml` build/typecheck step | Matches this repo's own documented "Production Validation Gates" (see `CLAUDE.md`) — makes them mechanically enforced instead of convention-only |
| Require branches to be up to date before merging | ON | Prevents merging a PR that was validated against a stale base |
| Require conversation resolution before merging | ON | Ensures review threads are not silently ignored |
| Restrict who can push to matching branches | Limit to the CI/deploy service identity and named maintainers only | Matches Principle 9 (Security First) — least privilege on the production branch |
| Require signed commits | Recommended (OFF today, no evidence this repo currently signs commits — enabling without preparation would break the existing pipeline's automated commits) | Documented as a future hardening step, not enabled now, to avoid breaking `scripts/safe_git_commit.py`'s automated commits without a corresponding signing-key rollout |

## 3. Why this is not already enabled

A `git log` / CI-behavior review during this mission shows `main` currently
accepts direct pushes from the automated pipeline (`scripts/safe_git_commit.py`,
`scripts/run_pipeline.py`) with commit messages like `"Intel v184.0 incremental
ingest..."` and `"[skip ci]"` markers — i.e., the automated ingestion pipeline
commits directly to `main` on its own schedule, outside the PR flow this
mission's own recommended branches (`claude/v185-*`) use. Any branch-protection
rollout that requires PRs for all changes to `main` would **break that
automated pipeline** unless the pipeline's service identity is added to a
bypass/allow list (`Restrict who can push` exemption) or the pipeline is
re-architected to push to a staging branch and open a PR for merge. That
architectural decision is out of scope for this mission (it would touch the
Level 0 additive-architecture and Level 2 production-stability constraints in
`CLAUDE.md`) and is called out here explicitly rather than silently enabling a
rule that would break the live ingestion pipeline.

## 4. Recommended rollout sequence for the operator

1. Confirm the automated pipeline's push identity (the GitHub Actions default
   token / any PAT used by `sentinel-blogger.yml`'s git-sync step).
2. Add that identity to the ruleset's bypass list, OR change the pipeline to
   push to a non-`main` branch (e.g. `pipeline/auto-ingest`) with
   auto-merge-on-green, before requiring PRs for all other pushes.
3. Enable the ruleset in **evaluate/dry-run mode first** (GitHub rulesets
   support "Evaluate" mode, which logs would-be violations without blocking)
   for at least one full pipeline cycle (~24h given this repo's cadence) to
   confirm the automated pipeline is unaffected.
4. Switch the ruleset from evaluate to active/enforced.
5. Verify with `GET /repos/{owner}/{repo}/rulesets` (or the UI) that the
   ruleset is `ACTIVE`, and re-run a `git push --force` against a disposable
   test branch pointed at `main` to confirm it is rejected.

## 5. Verification the next session must perform

Before ever marking this item resolved, a session with appropriate GitHub
tooling must:

- Confirm a ruleset or classic branch-protection rule targeting `main` exists
  and is enabled (not in evaluate-only mode).
- Confirm `Block force pushes` and `Restrict deletions` are both `true`.
- Confirm `Require pull request before merging` is `true` with the required
  status checks listed in Section 2 actually attached (not just "any check").
- Confirm the automated pipeline's push identity was explicitly reconciled
  (either exempted deliberately, or migrated to a PR-based flow) rather than
  silently broken.

Until all four are independently confirmed, this item remains
`BLOCKED_BRANCH_PROTECTION` and any release-gate verdict referencing it must
say so explicitly rather than assume completion.

---
*CYBERDUDEBIVASH SENTINEL APEX — Mission v185.0 Phase 13 fallback deliverable*
