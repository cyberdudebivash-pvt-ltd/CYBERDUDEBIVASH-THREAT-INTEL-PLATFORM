# Customer Documentation — v200

**Project TITAN Stage 22 Phase 8**

## Getting started

1. **Free tier**: no signup required for basic access — 100 API calls/day, 10 threat
   advisories/day, TLP:CLEAR feed, no API key needed (anonymous requests resolve to FREE tier
   automatically). See `V200_API_REFERENCE.md` for endpoints.
2. **Paid tiers (PRO/ENTERPRISE/MSSP)**: upgrade via `upgrade.html` (Razorpay or Gumroad
   checkout — both live and functional, `COMMERCIAL_READINESS.md` §7). A confirmation email/webhook
   provisions your API key automatically.
3. **Dashboard**: `dashboard/enterprise_dashboard.html`, linked from the site homepage, is the
   current customer dashboard (`UI_FREEZE_POLICY.md`). It is live-data-driven, not static.

## What each tier includes

Canonical, current tier definitions live in `config/subscription_tiers.json` and are served live at
`/api/subscription/tiers` — this is intentionally the *only* place this guide points you for exact
feature/limit numbers, since a second hand-copied table here would itself become a source of drift
(exactly the problem `COMMERCIAL_READINESS.md` §1 found in one of the platform's own internal
files). At a glance: FREE is read-only/community-support; PRO adds STIX export, visible IOCs, dark
web monitoring, and CSV export; ENTERPRISE and MSSP add SIEM/SOAR integration, white-labeling, and
multi-tenant/partner features.

## Premium Intelligence

Two specific endpoints (`/api/v1/intel/apex.json`, `/api/v1/intel/ai_summary.json`) are Premium
Intelligence, requiring a tier above FREE — this is real, enforced gating
(`COMMERCIAL_READINESS.md` §2), not a marketing label without a mechanism behind it.

## Data quality — what you can rely on today, and what to treat as directional

Per `COMMERCIAL_QUALITY_CERTIFICATION_REPORT.md`, being transparent about current quality tiers
rather than implying uniform confidence across every field:

- **MITRE ATT&CK mapping and STIX bundles**: `Commercial Certified` — 96.9% coverage, independently
  validated, safe to build automation against.
- **IOC data**: `Enterprise Ready` — 80.5% of advisories carry extracted, typed indicators.
- **Threat actor attribution**: `Analyst Review` — every advisory carries a tag, but roughly 4 in
  10 are generic category buckets ("generic CVE," "generic ransomware") rather than a specific
  named actor. Treat attribution as a starting point for analyst judgment, not a definitive claim.
- **Confidence scores**: currently `Internal Draft` internally (the platform's own quality gate
  flags every item's confidence value as out-of-range pending an unresolved architecture decision,
  `COMMERCIAL_QUALITY_CERTIFICATION_REPORT.md` §3.4) — the number is present on every item but
  should not yet be treated as a precisely calibrated probability.

## Support

FREE tier: community support (no SLA). Paid tiers: SLA minutes defined per-tier in
`config/subscription_tiers.json`. Enterprise support/escalation contacts: see `contact-enterprise.html`
(linked from the site homepage).

## Known limitations to plan around

- The API is versioned inconsistently (most routes `/api/v1/*`, Admin/Auth/Payments unversioned by
  design — `V200_API_REFERENCE.md`). If you're integrating against unversioned routes, expect them
  to be more likely to change without a version bump than the `/api/v1/*` majority.
- No request-tracing ID is returned — if you need to correlate a specific request with support,
  capture your own request timestamp, IP, and full request payload when filing a ticket.
