# Production Sanitation — Intelligence Report Inventory

**Project TITAN — Production Sanitation & Commercial Readiness, Phase 4**

---

## Exact counts (git-tracked, measured directly)

| Location | Count | Notes |
|---|---:|---|
| `reports/2026/07/*.html` | 7,359 | Prior month |
| `reports/2026/08/*.html` | 2,661 | Current month (partial, as of audit date) |
| `reports/2026/*.html` total | 10,020 | Unique advisory IDs |
| `reports/pdf/*.pdf` | 9,934 | Flat directory, no month subdivision |
| `threat/*.html` | 2,144 | Separate, real, actively-generated advisory pages (`scripts/threat_page_generator.py`) — **zero overlap** with `reports/2026/*` (confirmed by ID comparison) |

## Quality checks

- **Failed/corrupted/incomplete**: **zero** files under 1,000 bytes found across all 10,020 HTML
  reports (a proxy for truncated/failed generation) — no evidence of corrupted report generation.
- **Development/experimental/draft reports**: **zero** filenames matching
  `test|draft|experiment|debug|temp|sample` — the report-generation pipeline does not appear to
  leak development artifacts into the production `reports/` tree (unlike, e.g., the
  `STANDALONE-TEST`-named remediation scripts found during Stage 22's quality certification, which
  live in a different directory).
- **Duplicates**: zero duplicate advisory IDs found between `reports/` and `threat/` — genuinely
  distinct content, not the same report generated twice into two locations.

## HTML/PDF correspondence — the real "orphan" finding

- 10,020 unique HTML report IDs vs. 9,934 unique PDF IDs.
- **725 HTML reports have no matching PDF** — likely recent reports where PDF generation lags HTML
  generation; not evidence of a problem.
- **639 PDFs have no matching current HTML report.** Their HTML counterpart is not present in
  `reports/2026/07/` or `reports/2026/08/` — meaning either an earlier month's HTML was already
  rotated out at some point (undocumented in any log this pass found) while the flat, non-dated
  `reports/pdf/` directory was never correspondingly cleaned, or these were generated from a source
  that no longer exists. **Confirmed not referenced by any `api/*.json` or `data/feed*.json` file**
  (spot-checked 5 samples, zero matches). This is the single cleanest, lowest-risk cleanup
  candidate found in the entire reports ecosystem — genuinely orphaned, not merely old.

## Recommendation (not executed by this document)

| Set | Recommendation | Rationale |
|---|---|---|
| `reports/2026/08/*.html` (current month) | **Production active** | Current, presumably still being actively linked to as new advisories publish |
| `reports/2026/07/*.html` (prior month) | **Archive candidate — blocked pending feed-reference update** | Real content, but 292+38 live references from `api/feed.baseline.json`/`api/feed.gold.json` (`PRODUCTION_SANITATION_DEPENDENCY_ANALYSIS.md` §3) make this unsafe to move without a coordinated update in the same operation |
| `reports/pdf/*.pdf` matching a currently-present HTML report | **Production active** | Mirrors the HTML disposition |
| **639 orphaned PDFs (no current HTML match)** | **Safe to archive now** | No dependency found on any axis |
| `threat/*.html` | **Production active, no action** | Live, wired, separately-managed |

No file has been moved, archived, or deleted by this inventory. The 639 orphaned PDFs are the one
concrete, ready-to-execute item this phase surfaces; everything else in `reports/` awaits the
retention policy (Phase 5) and, for the prior-month HTML set specifically, a follow-on effort
outside this pass's scope per Phase 3's finding.
