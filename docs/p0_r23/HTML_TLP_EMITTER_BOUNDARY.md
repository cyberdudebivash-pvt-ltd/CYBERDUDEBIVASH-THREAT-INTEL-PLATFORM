# P0 R23 — Standalone HTML Dossier Must Honor Central TLP Policy

Release state: **NO-GO** until the live customer artifacts, eight dossier claims, and historic TLP exposure are independently verified.

## Root cause

`scripts/report_generator.py::_build_html` previously displayed `TLP:CLEAR` when neither `tlp` nor `tlp_label` existed. The standalone `generate_report` / `--entry` path did not consult `scripts/tlp_policy.py::publication_decision` before writing to `reports/`. An unclassified or restricted source must **never** inherit a public label from a display fallback.

This is a distinct last-mile output boundary. Other publisher and manifest TLP guards are helpful but do not authorize a standalone HTML writer to bypass classification checks.

## Patch

- Before creating any report directory or writing report bytes, evaluate the **central** anonymous-public publication policy on the entire advisory including mixed source marks.
- Denied or unverified records return `(False, "tlp_publication_denied: ...")` and leave the input and existing report files unchanged.
- Explicitly authorized `TLP:CLEAR` entries remain supported.
- For an unlabelled advisory whose **source ID and source URL host** match the reviewed first-party-public allowlist, the report may display the policy-assigned `TLP:CLEAR`. This uses an ephemeral render copy; it does not rewrite the upstream advisory or assign a label to any denied item.
- Without an authorization decision, HTML display falls back to `UNCLASSIFIED — NOT APPROVED`, not a false public TLP mark.
- Mandatory R23 negative controls cover missing, RED/GREEN/AMBER, invalid, legacy, mixed upstream labels, source-host impostors, byte preservation and authorized public output.

## Limitations and release proof

This prevents **new unauthorized HTML writes** through this secondary generator. It cannot retroactively retract historical public R2/Pages objects, purge CDN caches, guarantee correctness of independent primary writer `scripts/generate_intel_reports.py`, or independently validate source facts. Existing restricted objects need a privately authorized inventory and targeted clean-up.

Do not treat a passing R23 CI run as an enterprise report-quality certificate. Continue to enforce issues #721 (eight historical dossier evidence), #725 (historic TLP containment), and #596 (customer auth/revocation). Require an actual fresh feed, verified R2/Pages+Worker SHA parity, privacy-safe analyst sign-off, premium entitlement and rollback tests before Enterprise GO.

## Additional false-green CLI defect

The `--entry` CLI used `ok = generate_report(...); return 0 if ok else 1`, but `generate_report` returns a **tuple** `(success, result)`. Even a failed `(False, error)` tuple is truthy, so automation could report success after a rejected write. The caller also passed an unsupported `force` keyword to `generate_report`. The R23 fix unpacks `ok, _result`, uses exit 2 on deny/failure and calls the supported interface. CLI tests now assert both denied/non-written and explicitly approved/CLEAR cases.
