# Project TITAN Stage 8 — Runtime Dependency Graph (Phase 5)

**Status:** Evidence-only, per Stage 8's explicit instruction ("No assumptions. Evidence
only."). Traces the confirmed-live path for each of the four capability chains Stage 8 names
(Evidence, Confidence, Relationship Graph, plus Storage/External/Outputs), citing file:line
throughout. Where a chain has a confirmed-dead branch, it is shown and marked dead rather than
omitted, so the graph reflects reality, not just the happy path.

---

## Confidence chain (live)

```
Route: GET /api/v1/p25/trust-score  (index.js:4217)
  ↓
Controller: handleP25TrustScore(request, env)  (p25-handlers.js:487)
  ↓ reads env.SECURITY_HUB_KV.get("feed:latest")  [Storage: Cloudflare KV]
  ↓
Service/Evidence: computeP20QualityScore(item)  (p20-handlers.js, imported p25-handlers.js)
  ↓
Confidence: computeEnterpriseTrustScore(item)  (p25-handlers.js — canonical, ADR-0007 A1)
  ↓
Output: JSON { p25_trust_score, p25_trust_tier, p25_dimensions[] }  — verified live response shape
```

**Dead branch (confirmed unreachable, not part of live traffic):**
```
Route: GET /api/v1/intelligence/confidence  (blog api/v1/intelligence/confidence.js — file exists)
  ↓ [Vercel platform-level NOT_FOUND — chain terminates here, verified]
  ✗ confidence-exposure.js / confidence-scorer.js (api/_lib/) — never invoked in production
```

## Evidence chain (live)

```
Route: GET /api/v1/p20/... (quality report family)  (index.js, P20 block)
  ↓
Controller: handleP20QualityReport / handleP20FeedAudit  (p20-handlers.js)
  ↓
Evidence: item.evidence_chain  (p20-handlers.js:185-244 — canonical, ADR-0008 E1)
  ↓ reads item.evidence_chain.reliability_code, source_category, chain_of_custody[]
  ↓
Storage: R2/KV-backed feed data  (env.INTEL_R2 / env.SECURITY_HUB_KV, per index.js's binding usage)
  ↓
Output: buildEvidenceChainBlock() rendered HTML/JSON block
```

**Dead branch (confirmed unreachable):**
```
Route: POST /api/v1/analysis/findings, /api/v1/workbench/investigations  (blog, files exist)
  ↓ [Vercel platform-level NOT_FOUND — chain terminates here, verified]
  ✗ evidence-manager.js / evidence-validator.js / evidence-conflict-engine.js (api/_lib/) — never invoked
```

## Relationship graph chain — TWO live, uncoordinated paths (the DEBT-000B finding, shown structurally)

```
Path A (R1):
Route: GET /api/v1/p31/graph  (index.js:4250)  — verified live, HTTP 402
  ↓
Controller: handleP31Graph(request, env)  (p31-handlers.js)
  ↓
Service: _buildGraph(...)  (p31-handlers.js — rebuilt from feed corpus PER REQUEST, no persistence)
  ↓
Storage: reads live feed data directly (same source as most P-layers)
  ↓
Output: buildP31RelationshipBlock() JSON

Path B (R3):
Route: GET /api/v1/intel/graph  (index.js:4360, api-extensions.js)  — verified live, HTTP 403
  ↓
Controller: handleIntelGraph(request, env, auth, rid)  (api-extensions.js:1542)
  ↓
Storage: env.INTEL_BUCKET.get("data/ai/intel_graph.json")  — a DIFFERENT, PRE-COMPUTED R2 object,
         producer unidentified (DEBT-013)
  ↓
Output: JSON graph data — DIFFERENT SHAPE, DIFFERENT FRESHNESS CHARACTERISTICS than Path A
```

**These two live paths do not call each other and do not share a data source.** This is the
graph-form illustration of DEBT-000B — two arrows into the same conceptual box ("relationship
graph for this feed"), diverging immediately after the route layer.

**Additional live branch, different repository (R4, not diagrammed in full — cross-repo):**
```
Blog: GET /api/v1/intel?action=graph  (blog api/v1/intel.js, verified live, 401 without auth)
  ↓ api/_lib/intel.js:294 → api/_lib/threat-graph.js (getGraphForTier, getTopActors, loadGraph)
  ↓
Storage: Redis (per Stage 7's reachability trace — threat-graph.js's own persistence, distinct
         from both Path A and Path B above)
```

## Storage layer (confirmed bindings, intel-platform)

| Binding | Type | Confirmed usage |
|---|---|---|
| `SECURITY_HUB_KV` | Cloudflare KV | Feed data (`feed:latest`), P25's read path confirmed live |
| `INTEL_BUCKET` / `INTEL_R2` | Cloudflare R2 | `data/ai/intel_graph.json` (R3's source), general feed/report storage |
| `REPORTS_R2` (`sentinel-apex-reports`) | Cloudflare R2 | HTML report serving, per `wrangler.toml`'s route comment |
| `API_KEYS_KV` | Cloudflare KV | Credential authority, per `ARCHITECTURE_DECISIONS.md` (pre-TITAN, unchanged) |

## Storage layer (confirmed, blog)

| Binding | Type | Confirmed usage |
|---|---|---|
| Redis | External (via `api/_lib/redis.js`) | Used by all 7 non-`og.js` live Vercel entry points (per Stage 7's reachability trace), including the confirmed-live `newsletter.js` |
| R2/static (per `generate_api_manifests.py`) | Immutable JSON bundles | `api/v1/intel/*.json` static delivery, distinct mechanism from both Worker routes and Vercel functions |

## External APIs (confirmed live integration points)

| Integration | Confirmed via |
|---|---|
| Razorpay | Live webhook routes on both platforms (`workers/intel-gateway`'s webhook handling, blog's `api/v1/billing/razorpay-webhook.js` — verified to exist and be in `vercel.json`'s declared functions) |
| Stripe | Blog `api/_lib/stripe.js`, confirmed reachable from `billing.js` and `webhook.js` per Stage 7's trace |
| Resend (email) | Blog `api/_lib/resend.js`, confirmed reachable from **both** `auth.js` and the newly-verified-live `newsletter.js` |
| GitHub Actions (dispatch) | `api/cron/dispatch-intel.js`, confirmed real by full-file read (Stage 7), dispatches to `blogger-syndication.yml`, `sentinel-apex.yml`, `freshness-check.yml` |

## What this graph does not show

- Any branch rooted in the 21 confirmed-unreachable blog routes beyond the two dead-branch
  illustrations above (Confidence, Evidence) — the full engine cluster (`graph-engine.js`,
  `quality-gates-engine.js`, `governance-engine.js`, etc.) is real code with its own internal
  logic, but since nothing reaches it, mapping its internals would document a graph with no
  live entry point, which is not useful runtime-dependency information.
- `revenue-engine` and `intel-retention-engine` (sibling Cloudflare Workers) — out of this
  stage's AR-000-focused verification scope.
