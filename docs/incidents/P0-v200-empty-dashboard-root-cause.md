# Incident Investigation — "Empty Dashboard" (SYNC: LOADING / 0 Advisories)

**Reported severity:** P0, customer-facing outage.
**Investigated:** 2026-09-03, ~10:36–11:05 UTC, against live production (`https://intel.cyberdudebivash.com/`) on `origin/main @ 64ddc6d98`.
**Verdict: does not reproduce as a permanent, customer-facing outage.** A genuine, narrower finding was made — see §4 — but it does not match the reported symptom (permanently stuck at zero) and no code change was made, per Proof-Before-Change: no specific, root-caused defect was located in the intel-loading pipeline itself.

---

## 1. Method

Reproducing this class of claim requires executing the actual production JavaScript against actual production data, not reading source or checking HTTP status codes — a live browser (Playwright/Chromium) remains blocked in this environment by a pre-existing, environment-wide proxy WebSocket-tunnel limitation (re-confirmed this session: `example.com` fails identically to production). The substitute methodology, used consistently across this investigation:

- jsdom 30, loading the **real, currently-deployed** `index.html`, `runScripts: "dangerously"`, real DOM.
- `window.fetch` wired to Node's native `fetch` (which does reach the real network through this environment's proxy — confirmed working throughout), resolving relative URLs against `window.location` the way a real browser does.
- No stubbing, mocking, or synthetic data at any layer — every response is the actual live API.

This was run **six times** across roughly 30 minutes, both as single fixed-wait snapshots and as a continuous poll sampling state every 2 seconds for up to 45 seconds.

## 2. Endpoint / data-layer health (§§2–4 of the incident brief)

| Check | Result |
|---|---|
| `GET /` | 200, `last-modified: 2026-09-03T09:27:08Z` (matches today's deploy) |
| `GET /api/feed.json` | 200, `count: 500`, `generated_at: 2026-09-03T09:22:00Z`, `version: v200.0` |
| `GET /api/preview/` | 200, real items, same dataset |
| `GET /api/feed` | 200 |
| `GET /api/v1/intel/latest.json` | 200 |
| `GET /api/health` | 200 |
| `GET /apex.json`, `/ai_summary.json` | 404 (not real endpoints the frontend calls — confirmed by reading `apex-data-plane.js`/inline fetch call sites, not guessed) |

No boundary in R2 → API is broken. `count: 500` is the authoritative figure this session traced end to end.

## 3. Frontend rendering — six independent runs

| Run | Method | `INTEL_RENDERED` | Grid state | Canvas-retry noise present |
|---|---|---|---|---|
| Pre-deploy (this session, earlier) | single 12s snapshot | `true` | 109/500 cards (mid-pipeline data) | not recorded |
| Post-deploy (this session, earlier) | single 12s snapshot | `true` | 500 cards | not recorded |
| Incident re-check #1 | single 12s snapshot | **`false`** | spinner, 0 cards | **11 occurrences** |
| Polling trace | sampled every 2s to 45s | `true` by **t=4s** | 500 cards | 0 occurrences |
| Quick-repeat #1 | single 12s snapshot | **`false`** | spinner, 0 cards | not isolated |
| Quick-repeat #2 | single 12s snapshot | `true` | 500 cards | not isolated |

4 of 6 runs converged correctly (with cards matching the authoritative 500-item API count) within the 12-second window; the polling trace shows the underlying convergence time is normally **~4 seconds**. 2 of 6 runs had not yet converged at the fixed 12-second checkpoint.

**This does not reproduce the reported symptom.** The claim is a *permanent* stuck-at-zero state with a *split-brain* (985 elsewhere, 0 on the primary grid). What was actually observed is, at worst, **convergence-time variance** — never a permanent hang, and in every run that had converged, the primary grid's item count matched the authoritative API count exactly (no split-brain: both the primary `#threat-grid` (GOC) and the secondary `#sapx-card-grid` (SAPX) renderer draw from the same `api/feed.json` and agreed on count in every run where both had a chance to finish).

## 4. The one real, narrower finding: a plausible test-environment confound

The runs that had *not* converged by 12s show heavy console activity (11 occurrences in one case) from an entirely unrelated subsystem: `CDB-V173`/`CDB-COMPOSITOR`'s GPU-tier canvas governance, which retries in a loop specifically because **jsdom has no native `<canvas>` 2D context** (a well-known, documented jsdom limitation — `Not implemented: HTMLCanvasElement's getContext()`, unrelated to intel data). The run that converged cleanest (polling trace, 4s) shows **zero** such retries. This is a correlation from a small sample, not proof, but it is the most parsimonious explanation available: a decorative, unrelated canvas-detection loop competing for Node's single-threaded event loop in this *test* environment, which would not occur in a real browser (which has a working canvas and would resolve that subsystem near-instantly).

**This cannot be fully distinguished from a real, if intermittent, production timing issue without real-browser telemetry**, which this environment cannot currently produce (Playwright blocked). That residual uncertainty is real and is the one thing this investigation cannot close out with full confidence.

## 5. Why no code change was made

Per this repository's Proof-Before-Change requirement, a modification needs a specific, evidenced defect. What exists here is: (a) the reported permanent-outage symptom does not reproduce, and (b) a timing-variance signal that is more consistent with this test harness's own jsdom limitation than with a production defect, with no specific line of code identified as the cause. Changing the render/boot-sequence code on this basis would be speculative, not evidence-based, against a currently-healthy production system.

## 6. Recommendation

The highest-value, lowest-risk next step is exactly what the incident brief itself proposes in its §17/§19: a **permanent, real-browser-based production contract test** (and post-deploy canary) for `/` that samples convergence time across many real runs. That is the only way to get ground truth this sandboxed environment cannot provide, and it is valuable regardless of whether this specific incident is confirmed — it directly targets the residual uncertainty in §4 rather than a hypothesis this investigation could not fully close.
