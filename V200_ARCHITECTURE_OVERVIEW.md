# Architecture Overview — v200

**Project TITAN Stage 22 Phase 8**
**A concise map, not a new architecture document** — every claim here is already established in
depth elsewhere in this repository; this page exists to orient a new reader before they go deep on
any one piece.

## The two lineages

**1. The live product**: `workers/intel-gateway/src/index.js` (4,480 lines) + the P16–P39 handler
stack (`p16-handlers.js` through `p39-handlers.js`, minus P24 which doesn't exist and P39 which is
deliberately unrouted). This is a single Cloudflare Worker (`sentinel-apex-gateway`), deployed to
one production environment, routed on `intel.cyberdudebivash.com`, backed by 4 KV namespaces and 2
R2 buckets — no D1, no external database. ~150–190 routes, mostly `/api/v1/p{16-38}/*`. This is what
customers actually reach today.

**2. The Gateway lineage**: `evidence-registry/` → `intelligence-platform/` →
`enterprise-gateway/` → `knowledge-platform/`/`product-platform/`/`relationship-framework/` →
`commercial-catalog/`, all under `workers/intel-gateway/src/`. Architecturally complete, internally
additive-only, extensively tested (particular strength: `node --test` suites across every layer) —
and **entirely disconnected from lineage 1**. Zero references from `index.js`, confirmed repeatedly
across Stage 21 and Stage 22 audits. This lineage exists, works, and is not customer-reachable.

Both lineages follow the same discipline: additive-only extension (new capabilities import and
compose, never re-implement), single-canonical-source enforcement (mechanically checked by
`scripts/titan_architecture_governance_check.py`, 98 checks as of Stage 21), and zero-blast-radius
boundaries. The P-layer stack governs lineage 1; the Gateway's own `AUTHORIZED_CONSUMER_DIRS`
pattern and per-directory `zero-blast-radius.test.js` suites govern lineage 2.

## The P-layer stack (lineage 1)

| Range | Role |
|---|---|
| P16–P19 | Subsystems, orchestration, correlation, SOC/IOC detail |
| P20–P23 | Report quality, certification, contradiction detection, actionability |
| P25–P29 | Trust scoring, grading, exposure analysis, environment risk, decision engine |
| P30–P33 | Continuous verification, knowledge graph, operational lifecycle, ECIOS (cross-feed aggregation) |
| P34–P38 | Engineering assurance, quality engineering, excellence/maturity, hardening, governance |
| P39 | Commercial Quality Orchestrator — built, real, deliberately unrouted |

Each layer imports from lower layers and extends their output; none re-implements. See CLAUDE.md's
own P-layer table for the authoritative per-layer function list.

## Data flow (lineage 1, simplified)

External sources → ingestion/enrichment (Python automation, `scripts/`, `agent/`) → canonical feed
(`data/feed.json`, 159 items — the file every `p*_production_certification.py` script certifies) →
STIX bundle generation (`data/stix/`, 503 bundles) → per-advisory HTML report generation
(`scripts/report_generator.py`, 10,040 files under `reports/`) → served live via the Worker, which
also independently assembles report HTML for some paths via `p19`/`p20-handlers.js` block builders.
A separate, differently-enriched feed variant (`api/feed.json`, 17 items) carries fields (e.g.
`evidence_chain`) that don't reach the canonical 159-item feed — a known integration gap, not a
design choice (`COMMERCIAL_QUALITY_CERTIFICATION_REPORT.md` §0).

## Commercial layer

Tiers (FREE/PRO/ENTERPRISE/MSSP) are defined once, canonically, in `config/subscription_tiers.json`,
enforced live via `revenue-enforcement.js`, imported directly into `index.js`. Payment: Razorpay and
Gumroad are live; Stripe is coded but unconfigured. This is entirely separate from
`commercial-catalog/` (lineage 2's Stage 21 work) — that's a Gateway *capability* catalog, not the
billing/tier system; despite the name similarity, they solve different problems and neither
duplicates the other.

## Governance

`scripts/titan_architecture_governance_check.py` (advisory-only, exits non-zero on any finding but
the CI workflow wraps it with `|| true`) is the one mechanically-enforced architectural boundary
check, covering both lineages: no duplicate engines, no unauthorized imports, no capability-ID
collisions, contract version-drift detection, and per-stage "still unwired" assertions confirming
lineage 2 stays disconnected from lineage 1. It does not check security posture (CORS, auth
coverage) or commercial correctness (pricing consistency) — those are this Stage's certification
documents' job, not the governance script's.

## Further reading

- Full audit: `TITAN_V200_RELEASE_AUDIT.md`
- Per-stage history: `TITAN_STAGE*.md` (21 stages' worth, Stage 6 onward has ADRs in `docs/adr/`)
- Gateway lineage detail: `TITAN_STAGE21_GATEWAY_ACTIVATION_REPORT.md`,
  `ARCHITECTURE_COMPLIANCE_REPORT.md`
- Commercial/billing detail: `COMMERCIAL_READINESS.md`
