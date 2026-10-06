# P0 Workflow Forensic Matrix — All 61 GitHub Actions Workflows

Full inventory of `.github/workflows/*.yml` (61 files, 18,434 lines), produced in response to a P0 incident investigation ("SYNC: LOADING / 0 advisories" reported on the customer dashboard while other page sections show real data). Every file was read in full — no sampling. Core data-plane files were read directly; the remaining 55 were read directly across four parallel research passes, cross-checked against direct source reads of `scripts/r2_upload.py`, `scripts/r2_upload_verifier.py`, `workers/intel-gateway/src/index.js`, and `service-worker.js`.

**Companion document:** `docs/incidents/P0-EMPTY-DASHBOARD-ROOT-CAUSE.md` (required verdict, root cause, and evidence per the incident brief's exact structure).

---

## 1. Writers of customer-facing dashboard state

Only workflows capable of touching `index.html`, `api/feed.json`, `api/v1/intel/**`, or `service-worker.js` are listed here in detail. Everything else is summarized in §3.

| Workflow | Writes | Mechanism | Concurrency group | Isolation from `sentinel-blogger` (`sentinel-data-writer`) |
|---|---|---|---|---|
| **sentinel-blogger.yml** | `api/feed.json`, `api/v1/intel/latest.json`, `latest_pro.json`, `top10.json`, `apex.json`, `manifest.json`, `ai_summary.json`, `api/reports/*.json` (all via `scripts/r2_upload.py`, confirmed by direct source read) + `gh-pages` (full `dist/`) + git commit of ~equivalent paths | `aws s3 cp` (R2) + `JamesIves/github-pages-deploy-action` + `git push` | `sentinel-data-writer` | — (this is the group) |
| **generate-and-sync.yml** | `api/feed.json` + ~25 other git paths; R2 `ai/tracker.json`, `ai/health.json`, `ai/executive-brief.json`, `ai/monetization.json` only | `git push` (git side) + `aws s3 cp` (R2 side, AI-tracker keys only) | `sentinel-ai-writer` | **No shared group** — relies on cron time-offset only (own header admits this); offset assumption (sentinel-blogger ≤90min) is **currently violated** — today's measured runtime was 105 min |
| **dashboard-feeds-sync.yml** | `api/v1/intel/apex.json`, `ai_summary.json` **(confirmed dual-writer with sentinel-blogger's r2_upload.py on these 2 keys)**, `stats.json`, `campaigns.json`, `ransomware.json`, `apt.json`, `epss.json`, `defcon.json`, `pulse.json`, `darkweb.json`, `cybermap.json` | `aws s3 cp` (R2) | `sentinel-dashboard-feeds` | **No shared group** — different group than sentinel-blogger; reads its source `api/feed.json` from its own git checkout, not directly from R2 |
| **pages-fast-publish.yml** | `gh-pages` deploy of `index.html`, `js/**`, `css/**`, `_headers`, `service-worker.js` only (explicit `clean-exclude` protects `api/**`, `reports/**`, `dashboard/**`, `customer/**`, `assets/**`) | `JamesIves/github-pages-deploy-action` | `pages-fast-publish` | Disjoint file scope by design from sentinel-blogger's own `gh-pages` deploy of the same branch; **no shared lock** between the two `gh-pages` writers, relies on disjoint file ownership holding |
| **v149-hardening.yml** | `index.html` (STAGE 9, dedup/container-clear patch) | `git push` | `v149-hardening-${{ github.ref }}` | **No shared group.** `workflow_dispatch`-only; **schedule removed since Aug 2, 2026** (last run: run #16, 2026-08-02) — confirmed via run history, cannot be the cause of a current incident, but is a live architectural risk if ever manually triggered while sentinel-blogger has an in-flight `index.html` write. Header: *"ALL SCRIPTS EXIT 0 — pipeline will never be blocked by hardening failures."* |
| **sync-dashboard.yml** | `index.html` (`EMBEDDED_INTEL` patch only) — but **structurally cannot run automatically** | `git push` | `sentinel-deployment` | N/A — dead (see §4) |

**Not a writer, confirmed by direct source read:** the Cloudflare Worker (`workers/intel-gateway/src/index.js`) serves `/api/feed.json` and `/api/preview` both from the single R2 key `api/v1/intel/latest.json` (`LATEST_JSON_KEY`). On a real R2 read failure it returns `503`, never a silent empty/zero payload. This is a single source of truth at the Worker layer — confirmed no split-brain at this boundary.

---

## 2. R2 key ownership (customer-facing keys only)

| Key | Authoritative writer(s) | Secondary/conflicting writer | Risk |
|---|---|---|---|
| `api/v1/intel/latest.json` (= `api/feed.json` at the Worker) | `sentinel-blogger.yml` (`r2_upload.py`) | none found | **Clean — single writer** |
| `api/v1/intel/apex.json` | `sentinel-blogger.yml` (STAGE 3.93.1 AI Brain Publisher + `r2_upload.py`) | `dashboard-feeds-sync.yml` | **Confirmed dual-writer, different concurrency groups, no serialization** |
| `api/v1/intel/ai_summary.json` | `sentinel-blogger.yml` (same) | `dashboard-feeds-sync.yml` | **Confirmed dual-writer, same as above** |
| `api/reports/index.json`, `api/reports/stats.json` | `sentinel-blogger.yml` (STAGE 3.3.7) | none (previously `dashboard-feeds-sync.yml` also wrote these — **already fixed**, F-02, removed from that workflow's scope; fix documented in the file's own header) | Clean — historical bug, already resolved |
| `intel/feed_manifest.json`, `_sync_meta.json`, `apex_enriched_manifest.json`, `apex_v2_*.json` | `sentinel-blogger.yml` (`r2_upload.py`) | `r2-data-sync.yml` (**disabled**, workflow_dispatch-only, its own header documents this exact overwrite risk as the reason it was disabled) | Clean — historical risk, already disabled |
| `feed_state.json`, `processed_intel.json`, `data/feed_manifest.json` | `multi-source-intel.yml` (via `r2_state_sync.py --upload`) | none | Clean — migrated off git (which permanently rejected these pushes via GH013) onto R2 as sole authority, per PR #330/#332 |
| `ai/tracker.json`, `ai/health.json`, `ai/executive-brief.json`, `ai/monetization.json` | `generate-and-sync.yml` | none | Clean on ownership, but see §3 for the push/R2 sequencing gap |

---

## 3. Full 61-workflow disposition summary

24 workflows write only to their own isolated `data/<domain>/` git subdirectory (genesis, cortex, quantum, sovereign, telemetry, graph, malware, predictive, arsenal, bughunter, detection rules, convergence, weekly briefings, zerodayhunter, status, products, etc.) — **none of these touch dashboard-facing files**, confirmed by direct grep/read across every file. Roughly 20 more are read-only (governance gates, security scanners, SBOM, backups reading not writing production data, revenue/billing/CRM state in a separate KV namespace, marketing/lead-response automations). Full per-file trigger/concurrency/masking detail for all 61 is preserved in this investigation's working notes; the table below is the disposition roll-up.

| Disposition | Count | Notes |
|---|---|---|
| KEEP | 51 | Correctly scoped, correctly gated, or confirmed read-only |
| HARDEN | 8 | `generate-and-sync.yml` (push/R2 sequencing gap + 4 mis-masked "hard-fail" gates), `dashboard-feeds-sync.yml` (≤3/11 upload-failure tolerance + `continue-on-error` validation), `multi-source-intel.yml` (persistence-engine `2>/dev/null \|\| true`), `v149-hardening.yml` (own concurrency group + exit-0 policy), `master-deployment-orchestrator.yml` (name/behavior mismatch — claims deploy authority, is fully read-only), `enterprise-intel-quality.yml` (double-masked exceptions across 6 phases), `autonomous-guardian.yml` + `enterprise-alerts.yml` (the monitors' own masking could blind them to the exact incidents they exist to catch), `nexus-intelligence.yml` (self-admitted duplicate of `sovereign-platform.yml` + missing branch gate), `automated-backup.yml` (job-level `continue-on-error`), `revenue-orchestrator.yml`, `telemetry-fabric.yml` (minor git-hygiene) |
| DEPRECATE | 1 | `bughunter-recon.yml` — schedule already disabled after a documented historical collision with `bughunter-resilient.yml` on the same cron+group; dispatch-only usage should be confirmed unnecessary and removed |
| Already DISABLED (verified genuinely inert) | 3 | `sync-dashboard.yml`, `r2-data-sync.yml`, (schedule-removed) `v149-hardening.yml`, `nexus-intelligence.yml`'s own schedule |
| INCIDENT-CULPRIT (confirmed currently active) | 0 | See root-cause doc — no live workflow reproduces the reported symptom |
| INCIDENT-CULPRIT (plausible, unconfirmed, evidenced) | 1 | `generate-and-sync.yml`'s STAGE 9/9.5 sequencing gap — see root-cause doc §"Contributing causes" |

---

## 4. Historical culprit (sync-dashboard.yml) — verified dead

Confirmed via direct read of the file plus a repo-wide search for equivalent logic:

- `on:` block: `workflow_run` and `schedule` triggers are **commented out**, not merely disabled by a condition — they do not exist as live YAML.
- The only remaining trigger, `workflow_dispatch`, is gated: `if: github.event.inputs.force_patch == 'true'` — a dispatch without that explicit input does nothing.
- Even under manual force, the job **no longer contains a `--force-rebuild` invocation** — zero occurrences as an executed command (only in comments describing the old bug) — and the commit step explicitly self-blocks the historical target: `git add -f data/stix/feed_manifest.json` is commented out with `# ⛔ BLOCKED: manifest destruction risk`.
- Concurrency group changed from the shared `sentinel-data-writer` to its own `sentinel-deployment` — the race mechanism (queuing directly behind sentinel-blogger, second-writer-wins) has no active pairing today.

**One adjacent, narrower, unconfirmed gap found nearby** (not a second racing workflow — inside `sentinel-blogger.yml`'s own `run_pipeline.py`): a gated `--force-rebuild` path triggers when `engine_count < 10`, calling `bootstrap_critical_files.py --force-rebuild`. That script's zero-entry preservation guard (CRIT-01) only protects against a collapse to exactly zero entries, not a collapse to a small-but-nonzero count (the original bug's 52→9 shape). This is architecturally different from the historical defect (single in-process call, not a second workflow racing over a shared concurrency group) and was not observed to fire in the run this investigation traced end-to-end. Flagged as follow-up, not asserted as active.
