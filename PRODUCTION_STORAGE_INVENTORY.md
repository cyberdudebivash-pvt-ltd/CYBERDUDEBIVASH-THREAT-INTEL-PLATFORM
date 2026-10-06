# Production Storage Inventory

**Project TITAN — Production Sanitation & Commercial Readiness, Phase 1**
**Measured directly** (`du`, `git ls-files`, `git log`), 2026-08-07. All figures are git-tracked
sizes unless explicitly marked "on-disk only" — tracked size is what actually affects repository
clone time, CI checkout time, and (if ever included in a deploy bundle) deployment payload; on-disk
figures include local/untracked scratch data that doesn't inflate the repository itself.

---

## 0. Headline numbers

| Metric | Value |
|---|---|
| Total on-disk size (excl. `.git`) | 1.8GB |
| `.git` directory size | 301MB |
| Total git-tracked files | 37,067 |
| Largest git-tracked top-level directory | `reports/` — **1,221.8MB** (61% of all tracked content) |

## 1. Top-level directories by git-tracked size

| Directory | Tracked size | Note |
|---|---:|---|
| `reports/` | 1,221.8MB | 9,934 `.html` (`2026/07`: 7,359, `2026/08`: 2,661) + PDFs (`reports/pdf/`, 330.2MB) |
| `data/` | 193.8MB | Operational/intelligence data — see §2 |
| `workers/` | 117.6MB | **117MB of this is `workers/intel-gateway/node_modules/`** — see §3, finding 1 |
| `DASHBOARD-OVERVIEW-LIVE-VIDEO.mp4` | 33.9MB | Single file at repo root — see §3, finding 2 |
| `syndicate/` | 24.0MB | Real subsystem (social syndication tool), referenced by `scripts/gumroad_auto_refresh.py` |
| `threat/` | 23.7MB | 2,144 real, generated HTML advisory pages, referenced by `scripts/threat_page_generator.py` |
| `api/` | 20.6MB | Live-served API JSON snapshots |
| `scripts/` | 8.5MB | Source — 412+ Python automation scripts |
| `agent/` | 5.6MB | Source — Python automation package |
| `index.html` | 1.3MB | Marketing homepage |
| `core/`, `platform/`, `.github/`, `tests/`, `dashboard/`, `docs/` | <1MB each | Source/config/docs |

## 2. `data/` breakdown (top contributors, git-tracked)

| Subdirectory | Size | Note |
|---|---:|---|
| `data/.manifest_backups/` | ~24MB (35 files) | **Explicitly listed in `.gitignore` (line 44) yet tracked** — see §3, finding 3 |
| `data/intelligence_repository/` | ~21MB | Registry JSON files (retention, advisory, lifecycle registries) |
| `data/archive/` | ~7.4MB | Output of the *existing* `cold_archive_automation.py` — real, working, in active use |
| `data/stix/` | ~8MB | 503 STIX bundles (Stage 22 finding — real, actively served) |
| `data/intelligence/` | ~8MB | The directory `cold_archive_automation.py` actually manages (HOT/WARM/COLD/PURGE) |
| `data/analyst/`, `data/trust/`, `data/quarantine/`, `data/ocios/` | 1–5MB each | Real, actively-generated operational data |

## 3. Notable individual findings

**1. `workers/intel-gateway/node_modules/` is git-tracked (894 files, ~118MB) despite
`.gitignore` explicitly excluding `node_modules/` and `**/node_modules/` (lines 126–127).** It was
evidently force-added before, or despite, that rule. Single largest contributor:
`node_modules/@cloudflare/workerd-windows-64/bin/workerd.exe` — **a 72.5MB Windows binary
executable**, alone 61% of the tracked node_modules size, with zero function in a Linux-deployed
Cloudflare Worker. `workers/intel-gateway/src/` (the real source) is only 2.8MB by comparison. This
is fully reproducible via `npm install` from the properly-tracked `package.json`/`package-lock.json`
— removing it from git has zero functional risk.

