# P0 R19 — Production Worker release-truth acceptance (NO-GO baseline)

## Confirmed pre-change defect

On 2026-10-09 the production `/api/health/live` returned a Worker deployment SHA of `86c5eedf86fbad680e8f76e6d2504d625ce9d0cf` while GitHub `main` had advanced through #743, #744 and #745. Both `/api/health` and `/api/preview` responded successfully, but their healthy responses do **not** mean the latest source fixes were deployed. The previously advertised FREE report links for three sample advisories returned 404, and their authoritative `/api/v1/reports/{id}/publication-status` were `BLOCKED` with evidence/trust reasons. Hiding those blocked report links was implemented in #745; the deployment still has to converge.

## New independent read-only gate

`scripts/p0_r19_live_release_truth.py` accepts only an explicit 40-character expected Worker SHA and samples up to five public advisories (default three). All network actions are `GET` with timeouts and a strict fixed origin; there are no provider secrets, writes, R2 cache purges, payments or customer API keys.

It **blocks** unless:

1. `/api/health/live` is alive and its `deploy_commit_sha` equals the intended, actually deployed release's SHA exactly.
2. `/api/health` declares publication integrity OK and source-backed intelligence freshness within six hours, cross-checked against the local UTC clock (not response-time restamping).
3. `/api/preview` declares fresh intelligence and exposes the R18 internal advisory vs STIX syntax-only identifiers correctly.
4. Preview TLP is explicitly CLEAR; no blocked report's internal URL is advertised.
5. Every sampled `report_customer_ready` boolean matches the separately queried, authoritative `/api/v1/reports/{id}/publication-status` decision. A claimed ready report must have an internal report link.

The only successful output is `LIVE_SLICE_VERIFIED_NOT_ENTERPRISE_GO` (exit 0). Any missing source, endpoint error, incorrect SHA, contradictory verdict, TLP violation or stale data returns `BLOCKED` (exit 2), with reason codes only.

## Operation

Following a separately approved deployment (not during a draft PR or before deploy), run from the checked-out release SHA:

```powershell
Set-Location 'C:\CDB\repos\CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM'
git fetch origin
git switch main
git pull --ff-only
$Expected = (git rev-parse HEAD).Trim()
python scripts/p0_r19_live_release_truth.py --expected-worker-sha $Expected --limit 3
if ($LASTEXITCODE -ne 0) { throw 'P0 R19 Worker release acceptance BLOCKED. NO DEPLOY/NO GO.' }
```

The `$Expected` value here is the **intended** release revision. A green git state does not prove deployment; the live response must match it independently. Operators can also manually dispatch the least-privilege workflow `.github/workflows/p0-r19-live-intel-release-truth.yml` **on main only** after an approved deployment. Do not schedule hourly probes, add credentials, or relax SHA/freshness thresholds to force a pass. No new Cloudflare resources or Workers are required.

## Explicit non-GO areas

This smoke gate samples only a bounded public preview slice. It does **not** prove completeness, truth or analytical quality of the eight historical enterprise dossiers (#721); customer PDF/HTML/STIX hashes and independent source evidence; historical TLP cache/object retraction (#725); immediate customer access revocation (#596); full R2+Pages CDN convergence, uninterrupted availability, or payment-to-entitlement; or observability and rollback acceptance.

These remain mandatory, separately signed P0 release gates. The overall SENTINEL APEX Enterprise Customer Readiness verdict remains **NO-GO** until every category is proven in the deployed environment.
