# P0 R18 — Eight-dossier private evidence preflight (release HOLD)

Status: **NO-GO until live, independent customer evidence review is completed.** This tool verifies completeness and cryptographic integrity of an **operator-supplied private bundle**. It never proves threat-report claims, TLP declassification, payment flow, deployed CDN parity, or production release approval.

## Why a separate gate

`tests/test_dossier_integrity_p0_721.py` intentionally skips two golden-eight checks when `tests/fixtures/golden_721/*.json` are absent. A green Python CI run cannot be presented as an eight-dossier enterprise certification. The private preflight fails closed when its index, any of eight unique cases, supporting evidence, or report bytes are missing. Its unit tests run in the standard mandatory Gateway CI without embedding customer materials.

## Secure operator evidence bundle

Create this **outside the public repository**, in a restricted operator workspace with role-limited access, retention policy, and encrypted backups. Never upload the records, private index, restricted IOCs, source material, or full pages to public GitHub issues, PRs, build artifacts, or workflow logs.

At the root, supply `index.json` with `schema_version: 1`, `deployment_sha` (40 lowercase hexadecimal characters from the **actual deployed** Worker/Pages release), and `cases`: precisely eight objects, one per CVE:

- CVE-2026-71183
- CVE-2026-89191
- CVE-2026-12260
- CVE-2026-4894
- CVE-2026-105110
- CVE-2026-107466
- CVE-2026-87426
- CVE-2026-107510

Each object must provide `cve`; `record`, `html`, `pdf`, and `stix` file references; and a nonempty `source_evidence` array of file references. Each file reference has exactly two fields: `path` (relative to the private root, no traversal) and `sha256` (lowercase SHA-256 of the exact bytes). Duplicate file reuse is refused. The source record JSON must identify the exact target as `cve_id` and have explicit `tlp: TLP:CLEAR` for anonymous publication. The HTML must identify the CVE, PDF must have the PDF signature, and STIX must have a populated bundle with correctly formed STIX identifiers. **Private, non-CLEAR information cannot be certified for anonymous-public release by this gate.** Paid/gated delivery needs an independent entitlement/TLP review.

Run locally in a restricted operator shell:

```powershell
$EvidenceRoot = 'C:\CDB\secure\r18-private-evidence'
$DeployedSha = (Get-Content 'C:\CDB\secure\r18-deployed-sha.txt' -Raw).Trim()
python scripts/p0_r18_private_evidence_gate.py --private-evidence-root $EvidenceRoot --expected-deployment-sha $DeployedSha
if ($LASTEXITCODE -ne 0) { throw 'P0 R18 dossier evidence preflight BLOCKED; do not release' }
```

The SHA file must be populated from an independently observed **deployed** release; a local `git rev-parse HEAD` does not prove deployment. Exit code `2` = BLOCKED; `0` = `EVIDENCE_BYTES_VERIFIED_NOT_RELEASE_GO`, **not** a certification or deployment authorization.

## Remaining independent GO requirements

1. Two-person/source-independent analyst claim review for all eight: dates, CVE identity, references, exploit status, actor confidence, validated IOCs, CVSS/EPSS/KEV provenance, ATT&CK IDs/version, observed-vs-inferred behavior, and legal/TLP restrictions. Record signatures and disposition privately.
2. Run the existing full `tests/test_dossier_integrity_p0_721.py` against authorized sanitized source records **with zero skipped golden-eight tests**, record exact test IDs and hashes; do not create fictitious public fixtures.
3. Confirm rendered HTML/PDF/STIX byte parity with the **served** CDN/Worker/R2 artifacts and compare release SHA, cache state and current authoritative feeds.
4. Close issue #725 via authorized targeted TLP retraction and independent unauthenticated recheck of all delivery routes. Do not infer erasure from no-new-PUT controls.
5. Verify ingestion freshness, M9/M10 mandates, customer auth/key lifecycle, FREE vs paid entitlements, payment-to-access, rate limits, rollback and Cloudflare plan budget.
6. Only then issue a separately signed production GO decision. Missing any evidence keeps status NO-GO.

Synthetic inputs in `tests/test_p0_r18_private_evidence_gate.py` exercise validator failure modes only and have **zero standing** as customer intelligence or live evidence.