**2. `DASHBOARD-OVERVIEW-LIVE-VIDEO.mp4` (33.9MB, repo root) — RESOLVED 2026-09-01: KEEP.** Added
2026-08-04 in the same commit as the findings in #4 below, and until now was unreferenced by any
`.html`, `.js`, or `.md` file in the repository (grep-confirmed) — flagged as an intentional
marketing asset awaiting a future embed, pending confirmation of intended use. That confirmation has
happened: it is now embedded in `index.html`'s homepage `#demo-video` section as a self-hosted
HTML5 `<video>` (click-to-play, real dashboard footage), with a dedicated long-lived `Cache-Control`
rule for this path in `_headers`. It is a live, customer-facing production asset — do not archive or
delete it (see `PRODUCTION_SANITATION_DEPENDENCY_ANALYSIS.md` §4a).

**3. `data/.manifest_backups/` (35 files, ~24MB) is tracked despite being explicitly gitignored.**
Daily manifest snapshots from 2026-03-23 through at least 2026-03-26, ~700–740KB each. This looks
like exactly what `.gitignore` line 44 was written to prevent — snapshots that should live outside
git (or in the existing `data/archive/` cold-storage path) but were committed anyway.

**4. Loose historical artifacts at the repo root**, all added in a single commit on 2026-08-04
(`c2afe9ca`), none referenced anywhere: `v55.2-complete.patch` (0.5MB),
`SENTINEL_APEX_v78_P0_FIX.tar.gz` (0.2MB), `0001-SENTINEL-APEX-v28.0-FORTRESS-Security-Hardening-Rele.patch`
(0.2MB), `claude-tasks-history-screenshot.jpg` (0.3MB). Small individually, but exactly the
"historical build products"/"screenshots" categories this sanitation effort was chartered to find.

**5. 392 `.zip` and 337 `.bat` files are git-tracked repository-wide.** Not yet classified — a
sample path (`data/simulations/apex_sim_CVE-2026-4146_-_Loco_Translate.bat`, found during Stage 22)
suggests these may be **intentional threat-simulation/detection-test payloads**, i.e., real product
data, not junk. Flagged for careful dependency analysis in Phase 3 before any classification —
`.bat`/`.zip` extensions pattern-match "junk" on first glance but must not be assumed so.

## 4. File-type breakdown (git-tracked, repository-wide)

| Extension | Count |
|---|---:|
| `.html` | 12,388 |
| `.pdf` | 9,944 |
| `.json` | 9,622 |
| `.py` | 1,110 |
| `.yml`/`.yaml` | 1,122 |
| `.js` | 642 |
| `.md` | 487 |
| `.zip` | 392 |
| `.bat` | 337 |
| `.yar` | 179 |
| `.ts` | 172 |

## 5. Existing storage-governance infrastructure (found, not built — critical context for later phases)

Two real, already-built systems exist and materially change the shape of Phases 5–8 of this effort
— full detail in `RETENTION_POLICY.md` and `SAFE_CLEANUP_PLAN.md`:

- **`scripts/cold_archive_automation.py`** + `storage-lifecycle-governance.yml` (weekly): a real,
  well-built HOT/WARM/COLD/PURGE lifecycle manager with hash-verified compression, atomic writes,
  and audit logging — but scoped only to `data/intelligence/*.json`, never `reports/`.
- **`scripts/storage_governance.py`** + `storage-governance.yml` (weekly): includes a
  `prune_old_reports()` function that directly targets `reports/**/*.html` with a retention policy
  (`max_count: 50, max_age_days: 30`) — **exactly the mechanism this sanitation effort might
  otherwise be asked to build from scratch.** Critically: `data/governance/storage_governance_log.json`
  does not exist, and the scheduled workflow's execute mode is gated behind
  `github.event.inputs.mode`, which is only ever set on a manual `workflow_dispatch` — **the
  weekly cron trigger always runs in dry-run mode.** This tool has evidently never been run with
  `--execute` since it was built, which is the direct, root cause of `reports/`'s current 1.2GB
  size. It also deletes files directly (`f.unlink()`) with no backup, hash, or rollback manifest —
  weaker safety than `cold_archive_automation.py` demonstrates is achievable in this same
  repository.

## 6. What this inventory does not yet tell us

Whether any of `reports/2026/07`'s 7,359 files are still needed for compliance, customer access to
historical intelligence, or active certification gates (P33's own gate G16 currently *warns* that
HTML report count is *below* feed item count, suggesting the certification chain expects reports to
persist, not shrink) is a Phase 4 (Report Inventory) and Phase 5 (Retention Policy) question, not
answered by raw size measurement alone.
