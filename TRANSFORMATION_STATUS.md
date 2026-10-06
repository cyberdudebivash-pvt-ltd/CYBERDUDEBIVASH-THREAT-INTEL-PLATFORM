# Transformation Status

**Last updated:** 2026-08-21 · Tracks the repository rationalization / canonicalization program (EPTP). This document covers repository organization and architecture consolidation. It is not a security status report.

## Completed

- Repository-wide legacy and dead-code identification, with evidence-based classification (production / legacy / experimental / customer artifact / archived / unknown).
- Business-decision reconciliation: confirmed which repository artifacts correspond to retired infrastructure (Railway hosting, Blogger publishing) versus active systems.
- **Batch 1** (EPTP Phase 8): removed a confirmed-orphaned cluster of Blogger-publishing code and its two unused dependencies; removed four stale, unreferenced `index.html` backup files; added a Cloudflare KV restore script to pair with the existing backup automation.
- **Batch 2**: introduced this canonical documentation set (`production_manifest.yaml`, `REPOSITORY_STATUS.md`, `PRODUCTION_RUNTIME.md`, `LEGACY_COMPONENTS.md`, `TRANSFORMATION_STATUS.md`, `COMPONENT_REGISTRY.json`, `ARCHITECTURE_DECISIONS.md`).
- **Batch 3**: cross-checked Batch 2's documentation against the repository directly and fixed 5 factual inconsistencies, including a second production deployment pipeline (`deploy-revenue-engine.yml`) that had been missed entirely.
- **Batch 4**: added automated validation (`scripts/validate_canonical_docs.py`, `scripts/detect_repository_drift.py`) and a dedicated, non-blocking CI workflow (`repository-integrity-check.yml`) so this documentation set can no longer silently drift from the repository without detection.
- **Batch 5**: resolved every open drift-detection finding and the two largest remaining low-confidence areas. `api/v1/` and `api/apex_v2/` reclassified from unknown to confirmed production (they're the report pipeline's local staging output, not competing API code). All 34 version-suffixed `agent/` directories individually evidenced: 17 confirmed production via dedicated scheduled workflows, 1 confirmed superseded (`v60_incident_engine`), 13 left honestly unknown for lack of evidence either way. `scripts/`'s 410 files given a quantified aggregate signal (49.5% referenced by at least one workflow) rather than remaining a bare guess.
- **Batch 6**: verified dependencies for every `legacy`/`customer_artifact` component and produced a retirement readiness matrix. Found two real hidden dependencies previously unknown to this program: `enterprise-rollback-governance.yml` treats `agent/api/api_server.py` as a "critical file" requiring extra rollback scrutiny, and `scripts/soc2_compliance_engine.py` checks `api/main.py`'s existence/content as SOC2 compliance evidence — both would need updating before either file could ever be safely removed. 4 components confirmed `READY` for future retirement (the already-removed Blogger cluster, the `publisher.py` cluster, `agent/v60_incident_engine/`, the root dev docker-compose pair); the rest remain `BLOCKED` or `NEEDS VALIDATION` with the specific blocker documented per component.
- **EPTP Phase 9, Batch 1** (this phase): the first actual retirement. Re-verified each of the 3 non-already-removed `READY` components immediately before deletion (no new dependency found for any), then removed them one at a time with validation after each: the `publisher.py`/`resilient_publish` cluster, `agent/v60_incident_engine/`, and the root dev `docker-compose.yml`/`docker-compose.prod.yml` pair. `COMPONENT_REGISTRY.json` updated to `archived` with retirement date, batch, and rollback commit SHA for each. Validator and drift detector both pass clean after every step.
- **Railway retirement** (2026-08-21, business decision: Railway hosting fully discontinued): removed the previously-`BLOCKED` Railway cluster -- `railway.json`, `Dockerfile.railway`, `Procfile`, `sentinel-apex-api/`, `agent/api/api_server.py`, `api/main.py` -- unblocking the two Batch 6 hidden dependencies first: `enterprise-rollback-governance.yml`'s critical-file list and `scripts/soc2_compliance_engine.py`'s SOC2 evidence checks were both updated to point at `workers/intel-gateway/src/index.js` (the confirmed-live production Worker) before deletion. `api/main.py`'s premium-content routes were re-targeted there rather than deleted outright. The root `Dockerfile` was deliberately kept, not retired -- reclassified instead, since `sbom-generation.yml` builds it as a live dependency-CVE scan target unrelated to Railway hosting. `COMPONENT_REGISTRY.json`'s 4 corresponding entries updated to `archived` with retirement date and batch.

## In Progress

- Establishing this documentation set as the single point of reference for future implementation batches, so each batch can cite it rather than re-deriving architecture facts.

## Blocked

- Retirement of the customer-installer cluster (`deploy/docker-compose.yml`, `Dockerfile.api`, `agent/v49_intelligence_api/`) is gated on a business decision: is self-hosted/on-prem installation still an offered product SKU? This is a functioning distribution mechanism, not dead code.
- A business decision on whether the `platform/` microservices monorepo and the ClickHouse cluster in `infrastructure/clickhouse/` should be adopted as a second production architecture or retired has not yet been made.

## Deferred

- 13 `agent/` directories remain classified `unknown` after Batch 5's investigation (see `COMPONENT_REGISTRY.json`'s `agent-version-generations-unresolved` entry) — evidence was insufficient either way, not a placeholder for future work so much as an honest ceiling on what static analysis alone can establish.
- `scripts/`'s ~207 workflow-unreferenced files have not been individually classified — Batch 5 established an aggregate signal, not a per-file audit.

## Future

- Reorganizing root-level historical documentation (versioned changelogs, point-in-time audit reports) into a dedicated archive location, reducing repository-root clutter — an isolation plan for this exists (Batch 6) but no files have been moved.
