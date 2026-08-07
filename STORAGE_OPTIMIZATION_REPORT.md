# STORAGE OPTIMIZATION REPORT — Project Titan Stage 22

**Date:** 2026-08-07

---

## 1. Before / after (tracked files)

| Metric | Before | After | Delta |
|---|---|---|---|
| Tracked files (`git ls-files \| wc -l`) | 37,067 | 28,725 | **-8,342** |
| `reports/` tracked HTML count | 19,955 (html+pdf+stray) | ~12,596 (html+pdf+stray) | -7,359 |
| `workers/intel-gateway/node_modules/` tracked | 894 | 0 | -894 |
| `data/.manifest_backups/` tracked | 35 | 5 | -30 |
| Root loose `.bat`/`.ps1`/stray files | 66 | 0 | -64 (+2 stray singles = 66 total removed) |

## 2. What "reclaimed" means here (read before quoting the headline number)

**Headline: ~808MB removed from git tracking**, computed as the sum of each candidate's on-disk size at time of audit (node_modules 118MB + reports/2026/07 669MB + manifest_backups 19.9MB + root cruft ~450KB).

This number describes **future checkout size**, not this session's current disk usage. Two mechanisms were used throughout, both deliberately reversible without rewriting git history (the task rules prohibit `git filter-repo`/BFG):

1. **`git rm --cached`** (node_modules, reports/2026/07) — removes a path from the git index going forward. The blob remains in every prior commit's history indefinitely (recoverable via `git checkout <old-commit> -- <path>`, no special tooling needed), and for `reports/2026/07/` specifically, the actual files remain on this container's local disk too (untracked). This means:
   - A **fresh `git clone` of this branch from this commit forward** will not download these 8,283 files — this is the real, durable win, and it compounds every time someone clones or CI checks out the branch.
   - **This container's own `du -sh .` output does not drop** — the bytes are still sitting on local disk, just no longer tracked. That's expected, not a failure of the cleanup (see `scripts/report_archive_manager.py`'s own docs: "Disk files intact: YES (files not deleted from disk)").
   - **`.git`'s pack size on this specific clone is unaffected** — old commits still reference the old blobs. Only history rewriting shrinks that, which is explicitly out of scope here.

2. **Checksum-verified delete** (`data/.manifest_backups/` prune, via the new `storage_governance.py` machinery) — this one *does* free local disk immediately (files are copied to a verified local backup, then `unlink()`ed), in addition to being untracked going forward.

## 3. Repo composition, before this pass

| Directory | Size | Share of 2.0GB |
|---|---|---|
| `reports/` | 1.3GB | 65% |
| `data/` | 226MB | 11% |
| `workers/` | 122MB | 6% |
| everything else | ~352MB | 18% |

`reports/` was the dominant cost center by a wide margin — see `SAFE_CLEANUP_PLAN.md` §3 for why it had grown despite an already-live archiving tool (a month-granularity classification quirk in `report_archive_manager.py`, now documented; the tool itself was working as designed, just conservatively).

## 4. What remains unaddressed (sized for a future pass)

| Item | Size | Why not this pass |
|---|---|---|
| `reports/pdf/` | 354MB | No existing archive tool covers PDFs; same R2-backed safety argument likely applies but wasn't independently verified |
| `reports/` ongoing regrowth | ~240-380 files/day per `report_archive_manager.py`'s own docstring | Root cause (`safe_git_commit.py` force-adding despite `.gitignore`) lives inside a CI stage explicitly marked "never modify" |
| `data/analyst/` | 26MB, unbounded growth | Real consumer confirmed, but no safe retention threshold verified this session |
| 7 untraced small `data/` subdirs | ~1.5-21MB each | Insufficient evidence gathered this session; per task rule, UNKNOWN defaults to KEEP |

Realistic next-largest opportunity, if pursued: extending `report_archive_manager.py`'s pattern to `reports/pdf/` would be worth roughly as much as this pass's node_modules + manifest_backups cleanup combined.

## 5. CI / runtime effect

- **Checkout time**: every future `actions/checkout` on this branch transfers ~808MB less.
- **`dist/` build time**: unaffected in practice — `build_dist_artifact.py` already hard-caps `REPORT_RETENTION_DAYS=3`, so July's reports were never included in deploy artifacts regardless of this cleanup.
- **`npm install`/`npm ci` steps**: unaffected — they never read tracked `node_modules`, they always reinstall.
- **Cloudflare R2/KV/D1**: zero bytes changed. This pass touched git tracking only.
