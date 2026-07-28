# Production Runtime Architecture

**Last updated:** 2026-07-28 · Authoritative source for this document: direct code and configuration review conducted across the EPTP transformation program. Where this document and older, unreviewed documentation disagree, this document takes precedence.

## Runtime Architecture

Cloudflare Workers is the platform's canonical production runtime. Three Workers are deployed:

| Worker | Path | Responsibility |
|---|---|---|
| `intel-gateway` | `workers/intel-gateway/` | Public API gateway, credential resolution, admin key management, report serving |
| `revenue-engine` | `workers/revenue-engine/` | Billing/subscription webhook handling, customer provisioning |
| `intel-retention-engine` | `workers/intel-retention-engine/` | Data retention and lifecycle management |

Each Worker has its own `wrangler.toml` defining its bindings; there is no shared runtime configuration file across the three.

## Cloudflare Architecture

- **KV** — 6 namespaces in active use: `API_KEYS_KV`, `RATE_LIMIT_KV`, `ANALYTICS_KV`, `SECURITY_HUB_KV` (bound in `intel-gateway`, and `API_KEYS_KV` also bound in `revenue-engine` so both Workers write and read the same credential store), plus `REVENUE_CRM_KV` and `EMAIL_QUEUE_KV` (bound only in `revenue-engine`).
- **R2** — two buckets: `sentinel-apex-data` (bound as `INTEL_R2`) and `sentinel-apex-reports` (bound as `REPORTS_R2`), serving generated intelligence data and rendered reports respectively.
- **D1** — one database, `sentinel-crm`, used by `revenue-engine` for CRM-style records.

## Worker Responsibilities

`intel-gateway` is the single entry point for all customer-facing API traffic. It is the only Worker that resolves a caller's identity and tier before serving a request. `revenue-engine` and `intel-retention-engine` do not independently authenticate API traffic in the same sense — `revenue-engine` writes into the same `API_KEYS_KV` store that `intel-gateway` reads from, so a customer provisioned via a payment webhook is immediately recognized by the gateway without any separate sync step.

## Storage Architecture

`API_KEYS_KV` is the platform's sole runtime credential authority. Every credential-issuing code path — the admin endpoint (`POST /api/admin/keys` in `intel-gateway`) and the payment-triggered provisioning path (`revenue-engine`) — writes a record keyed by the raw API key string itself, matching exactly how the gateway looks it up. This consistency is deliberate and should be preserved by any future change to either Worker.

## Deployment Flow

```
push to main (or workflow_dispatch)
        |
        v
.github/workflows/deploy-worker.yml
        |
        v
wrangler deploy  ->  workers/intel-gateway  ->  Cloudflare edge
```

`revenue-engine` and `intel-retention-engine` are deployed independently (each has its own `wrangler.toml`); this repository's automated CI currently drives `deploy-worker.yml` for `intel-gateway` specifically.

## Authentication Flow

1. A request arrives with a credential in `X-API-Key`, `Authorization: Bearer`, or the `api_key` query parameter.
2. If the credential is JWT-shaped (two dots), it is verified against `CDB_JWT_SECRET` and checked against a revocation list in `SECURITY_HUB_KV`.
3. Otherwise, the raw value is looked up directly in `API_KEYS_KV`; a match yields the caller's tier and customer ID, subject to an `expires_at` check.
4. `POST /auth/login` is the only path that mints a JWT — it requires a valid `API_KEYS_KV` record first, so JWTs are always a short-lived derivative of the underlying key record, never an independent credential.
5. Both the JWT path and the direct-key path share the same brute-force lockout tracking, keyed by client IP.

## Report Generation Flow

```
.github/workflows/sentinel-blogger.yml  (job: generate-and-sync)
        |  multi-stage enrichment (CVSS/EPSS/KEV/MITRE, STIX)
        v
HTML + PDF report rendering
        |
        v
scripts/r2_upload.py  -->  sentinel-apex-data / sentinel-apex-reports (R2)
        |
        v
intel-gateway serves /reports/* and /api/v1/intel/* from R2
```

Despite its filename, `sentinel-blogger.yml` and its underlying `agent/sentinel_blogger.py` do not publish to any external blogging platform — that capability was removed from this pipeline in an earlier version, and the pipeline has been R2-native since. The name is retained; the function is the platform's core report pipeline.
