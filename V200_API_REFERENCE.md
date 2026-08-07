# API Reference — v200

**Project TITAN Stage 22 Phase 8**
**Canonical source**: `workers/intel-gateway/src/index.js`'s own header comment (lines ~34–66,
self-maintained and updated with each route addition) and its runtime 404 handler's
`available_endpoints` array (`index.js:4382-4454`) are the two places route lists are actually kept
current. This document is a structured guide to that live surface, not a second copy of it — per
this repository's own Single Source of Truth principle, exhaustively hand-transcribing all ~150–190
routes here would create exactly the duplicate-source problem `TITAN_V200_RELEASE_AUDIT.md` and
`COMMERCIAL_READINESS.md` flag elsewhere. Verify against `index.js` directly for the current
authoritative list.

## Versioning

Per ADR-0012 (Accepted, `docs/adr/0012-api-versioning-interface-governance.md`): the majority
convention is `/api/v1/p{16..38}/*`, one route per capability. A meaningful minority of routes are
unversioned by design — Admin, Auth, and Payments are explicitly grandfathered in ADR-0012's own
landscape table, not an oversight. No `/api/v2/` exists. Additive changes (new field, new route, new
enum value) are compatible without a version bump; removing/retyping a field, removing a route, or
changing auth behavior requires a `v2` path per ADR-0012's compatibility table — not yet mechanically
enforced (`TITAN_V200_RELEASE_AUDIT.md` §3).

## Authentication

Header `X-API-Key: <key>`, `Authorization: Bearer <jwt-or-key>`, or `?api_key=` query parameter.
No credentials → `FREE` tier (request proceeds, not rejected — the baseline API is intentionally
anonymous-accessible). See `SECURITY_CERTIFICATION.md` §6 for the one exception (TAXII routes
hard-enforce auth) and the one gap (P34 assurance endpoints have none at all, including where they
arguably should).

## Route categories

| Category | Pattern | Example | Auth |
|---|---|---|---|
| Core intel feed | `/api/v1/intel/*` | `/api/v1/intel/latest.json`, `/apex.json` (premium-gated), `/top10.json` | Tier-gated (FREE works, premium paths need PRO+) |
| P-layer capability | `/api/v1/p{16-38}/*` | `/api/v1/p33/dashboard`, `/api/v1/p20/quality-score` | Varies — most unauthenticated (`TITAN_V200_RELEASE_AUDIT.md` §11), P16 control-plane requires a key |
| Reports | `/reports/**`, `/api/reports/*` | `/api/reports/index.json` | Public |
| TAXII 2.1 | `/taxii/*` | `/taxii/collections/{id}/objects/` | **Hard-enforced** — 401 without PRO/ENTERPRISE |
| Auth | `/auth/*` | `/auth/login`, `/auth/logout` | N/A (issues/revokes credentials) |
| Admin | `/api/admin/*` | — | **Hard-enforced** — `X-Admin-Key` + `timingSafeEqual` |
| Payments | `/api/payment/*`, `/api/webhooks/*` | Razorpay/Gumroad checkout + webhooks | Webhook signature verification (HMAC-SHA256, idempotency-guarded) |
| Search/correlation/NLQ | `/api/search`, `/api/intel/correlate`, `/api/nlq` | — | Tier-gated |
| "God Mode" domains | `/api/{brand,vendor-risk,geopolitical,incidents,copilot}/*` | — | Tier-gated |
| Enterprise integrations | `/api/{misp,sigma,yara,siem,stream,mssp}` | — | Tier-gated, ENTERPRISE/MSSP-scoped |
| Health | `/api/health` | — | Public |

## Rate limits and quotas

Per-tier, KV-backed sliding window (`SECURITY_CERTIFICATION.md` §9, `COMMERCIAL_READINESS.md` §3).
Exact per-tier numbers are defined once, canonically, in `config/subscription_tiers.json` (e.g. FREE:
100 calls/day, 20/hour) — refer there rather than to any other inline table, per the Single Source
of Truth finding in `COMMERCIAL_READINESS.md` §1.

## Response envelope

Standard JSON responses carry `SECURITY_HEADERS` (HSTS, X-Content-Type-Options, X-Frame-Options,
Referrer-Policy, Permissions-Policy — `SECURITY_CERTIFICATION.md` §4) and
`Access-Control-Allow-Origin: "*"` (§5 of the same document — a known, flagged gap, not a
documented feature to rely on for origin-restricted integrations). CSP is present only on the 3 HTML
report response sites, not on JSON responses.

## Known API-surface gaps (full detail in the referenced certification documents)

- 12 `/api/v1/p34/*` endpoints are unauthenticated where their own governing ADR says they should be
  internal-only (`SECURITY_CERTIFICATION.md` §6).
- No request-level tracing/correlation ID is returned in any response
  (`OPERATIONAL_READINESS.md` §2) — integrators building retry/debugging tooling against this API
  cannot correlate a client-side request to a server-side log entry today.
- CORS is unrestricted (`SECURITY_CERTIFICATION.md` §5) — fine for public GETs, worth confirming
  before building any credentialed cross-origin integration.
