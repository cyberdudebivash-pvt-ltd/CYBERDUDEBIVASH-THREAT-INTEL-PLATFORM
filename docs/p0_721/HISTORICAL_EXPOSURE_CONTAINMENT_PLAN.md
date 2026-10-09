# Historical exposure containment plan (P0 #721 / #725) — NON-DESTRUCTIVE until the operator authorizes

Scope: restricted-labelled (or invalid/unmigrated-label) advisories that were — or may still be — reachable
anonymously. **This document and its tooling perform no deletion, purge, rewrite or deployment.**

## 1. Distinguish five states (never conflate them)
| State | Meaning | How it is established |
|---|---|---|
| Newly prevented publication | gates now withhold the record | `data/quality/tlp_quarantine_report.json`, `r2_tlp_quarantine_report.json`, `pages_tlp_boundary_report.json` (ids + reason codes only) |
| Previously published origin objects | the artifact exists in repo / Pages / R2 | private ledger (`scripts/tlp_exposure_inventory.py`) — offline |
| Cached historical copies | CDN edge, Worker KV, browser/search caches | **not knowable offline** — operator inspects Cloudflare cache/KV per URL |
| Unverified exposure | listed in a public manifest, not yet probed | ledger `verification_status = NOT_VERIFIED_ANONYMOUSLY` |
| Confirmed anonymous accessibility | anonymous `HEAD`/`GET` returned 200 | ledger `CONFIRMED_ANONYMOUSLY_ACCESSIBLE` (`--probe N`) |

## 2. Private evidence ledger (specification)
* Producer: `TLP_LEDGER_SALT=<operator secret ≥16 chars> python3 scripts/tlp_exposure_inventory.py --out <private path> [--probe N]`.
* Location: outside the git work tree (the tool refuses otherwise), mode `0600`, stored in the operator's private
  evidence store. **Never** attach to a public issue/PR/CI log.
* Row fields: `opaque_ref` (HMAC-SHA256 of the id under the secret salt — not reversible by guessing ids),
  `reason_code`, `label`, `in_public_manifests[]`, `artifacts[]{kind, route, storage, access, cache,
  anonymous_http_status?, probed_at?}`, `recommended_operations[]{kind, op, cost, rollback}`,
  `originator_notification_required`, `evidence_timestamp`, `verification_status`.
* No titles, descriptions, IOC values or bodies are ever written. stdout carries counts only.
* Map `opaque_ref → id` only inside the operator's private store (recompute with the same salt).

## 3. Inventory result at this commit (offline, working tree; counts only)
* 706 distinct advisories carry a restricted/invalid/unmigrated label across the public manifests
  (643 `TLP:GREEN`, 57 `TLP:AMBER`, 6 `TLP:RED`); 831 manifest memberships; 403 report files for them exist in the tree.
* Bounded anonymous probe: 5 `HEAD` requests to report routes → 5 × `404`. **This does not establish absence for the
  other 398**; it is a sample (first five opaque refs), not a verification.
* Live anonymous `GET /api/feed.json` and `/api/v1/intel/latest.json` (generated 2026-10-08T16:48:36Z, produced before
  #727 reached `main`): 36 records each, **1 restricted** in both. `latest_pro.json` / `feed_public.json`: 404.
  Re-probe after the first pipeline run containing #727 and this change; any restricted record still present means a
  remaining bypass.
* The 706 figure counts advisories, not confirmed exposures. 643 are `TLP:GREEN` and the platform's own backfill
  (`apex_quality_field_backfill.py::_TLP_MAP`) assigns `TLP:GREEN` to every CRITICAL/HIGH record: many of these labels
  may be platform-derived rather than originator-assigned. The operator must determine label provenance before any
  originator notification; the safe handling (do not publish) does not depend on that answer.

## 4. Targeted retraction plan (operator-approved, per item, dry-run first)
Preconditions (all required): (a) ledger reviewed by the operator; (b) rights/ownership confirmed per item (who is the
label originator); (c) encrypted private backup of every object to be removed; (d) this plan's item list approved in
writing. **No** bucket-wide LIST, bulk DELETE, prefix delete, mass report rewrite, global cache purge or git-history
rewrite without separate explicit authorization.

| Step | Operation | Bound / cost | Dry-run | Rollback |
|---|---|---|---|---|
| 1 | Freeze: confirm a pipeline run containing the gates (#724, #727, this change) completed and the live feeds no longer list restricted ids | 0 R2 ops | `curl` GET counts (no storage of bodies) | n/a |
| 2 | Pages: remove the exact report files / replace JSON via the boundary-sanitized dist, one reviewed commit to gh-pages | 0 R2 ops, 1 commit | `tlp_public_boundary.py --dist dist --dry-run` | revert the commit (restores restricted bytes — only on operator instruction) |
| 3 | R2 reports: `DeleteObject` on the exact key list from the ledger (keys derive deterministically: `reports/YYYY/MM/<id>.html`, `reports/pdf/<id>.pdf`) | ≤ N DELETEs, no LIST; stays inside `MAX_REPORT_DELETIONS_PER_RUN` | print the key list, execute nothing | re-PUT from the private backup |
| 4 | R2 JSON objects: re-publish via `r2_upload.py` (TLP-verified copy overwrites the stale object) | 1 PUT each, inside `MAX_R2_DATA_WRITES_PER_RUN` | `--dry-run` of the budget guard | re-PUT previous object from backup |
| 5 | Caches: purge the exact URLs (Cloudflare cache purge by URL), delete the exact KV keys that mirror them | per-URL purge calls (rate-limited API); KV deletes | list URLs/keys, call nothing | caches repopulate from origin; nothing to restore |
| 6 | Anonymous verification: for every URL/key, anonymous `HEAD` → 404/410 (or sanitized body), feeds no longer list the id; record status + timestamp in the ledger | ≤ 1 request per URL | — | — |
| 7 | Originator notification (when provenance shows a third-party originator): record who, when, what | — | — | — |
| 8 | Git history / forks: coordinate separately (history rewrite or GitHub support takedown) — **not** part of this plan | — | — | — |

## 5. Expected continuity behaviour of the new gates (so operators are not surprised)
* A pipeline window whose only fresh items are policy-withheld no longer fails `--fail-on-zero` (run 37806739926 went
  red for exactly that reason), but emits a workflow warning and a quarantine report: **nothing is published for them**.
* `api/iocs/feed.json` (`TLP:WHITE`) and the 162 per-advisory detection documents without a verified `TLP:CLEAR`
  parent are withheld/tombstoned until the operator (a) reviews `legacy_white_treated_as_clear` and (b) adds label
  provenance upstream. Do not mass-assign `TLP:CLEAR`.
* Rollback that does not republish restricted bytes: `R2_REPORT_PUBLISHING_ENABLED=false` (publisher pause; the
  verdict step then reports PASS-WITH-PUBLISHER-DISABLED, never a clean release). Reverting a gate re-enables
  publication of restricted material and is not a rollback.
