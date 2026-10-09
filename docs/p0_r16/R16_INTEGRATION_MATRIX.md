# SENTINEL APEX R16 — source integration evidence (NO-GO)

This branch integrates **only** existing reviewed draft-PR file blobs from #734, #735, #736, #737, #738, #739 and #740 against exact parent main `36a08fad5170c398269a4706e636b1729092a743`.

It does not merge the seven original PRs, deploy to any production environment, delete or reclassify intelligence, change subscription entitlements, or grant publication approval.

## Manual collision reconciliation

- `.github/workflows/intel-gateway-regression-gate.yml`: combines all three R16 mandatory Python test entries from #737, #738 and #739; their original gates remain unchanged.
- `config/frontend_checksums.json`: uses the original verified index.html SHA256/size from #735 and card_renderer.js SHA256/size from #736, preserving all six other baseline asset hashes; no hash has been fabricated. Verify again with the real frontend-integrity tool on CI and reject any mismatch.

## Required integration gates

1. Run all Python/Node regressions, including the T19 authenticated R2 test and all R15/R16 negative controls. Do not count tests not executed.
2. Run authenticated R2 integrity, source provenance, negative TLP controls, enterprise/customer authorization, report validity, historic-retraction and public-preview contract checks.
3. Inspect Bandit, Semgrep, Safety, TruffleHog and GitGuardian outcomes individually; a green classifier with skipped security scans is not execution evidence.
4. Confirm fixed-date and runtime contract assertions do not fabricate freshness, exploitation, STIX compliance, actor attribution or publication receipts.
5. Do not issue GO until genuine new intelligence clears the anti-stale five-item floor and 30-day/actor mandates, a complete current-window HTML report is generated, origin and CDN copies converge, commercial entitlement canaries pass, approved Cloudflare budget holds and rollback is rehearsed.

All fixes are REVIEW CANDIDATES. GO remains **blocked**.
