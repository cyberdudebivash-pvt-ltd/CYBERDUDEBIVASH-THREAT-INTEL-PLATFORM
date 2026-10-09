# P0 R18 — Public Preview Identifier Truth Boundary

## Observed incident (2026-10-09)

Read-only public census of `/api/preview?limit=25`: 25/25 FREE preview records contained `stix_id: "intel--<hex>"`. Those values are internal report/advisory keys, **not** STIX 2.1 `type--UUID` identifiers. Published HTML/report links historically depend on these keys. Blindly replacing them with random UUIDs would break URL references and falsely claim STIX interoperability.

## Additive, backward-compatible response fields

In each FREE preview item:
- `id`: unchanged internal source/report key.
- `stix_id`: **deprecated legacy field** retained unmodified for clients that currently use it to locate reports. It must **not** be treated as a STIX 2.1 ID without an explicit verified claim.
- `internal_advisory_id`: stable internal report identifier. Prefer this (or `id`) for report selection.
- `stix_object_id`: STIX-shaped ID **only if the already-public legacy stix_id value** matches the RFC 4122 STIX 2.1 `type--UUID` shape; otherwise `null`. Never derive it from a separately gated enterprise STIX object field.
- `stix_id_kind`: `STIX_2_1_SYNTAX_ONLY` or `LEGACY_INTERNAL_IDENTIFIER`.
- `stix_object_id_validation`: `SYNTAX_ONLY` or `UNAVAILABLE`.

**Crucial:** Syntactic matching is NOT confirmation that the object exists in a validated STIX bundle, passes schema validation, has sound relationships/lineage, or is commercially deliverable. These fields confer no new FREE entitlement, and paid bundle exports remain subject to the existing permission gate. Never advertise the public preview as "STIX 2.1 verified" based on the identifier shape.

## Customer migration and certification

Consumers should use `internal_advisory_id` for report URLs and `stix_object_id` only as a non-authoritative format hint. For **validated enterprise STIX**, clients must use their entitled export endpoint and independently verify its actual bundle, UUIDs, object types, relationships, provenance and TLP.

Deprecation of legacy `stix_id` requires a versioned API contract, migration notice, SDK update and explicit downstream acceptance; it must not be removed as part of this narrow additive fix.

Regression tests invoke the real Worker public preview route with stubbed R2 and verify: legacy aliases survive, format-only labels are not overclaimed, and premium-only STIX fields do not leak to FREE.

## P0 addendum — preview links for reports withheld by the publication gate

A live read-only check on 2026-10-09 found three public FREE preview `blog_url` links returning 404. The **authoritative** `/api/v1/reports/{id}/publication-status` endpoints classified all three as `BLOCKED` due to P25 trust and (for two) P23 operational readiness. The 404 is therefore a correct fail-closed serving decision, but advertising that URL as an available report is inconsistent and misleading.

The public preview now invokes the exact `evaluatePublicationGate(item)` authority already used by `/reports/**` and exposes only `report_customer_ready` (boolean) and `report_publication_state` (`CUSTOMER_READY` or `BLOCKED`). **When blocked, internal-platform `blog_url` and `report_url` links are nullified**; external vendor/source links are retained. Teaser availability does not mean a published report exists, and no internal scoring or forbidden full-content is added to the public response. Real Worker-route negative controls prove blocked links disappear, approved links remain, and the original FREE IOC masking still works.

This is **NOT** an approval of any blocked report; the correct remediation remains source/evidence correction followed by the real publication gate's approval. Do not lower P23/P25/P26 thresholds or generate fabricated quality signals.
