# Cloudflare Worker workload configuration guard

Run from the repository root:

```powershell
python scripts/cloudflare_workload_guard.py
python -m pytest tests/test_cloudflare_pre_revenue_guard.py tests/test_cloudflare_workload_guard.py -q
```

The R2 FinOps gate runs both commands on pull requests. Relevant main pushes
also trigger it for all Worker Wrangler configurations, the script, tests
and baseline.

The baseline records the existing gateway, revenue, retention and swarm
resource/schedule configuration from main 92071a53c60c01796810a64fd2d298fede7cc865.
It detects new or removed Worker configurations, binding additions and
resource-target changes, cron changes, environment-specific resource
changes, and other non-metadata Wrangler configuration drift. Existing
gateway tests separately keep dormant workload activation flags disabled.
Source entry points, release dates and compatibility flags are release
metadata and remain subject to the normal code/security regression gates.

This guard performs local reads only. It adds no Cloudflare operation,
storage, binding, trigger, polling or paid service. A changed resource
configuration fails until reviewed; do not regenerate the baseline simply
to turn a failed check green.

For a legitimate workload change, attach:
- The proposed request/CPU, KV, D1, R2, queue or Durable Object impact, including retries and schedules.
- Current account plan allowances, billing period and measured aggregate usage across all eight platforms.
- Expected peak load, remaining headroom and a bounded rollback/containment plan.
- Explicit authorization for any new spend or plan upgrade.

The baseline is configuration evidence, not a quota meter. It does not
certify deployed state, application-level operation rates or account-wide
plan compliance. Existing workloads can still exceed a plan under load.
The other seven platforms require their own configuration guards and
shared-account capacity review. Do not widen runtime workloads while
current account headroom is unverified.

