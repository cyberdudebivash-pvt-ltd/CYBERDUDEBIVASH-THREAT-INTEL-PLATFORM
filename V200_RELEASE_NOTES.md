# Release Notes — v200 (Commercial Release Certification)

**Status: Release Candidate documentation — not yet tagged.** Current live version remains
`184.0` (internal) / `v185` (label) per `config/version.json`. This document describes what a
v200.0.0 release represents and what changes as part of it; the version bump itself is a deploy-time
decision gated by `V200_RELEASE_GATE.md` and `V200_EXECUTIVE_RELEASE_REPORT.md`.

## What v200 is

Not a new-features release. Project TITAN Stage 22 is a certification milestone: the platform's
existing capabilities (built across Stages 1–21) were audited, measured, and certified against
explicit commercial-release criteria, rather than expanded. See `TITAN_V200_RELEASE_AUDIT.md` for
the full audit and `V200_EXECUTIVE_RELEASE_REPORT.md` for the GA recommendation.

## What's new for customers

Nothing functionally — this is a readiness milestone, not a feature release. What changes is
**certainty**: every capability documented in `COMMERCIAL_SERVICE_CATALOG.md` (Stage 21) and
`COMMERCIAL_QUALITY_CERTIFICATION_REPORT.md` (Stage 22) now carries an explicit, evidence-based
quality tier rather than an implicit assumption of readiness.

## What's new for operators/administrators

- A real, current SBOM (`data/sbom/`).
- An explicit UI freeze policy (`UI_FREEZE_POLICY.md`) — the dashboard's navigation and layout are
  now a committed contract, not something that can drift release-to-release without an ADR.
- A named, prioritized list of pre-GA remediation items (`V200_RELEASE_GATE.md`), several of which
  are small, concrete fixes (one duplicate pricing table, one disabled feature flag, one broken
  link) rather than large engineering efforts.

## Certified quality levels (summary — full detail in `COMMERCIAL_QUALITY_CERTIFICATION_REPORT.md`)

MITRE mapping and STIX generation are `Commercial Certified`. IOC completeness, source-level
provenance, and executive summaries are `Enterprise Ready`. Attribution quality is `Analyst Review`.
Evidence-chain quality, confidence calculation, explainability, and remediation guidance are
`Internal Draft` — real engineering exists behind each, but none is yet safe to market as an
unqualified commercial claim.

## Known issues carried into this release candidate

See `V200_EXECUTIVE_RELEASE_REPORT.md` §"Known Limitations" for the complete, prioritized list.
Headline items: a disaster-recovery document that overstates actual deployed infrastructure, a
CORS wildcard policy, 12 unauthenticated internal-assurance API endpoints, and 219 known dependency
vulnerabilities (4 critical) repository-wide.

## Versioning note

This repository's live version tracking (`config/version.json`, currently `184.0`/`v185`) and this
certification's "v200" designation are **currently different numbers, intentionally not reconciled
by this document.** Reconciling them (i.e., actually cutting a `v200.0.0` tag) is a deploy-time
action downstream of the GA decision in `V200_EXECUTIVE_RELEASE_REPORT.md` — not performed as part
of writing release documentation.
