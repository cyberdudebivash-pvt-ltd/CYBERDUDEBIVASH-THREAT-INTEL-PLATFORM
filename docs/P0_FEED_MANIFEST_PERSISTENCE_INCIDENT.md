# P0 — Feed Manifest Persistence Incident: Forensic Baseline

Status: **Phase 0 forensics only. No architectural change made yet**, per this
mission's Section 3 ("do not start by restoring to git, do not start by
switching to R2 — first build the forensic baseline").

## 1. Corrected finding: this is a dual-manifest problem, not a single untracked file

The initial hypothesis (raised in the prior session turn) was that a single
commit removing `data/stix/feed_manifest.json` from git tracking caused the
population collapse. Deeper investigation shows the real shape is different
and pre-existing:

**The repository has carried two independent files both named
`feed_manifest.json` for at least 6+ days before this incident:**

| Path | Schema | Generator | Consumers |
|---|---|---|---|
| `data/feed_manifest.json` | dict envelope (`version`, `schema_version`, `advisories`, `cve_index`, `actor_index`) | `SENTINEL_APEX_v70` (legacy) | ~30 scripts: `actor_attribution_enricher.py`, `intel_dedup_engine.py`, `intel_trust_governance.py`, `ocios_coordinator.py`, `mssp_executive_engine.py`, `apex_intelligence_engine.py`, and others |
| `data/stix/feed_manifest.json` | flat list, STIX-derived | `run_pipeline.py` v184.0 pipeline | `run_pipeline.py`'s `stage_sync_root_feed_json()` (the function that writes `api/feed.json`), `multi_source_collector.py`, `field_preserving_merge.py`, `api_dashboard_contract_validator.py`, `r2_reports_verifier.py` |

Both paths are listed in `.gitignore` (lines 65-66), **added together in the
same commit** `a6d55f86e` (2026-08-08 02:20:31 UTC) — six days before this
incident. Being gitignored did not stop either file from being committed:
git does not retroactively untrack already-tracked files when a
`.gitignore` rule is added, so both continued to be committed by the
automated `CDB-Sentinel-Bot` on a regular cadence (confirmed via
`git log -- data/feed_manifest.json`: commits on Aug 11, 12, 13 with the
`[P0-FIXED]` tag pattern, each carrying a fluctuating "N advisories" count
in the message, e.g. 24, 74, 209, 33, 99, 207, 29, 239, 267).

## 2. What actually happened at 17:45:47 UTC on 2026-08-14

Commit `55413265c934c7f60ff21b905ff04a682eaf335b` (author `CDB-Sentinel-Bot`,
message `SENTINEL APEX v184.0 -- 866 advisories @ ... [P0-FIXED] [skip ci]`)
touched 14 modified files plus a large STIX-bundle churn, and included:

```
M  data/feed_manifest.json        (397911 changed lines -- modified, stayed tracked)
D  data/stix/feed_manifest.json   (26704 lines -- deleted from git tracking)
```

Only the **STIX** manifest was untracked. The legacy `data/feed_manifest.json`
was untouched in terms of tracking status — it kept being committed normally.

This is the file `run_pipeline.py`'s `stage_sync_root_feed_json()` (STAGE 3.9)
reads to populate `feed.json` / `api/feed.json` on every run
(`manifest_path = REPO_ROOT / "data" / "stix" / "feed_manifest.json"`).
`data/feed_manifest.json` (the legacy file) is **not** read by this function
and has no code path connecting it to `api/feed.json`'s population in the
current v184.0 pipeline. So losing the STIX file's git persistence directly
explains `api/feed.json`'s collapse, while the legacy file's population
(497 items as of this writing) is irrelevant to that specific consumer.

