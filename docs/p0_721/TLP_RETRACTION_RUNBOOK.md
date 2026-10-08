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
* **Unlabelled items are quarantined.** `data/apex_enriched_manifest.json` carries no `tlp` label on any of its 2,000
  records, so any publisher that reads it directly would withhold everything. The two publishers gated below read
  `api/feed.json` instead, where 98 of 109 records are `TLP:CLEAR` and 11 are withheld (measured at this commit).
* **Collector approval is bound to a host, not to feed text.** To publish unlabelled content from a collector whose
  material is public by nature, add `{"source": "<exact lower-case id>", "hosts": ["<hostname>", ...]}` to
  `first_party_public_sources` in `config/tlp_publication_policy.json` **in a reviewed commit**. The item's source id
  AND the hostname of its `source_url` must both match, so a `source` string supplied by feed text cannot self-approve.
  Residual risk: the URL is still record content. A collector-stamped identity that upstream text cannot write
  (e.g. a signed ingest stamp) would close this fully; it is not implemented. The allowlist is empty today.
  An item with any explicit label is never policy-assigned, and an invalid label is never assignable.
* **Mixed sources: most restrictive wins.** The effective label is the most restrictive of `tlp`, `tlp_label` and the
  `tlp`/`tlp_label` of entries in `evidence_chain`, `sources`, `merged_from`, `source_documents` and
  `corroborating_sources`. Components that carry no label cannot be proven restricted and are not counted against the
  item; today's `evidence_chain` entries carry none, so per-source provenance must be added upstream to make this
  check bite on real records.
* `TLP:WHITE` (TLP v1) stays quarantined until `legacy_white_treated_as_clear` is set after reviewing those items.
* There is no environment variable or CLI flag that bypasses the gate.

## Operational continuity, visibility and rollback
* `scripts/r2_report_publisher.py` (STAGE 3.5a and 5.4.0c): denied items never become publish candidates, so no PUT of
  their HTML/PDF is planned. It deletes nothing by itself. Previously published objects that are now denied are listed
  in `data/quality/r2_tlp_quarantine_report.json` (`needing_retraction_review`; ids and reason codes only) and in a
  WARNING log line — retraction stays an operator action under the steps above.
* `scripts/generate_api_manifests.py` (STAGE 3.93 and its re-run): denied items are dropped from the anonymously served
  manifests and counted by reason code in the log. If nothing is publishable, or `tlp_policy` cannot be imported, it
  exits non-zero **before writing**, leaving the previous artifacts unmodified (the pipeline stops there; that is the
  intended fail-closed behaviour, not a silent empty feed).
* **Rollback that does not republish restricted bytes:** use the existing kill switch `R2_REPORT_PUBLISHING_ENABLED=false`
  (no R2 call at all) rather than reverting the gate. Reverting the gate re-enables publication of restricted items.
  Do not mass-assign `TLP:CLEAR` and do not widen the allowlist without evidence for each collector.

## Output paths and their enforcement status
| Output | Status |
|---|---|
| Report HTML (`generate_intel_reports.py`), enhancer HTML/PDF, governor feeds (`api/feed.json`, tier files) | gated (round 1) |
| R2 report publisher (`r2_report_publisher.py`, both stages) | gated (this round) |
| Immutable API manifests (`generate_api_manifests.py`) | gated (this round) |
| `r2_upload.py` (copies `api/feed.json` and other `api/*.json` to R2) | NOT gated: it uploads whatever the writers above leave in `api/`; the 11 already-withheld-by-policy records still sit in the checked-in `api/feed.json` |
| Cloudflare Worker routes / direct R2 key access | NOT gated (outside the Python producers) |
| Other `api/*.json` writers, STIX/MISP/TAXII and non-report PDF exporters | NOT gated |

Until the NOT-gated rows are closed and the historical exposure above is contained and verified anonymously, the
control is incomplete and no release certification is claimed.
