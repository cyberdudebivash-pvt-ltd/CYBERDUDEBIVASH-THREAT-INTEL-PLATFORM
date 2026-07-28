# Legacy & Non-Production Components

**Last updated:** 2026-07-28. This document classifies components found during the EPTP transformation program's repository analysis. **It does not recommend removal of anything listed here** — classification only. See [`production_manifest.yaml`](production_manifest.yaml) and [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md) for what *is* in production, by contrast.

## Legacy Runtime

A Python FastAPI application, with two possible entry points defined in the repository (`agent/api/api_server.py` and `api/main.py`), was built to run on Railway. Railway hosting has been retired by business decision. Repository evidence does not establish that either entry point is currently deployed anywhere. The repository root `Dockerfile` defaults to running `agent/api/api_server.py`; its alternate `SENTINEL_MODE=blogger` branch (which would instead run the report pipeline inside the container) is confirmed unreachable in practice — nothing else in the repository sets that variable, and the real pipeline runs natively via `sentinel-blogger.yml`, not through this Dockerfile.

`sentinel-apex-api/` is a second, independently-scaffolded Railway-targeted codebase (its own `railway.toml` and `Dockerfile`), separate from the above.

Within `agent/`'s 34 version-suffixed directories, one (`agent/v60_incident_engine/`) was explicitly superseded — `agent/incident_response/incident_engine.py` states directly that it "replaces the CLI stub" there — and was removed in EPTP Phase 9, Batch 1 (see Retired Components, below). See [`COMPONENT_REGISTRY.json`](COMPONENT_REGISTRY.json) for the full per-directory breakdown of the remaining 33 (17 confirmed production via dedicated scheduled workflows, 13 left unresolved for lack of evidence either way).

## Legacy Infrastructure

- `railway.json`, `Dockerfile.railway`, `Procfile` — Railway deployment configuration, retired alongside the hosting platform.
- Root-level `docker-compose.yml` / `docker-compose.prod.yml` — a Redis/Prometheus/Grafana/Loki development stack; its production variant's own configuration sourced secrets "from Railway." **Removed in EPTP Phase 9, Batch 1** (see Retired Components, below).

## Experimental Infrastructure

- `platform/` — a substantially-built 19-service microservices monorepo (Terraform, Helm, a Turborepo build graph, its own frontend). CI validates this tree (lint, container builds, Helm/Terraform validation) but no evidence establishes it has ever been deployed to a live environment.
- `infrastructure/clickhouse/` — a 9-service ClickHouse cluster definition (sharding, replication, a Vector-based telemetry pipeline). Not referenced by any workflow, script, or application configuration found elsewhere in the repository.
- `infrastructure/` (Terraform, Kubernetes, Redis configuration outside the ClickHouse tree) — single-file scaffolds without a README or CI wiring.

## Customer Installation Artifacts

- `deploy/docker-compose.yml` — not part of this repository's own runtime. It is copied by an installer script into a customer's own deployment directory as part of a self-hosted/on-premises distribution path. As currently authored, it references configuration files that do not exist in this repository's tracked tree.
- `Dockerfile.api` — the build context for `deploy/docker-compose.yml`'s `api` and `worker` services. Runs `agent/v49_intelligence_api/`'s FastAPI app. Same customer-installer package as the item above, not a separate concern.

## Archived Systems

- A cluster of Blogger-publishing modules (`agent/blogger_client.py`, `agent/blogger_auth.py`, and their callers) was confirmed to have zero remaining references anywhere in the repository and was removed in EPTP Phase 8, Batch 1. This is noted here for continuity rather than as an outstanding item.

## Retired Components (EPTP Phase 9, Batch 1)

Each retired only after re-verification immediately before removal found no new dependency. Individually revertible — see `COMPONENT_REGISTRY.json`'s `rollback_commit` field per entry.

- **`publisher.py`, `agent/publisher.py`, `agent/v56_publish_guard/publisher.py`** — the `resilient_publish()` cluster the current report pipeline never called. `agent/v56_publish_guard/__init__.py` was left untouched.
- **`agent/v60_incident_engine/`** — the superseded incident-response stub.
- **`docker-compose.yml`, `docker-compose.prod.yml`** (root) — the unused dev stack noted above.

## Duplicated / Unconsolidated Surfaces

`agent/api/` presents an independently-versioned API surface alongside the production Cloudflare Worker API, tied to the same unresolved Railway deployment-target question as the Legacy Runtime section above. See [`COMPONENT_REGISTRY.json`](COMPONENT_REGISTRY.json) for classification and confidence.

**Correction (EPTP Phase 8 Batch 5):** `api/v1/` and `api/apex_v2/` were previously listed here as unconfirmed/duplicated surfaces. They are not — both contain generated data only (no code), are the report pipeline's local staging output before upload to R2, and are confirmed production. See [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md)'s Report Generation Flow.

## Retirement Readiness (EPTP Phase 8 Batch 6)

Every component above was checked for hidden dependencies (governance rules, compliance tooling, cascading callers) before any retirement-readiness judgment. **This is classification only — nothing above has been removed or scheduled for removal.** Full detail, including specific blockers, is in [`COMPONENT_REGISTRY.json`](COMPONENT_REGISTRY.json)'s `retirement_readiness` field per component.

- **RETIRED (EPTP Phase 9, Batch 1)**: the `publisher.py`/`resilient_publish` cluster, `agent/v60_incident_engine/`, and the root dev `docker-compose.yml`/`docker-compose.prod.yml` pair — all 3 were `READY`, re-verified immediately before removal, and are now gone. See Retired Components, above.
- **NEEDS VALIDATION**: `sentinel-apex-api/` — several whole-repo maintenance scripts reference it, likely as generic iteration rather than a real dependency, but not individually confirmed.
- **BLOCKED**: the Railway cluster (`agent/api/api_server.py`, `api/main.py`, `sentinel-apex-api/`'s own Railway targeting, `railway.json`/`Dockerfile.railway`/`Procfile`, the root `Dockerfile`) — two newly-found hidden dependencies (a rollback-governance workflow's "critical files" list, and a SOC2 compliance script that checks for `api/main.py`'s existence as control evidence) plus the still-open question of whether Railway-dependent frontend pages still function. The customer-installer cluster (`deploy/docker-compose.yml`, `Dockerfile.api`, `agent/v49_intelligence_api/`) — blocked on a business decision (is self-hosted installation still offered), not a technical blocker.
