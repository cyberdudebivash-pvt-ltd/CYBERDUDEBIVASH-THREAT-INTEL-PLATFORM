# Project TITAN Stage 15 — Migration Runbook

Covers the one migration action this stage performed, plus its rollback. See `TITAN_STAGE15_GATEWAY_ADOPTION_REPORT.md` for the full discovery/evidence trail behind this decision.

## 1. What was migrated

`scripts/intelligence_platform_snapshot.mjs` — the only real direct-composition consumer of `intelligence-platform/` found anywhere in the repository (`TITAN_STAGE15_GATEWAY_ADOPTION_REPORT.md` §2.1) — was **deprecated in place**, not rewritten or deleted.

## 2. Why deprecation, not a rewrite

Its full functionality (evidence registration, `byCVE` lookup, metrics snapshot) is already a strict subset of what `scripts/enterprise_gateway_snapshot.mjs` (Stage 14 Phase 1) does, Gateway-routed. Rewriting the older script's internals to also call the Gateway would produce two near-duplicate scripts solving the same problem — itself a violation of Single Source of Truth. Marking the transition explicitly, while keeping the original fully functional, is the smaller and safer action, per CLAUDE.md's Deprecation Instead of Deletion policy.

## 3. Exact steps performed

1. Added an `@deprecated` JSDoc block to `scripts/intelligence_platform_snapshot.mjs`'s header comment, naming the replacement (`scripts/enterprise_gateway_snapshot.mjs`), the reason (bypasses the Gateway), confirmation of zero known consumers (not CI-wired, not referenced by any workflow/`package.json` — grep-confirmed), and a removal-eligibility criterion (Stage 16+, after zero-consumer status holds one full stage cycle past this notice).
2. Added one `console.log` deprecation notice near the top of the script's runtime output (prints unconditionally, before the `INTERNAL_ADOPTION_ENABLED` gate check) — visible to anyone who actually runs it, not just source readers.
3. Added `check_gateway_bypass_new_direct_composition_consumers()` to `scripts/titan_architecture_governance_check.py`, with `intelligence_platform_snapshot.mjs` as the one named, allowed exception — so any **future** new direct-composition script gets flagged, preventing the same pattern from silently reappearing.
4. Zero changes to the script's actual logic, CLI contract, argument handling, flag-gating semantics, or JSON output shape.

## 4. Verification performed

- `intelligence-platform/__tests__/internal-adoption.test.js` (the black-box child-process test of this exact script) re-run: all assertions on output shape, flag behavior, and JSON structure still pass — confirmed the new console.log line (no `{`/`}` characters) cannot interfere with the test's brace-index-based JSON extraction, then verified by direct test execution, not just reasoning.
- Full regression suite (§8 of the adoption report) re-run after the change.
- Governance script re-run: the now-deprecated script is correctly recognized as the authorized exception, not flagged as a new violation.

## 5. Rollback

**Trivial — no functional risk.** The change is a comment block plus one `console.log` call; nothing about the script's behavior, output, or exit codes changed.

To roll back:
```bash
git revert <commit-sha-of-this-change>
```
or manually: remove the `@deprecated` block from the header comment and the one `console.log` line added near the top of the runtime output. No other file needs to change — the governance check's allowlist entry can stay (it's inert once the deprecation notice is gone; it only ever prevented a false-positive flag on this specific file) or be removed in the same revert for full symmetry.

No data migration, no schema change, no flag flip, no persisted state anywhere in this change — rollback is a pure source-code revert.

## 6. Future full removal (not this stage)

Per the deprecation notice's own criterion: eligible for actual removal at Stage 16 or later, once confirmed zero-consumer status has held for a full stage cycle after this notice was added. At that point: delete the file, remove its entry from `AUTHORIZED_LEGACY_GATEWAY_BYPASS_CONSUMER_NAMES` in the governance script, remove `intelligence-platform/__tests__/internal-adoption.test.js` (or repoint it at the Gateway-routed script if that coverage is still wanted), and update this runbook and the adoption report to reflect the completed removal.
