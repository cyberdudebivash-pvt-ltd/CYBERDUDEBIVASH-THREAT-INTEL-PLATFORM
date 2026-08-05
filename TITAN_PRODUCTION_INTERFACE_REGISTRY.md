# Project TITAN Stage 8 — Production Interface Registry (Phase 4)

**Status:** Verified registry. This supersedes `TITAN_INTERFACE_REGISTRY.md` (Stage 7) for
every row where this stage obtained live HTTP evidence — those rows are upgraded from
"documented/inferred" to "verified." Rows not independently re-tested this stage retain their
Stage 7 status and are marked accordingly. Columns per Stage 8's Phase 4 spec.

Full per-route-family ownership already lives in `TITAN_INTERFACE_OWNERSHIP.md` (Stage 7) —
not repeated here in full; this table adds the verification-specific columns (Runtime,
Monitoring, Logging, Health Check, Rate Limiting) Stage 7's registry didn't carry.

---

## Verified this stage (live HTTP evidence)

| Path | Method | Owner | Repo | Runtime | AuthN | AuthZ | Consumer | Doc'd | Version | Status | Monitoring | Logging | Health Check | Rate Limit | Deprecation | Canonical Owner |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `/api/health` | GET | Platform SRE | intel-platform | CF Worker | None | None | Public/monitoring | Yes (own route name) | v1 | **Production, verified 200** | Implied by route's own existence | Unknown (not inspected) | **Is itself the health check** | Unknown | None | Platform SRE |
| `/api/v1/p25/trust-score` | GET | Intelligence Eng | intel-platform | CF Worker | None visible (public) | Item-scoped 404 if absent | P26–P38 internal + external | Partial (P-layer table only) | P25.0 | **Production, verified** (custom JSON, not platform 404) | Unknown | Unknown | No dedicated health route; `/api/health` covers Worker liveness | `RATE_LIMITS` tiers (`revenue-enforcement.js`) | None | Intelligence Eng — **canonical per ADR-0007** |
| `/api/v1/p38/observability` | GET | Intelligence Eng | intel-platform | CF Worker | None visible | None visible | Internal/external monitoring | Partial | P38.0 | **Production, verified 200** | Self (this *is* an observability endpoint, per Principle 7) | Unknown | N/A (is an observability endpoint) | Unknown | None | Intelligence Eng |
| `/api/v1/p31/graph` | GET | Intelligence Eng | intel-platform | CF Worker | Tier-based | **402 without payment/tier** | Paid-tier customers | Partial | P31 | **Production, verified 402** | Unknown | Unknown | Via `/api/health` | Tiered (`RATE_LIMITS`) | None | Intelligence Eng — **R1, target-canonical per ADR-0010** |
| `/api/v1/intel/graph` | GET | Intelligence Eng | intel-platform | CF Worker | Tier-based | **403 without tier** | Paid-tier customers | Partial | Unversioned | **Production, verified 403** | Unknown | Unknown | Via `/api/health` | Tiered | None | Intelligence Eng — **R3, competes with R1, see DEBT-000B** |
| `/api/v1/intel/relations` | GET | Intelligence Eng | intel-platform | CF Worker | Tier-based | 403 without tier | Paid-tier customers | Partial | Unversioned | **Production, verified 403** | Unknown | Unknown | Via `/api/health` | Tiered | None | Intelligence Eng |
| `/taxii/` | GET | Intelligence Eng | intel-platform | CF Worker | None | Public | TAXII/STIX partners | Yes (header comment) | TAXII 2.1 | **Production, verified 200** | Unknown | Unknown | Via `/api/health` | Unknown | None | Intelligence Eng — canonical pending DEBT-014 |
| `/api/taxii/` | GET | Intelligence Eng | intel-platform | CF Worker | Tier-based | **403 without tier** | TAXII/STIX partners (paid?) | No | Unversioned | **Production, verified 403** | Unknown | Unknown | Via `/api/health` | Tiered | None | Intelligence Eng — see DEBT-014, may be a legitimate paid-tier variant, not a duplicate |
| `/api/og` | GET | Blog/Vercel Eng | blog | Vercel serverless | None | Public | Social-preview crawlers | No | Unversioned | **Production, verified 200** | Unknown | Unknown | None dedicated | Unknown | None | Blog/Vercel Eng |
| `/api/v1/intel` | GET (`?action=`) | Blog/Vercel Eng | blog | Vercel serverless | Required | **401 without auth** | Blog frontend, external | Partial (rewrites documented in `vercel.json`) | v1 (blog namespace) | **Production, verified 401** | Unknown | Unknown | None dedicated | Unknown | None | Blog/Vercel Eng |
| `/api/v1/auth` | GET (`?action=`) | Blog/Vercel Eng | blog | Vercel serverless | Required | **401 without auth** | Blog frontend | Partial | v1 | **Production, verified 401** | Unknown | Unknown | None dedicated | Unknown | None | Blog/Vercel Eng |
| `/api/v1/newsletter` | POST | Blog/Vercel Eng | blog | Vercel serverless | None | Public (method-gated: 405 on GET) | Blog frontend, public signup | **No — newly documented this stage** | Unversioned | **Production, verified 405→200** | None found | None found | None | Unknown | None | **Blog/Vercel Eng — needs a named owner, currently none** |
| `/api/v1/intelligence/confidence` | GET | — | blog | Vercel serverless (file exists, **not deployed**) | N/A | N/A | **None — unreachable** | Yes, in its own header (never realized in production) | v1 (designed) | **Unreachable, verified** (Vercel `NOT_FOUND`) | N/A | N/A | N/A | N/A | N/A | **None — see DEBT-000/AR-000** |
| (20 more `api/v1/{intelligence,workbench,analysis,customer,products,quality,reports,detections,ioc}/*` routes) | Various | — | blog | Vercel serverless (files exist, **not deployed**) | N/A | N/A | None — unreachable | Partial (inline only) | Various (designed) | **Unreachable, verified** | N/A | N/A | N/A | N/A | N/A | None — see DEBT-000/AR-000 |

## Not independently re-verified this stage (status carried over from Stage 7)

All P16–P24, P26–P30, P32–P38 routes not listed above; `enterprise-endpoints.js`'s MISP/Sigma/
YARA/scoring/SIEM routes beyond the TAXII spot-check; blog's billing/admin routes beyond the
401 spot-check; the archived `lib/api/*` (ADR-0013, confirmed dormant by absence of any HTTP
surface at all — TypeScript source, never built/deployed). See `TITAN_INTERFACE_REGISTRY.md`
and `TITAN_INTERFACE_OWNERSHIP.md` (Stage 7) for these — not restated here to avoid the two
documents drifting apart through partial duplication.

## Systemic gaps found across every row tested (monitoring/logging/health-check columns)

Worth naming directly rather than leaving as blank cells: **no route tested this stage,
including canonical, heavily-consumed ones like P25's trust-score, has a discoverable,
documented monitoring or structured-logging story.** `/api/health` and the per-P-layer
`/observability` endpoints exist and could serve as monitoring *targets*, but whether anything
actually polls them, alerts on them, or logs their invocations was not found in-repo. This is
a real gap relative to Stage 8's own "Engineering Requirements" (`Observable`, `Auditable`) —
logged as a new tech-debt item below rather than left implicit.
