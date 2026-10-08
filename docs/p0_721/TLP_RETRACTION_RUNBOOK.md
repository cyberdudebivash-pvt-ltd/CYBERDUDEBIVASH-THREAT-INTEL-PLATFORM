# TLP retraction runbook — restricted content that is already public (P0 #721)

Scope: advisories labelled `TLP:GREEN`, `TLP:AMBER`, `TLP:AMBER+STRICT` or `TLP:RED` (FIRST TLP v2.0), or carrying
no/invalid label, that have already been served anonymously. The new gate (`scripts/tlp_policy.py`) stops *new*
distribution; it deliberately does **not** delete anything automatically. Retraction is an operator decision.

## What the measurement shows (checkout at this commit; `scripts/p0_721_dossier_integrity_audit.py`)
Static feed files that are anonymously reachable and list restricted entries: `api/feed.json` (11, of which 2 are
TLP:RED, all with a report page on disk), `api/feed_public.json` (26), `api/feed_mssp.json` (26),
`api/feed_enterprise.json` (13, 8 with a report page on disk). Note `feed_mssp.json` / `feed_enterprise.json` are
plain static files — being "tier" feeds does not make them access-controlled on a public site.
The audit lists per-file counts; `data/quality/tlp_quarantine_report.json` (written by the generator) names the
items whose report file already exists (`needing_retraction_review`).

## Steps (in order; none is automated)
1. **Freeze**: confirm the TLP gate is deployed so nothing new is emitted (generator, enhancer/PDF, governor feeds).
2. **Inventory** the exposed artifacts per item: report HTML (`reports/YYYY/MM/<id>.html`), PDF (`reports/pdf/`),
   STIX/MISP exports, R2 objects (`sentinel-apex-reports`), static feed entries, search/sitemap entries
   (`sitemap*.xml`, `reports-index`), and any cached copies (Cloudflare Pages/CDN, Workers KV).
3. **Notify the label originator** (the party whose TLP label applies). A label restricts *their* content;
   they decide the impact. Record who was told and when.
4. **Remove from the origin**: delete/replace the objects (R2 delete; remove files in a reviewed commit; drop the
   entries from the feed files). Prefer a tombstone that carries no restricted text.
5. **Purge caches**: Cloudflare cache purge by URL/prefix for each path above; invalidate KV keys that mirror them.
   Verify with an anonymous request that every URL returns 404/410 and that feed JSON no longer lists the ids.
6. **Git history**: this repository is public — removed files remain in history and forks. If the originator
   requires it, treat it as a data-spill: coordinate history rewrite/GitHub support takedown. Do not rewrite shared
   history without owner approval.
7. **Record** the retraction (ids, timestamps, actor, evidence of purge) and re-run
   `python3 scripts/p0_721_dossier_integrity_audit.py --reports --strict`; the TLP section must report 0.

## Migration notes for the fail-closed default
* **Unlabelled items are now quarantined.** The platform's own enriched manifest (`data/apex_enriched_manifest.json`)
  carries no `tlp` label on any record. Until the owner reviews collectors, nothing from it is published.
* To publish unlabelled content from a collector whose source material is public by nature, add that collector's
  exact lower-case source id to `first_party_public_sources` in `config/tlp_publication_policy.json` **in a reviewed
  commit**. An item carrying any explicit label is never policy-assigned; an invalid label is never assignable.
* `TLP:WHITE` (TLP v1) stays quarantined until `legacy_white_treated_as_clear` is set after reviewing those items.
* There is no environment variable or CLI flag that bypasses the gate.

## Not covered by this change (still open)
Cloudflare Worker routes and R2 key-level access (direct-object access outside the Python producers),
`scripts/r2_report_publisher.py`, `generate_api_manifests.py`/STIX/MISP/PDF exporters other than the report PDF,
and every other writer of `api/*.json`. Each must call `tlp_policy.publication_decision()` /
`partition_publishable()` before emitting bytes; until then the control is verified for: report HTML, the
enhancer (HTML + PDF), and the `commercial_readiness_governor` feeds (`api/feed.json` and tier files).
