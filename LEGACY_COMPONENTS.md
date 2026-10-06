# Legacy & Non-Production Components

**Last updated:** 2026-08-21. This document classifies components found during the EPTP transformation program's repository analysis. **It does not recommend removal of anything listed here** — classification only, except where a component has actually been retired (see Retired Components). See [`production_manifest.yaml`](production_manifest.yaml) and [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md) for what *is* in production, by contrast.

## Legacy Runtime

A Python FastAPI application, with two possible entry points defined in the repository (`agent/api/api_server.py` and `api/main.py`), was built to run on Railway. Railway hosting has been retired by business decision. Repository evidence never established that either entry point was deployed anywhere. Both entry points, plus the second independently-scaffolded Railway-targeted codebase `sentinel-apex-api/`, were **retired in this batch** (see Retired Components, below).

The repository root `Dockerfile` defaulted to running `agent/api/api_server.py`; its alternate `SENTINEL_MODE=blogger` branch (which would instead run the report pipeline inside the container) is confirmed unreachable in practice — nothing else in the repository sets that variable, and the real pipeline runs natively via `sentinel-blogger.yml`, not through this Dockerfile. **The Dockerfile itself was NOT retired** despite its now-stale default CMD (`uvicorn agent.api.api_server:app`, referencing a deleted module) — `.github/workflows/sbom-generation.yml` builds it (`context: .`, no explicit Dockerfile override) as a live, load-bearing dependency-CVE scan target, unrelated to Railway hosting. That CMD is never exercised (the SBOM job only builds and inspects the image with Syft/Grype, never runs the container), but rewriting it is a separate decision requiring its own verification, not made here.

Within `agent/`'s 34 version-suffixed directories, one (`agent/v60_incident_engine/`) was explicitly superseded — `agent/incident_response/incident_engine.py` states directly that it "replaces the CLI stub" there — and was removed in EPTP Phase 9, Batch 1 (see Retired Components, below). See [`COMPONENT_REGISTRY.json`](COMPONENT_REGISTRY.json) for the full per-directory breakdown of the remaining 33 (17 confirmed production via dedicated scheduled workflows, 13 left unresolved for lack of evidence either way).

## Legacy Infrastructure

- `railway.json`, `Dockerfile.railway`, `Procfile` — Railway deployment configuration. **Removed** alongside the hosting platform (see Retired Components, below).
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

## Retired Components (Railway retirement, 2026-08-21)

Business decision: Railway hosting retired, Cloudflare Workers is the sole production runtime (see `ARCHITECTURE_DECISIONS.md`). Each blocker flagged in the prior "Retirement Readiness" batch was resolved before removal:

- **`railway.json`, `Dockerfile.railway`, `Procfile`** — Railway deployment configuration. Removed.
- **`api/main.py`, `agent/api/api_server.py`** — the two Railway-targeted FastAPI entry points. Removed. `api/main.py`'s `/api/v1/premium/*` routes (added in a prior session for tiered-feed/detection-pack entitlement checks) were re-targeted to `workers/intel-gateway/src/index.js` first, since that Worker is the confirmed-live production gateway and `api/main.py` had no deployment evidence.
- **`sentinel-apex-api/`** — the second, independent Railway-targeted codebase. Removed. Its two "NEEDS VALIDATION" inbound references were confirmed false-positive/inert before removal: the Grafana dashboard match was an unrelated `uid` string containing the same substring; `scripts/build_dist_artifact.py` has it in an explicit `EXCLUDE_ROOT_DIRS` set (excluding a non-existent directory is a no-op).
- **`agent/monetization/premium_storage.py`** — the boto3 R2 client built for `api/main.py`'s premium routes, needing a new `sentinel-apex-premium` bucket and new `CF_R2_PREMIUM_*` credentials. No longer needed: `intel-gateway`'s replacement routes reuse the existing `sentinel-apex-data` bucket (already bound there as `INTEL_R2`) under a private `premium/` prefix, and `scripts/generate_tiered_feeds.py`/`generate_detection_pack.py` now upload via `scripts/r2_upload.py`'s existing AWS-CLI credentials (already set at job level in `sentinel-blogger.yml`) instead.

