# Legacy & Non-Production Components

**Last updated:** 2026-07-28. This document classifies components found during the EPTP transformation program's repository analysis. **It does not recommend removal of anything listed here** — classification only. See [`production_manifest.yaml`](production_manifest.yaml) and [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md) for what *is* in production, by contrast.

## Legacy Runtime

A Python FastAPI application, with two possible entry points defined in the repository (`agent/api/api_server.py` and `api/main.py`), was built to run on Railway. Railway hosting has been retired by business decision. Repository evidence does not establish that either entry point is currently deployed anywhere. The repository root `Dockerfile` defaults to running `agent/api/api_server.py`; its alternate `SENTINEL_MODE=blogger` branch (which would instead run the report pipeline inside the container) is confirmed unreachable in practice — nothing else in the repository sets that variable, and the real pipeline runs natively via `sentinel-blogger.yml`, not through this Dockerfile.

`sentinel-apex-api/` is a second, independently-scaffolded Railway-targeted codebase (its own `railway.toml` and `Dockerfile`), separate from the above.

Within `agent/`'s 34 version-suffixed directories, one (`agent/v60_incident_engine/`) is explicitly superseded — `agent/incident_response/incident_engine.py` states directly that it "replaces the CLI stub" there. It remains on disk; nothing recommends its removal here. See [`COMPONENT_REGISTRY.json`](COMPONENT_REGISTRY.json) for the full per-directory breakdown (17 confirmed production via dedicated scheduled workflows, 13 left unresolved for lack of evidence either way).

## Legacy Infrastructure

- `railway.json`, `Dockerfile.railway`, `Procfile` — Railway deployment configuration, retired alongside the hosting platform.
- Root-level `docker-compose.yml` / `docker-compose.prod.yml` — a Redis/Prometheus/Grafana/Loki development stack; its production variant's own configuration sources secrets "from Railway."

## Experimental Infrastructure

- `platform/` — a substantially-built 19-service microservices monorepo (Terraform, Helm, a Turborepo build graph, its own frontend). CI validates this tree (lint, container builds, Helm/Terraform validation) but no evidence establishes it has ever been deployed to a live environment.
- `infrastructure/clickhouse/` — a 9-service ClickHouse cluster definition (sharding, replication, a Vector-based telemetry pipeline). Not referenced by any workflow, script, or application configuration found elsewhere in the repository.
- `infrastructure/` (Terraform, Kubernetes, Redis configuration outside the ClickHouse tree) — single-file scaffolds without a README or CI wiring.

## Customer Installation Artifacts

- `deploy/docker-compose.yml` — not part of this repository's own runtime. It is copied by an installer script into a customer's own deployment directory as part of a self-hosted/on-premises distribution path. As currently authored, it references configuration files that do not exist in this repository's tracked tree.
- `Dockerfile.api` — the build context for `deploy/docker-compose.yml`'s `api` and `worker` services. Runs `agent/v49_intelligence_api/`'s FastAPI app. Same customer-installer package as the item above, not a separate concern.

## Archived Systems

- A cluster of Blogger-publishing modules (`agent/blogger_client.py`, `agent/blogger_auth.py`, and their callers) was confirmed to have zero remaining references anywhere in the repository and was removed in EPTP Phase 8, Batch 1. This is noted here for continuity rather than as an outstanding item.
- `publisher.py` (repository root), `agent/publisher.py`, and `agent/v56_publish_guard/publisher.py` define a `resilient_publish()` function intended (per their own docstrings) to be called from the report pipeline. The current report pipeline does not call any of them. Not yet removed; documented as a known finding for a future batch.

## Duplicated / Unconsolidated Surfaces

`agent/api/` presents an independently-versioned API surface alongside the production Cloudflare Worker API, tied to the same unresolved Railway deployment-target question as the Legacy Runtime section above. See [`COMPONENT_REGISTRY.json`](COMPONENT_REGISTRY.json) for classification and confidence.

**Correction (EPTP Phase 8 Batch 5):** `api/v1/` and `api/apex_v2/` were previously listed here as unconfirmed/duplicated surfaces. They are not — both contain generated data only (no code), are the report pipeline's local staging output before upload to R2, and are confirmed production. See [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md)'s Report Generation Flow.
