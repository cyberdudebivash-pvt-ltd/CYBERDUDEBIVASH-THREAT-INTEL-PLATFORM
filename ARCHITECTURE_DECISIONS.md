# Architecture Decisions

**Last updated:** 2026-08-21. Each entry below is a decision established during the EPTP transformation program, with the evidence or business input it rests on. This document only records decisions already made — it is not a proposal list.

## Cloudflare Workers is the canonical production runtime

Established by direct evidence: `workers/intel-gateway`, `workers/revenue-engine`, and `workers/intel-retention-engine` are the only components in the repository with a confirmed live continuous-deployment path (`.github/workflows/deploy-worker.yml`). No other candidate architecture found in the repository (a Python/Railway application, a 19-service microservices monorepo, a ClickHouse-based telemetry cluster) has equivalent deployment evidence.

## `API_KEYS_KV` is the sole runtime credential authority

Established by direct code review: every credential-issuing path in `intel-gateway` and `revenue-engine` writes to, and `intel-gateway`'s request-handling reads from, this one Cloudflare KV namespace, using a consistent key convention.

## Railway hosting is retired

Business decision, accepted as given for this program. Repository evidence (dedicated Railway deployment configuration in three separate locations) is consistent with Railway having previously been an active deployment target.

**Update (2026-08-21):** acted upon. `railway.json`, `Dockerfile.railway`, `Procfile`, `api/main.py`, `agent/api/api_server.py`, and `sentinel-apex-api/` were removed. `api/main.py`'s premium-content entitlement routes (added in a prior session, before this file's non-deployment was established) were re-targeted to `workers/intel-gateway/src/index.js` first. Three live customer-facing pages (`landing/api.js`, `landing/dashboard.html`, `landing/auth.html`) were found still calling the dead Railway domain and repointed to `intel-gateway`. See `LEGACY_COMPONENTS.md`'s "Retired Components (Railway retirement, 2026-08-21)" section for full detail, including what was intentionally left unresolved (an architecture mismatch in `auth.html`'s login/register forms, and several now-orphaned `api/*.py` helper modules not in the agreed removal scope).

## Google Blogger publishing is retired

Business decision, corroborated by repository evidence: the platform's report-generation pipeline (`agent/sentinel_blogger.py`) documents its own removal of Blogger integration in an earlier version, replacing it with direct R2 writes. A cluster of now-unused Blogger-publishing modules was identified as a consequence and removed in EPTP Phase 8, Batch 1.

## Report generation is R2-native

Established by direct evidence: the report pipeline writes HTML/PDF output to Cloudflare R2 (`sentinel-apex-data`, `sentinel-apex-reports`), which `intel-gateway` then serves directly. No external publishing step remains in this path.

## Production deployment follows the Cloudflare Worker pipeline exclusively

Consequence of the first decision above: `.github/workflows/deploy-worker.yml` is treated as the production deployment mechanism. Other deployment-shaped artifacts in the repository (Railway configuration, Docker Compose stacks, the `platform/` monorepo's Terraform/Helm definitions) are documented in [`LEGACY_COMPONENTS.md`](LEGACY_COMPONENTS.md) but are not treated as production deployment paths absent further evidence or a future decision to adopt one of them.

## This documentation set is the production source of truth going forward

Decision of this phase (EPTP Phase 8, Batch 2): future implementation batches should cite `production_manifest.yaml`, `PRODUCTION_RUNTIME.md`, `LEGACY_COMPONENTS.md`, and `COMPONENT_REGISTRY.json` rather than re-deriving architecture facts from scratch. Where new evidence contradicts these documents, the documents should be updated, not silently bypassed.
