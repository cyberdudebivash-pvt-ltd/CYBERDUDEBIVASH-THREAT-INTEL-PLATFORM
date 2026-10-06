# ADR-0012: API Versioning & Interface Governance

**Date:** 2026-08-05
**Status:** **Accepted** — 2026-08-06, by executive architecture authority (see "Approval"
section below and `TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md`).
**Deciders (proposed reviewers):** Platform Governance Lead, Chief Threat Intelligence
Architect, Principal API Gateway Architect, Blog/Vercel Engineering
**Program:** Project TITAN, Stage 7
**Fills the gap named in:** `TITAN_IMPLEMENTATION_READINESS.md` (Stage 6), which found that
Stage 5's original six required ADRs included "API versioning" and that none of Stage 6's five
ADRs (0007–0011) covered it — this is that sixth, originally-missing ADR.
**Depends on:** ADR-0008 (Canonical Evidence Framework) for anything touching Evidence API
shape specifically; otherwise independent.

---

## Context

The CYBERDUDEBIVASH® ecosystem exposes APIs from at least three independently-versioned
surfaces, discovered across Stage 6 and this stage:

1. **intel-platform's Cloudflare Worker** (`workers/intel-gateway/src/index.js`) — ~150+
   routes under `/api/v1/*`, spanning P16–P38, TAXII 2.1, admin, auth, and payments.
2. **Blog's Vercel deployment** (`api/v1/*.js`, 4 query-parameter-routed functions plus 2
   webhooks) — a **separate** `/api/v1/*` namespace, different domain, different schema,
   different owner, coincidentally sharing the string "v1."
3. **Blog's static immutable bundle generator** (`scripts/generate_api_manifests.py`) —
   versioned, checksummed JSON files served as static assets (`api/v1/intel/manifest.json`
   etc.), a third delivery pattern that is neither a dynamic REST endpoint nor a webhook.

None of these three surfaces currently has a documented, cross-surface versioning policy. Each
has grown its own ad hoc convention. `lib/api/*` (the archived-per-ADR-0013 TypeScript RC1
tree) is the only place in either repository that ever wrote down a *formal* versioning policy
(a stability classification — IMMUTABLE/STABLE/FROZEN/EXPERIMENTAL/DEPRECATED — and a breaking-
change process table) — but that tree has zero production consumers, so its policy has never
been tested against a real breaking change.

---

## Problem

**How does a version get assigned to an API response shape, what does "v1" actually promise,
what counts as a breaking vs. non-breaking change, and how does a deprecated interface get
retired without silently breaking a consumer?** Right now, the answer is different depending
on which of the three surfaces above you ask, and two of the three ("intel-platform /api/v1",
"blog /api/v1") use the identical version label for unrelated systems — a naming collision
that is not a technical conflict (different domains) but is a real governance and documentation
hazard: any future cross-repo reference to "the v1 API" is ambiguous without also naming which
repository.

---

## Current API Landscape

| Surface | Repository | Protocol | Route count (approx.) | Version label | Deployment |
|---|---|---|---|---|---|
| P-layer Worker API | intel-platform | REST (JSON) | 150+ (`/api/v1/p16`–`/api/v1/p38/*`, plus core routes) | `/api/v1/` prefix, no `v2` anywhere | Cloudflare Workers |
| TAXII 2.1 server | intel-platform | TAXII 2.1 (STIX 2.1 payloads) | 3 (`/taxii/`, `/taxii/collections/`, `/taxii/collections/{id}/objects/`) | TAXII spec version pinned (2.1), not this platform's own versioning | Same Worker |
| Admin API | intel-platform | REST, `ADMIN_SECRET`-gated | 4 (`/api/admin/*`) | Same `/api/v1`-adjacent, actually unprefixed `/api/admin/*` | Same Worker |
| Auth | intel-platform | REST, JWT HS256 | 2 (`/auth/login`, `/auth/logout`) | Unprefixed | Same Worker |
| Payments | intel-platform | REST, webhook | Razorpay + Gumroad webhook handlers | Unprefixed | Same Worker |
| Blog Vercel API | blog | REST, query-parameter-routed (`?action=`) | 4 real functions covering ~25 logical operations via rewrites | `/api/v1/` prefix — **different namespace than intel-platform's**, same label | Vercel serverless |
| Blog static bundles | blog | Static JSON, versioned + checksummed | `api/v1/intel/{latest,top10,apex,manifest}.json` + others | Own `manifest.json` registry with checksums/timestamps, no semantic version number | Static (R2-adjacent per Worker serving) |
| `lib/api/*` (archived, ADR-0013) | blog | REST (designed, undeployed) | 2 files, 11 documented endpoints | Explicit IMMUTABLE/STABLE/FROZEN scheme, `version: 'v1'` in every response envelope | Not deployed |

