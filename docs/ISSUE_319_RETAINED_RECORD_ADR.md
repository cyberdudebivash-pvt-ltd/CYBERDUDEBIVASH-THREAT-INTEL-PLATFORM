# ADR: Retained-Record Fallback for the News-Ticker (Issue #319)

**Status:** Proposed (design/recommendation only — no code changed by this document)
**Context:** Stage 4 (Runtime Intelligence Architecture) audit, per that stage's explicit instruction not to implement #319 until this ADR exists and is reviewed.
**Decision needed from:** repository owner / account holder.

## The question

> Should Sentinel APEX retain and display a "last known good" intelligence record when the current authoritative source is unavailable?

Scoped specifically to `index.html`'s `initLiveCyberNews()` news-ticker widget — the subject of issue #319. This ADR does not extend to other fallback surfaces (e.g. the EICC panel, which already implements an honest-unavailable-state pattern worth reusing, not revisiting).

## Current state (evidence, not assumption)

Traced directly in code, confirmed independently by two passes:

- `initLiveCyberNews()` (`index.html:7176`) talks **only** to third-party CORS proxies — `api.allorigins.win`, `corsproxy.io`, `api.rss2json.com` — proxying `cisa.gov`, two `feedburner.com` feeds, `krebsonsecurity.com`, `bleepingcomputer.com`. It **never** calls this repository's own backend. Its only fallback is `STATIC_FALLBACK`, 12 hand-authored headline objects baked into `index.html` at build time (relabeled `SAMPLE` in PR #317 — an honesty fix, not a retention mechanism).
- A **separate, already-deployed, already-live** backend endpoint exists and is unused by this widget: `GET /api/v1/news/feed` (`workers/intel-gateway/src/index.js:5207`, handler `fetchNewsFromRSS()` at line ~1943). It:
  - Checks a KV cache first (`RATE_LIMIT_KV`, key `news:feed:v2`, 300s TTL).
  - On a miss, fetches the **same class of RSS sources** server-side (`RSS_SOURCES`, `Promise.allSettled`, 8s per-source timeout — no CORS problem server-side), dedupes, sorts, caps at 25 items, and writes the result back to KV.
  - On total source failure, returns an **honest empty state** (`{items: [], count: 0, error: "Feed temporarily unavailable", ...}`) — it does **not** currently keep serving a previous non-empty cached value; the 300s TTL simply governs "is there *any* usable cache," not "is there a *good* one."
- `workers/intel-retention-engine` (a third, separate live Worker, route `/api/v1/repository/*`) already implements a genuine "server-authoritative retained record" pattern in production — R2-backed, retention-policy-aware, deduped, with a historical run registry — but for **cumulative advisory counts** (dashboard stat stability), not news headlines. It is not itself the fix, but it is direct, working precedent for Option B below.
- `data/intelligence_repository/` — the retention-engine's backing data — is **dual-written**: committed to git (via `scripts/safe_git_commit.py`) *and* uploaded to R2 (`sentinel-blogger.yml` STAGE 3.5 / 4.1), and the pipeline's own comments document that this dual-write has caused **real, observed divergence** between the two copies before (`sentinel-blogger.yml`'s STAGE 4.1 exists specifically to reconcile it). This is a cautionary data point against introducing a *new* git-committed retention store.

## Options

### Option A — No retained fallback
Show an honest `CURRENT INTELLIGENCE UNAVAILABLE` state when live sources fail, matching the EICC panel's already-established pattern.
**Pros:** strongest truth semantics, zero new state to manage.
**Cons:** for a low-stakes news ticker, replacing a transient few-minutes RSS hiccup with a blank/unavailable widget is a UX regression the current `SAMPLE` fallback (imperfect as it is) doesn't have.

### Option B — Server-authoritative retained record (recommended)
Small, additive enhancement to the **already-live** `fetchNewsFromRSS()`: when a fresh fetch returns zero items but a previous non-empty result exists in KV, keep serving that previous result (separate "last good snapshot" key, independent of the 300s rotation TTL) with an honest `stale: true` flag and a server-computed `last_verified` timestamp — never a client `Date.now()` guess. Then repoint `initLiveCyberNews()` at `/api/v1/news/feed` instead of the three third-party CORS proxies.

**Pros:**
- Reuses infrastructure that already exists and is already deployed (`RATE_LIMIT_KV`, `fetchNewsFromRSS`, the `/api/v1/news/feed` route) — this is an enhancement to ~10 lines of an existing function, not a new subsystem. Directly satisfies this repo's own Reuse-Before-Build principle.
- Removes the CORS-proxy dependency entirely — a real reliability win independent of the retention question (three external, uncontrolled, occasionally-down services replaced by one first-party endpoint).
- Server-authoritative: the retention decision and the "is this stale" truth live on the backend, not scattered across every visitor's browser.
- No git-commit dual-write risk — this is pure KV, the same lesson `data/intelligence_repository/`'s own history already taught this codebase.
- Provenance is honest and cheap: `last_verified` is a real backend timestamp, not a fabricated freshness claim.

**Cons:** requires a (small, scoped) Worker code change and its own test coverage — real but modest engineering cost.

### Option C — Client-side retained record (localStorage or similar)
Not recommended, and this ADR does not implement it. Beyond the risks the Stage 4 brief itself lists (customer-to-customer inconsistency, uncontrolled persistence, provenance ambiguity, browser-specific behavior, cache-invalidation complexity), Option B makes this the *more* expensive path here, not just the riskier one: it would mean building new client-side retention logic from scratch when a working, server-side, KV-cached equivalent already exists one small enhancement away.

## Recommendation

**Option B.** For a security/intelligence platform, prefer authoritative server-side truth over client-owned state, and this is the case where that principle and the path of least engineering effort point the same direction — `/api/v1/news/feed` already does everything Option B needs except remembering the *last good* result instead of just *any* result.

## Scope of what this ADR does NOT decide

- Whether to widen this pattern to other fallback surfaces beyond the news ticker (out of scope — issue #319 is specifically about `initLiveCyberNews()`).
- The exact KV key layout / TTL tuning for the "last good snapshot" key — an implementation detail for whoever picks this up, not an architectural decision.
- Whether `STATIC_FALLBACK` should be deleted once Option B ships (it becomes a last-resort fallback for the case where KV has *never* had a successful fetch at all, e.g. a brand-new deployment — likely worth keeping as a final tier, not worth deciding here).

## Next step if approved

A small, focused PR: extend `fetchNewsFromRSS()` with the last-good-snapshot KV key, add its own unit tests (module is already dependency-free-testable via the same pattern `intel-static-proxy.js` / `subscription-lifecycle.js` use), repoint `initLiveCyberNews()` at `/api/v1/news/feed`, and prove — the same way PR #323's deployment-decoupling test does — that a KV-level change reaches the widget with no frontend deploy involved.
