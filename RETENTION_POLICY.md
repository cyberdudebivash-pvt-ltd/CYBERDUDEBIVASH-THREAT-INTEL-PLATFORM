# Production Sanitation — Retention Policy

**Project TITAN — Production Sanitation & Commercial Readiness, Phase 5**
**Governs what Phase 7 (Safe Cleanup Plan) and Phase 8 (Automated Cleanup Tool) are allowed to
act on.** Built directly on the Phase 1–4 evidence, not a generic policy — every rule below traces
to a specific finding in `PRODUCTION_STORAGE_INVENTORY.md`,
`PRODUCTION_SANITATION_CLASSIFICATION.md`, `PRODUCTION_SANITATION_DEPENDENCY_ANALYSIS.md`, or
`PRODUCTION_SANITATION_REPORT_INVENTORY.md`.

---

## 1. The governing constraint: the feed-reference guard

Phase 3 found the mechanism that makes `reports/` unsafe to prune blindly: four live-served feed
files — `api/feed.baseline.json`, `api/feed.gold.json`, `api/feed.silver.json`,
`api/feed.standard.json` — carry per-item fields that point directly at files on disk:

```json
"report_url":          "/reports/2026/07/intel--<id>.html",
"internal_report_url":  "/reports/2026/07/intel--<id>.html",
"pdf_url":              "/reports/pdf/intel--<id>.pdf",
"pdf_available":        true
```

(Confirmed directly against `api/feed.baseline.json` item 0, 2026-08-07.)

**Rule R0 (absolute, supersedes every other rule in this document):** No file under `reports/` may
be moved, renamed, recompressed-out-of-place, or deleted unless its path is first confirmed absent
from `report_url`, `internal_report_url`, and `pdf_url` across all four `api/feed*.json` files. This
is a mechanical, script-checkable condition — Phase 8's tool implements it as a hard gate, not a
judgment call made per-run.

This single rule is what separates the two disposition classes below: "orphaned" (present on disk,
absent from every feed file) vs. "referenced" (present in at least one feed file). Age and month are
not, by themselves, sufficient grounds for action on anything under `reports/` — reference status is.

---

## 2. Per-category retention rules

| Category | Rule | Enforcement window | Basis |
|---|---|---|---|
| `reports/**/*.html`, `reports/pdf/**/*.pdf` — **referenced** (passes R0 check = fails, i.e. found in a feed) | **Retain indefinitely at current path.** Not eligible for archive/delete under this sanitation effort. | N/A — no window until a coordinated feed-update migration exists | Phase 3 §3: 292+38 live references |
| `reports/**/*.html`, `reports/pdf/**/*.pdf` — **orphaned** (passes R0 check = clean, i.e. absent from all four feed files) | Eligible for archive (compress to `data/archive/cold/reports/`) after a 1-run grace period (see §4) | Immediate for the 639 already-confirmed orphaned PDFs; ongoing for future orphans as they age out of the feed window | Phase 4: 639 PDFs, zero feed references, zero corruption |
| `reports/2026/08/*.html` (current month) and its matching PDFs | **Production active — no retention action.** Current month is presumptively still accumulating feed references as new advisories publish. | N/A | Phase 2/4 |
| `threat/*.html` | **Production active — no retention action.** Separately managed by `scripts/threat_page_generator.py`; zero overlap with `reports/`. | N/A | Phase 1/4 |
| Tracked `workers/intel-gateway/node_modules/` | **Remove from git tracking immediately** (not from disk — `npm install` regenerates from tracked `package.json`/`package-lock.json`). Zero retention window; this is a `.gitignore`-violating build artifact, not data. | Immediate, one-time | Phase 3 §1: zero dependency of any kind |
| `data/.manifest_backups/` | **Keep the 5 most recent snapshots at the current path; archive the remaining 30** (compress to `data/archive/cold/manifest_backups/`, not delete). Re-evaluate the "5" figure only if a consumer is later found to need more. | Rolling, re-applied on each future accumulation | Phase 3 §2: category is referenced by `validate_intel_schema.py`/`sanitize_repo.py` as a "latest" lookup, not confirmed to require full 35-file history |
| Root-level orphan files (`DASHBOARD-OVERVIEW-LIVE-VIDEO.mp4`, `v55.2-complete.patch`, `SENTINEL_APEX_v78_P0_FIX.tar.gz`, `0001-SENTINEL-APEX-v28.0-FORTRESS-*.patch`, `claude-tasks-history-screenshot.jpg`) | **Move to `archive/root-artifacts-2026-08/` in a single, reversible commit.** Not deleted — zero dependency found, but "not confidently provable as dead" (Phase 1 finding 2) keeps this at archive, not delete. | Immediate, one-time | Phase 1 finding 4, Phase 3 §4 |
| `data/simulations/*.bat`, `data/products/*.zip` | **No retention action — permanent KEEP.** | N/A | Phase 2/3: real commercial product data |
| `data/archive/`, `data/intelligence/` | **No retention action from this effort.** Already governed by the real, working `cold_archive_automation.py` HOT/WARM/COLD/PURGE lifecycle (30/90/365-day windows) — this policy does not duplicate or override that system. | N/A (pre-existing) | Phase 1 §5 |
| Source, tests, docs, CI, ADRs | **No retention action — out of scope by this effort's own absolute rule.** | N/A | Task governing constraints |

