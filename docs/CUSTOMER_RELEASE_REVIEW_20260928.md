# Customer release review — 2026-09-28

Decision: HOLD broad customer-release certification pending the operational
checks below. A successful synthetic engine run is not a production audit,
tenant-isolation certification, uptime guarantee, or proof of revenue.

## Observed production evidence

Read-only probes on 2026-09-28 around 06:43–06:46 UTC:

| Surface | Observed result |
| --- | --- |
| `/api/health` | `ok`, 181 advisories, fresh intelligence |
| `/api/ai-feed/health` | `FRESH`, eight available AI items |
| `/api/ai-feed/live` without credentials | FREE, locked, five items |
| `/api/reports/latest.json` | CVE arrays populated in sampled reports |
| `/get-api-key.html` | HTTP 200; frame guard deployed; no HTTP X-Frame-Options or CSP header |
| `/api/sla/status` | `monitoring_delayed`, eight samples, last ping ~18,187 seconds old |

These are point-in-time observations. They do not validate authenticated paid
entitlements or a payment-provider round trip. Do not advertise the eight
successful pings as verified continuous 30-day availability.

## Verified defects addressed by this change

- Hardening workflow run 36386230396 reported success after three GH013
  protected-branch rejections. Required JSON validation could print FAIL and
  still exit zero; five steps suppressed errors. Replace this with isolated,
  fail-closed smoke evidence, contents-read permissions, and three-day artifacts.
- Synthetic tenant/monetization fixtures ran alongside tracked production data.
  A new empty temporary working directory prevents stale reports from passing
  checks and keeps generated fixtures out of the repository and customer data.
- Checkout displayed unsupported ratings and customer counts. Replace those
  claims with checkout, documentation, and source-linked intelligence facts.
- Cloudflare rule deployment instructions could replace an entire existing
  ruleset. Require preserving unrelated rules; exclude API route roots as well
  as their descendants. No Cloudflare rule has been applied by this PR.

## Release gates still requiring operational evidence

| Priority | Gate | Acceptance |
| --- | --- | --- |
| P1 | Static response headers | Apply the reviewed Cloudflare rule while preserving other rules. Confirm CSP `frame-ancestors 'self'`, X-Frame-Options SAMEORIGIN, nosniff, Referrer-Policy and Permissions-Policy on login, key and checkout pages. Verify checkout still works. |
| P1 | External monitoring continuity | Restore timely external heartbeats; observe multiple consecutive scheduled samples within the published 2,700-second threshold. Investigate scheduler execution gaps; do not synthesize missed samples. |
| P0 release gate | Paid customer acceptance | Use an authorized provider test transaction: payment confirmation, single key provisioning, duplicate webhook, renewal, cancellation, refund/revocation, and cross-tenant denial. Retain sanitized evidence. Not executed in this review. |
| P0 release gate | Deployment convergence | Confirm the merged checkout changes are served live and the new smoke workflow retains a manifest for the deployed revision. |

The current execution session has no Cloudflare administration credentials or
payment test credentials. Those operational gates remain open; no production
certification or first-revenue guarantee is made.

Rollback: revert this PR. It changes smoke evidence and checkout copy; it does
not modify payment routing, entitlements, database schemas, or production data.