**Why the STIX file was untracked is not yet proven with a code-level
citation** (no script in this repo currently performs a `git rm --cached`
or deliberate untrack of that specific path was found in this pass) — the
most likely mechanism, based on the identical `[P0-FIXED]` tag and timing,
is `safe_git_commit.py`'s commit-staging logic no longer adding the file
back after some other stage stopped writing to (or explicitly removed) it
that run, causing git to record it as deleted relative to the previous
commit. This needs one more targeted pass through `safe_git_commit.py`
and whatever stage last wrote `data/stix/feed_manifest.json` that run
before it can be stated as fully proven (Section 5's requirement) — flagging
as **NOT YET FULLY PROVEN**, not guessing further.

## 3. Current live state (snapshot, this is a moving target)

As of `origin/main` HEAD `7289f59e6` (~2026-08-15T03:32 UTC, i.e. ~10 hours
after the incident, many pipeline runs later):

| File | Count |
|---|---|
| `data/feed_manifest.json` (legacy) | 497 |
| `data/stix/feed_manifest.json` (STIX, the one that collapsed) | 226 (tracked again, rebuilding) |
| `api/feed.json` (customer-facing, derived from STIX manifest) | 21 |

Observed trajectory for the STIX-derived population since the incident:
516 (pre-collapse) → 29 → 68 → 226 (manifest, climbing) while `api/feed.json`
itself has been volatile (61 → 68 → ... → 21), **not monotonically
recovering** — each run's `api/feed.json` size depends on that run's
specific mix of `stage_sync_root_feed_json()`'s manifest-derived population
plus whatever `multi_source_collector.py` adds that run, so it fluctuates
rather than steadily climbing back to ~500. A separate `SENTINEL APEX v184.0
-- conflict-recovery (attempt 1): restore generated artifacts from
ORIG_HEAD` commit occurred in this window too, suggesting at least one git
merge-conflict recovery event further complicated continuity — not yet
investigated in this pass.

## 4. Open forensic questions not yet answered (honest gaps)

- Exact code path that caused `data/stix/feed_manifest.json` to stop being
  included in the 17:45:47 commit (Section 5 requirement) — not yet proven.
- Whether the dual-manifest split (legacy `data/feed_manifest.json` vs. STIX
  `data/stix/feed_manifest.json`) is intentional (two deliberately-scoped
  subsystems) or unintentional duplication/incomplete migration debt.
- Whether R2 already holds a durable copy of the STIX manifest that could
  serve as a recovery source (Section 6 candidate C/D) — not yet checked.
- Root cause and impact of the `conflict-recovery (attempt 1)` commit.

## 4a. Recovery candidate ruled out: the "Automated Backup" system

The repository has a full, real backup system (`agent/backup/backup_engine.py`,
run daily at 01:00 UTC by `.github/workflows/automated-backup.yml`,
`_BACKUP_TARGETS` includes `data/stix`). Checked its most recent real run
(`31858727166`, 2026-08-15T02:15:42Z, `conclusion: success`) directly:

- `CDB_BACKUP_DESTINATION: local` — the `vars.CDB_BACKUP_DESTINATION` repo/org
  variable has never been configured, so every run falls back to the
  workflow's own default of `local`. `CDB_BACKUP_S3_BUCKET` and
  `CDB_BACKUP_R2_BUCKET` are both empty (unconfigured secrets).
- This means the actual encrypted backup archive is written to
  `data/backups` **on the ephemeral GitHub Actions runner** and is lost the
  moment the runner terminates. Only `backup-manifest.json` — a **hash/path
  listing**, not the archive content — gets uploaded as a GitHub Actions
  artifact (90-day retention).
- **This backup system has, as far as this evidence shows, never actually
  produced a durably-recoverable off-runner backup for its entire operating
  history.** This is a separate, real gap from today's incident, worth its
  own fix, but it is being surfaced here because the mission's Section 6
  listed it as a recovery candidate (E) and it needed to be checked, not
  assumed.
- Even setting the destination bug aside: this specific run's backup
  manifest lists 2,138 individual `data/stix/CDB-APEX-*.json` STIX bundle
  files but **does not include `data/stix/feed_manifest.json` itself** — so
  even a correctly-configured backup would not have captured the aggregate
  manifest directly, only the raw bundles it's built from.
- **Verdict: candidate E is not viable for recovering historical
  `feed_manifest.json` content.** The raw STIX bundle files it does catalog
  are informative (2,138 cataloged vs. only ~27-226 currently being
  discovered by the live reconstruction path) but the backup content itself
  is unrecoverable — only file names + hashes survive, in the GH Actions
  artifact.

## 4b. Recovery candidate not yet checked: R2 (`intel/feed_manifest.json`)

`scripts/r2_upload.py` uploads `data/stix/feed_manifest.json` to R2 as
`intel/feed_manifest.json` in `BUCKET_DATA` on every successful pipeline
run (STAGE 3.5). This is the strongest remaining candidate (C in Section 6)
since it's independent of the local git checkout — **but it cannot be
checked from this environment**: no `CF_ACCOUNT_ID` is set and no `aws` CLI
is installed here (consistent with this session's established R2-access
constraint from the RX-PUB-A0 work — R2 can only be queried from inside a
CI run, not this sandbox). Whether R2's copy is any healthier than git's
depends entirely on whether R2 uploads happened on the same collapsed runs
or whether object versioning/an older un-overwritten object exists there.
This needs a small CI-side diagnostic (a workflow step or manually-triggered
job that runs `aws s3api head-object` / `get-object` against
`intel/feed_manifest.json` and reports size/hash/last-modified) before it
can be ruled in or out — not yet done.

## 5. Implication for the mission's proposed fix

This reframes but does not invalidate the mission's core concern: the STIX
manifest genuinely has no proven durable cross-run persistence right now,
and a similar collapse could recur (or the current rebuild could be
interrupted again) without a continuity guard. It does mean the "restore a
whole new R2-hydration architecture" scope (mission Sections 10-57) may be
larger than what the evidence currently requires — the minimal, evidenced
fix candidates are narrower and are laid out in the follow-up message to
the user rather than assumed here.