---

## 3. Explicit non-goals

- This policy does **not** authorize deleting anything currently referenced by
  `api/feed*.json`. Unlocking `reports/2026/07/`'s ~654MB is a separate, future effort scoped
  around one of Phase 3's three options (regenerate feed references, compress-in-place preserving
  URL, or exclude referenced files from scope) — not something this sanitation pass forces through.
- This policy does **not** replace or modify `scripts/cold_archive_automation.py`'s existing
  `data/intelligence/*.json` lifecycle. That system already works and is out of scope.
- This policy does **not** lower `storage_governance.py`'s existing `RETENTION` values for
  non-`reports` categories (`rollback_snapshots`, `health_history`, `alert_history`, etc.) — those
  were not flagged by Phase 1–4 as problems and are left untouched.

## 4. Grace period and enforcement mechanism

- **Grace period**: a file becomes "orphaned" the moment it's absent from all four feed files, but
  Phase 8's tool re-checks R0 at the moment of execution (not at policy-design time) — the 639-count
  from Phase 4 is a Phase-4-dated snapshot, not a frozen list. Any file that has since gained a feed
  reference between Phase 4 and execution is automatically excluded by the live R0 check.
- **Enforcement mechanism**: Phase 8 extends `scripts/storage_governance.py`'s existing
  `prune_old_reports()` — which today deletes by mtime/count alone via direct `f.unlink()`, with
  **no R0 check and no backup** — into a version that (a) adds the R0 feed-reference gate as a
  mandatory pre-condition, and (b) adds the backup/hash-verify/atomic-manifest safety pattern
  `cold_archive_automation.py` already demonstrates elsewhere in this same repository. This is a
  **Reuse Before Build** decision: both safety primitives already exist in the codebase; Phase 8
  composes them rather than writing a third, competing implementation.
- **Existing `RETENTION["reports_html"]` config** (`max_count: 50, max_age_days: 30`) is retained as
  a secondary filter *after* the R0 gate, not a replacement for it — a file can be within the
  age/count window and still be permanently protected by R0.

## 5. Reversibility

Every action this policy permits is one of: **remove-from-git-only** (node_modules — trivially
regenerable, not a data-loss risk), or **archive** (compress + move, original content fully
recoverable by decompression — manifest_backups, root orphan files, orphaned PDFs). This policy
authorizes **zero permanent, irreversible deletions**. That determination — whether any of these
archive candidates later graduate to permanent deletion — is explicitly deferred to a future,
separate decision with its own sign-off, consistent with this effort's governing rule that every
deletion must be justified and reversible.
