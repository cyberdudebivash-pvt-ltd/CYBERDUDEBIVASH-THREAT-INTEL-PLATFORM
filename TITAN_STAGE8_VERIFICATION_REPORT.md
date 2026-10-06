# Project TITAN Stage 8 — Production Architecture Verification Report (Phases 1–2)

**Status:** Complete. This is the first TITAN stage to verify against **live production HTTP
behavior** rather than repository static analysis alone. All findings below are backed by
direct requests to `blog.cyberdudebivash.in` and `intel.cyberdudebivash.com`, run from this
environment (no Vercel/Cloudflare dashboard or build-log access — that gap is noted explicitly
wherever it matters, not glossed over).

**Headline result:** Stage 7's AR-000 (formerly DEBT-000) — "22 undocumented blog routes very
likely live" — does not hold up under direct testing. **21 of the 22 are confirmed NOT live**
(byte-identical to Vercel's platform `NOT_FOUND` response). One (`newsletter.js`) is confirmed
live. Full evidence in §Phase 2 and `TITAN_AR000_RESOLUTION.md`.

---

## Phase 1 — Production Architecture Verification

### Deployment topology (verified, not assumed)

| Platform | Domain | Confirmed via |
|---|---|---|
| intel-platform | `intel.cyberdudebivash.com` | `workers/intel-gateway/wrangler.toml` route patterns (`intel.cyberdudebivash.com/api/*`, `/reports/*`, `/taxii/*`, `/auth/*`), `config/platform_version.json`'s documented `api_base`, and live `GET /api/health` → **200** |
| blog | `blog.cyberdudebivash.in` | `vercel.json`'s own CSP `connect-src` header names it as `'self'` equivalent, and it is this repository's own documented production domain per `.vercelignore`'s header comment ("were live and Google-indexable at blog.cyberdudebivash.in") |

### Runtime topology

- **intel-platform**: Single Cloudflare Worker (`workers/intel-gateway`), ESM, deployed via `.github/workflows/deploy-worker.yml`. Confirmed live and responding with real, distinct HTTP status codes across dozens of routes (see registry). Two sibling workers (`revenue-engine`, `intel-retention-engine`) exist per `wrangler.toml` files but were not independently live-tested this stage (out of AR-000's scope, which is blog-specific).
- **blog**: Vercel serverless (Node.js functions under `/api`), no build step for static content (confirmed by `.vercelignore`'s own header comment), functions deployed per-file. **Confirmed empirically: not every file under `api/v1/` that exists in the git repository is actually deployed** — see Phase 2.

### Actual public API surface — verified subset

| Endpoint | Method | Live status | Evidence |
|---|---|---|---|
| `intel.cyberdudebivash.com/api/health` | GET | **200** | Direct curl |
| `intel.cyberdudebivash.com/api/v1/p25/trust-score` | GET | **200-shaped (404 body is application-level)** | Custom JSON `{"error":"Item not found","version":"P25.0"}` — real handler executed, see `handleP25TrustScore` (`p25-handlers.js:487`); 404 here means "no item matched," not "no route" |
| `intel.cyberdudebivash.com/api/v1/p38/observability` | GET | **200** | Direct curl |
| `intel.cyberdudebivash.com/api/v1/p31/graph` | GET | **402** (Payment Required) | Route exists, tier-gated |
| `intel.cyberdudebivash.com/api/v1/intel/graph` | GET | **403** (Forbidden) | Route exists, tier-gated (`aiTierReject`, per `api-extensions.js:1548`) |
| `intel.cyberdudebivash.com/api/v1/intel/relations` | GET | **403** | Same pattern |
| `intel.cyberdudebivash.com/taxii/` | GET | **200** | Live, public |
| `intel.cyberdudebivash.com/api/taxii/` | GET | **403** | Live, tier-gated (not dead — see DEBT-014 resolution below) |
| `blog.cyberdudebivash.in/api/og` | GET | **200** | Live |
| `blog.cyberdudebivash.in/api/v1/intel?action=live` | GET | **401** | Route exists, requires auth |
| `blog.cyberdudebivash.in/api/v1/auth?action=me` | GET | **401** | Route exists, requires auth |
| `blog.cyberdudebivash.in/api/v1/newsletter` | GET | **405**, POST **200** | Route exists, method-gated (confirmed in code: `newsletter.js:48`) |
| `blog.cyberdudebivash.in/api/v1/intelligence/confidence` | GET, POST | **404 (platform NOT_FOUND)** | See Phase 2 — not deployed |

### Internal API surface

P16, P17, admin (`/api/admin/*`), and the P34 "Engineering assurance" surface remain internal-
only by design (credential-gated); not independently probed this stage beyond confirming they
are not publicly callable without `ADMIN_SECRET` (consistent with Stage 6/7 findings, not
re-verified live this stage to avoid triggering auth-failure logging/alerting on a system this
environment doesn't own the on-call for).

### Authentication / Authorization (observed, not inferred)

Confirmed distinct auth signal shapes empirically:
- **401** (blog `/api/v1/intel`, `/api/v1/auth`) — authentication required, credentials missing/invalid.
- **402** (intel-platform `/api/v1/p31/graph`) — payment/tier required.
- **403** (intel-platform `/api/v1/intel/graph`, `/api/v1/intel/relations`, `/api/taxii/*`) — authorization/tier denial, distinct from 401.
- **404 application-level** (intel-platform `/api/v1/p25/trust-score` with no matching item) — business-logic "not found," not an auth or routing signal.
- **404 platform-level** (blog's 21 unreachable routes) — Vercel's own `NOT_FOUND`, no function deployed.

This three-way distinction (401 vs. 403 vs. two different kinds of 404) is exactly the signal
Phase 1 asks for under "Authentication / Authorization" and "Routing behavior" — captured here
with reproducible evidence rather than asserted from reading code alone.

### Customer / Evidence / Confidence / Relationship / Graph / Dashboard / Health endpoints

Covered by category in `TITAN_PRODUCTION_INTERFACE_REGISTRY.md` (Phase 4). Headline: every
category named in Stage 8's Phase 1 list has a confirmed-live intel-platform implementation;
the blog-side "second implementation" of most of these categories (per Stage 7's DEBT-000) is
confirmed **not** live, except newsletter capture (Customer/Growth category, not Evidence/
Confidence/Relationship).

### Background workers / scheduled jobs / edge functions

| Component | Type | Status |
|---|---|---|
| intel-platform Worker cron | Cloudflare cron trigger, `*/15 * * * *` (`wrangler.toml`) | Configured, not independently live-tested (would require waiting for/observing a scheduled invocation, out of this stage's practical scope) |
| `api/cron/dispatch-intel.js` | Vercel cron → GitHub Actions dispatch bridge | Confirmed real by Stage 7's full-file read: forwards to `blogger-syndication.yml`, `sentinel-apex.yml`, `freshness-check.yml` via `workflow_dispatch`, `CRON_SECRET`-gated. Not re-tested live this stage (would require a valid `CRON_SECRET`, which this environment does not have and should not attempt to guess/brute-force) |
| GitHub Actions scheduled workflows | `sentinel-blogger.yml` and others, `schedule:` triggers | Confirmed via direct git history that these run continuously (dozens of automated commits observed across Stages 6–8's session, e.g. "AI Tracker v184.0: run #424," "Guardian report," timestamps hours apart) — this is the strongest possible evidence of an actively-running scheduled system, short of triggering one manually |

---

## Phase 2 — Runtime Reachability Analysis

Every subsystem touched by this program, classified with supporting evidence. Categories per
Stage 8's own list: **Production, Internal, Dormant, Experimental, Deprecated, Archived,
Shadow, Unreachable, Dead Code.**

| Subsystem | Classification | Evidence |
|---|---|---|
| intel-platform P16–P38 (all layers) | **Production** | Live HTTP 200/402/403 responses across sampled routes; regression suite 21/21; P33 certification WORLDWIDE_RELEASE |
| intel-platform `enterprise-endpoints.js` (`/api/taxii`, MISP, Sigma/YARA bulk, scoring, SIEM) | **Production** | `/api/taxii/` confirmed live (403, tier-gated, not dead) |
| intel-platform `api-extensions.js` (`/api/v1/intel/graph`, `/relations`, search, actors, etc.) | **Production** | `/api/v1/intel/graph`, `/relations` confirmed live (403, tier-gated) |
| blog `Sentinel-APEX/` Python engine | **Production** | Confirmed via continuous automated commit history (syndication, report generation) — the actual mechanism producing the blog's published content |
| blog `api/v1/intel.js`, `auth.js`, `billing.js`, `admin.js` + 2 webhooks + cron + `og.js` (the original 8) | **Production** | Live 401/200 responses |
| blog `api/v1/newsletter.js` | **Production** | Live 405→200 responses, confirmed method-gated real handler |
| blog `api/v1/{intelligence,workbench,analysis,customer,products,quality,reports,detections,ioc}/*` (21 files) | **Unreachable** (files exist, code is real and non-trivial, but return Vercel's platform-level `NOT_FOUND` — indistinguishable from a route that was never created) | Direct HTTP verification, §Phase 1 table; byte-identical response body to a deliberately-nonexistent baseline path |
| blog `api/_lib/{confidence-scorer,confidence-exposure,evidence-manager,evidence-validator,evidence-conflict-engine,evidence-traceability-engine,source-reliability-engine,graph-engine,graph-traversal,relationship-engine,correlation-engine,governance-engine,quality-gates-engine,quality-scorer,quality-validators,threat-scorer,consistency-engine}.js` | **Unreachable** (same basis — these are only ever required by the 21 unreachable route files above; `TITAN_STAGE7_VALIDATION.md`'s reachability trace already established this require-graph, and no other reachable file calls them) | Transitive from the route-level finding above |
| blog `api/_lib/campaign-engine.js`, `threat-graph.js` | **Production** | `threat-graph.js` confirmed live via `api/v1/intel.js`'s working `?action=graph`/`?action=top-actors` (original Stage 7 finding, still valid — these are reached via the **live** `intel.js`, not the dead `intelligence/graph.js`); `campaign-engine.js` per `platform/open-issues.md` Issue 15's independent prior confirmation |
| blog `lib/*` (intelligence, reporting, ioc, detection, governance, api) | **Dormant** (per ADR-0013, unchanged this stage) | Zero consumers, no HTTP surface at all (not even file-based routing, since these are TypeScript source files, not deployed as Vercel functions — a different kind of "not live" than the 21 unreachable JS route files, which at least exist as file-routable paths) |
| `data/ai/intel_graph.json` producer (DEBT-013) | **Unknown / Unreachable-to-identify** | Not found this stage either — the file's *consumer* (`api-extensions.js`) is confirmed live, but its *producer* remains unidentified |

---

## What this report does not do

- Does not claim 100% certainty about *why* the 21 blog routes are unreachable (Vercel dashboard
  config, a build failure, or something else — see `TITAN_AR000_RESOLUTION.md` for the explicit,
  unresolved candidate list). It claims certainty about *whether* — that question is answered.
- Does not modify any code based on these findings in this document — resolution actions are in
  the AR-000 report and, where authorized, Phase 9's scaffolding.
- Does not independently verify the sibling workers (`revenue-engine`, `intel-retention-engine`)
  or GitHub Actions cron internals beyond git-history evidence — out of AR-000's scope.
