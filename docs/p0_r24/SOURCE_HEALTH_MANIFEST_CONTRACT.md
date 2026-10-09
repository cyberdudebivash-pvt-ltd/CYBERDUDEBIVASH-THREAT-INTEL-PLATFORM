# P0 R24 — Source-Fabric Observation Contract Repair

## Verified P0 production incident
Sentinel Blogger #2538 and its previous failures ended with APEX Stage 3.1 loading 0 public items, T04 failing, public freshness 503, and source-fabric gate G10 reporting zero HEALTHY sources. Other source evidence in the same job showed records entering the pipeline. Current `scripts/source_fabric_health.py` reads `data/stix/feed_manifest.json` but **silently changes a non-list JSON object to `[]`**, while Stage 3.9 and the report generator explicitly support canonical `{"advisories":[...]}`, `{"reports":[...]}`, and `{"items":[...]}` envelopes. When the manifest is object-wrapped, registered-source telemetry disappears from G10.

## Change
- `_manifest_rows()` recognizes the established canonical list and supported object envelopes, extracts **only existing advisory dicts** and never invents source rows, timestamps or freshness.
- `compute_health` now uses the normalized canonical rows for registered source accounting; the existing real `last_seen`, age rules, status restrictions and G10 hard-fail gate are left intact.
- Offline required CI includes positive tests for each envelope and source-health accounting, and negative tests for stale, unmatched, missing and malformed records.

## Safeguards and release HOLD
This is a telemetry correction, **not** proof that any of the 104 integrations is now delivering data. A source becomes HEALTHY only if a real registered manifest entry contains an acceptable actual event timestamp within its preexisting freshness limit. Do not use this PR to bypass source provenance, empty `api/feed.json`, TLP classification, historical #721/#725 dossiers or commercial revocation #596. Await exact-head CI, next successful pipeline with genuine published artifacts, and independent live Worker SHA parity before Enterprise GO. No R2/Cloudflare writes or deployment in this PR.