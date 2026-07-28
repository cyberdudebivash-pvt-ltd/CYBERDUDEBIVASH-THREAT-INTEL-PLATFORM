# Transformation Status

**Last updated:** 2026-07-28 · Tracks the repository rationalization / canonicalization program (EPTP). This document covers repository organization and architecture consolidation. It is not a security status report.

## Completed

- Repository-wide legacy and dead-code identification, with evidence-based classification (production / legacy / experimental / customer artifact / archived / unknown).
- Business-decision reconciliation: confirmed which repository artifacts correspond to retired infrastructure (Railway hosting, Blogger publishing) versus active systems.
- **Batch 1** (EPTP Phase 8): removed a confirmed-orphaned cluster of Blogger-publishing code and its two unused dependencies; removed four stale, unreferenced `index.html` backup files; added a Cloudflare KV restore script to pair with the existing backup automation.
- **Batch 2** (EPTP Phase 8, this phase): introduced this canonical documentation set (`production_manifest.yaml`, `REPOSITORY_STATUS.md`, `PRODUCTION_RUNTIME.md`, `LEGACY_COMPONENTS.md`, `TRANSFORMATION_STATUS.md`, `COMPONENT_REGISTRY.json`, `ARCHITECTURE_DECISIONS.md`).

## In Progress

- Establishing this documentation set as the single point of reference for future implementation batches, so each batch can cite it rather than re-deriving architecture facts.

## Blocked

- Retirement of Railway-specific configuration (`railway.json`, `Dockerfile.railway`, `Procfile`, `sentinel-apex-api/`) is gated on confirming whether any currently-served page still depends on a Railway-hosted endpoint. Not yet confirmed.
- A business decision on whether the `platform/` microservices monorepo and the ClickHouse cluster in `infrastructure/clickhouse/` should be adopted as a second production architecture or retired has not yet been made.

## Deferred

- Three additional dead-code files discovered while validating Batch 1 (`publisher.py`, `agent/publisher.py`, `agent/v56_publish_guard/publisher.py`) were confirmed orphaned but intentionally left out of Batch 1's scope; carried forward as a candidate for a future batch.
- A full live/dead inventory of `scripts/` (412 files) and the older version-suffixed directories under `agent/` has not yet been performed at the individual-file level.

## Future

- Consolidating the multiple parallel API surfaces (`api/v1/`, `api/apex_v2/`, `agent/api/`, `sentinel-apex-api/`) once their respective live/dead status is established.
- Reorganizing root-level historical documentation (versioned changelogs, point-in-time audit reports) into a dedicated archive location, reducing repository-root clutter.