---

## Existing Interfaces

See `TITAN_INTERFACE_REGISTRY.md` (Task 3, this stage) for the complete row-per-surface
inventory. Summary counts by owner: intel-platform owns the large majority of active, customer-
facing routes (P16–P38, TAXII, admin, payments); blog owns a much smaller, but real and
customer-facing (billing, auth), Vercel-deployed surface; the archived `lib/api/*` contributes
zero live routes.

---

## Versioning Strategy

**Decision: adopt path-prefix major versioning (`/api/v1/`, `/api/v2/` when needed) as the
ecosystem-wide convention, formalizing what intel-platform already does de facto, and layer a
field-level `version_introduced` convention (already proven at P38's `SCHEMA_REGISTRY`) on top
for additive changes that don't warrant a new path version.**

This is Reuse Before Build applied at the policy level: intel-platform already uses `/api/v1/`
consistently across 150+ routes; P38 already tracks `version_introduced` per schema field.
Rather than inventing a new scheme, this ADR names the existing, already-dominant pattern as
canonical and asks the smaller surfaces (blog's Vercel API, any future API) to conform.

- **Path version (`/v1/`, `/v2/`)**: bumped only for breaking changes to a route's request or
  response contract. No route in this platform has ever needed a `/v2/` yet — this ADR does not
  create one, it defines when one would be warranted.
- **Field version (`version_introduced`)**: for additive, backward-compatible field changes
  within a `v1` contract, per P38's existing convention. Recommended for adoption ecosystem-wide,
  not just P38's `SCHEMA_REGISTRY`.

---

## Compatibility Rules

Adapted from `lib/api/*`'s already-designed (but never-tested-in-production) breaking-change
table, since it is the only existing artifact in either repository that already thought this
through carefully — reused per Reuse Before Build rather than redesigned:

| Change type | Compatible? | Action |
|---|---|---|
| Add a new field to a response | Yes | Document in release notes; `version_introduced` tag recommended |
| Add a new optional request parameter | Yes | Document in release notes |
| Add a new route | Yes | No version bump; add to the interface registry |
| Add a new enum value | Yes (minor) | Document; existing consumers that switch/exhaustively-match may need a default case — call this out explicitly in release notes |
| Remove a field | **No** | Requires `v2` path or a documented, time-boxed deprecation window on the existing field first |
| Change a field's type or meaning | **No** | Requires `v2` path |
| Remove a route | **No** | Deprecation Instead of Deletion protocol first (both repos' CLAUDE.md), then `v2`-only removal |
| Reorder an enum's underlying values (where consumers may compare numerically) | **No** | Requires `v2` path |
| Change auth/authorization behavior on an existing route | **No**, per both repos' "ZERO auth changes" constraint | Out of scope for a version bump — requires its own explicit, separately-authorized change |

---

## Deprecation Policy

Follows both repositories' existing Deprecation Instead of Deletion policy exactly — this ADR
does not create a new policy, it applies the existing one specifically to API routes and fields:

1. Mark deprecated in code comment and in the interface registry's Status column.
2. Document the replacement route/field.
3. Keep the deprecated interface functioning through the migration window.
4. Set an explicit removal milestone (tied to a future Stage, not a calendar date, consistent
   with how this program already sequences work).
5. Remove only after confirmed zero remaining callers — for public/external routes, "confirmed"
   means a documented monitoring period showing zero traffic, not just an assumption.

---

## Migration Rules

For any future `v2` (none exists yet, none is created by this ADR):

- `v1` and `v2` run concurrently for a documented window — no flag-day cutover.
- `v1` responses are not modified when `v2` ships; consumers who never migrate keep working
  indefinitely until `v1` is explicitly, separately deprecated per the policy above.
- New capability is added to `v1` where backward-compatible (per Compatibility Rules); only
  genuinely breaking changes justify starting a `v2` namespace at all.

---

## Semantic Versioning Strategy

**API path versions are not semver** (they're a coarse major-version-only signal, `v1`/`v2`,
matching what's already in use). **Field-level and schema versioning uses semver-adjacent
`version_introduced` tags** (already P38's pattern: a string tag per field, not a full x.y.z
number) — recommended over full semver for API responses because none of the three surfaces
currently version at finer granularity than "this field exists as of roughly this point," and
introducing full semver without an existing practice to build on would be new process weight
without demonstrated need. **Internal packages/scripts** (e.g., a future shared validation
library) should use conventional semver (`package.json` `version` field) if and when such a
package is created — not applicable to any existing artifact today.

---

## REST

The default and near-universal protocol across both repositories. No formal OpenAPI/Swagger
specification exists for either surface today — flagged as a gap in Contract Governance
(`TITAN_CONTRACT_GOVERNANCE.md`), not solved by this ADR.

## GraphQL

**Not applicable.** Confirmed by direct search: no GraphQL server, schema, or dependency exists
anywhere in either repository. The one text match for "graphql" in the entire codebase
(`p27-handlers.js:189,193`) is a string literal inside a list of attack-surface *keywords* that
P27's exposure-analysis feature checks a *third party's* public surface for — unrelated to this
platform exposing GraphQL itself. If GraphQL is ever introduced, it should get its own ADR
before implementation, per this program's standing rule that new architectural paradigms
require a decision record, not silent introduction.

## Internal APIs

Admin API (`/api/admin/*`, `ADMIN_SECRET`-gated) and the P34 "Engineering assurance API
surface" are the clearest internal-only surfaces. Recommended taxonomy placement: see
`TITAN_API_TAXONOMY.md`'s "Administration APIs" category.

## External APIs

The large majority of `/api/v1/p*` routes, TAXII endpoints, and blog's billing/auth endpoints
are customer- or partner-facing. Rate-limited by tier (`RATE_LIMITS = { FREE: 30, PRO: 120,
ENTERPRISE: 600, MSSP: 1200 }`, `req/15min`) — an existing, real commercial-tier enforcement
mechanism this ADR does not modify.

## STIX

STIX 2.1 is a first-class, already-implemented content type (`application/stix+json;
version=2.1`), served through the TAXII 2.1 endpoints and referenced by `reports/pdf/`-adjacent
STIX bundle generation (`STIX bundle files >= feed item count` is an active P33 certification
gate, G18-adjacent). STIX's own versioning (2.1) is externally governed by OASIS, not this
platform — this ADR's versioning policy applies to the *transport* (the TAXII collection
routes), not the STIX object schema itself.

## Future APIs

Any future Evidence API (blocked per `TITAN_IMPLEMENTATION_READINESS.md` pending ADR-0008's
approval and its schema shipping) must launch as `/api/v1/evidence/*` under intel-platform's
existing namespace — consistent with Stage 2's system-of-record precedent (already applied to
Registry responsibilities in ADR-0008) and this ADR's path-versioning convention. It does not
get its own version scheme.

---

## Rollback Strategy

This ADR is policy-only — it creates no new code, route, or schema. "Rollback" means reverting
to the prior state of *no formal cross-surface policy*, which requires no technical action,
only a decision to stop citing this ADR. Any future `v2` namespace created under this policy
would carry its own rollback plan at that time (per the Migration Rules' concurrent-operation
requirement, `v1` is never removed as part of introducing `v2`, so there is always a rollback
path by construction).

---

## Future Expansion

- A formal OpenAPI specification for intel-platform's `/api/v1/*` surface is the highest-value
  next step this ADR identifies but does not execute — recommended as a Stage 8+ candidate in
  `TITAN_STAGE8_PLAN.md`.
- The "v1"-label collision between intel-platform and blog is not resolved by renaming either
  (a breaking change to both, unjustified by the problem, which is documentation clarity, not
  a technical conflict) — resolved instead by always qualifying references as "intel-platform's
  v1 API" vs. "blog's v1 API" in documentation going forward, starting with the interface
  registry this stage produces.
- If blog's Vercel API grows enough to need its own path-versioning event, it should follow
  this same ADR's rules rather than inventing a second policy.

---

## Approval

**Accepted, 2026-08-06.** Decided by executive architecture authority (cyberdudebivash,
Project TITAN executive/repository owner) via direct confirmation, recorded in
`TITAN_ARCHITECTURE_ACCEPTANCE_RECORD.md`. This is an executive-authority acceptance, not a
completed multi-party review — the individually-named sign-offs below, including the
cross-repository Blog/Vercel one this ADR's own text flagged as the least formality-like of the
three, were not independently obtained and remain unchecked; recorded accurately rather than
implied. If Blog/Vercel Engineering later finds the policy unworkable against their existing
`api/v1/*` surface, reopen per this ADR's own Revision pattern.

- [ ] Platform Governance Lead (not independently obtained — see note above)
- [ ] Chief Threat Intelligence Architect / API Gateway Architect (intel-platform surface) (not independently obtained)
- [ ] Blog/Vercel engineering owner (blog surface, and acknowledgment of the "v1" label
      collision documentation approach) (not independently obtained)

No code implementing this decision exists yet.
