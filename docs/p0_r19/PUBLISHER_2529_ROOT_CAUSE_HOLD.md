# P0 R19 — Publisher #2529 failure, evidence classification and release HOLD

## Verified production publisher evidence (2026-10-09)

GitHub Actions `sentinel-blogger` workflow #2529, run `37913512938`, job `113771803700`, **FAILED**. Its live logs show three independently significant defects:

1. **Static public feed empty:** `api/feed.json` had 0 entries at the report validator; Stage 3.1 `scripts/enrich_feed_apex.py` exited with `IndexError` from `enriched[0]`, and the mandatory T04 feed regression failed. The repository's current `api/feed.json` blob is empty. The public live Worker independently showed 38 advisories, which demonstrates that the edge's R2 feed and the working tree's static feed cannot be equated. Do not populate the public feed from old TLP:GREEN/AMBER/RED or unlabelled records.
2. **Report delivery failing:** Phase 2 repeatedly found a live HTTP 500 for one historical report and HTTP 404 for three other indexed report URLs; a different URL's 404 was correctly classified as an expected publication-gate rejection. Phase 3 had 0/15 confirmed; Phase 5 had insufficient completed probes. Not every historical 404 represents a broken deployment, and an HTTP 500 must not be masked.
3. **Probe budget exhaustion:** Phase 2 consumed the bounded request/time budget during backoff; subsequent Phase 3/5 probes returned `NOT_PROBED`. The old validator marked `NOT_PROBED` as `is_transient=False` and then misleadingly reported it as a **permanent 404**. This PR corrects **classification and early-stop only**; it does not convert any unavailable report into PASS.

The convergence verdict was `DEPLOYMENT_FAILED`, score 4.2/100; the full 600s protocol budget was reached. The report freshness check succeeding later in the pipeline is not evidence of report HTML availability or release GO.

## Narrow safe fix here

- A request/time exhaustion is `NOT_PROBED`, not an observed HTTP status. The validator marks it non-permanent, explicitly aborts later retry rounds, maintains the original request/time ceilings and the same report confirmation thresholds.
- Phase 2, Phase 3 and historical audit **remain FAIL** for missing/unverified customer reports. No 404, 500, missing report or out-of-budget condition becomes a successful delivery signal.
- Unit tests exercise observed HTTP 404, exhausted budget with zero outbound requests, and fail-closed Phase 2/Phase 3 behavior. The existing mandatory Python Gate now runs them.

## Next root-cause tasks, separate from this fix

- Rebuild `api/feed.json` only from verifiably authorized `TLP:CLEAR` items with source provenance, preserve the R2 authoritative feed and explain the zero-item working tree. Investigate `enrich_feed_apex.py` empty-input error without allowing fake/publicly restricted data.
- Audit `api/reports/index.json` against canonical R2 objects, authoritative `/api/v1/reports/{id}/publication-status`, and the actual deployed Pages/Worker version. Remove links to explicitly blocked records **from customer advertising**, without deleting legitimate restricted evidence or overriding publication gates.
- Resolve actual HTTP 500 and non-gate 404s before a new deployment convergence attempt. Maintain rate/request budget; do not blindly increase retry counts or probe quotas.
- Do not merge/deploy to production, claim report VERIFIED, close #721/#725/#720, or authorize enterprise GO on the basis of these diagnostic changes alone.
