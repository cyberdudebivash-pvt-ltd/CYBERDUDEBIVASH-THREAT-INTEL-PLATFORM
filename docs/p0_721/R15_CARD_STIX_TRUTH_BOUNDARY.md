# R15 — Customer card identity and STIX claim boundary

## Evidence and severity

Observed on current main `36a08fad`: `js/card_renderer.js::renderTrustFooter()` emitted a green `STIX 2.1 Verified Bundle` trust badge for **every** advisory card, without consulting a validated STIX export. The public `/api/preview?limit=5` response displayed `stix_id: intel--<24-hex>`, which is the platform's legacy **internal advisory identifier**, not a STIX 2.1 `object-type--UUID` identifier.

**Impact:** A customer can reasonably mistake a per-card visual assertion for verified export compliance. An internal advisory ID, a paid STIX access CTA, a download URL, or a successful API response is **not** proof of valid STIX object IDs, relationships or complete exported content.

## Fixed in source (PR #736)

- In the original trust-badge location, show **INTEL ADVISORY** rather than an unconditional `✓ STIX 2.1` claim.
- The copy tooltip identifies the existing key as an **Advisory reference**, without changing its bytes, DOM attributes, click-to-copy function, or backend identity.
- Preserve the CSS class, report action, MITRE badge, paid STIX unlock and actual download-link branches.
- Four source contract tests protect these invariants.

## Not fixed; mandatory separate certification

1. Canonical STIX 2.1 export uses `type--UUID` identifiers, with valid `spec_version`, timestamps, relationships and markings, validated with an independently pinned schema/checker.
2. Source-to-STIX references and STIX-to-report lookups preserve provenance and tenant/TLP authorization; internal `intel--` keys cannot be passed as STIX IDs.
3. Paid download paths prove that the exact bytes served are the exact bytes whose export checks passed; a 200 or link alone is not enough.
4. No unsupported attribution, inferred IOC, or unverifiable actor activity is inserted in exported objects.
5. Automated negative controls: invalid IDs, malformed bundles, broken references, restricted TLP, unentitled access, missing bundle, stale cache and cross-tenant requests.
6. Sample actual customer-facing bundle downloads after operator-approved deployment and compare R2-origin, Worker and edge delivery.

## Release decision

Status of PR #736: **FIXED IN SOURCE**. This is a claim-integrity correction, **not** STIX 2.1 exporter certification, merge approval, deployment authorization or a production GO verdict.

Keep #721 open until the original dossier fixtures and real export validation complete. Never populate a false badge simply to preserve visual density.