Hidden-dependency blockers resolved as part of this retirement (not deferred):
- `enterprise-rollback-governance.yml`'s `critical_patterns` list no longer references `agent/api/api_server.py`.
- `scripts/soc2_compliance_engine.py`'s CC6.1/CC6.3/CC6.4/CC6.5/CC7.4 checks now cite `workers/intel-gateway/src/index.js` (and, for CC6.4, `workers/intel-gateway/wrangler.toml`) instead of `api/main.py`/`railway.json` as evidence sources — these controls (JWT auth, RBAC/tier gating, TLS, rate limiting, audit logging) are genuinely implemented there in production; the compliance script was pointing at the wrong (non-deployed) file, not documenting a missing control.
- Live Railway-URL-dependent frontend pages (the open question this retirement was previously blocked on) were found and fixed: `landing/api.js`, `landing/dashboard.html`, and `landing/auth.html` all had hardcoded calls to the dead Railway domain. Repointed to `intel-gateway` (`https://intel.cyberdudebivash.com`), with unreachable-route functions (`onboard`, `fetchTiers`) marked `@deprecated` rather than invented against, and dead "API Docs" links removed (no equivalent route exists on `intel-gateway`). **Separately flagged, not fixed here:** `landing/auth.html`'s login/register forms send `{email, password}`, but the real backend (`POST /api/auth/login`) expects `{api_key}` and mints a JWT from an existing `API_KEYS_KV` record — there is no email/password login on production. This is an architecture mismatch needing a product decision (add backend support, or redesign the page around the API-key-paste pattern `landing/dashboard.html` already uses), not a URL/path fix.
- `api/rbac.py`, `api/enterprise.py`, `api/billing.py`, `api/auth.py`, `scripts/payment_abstraction_layer.py`, and the audit-evidence-only references in `scripts/commercial_readiness_auditor.py` / `scripts/business_readiness_certifier.py` / `scripts/self_improve_actions.py` / `scripts/api_snapshot_server.py` were confirmed to have no callers other than the now-removed `api/main.py`/`api_server.py` (or, for the auditor scripts, to be soft existence/keyword checks that degrade gracefully). **Not removed in this batch** — out of the explicitly agreed scope (railway.json/Dockerfile.railway/Procfile/api/main.py/agent/api/api_server.py/sentinel-apex-api/) — but now provably orphaned dead code; a candidate for a future cleanup pass.

## Duplicated / Unconsolidated Surfaces

**Resolved (Railway retirement, 2026-08-21):** `agent/api/` no longer presents a competing API surface — it was removed alongside the rest of the Railway cluster (see above).

**Correction (EPTP Phase 8 Batch 5):** `api/v1/` and `api/apex_v2/` were previously listed here as unconfirmed/duplicated surfaces. They are not — both contain generated data only (no code), are the report pipeline's local staging output before upload to R2, and are confirmed production. See [`PRODUCTION_RUNTIME.md`](PRODUCTION_RUNTIME.md)'s Report Generation Flow.

## Retirement Readiness (EPTP Phase 8 Batch 6 + Railway retirement, 2026-08-21)

Every component above was checked for hidden dependencies (governance rules, compliance tooling, cascading callers) before any retirement-readiness judgment. Full detail, including specific blockers, is in [`COMPONENT_REGISTRY.json`](COMPONENT_REGISTRY.json)'s `retirement_readiness` field per component.

- **RETIRED (EPTP Phase 9, Batch 1)**: the `publisher.py`/`resilient_publish` cluster, `agent/v60_incident_engine/`, and the root dev `docker-compose.yml`/`docker-compose.prod.yml` pair — all 3 were `READY`, re-verified immediately before removal, and are now gone. See Retired Components, above.
- **RETIRED (Railway retirement, 2026-08-21)**: the full Railway cluster (`agent/api/api_server.py`, `api/main.py`, `sentinel-apex-api/`, `railway.json`/`Dockerfile.railway`/`Procfile`) — see the dedicated Retired Components section above for how each prior blocker was resolved.
- **KEPT, reclassified**: the root `Dockerfile` — NOT part of this retirement despite building the now-removed `agent/api/api_server.py` by default. It is a live dependency of `.github/workflows/sbom-generation.yml`'s dependency-CVE scan (a concern unrelated to Railway hosting). See Legacy Runtime, above.
- **BLOCKED, unchanged**: the customer-installer cluster (`deploy/docker-compose.yml`, `Dockerfile.api`, `agent/v49_intelligence_api/`) — blocked on a business decision (is self-hosted installation still offered), not a technical blocker.
