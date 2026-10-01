# Customer release ledger — Sentinel APEX

The one living task ledger for customer-release acceptance (backlog R01–R35 of
the 2026-09-30 handoff). Dated reviews such as
[CUSTOMER_RELEASE_REVIEW_20260928.md](CUSTOMER_RELEASE_REVIEW_20260928.md)
stay as point-in-time records; this file carries current status. Update it in
the same PR as the change that moves a row. Historic evidence is never reused
as current certification.

Last updated: 2026-10-01T12:00Z, branch `claude/charming-thompson-ptma8e`.

## Decision

**HOLD.** Not RELEASE or CONDITIONAL RELEASE. Here is why:

- The certification run against the deployed SHA fails (Phase 8) and has a
  BLOCKED mandatory canary.
- Gumroad purchases are not provisioned in production (F21).
- Lifecycle state changes are only eventually consistent (F17).
- The per-minute limiter does not fire (F18).
- The feed breached its freshness threshold twice overnight (F3).
- Pages has not deployed since 08:53Z (F20; hotfix PR #638 is green).

### Release evidence matrix (2026-10-01, deployed `d80c72643`)

| Control | Implemented | Tested | Deployed | Live verified | Blocker | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| FREE responses carry no IOC values (F15) | yes | 6 tests, 3 fail pre-fix | `d80c72643` | PASS | — | 11:31Z: `/api/feed.json`, `/api/v1/intel/latest.json` 58 items, 0 with values, 23 paywalled; `/api/preview/` and `top10` masked |
| 429 at the per-minute cap (F1) | yes | 4 tests | yes | FAIL: limiter never reaches the cap | product + FinOps (F18) | cert 36839516753 phase 8 `200x33`; probe 07:26Z 35/35 200 in IAD |
| Operator calls not metered (F2) | yes | 7 tests | yes | PASS | — | cert 36839516753: "MSSP rotation preserves membership: PASS" |
| Verified webhooks not metered (F9) | yes | 10 tests | yes | NOT TESTED with signed deliveries | credential (provider test mode) | — |
| Razorpay webhook configured | yes | — | yes | PASS | — | 11:33Z unsigned POST → 401 "Signature mismatch" |
| Gumroad webhook configured | code yes | — | secret missing | FAIL (P0) | operator secret (F21) | 11:33Z → 500 "Webhook secret not configured"; `upgrade.html` sells 4 Gumroad products |
| Lifecycle deny/reactivate/rotate takes effect immediately | KV only; strong authority dormant | cert matrix | yes | INTERMITTENT: FAIL 07:01Z, PASS 08:56Z | FinOps (#596 auth authority) | F17 |
| Expiry boundary, tier entitlements, MSSP isolation and self-service | yes | cert | yes | PASS | — | cert 36839516753 |
| Enterprise signed-webhook canary | yes | cert | yes | BLOCKED | operator (`CDB_WATCHDOG_SINK_*`) | `OPERATOR_WEBHOOK_SINK_REQUIRED` |
| Publisher post-deploy gates run (F13) | yes | 4 tests | `c14dbae11` | PASS on c14dbae11; regressed on d80c72643 | F20 → PR #638 | run 36826966415 vs 36833320633 |
| Pages deploys | yes | 9 tests | no (PR #638 open) | FAIL since 08:53Z | merge of #638 | F20 |
| Feed age ≤ 6h | publisher on GitHub cron | — | — | FAIL twice overnight | FinOps (R01 activation) | F3, F7 |
| Buyer security/compliance copy matches implementation (F17, F19) | yes, in PR #638 | gates + tests | no | FAIL live (old pages served) | merge of #638 | `1227296b6` |
| No fixed refresh cadence outside sla.html (Phase 6) | yes, in PR #638 | gates | no | FAIL live | merge of #638 | `1d94967ce` |
| Invented business data off the site (Phase 7) | yes | 9 tests | merged, not deployed | FAIL live (pages still 200 at 11:54Z) | F20 / #638 | — |

| SKU / capability | Status | Blocking evidence |
| --- | --- | --- |
| FREE API | HOLD | Per-minute limit not enforced live (F18) |
| PRO | HOLD | Lifecycle immediacy intermittent (F17); Gumroad checkout unprovisioned (F21) |
| ENTERPRISE | HOLD | As PRO; signed-webhook canary BLOCKED; 4-hour freshness term unsupported (F7) |
| MSSP | HOLD | As ENTERPRISE (rotation canary now PASS) |
| Malware review package | HOLD | #593: independent human review pending |
| Swarm live operations | HOLD | #419/#420/#422 not re-verified |
| Publisher post-deploy validation | DEGRADED again since 08:53Z | F20; fix in PR #638 (green, mergeable) |

## Provenance at this update

| Component | Value | Evidence |
| --- | --- | --- |
| `main` | `d80c72643` | #636 squash-merged as `c14dbae11` (tree = reviewed head `82d9b7b5c`); #637 squash-merged 07:56:50Z as `d80c72643` (tree = reviewed head `ce348b2a2`) |
| Deployed gateway | `d80c726435969b97b7e0b47d0753f4c3e36c61ce`, deploy run 36833320610 | `GET /api/health/live` 11:31Z: `deploy_commit_sha` and `deploy_run_id` |
| Live health | 200 `ok`; feed generated 08:49:50Z (age 3h04m, limit 6h), 58 advisories | `GET /api/health` 11:54Z |
| Open PR | #638 (`dd4eba3d3`, F20 hotfix): all checks green, `mergeable_state: clean` | PR checks 11:37Z |
| Follow-up commits on the same branch | `1227296b6` (F17, F19), `1d94967ce` (Phase 6 copy), this ledger | pushed to PR #638 rather than held locally (the session container is ephemeral); `dd4eba3d3` remains the hotfix commit |

Overnight 2026-09-30/10-01, from `generated_at` values the publisher's own
freshness gate logged (no probe sampled either window; this session
triggered no production pipeline):

| Window (UTC) | Feed | Evidence |
| --- | --- | --- |
| 21:33:57 → ~21:45 (≈11 min) | over the 6h contract | guard run 36774781090 (20:44:53Z) dispatched publisher 36774798831; new generation 21:44:52Z |
| 03:44:52 → ~05:15 (≈1h30m) | over the 6h contract | guard's last run 00:29:47Z (36796464941); SLA heartbeat's last 02:23:40Z; next generation 05:15:14Z (scheduled run 36815948964) |

## Findings and changes this session

### F1 — Commercial rate limit answered HTTP 500 instead of 429 (C02, R03) — MERGED `c14dbae11`, DEPLOYED; live cap never reached (see F18)

- `workers/intel-gateway/src/index.js` built `X-RateLimit-Reset` from
  `resetAtMs`, which is defined nowhere. Added by #290 (`b97efcf59`,
  2026-09-01). It is the only `no-undef` hit in 224 gateway source files
  (ESLint 10, Worker globals); revenue-engine, swarm-live and
  intel-retention-engine production code have none.
- Every time any tier crossed its per-IP minute cap, the Worker threw and the
  top-level handler returned 500 "Internal gateway error": no Retry-After, no
  X-RateLimit-* headers, no FREE/PRO upgrade block. Certification phase 8
  only looked for a 429, so it reported "first 429 = 0" and never showed the 500.
- Reproduced through the real router for FREE/PRO/ENTERPRISE/MSSP and for the
  dormant `RATE_STRONG_CONSISTENCY_ENABLED` path. Activating #596's rate
  authority before this fix would have made request 31 a guaranteed 500.
- Fix `5efa55206`: `checkRateLimit()` returns `resetAtMs` (end of the fixed
  window, from the same `minute` as the counter key) on every path; the 429
  branch reads it. Tests: `commercial-rate-limit-response.test.js` (4; 3 failed
  before).
- Still open under R03: KV counters remain eventually consistent. Whether the
  live counter reaches 31 is shown by the next phase 8 run, which now prints
  the status histogram (commit `89a25865a`).

### F2 — Operator control-plane calls metered as anonymous FREE traffic (C05, R02, R04) — MERGED, DEPLOYED, LIVE PASS (MSSP rotation canary, cert 36839516753)

- `/api/admin/*`, `/api/sla/ping`, `/api/alerts/dispatch`, `/api/watchdog/ops`
  and `/api/ai-feed/ingest` carry an operator secret, not a customer
  credential. They are dispatched after the commercial gate, so they were
  metered as FREE: 30/min on the per-IP bucket `rl:{ip}:{minute}` that all
  tiers from that IP share, and 50/day on the IP's FREE daily quota.
- Live: "MSSP rotation preserves membership: FAIL (rotation returned no key)"
  in certification runs 36685097733, 36688506829 and 36690549981. In the last
  two the rotate call ran in the same UTC minute as ~50 MSSP/PRO requests from
  the runner IP (08:16:35–08:16:58, 08:35:24–08:35:57); it passed in
  36665394189 when issued in the next minute (03:41). The canary discarded the
  status code, so causation is probable, not proven. The next certification
  run records status and reason (commit `89a25865a`).
- Fix `5f8a3cb4f`: a request presenting the valid secret for its route (each
  rule mirrors that route handler's own check) skips commercial metering.
  Missing, wrong or crossed secrets are metered as before; handleAdmin's
  brute-force lockout is unchanged. Tests: `operator-plane-metering.test.js`
  (7; 5 failed before).

### F3 — Stale-feed 503 at 15:06Z: GitHub cron starvation (C04, R01) — ROOT-CAUSED; fix PREPARED, OPERATOR-BLOCKED

- SLA heartbeat run 36734158488 saw `/api/health` 503 twice at 15:06Z. That
  was the correct readiness answer: generation 07:51:55Z (logged by guard run
  36693001070), stale from 13:51:55Z, next generation 15:33:57Z (run
  36732567953, created 14:53:46Z). About 1h42m stale. Liveness was never lost.
- Cause: publisher and self-heal both run on GitHub cron, and GitHub delivers
  this repository's schedules roughly every 2.4–8.5 hours.
  `intel-freshness-guard.yml` (`7,37 * * * *`, 48/day) ran about 5 times/day;
  it ran at 08:57Z (feed 66 min old) and next at 15:51Z. `sla-heartbeat.yml`
  (`*/10`, 144/day) also ran about 5 times/day.
- Not fixable by `workflow_run` chaining: every workflow display name carries
  the release suffix (`test_every_workflow_display_name_is_v201`), so name
  references break at each version bump (see F4).
- Prepared `8f37c95ea` (ships OFF): on the :00/:30 ticks of the existing
  15-minute Worker cron, one `workflow_dispatch` of `intel-freshness-guard.yml`
  by file name. The guard keeps the only decision logic. Pinned OFF by
  `tests/test_cloudflare_pre_revenue_guard.py`; declared in
  `config/cloudflare_pre_revenue_guard.json`.

**R01 activation runbook (founder approval required first):**

1. Verify the current Cloudflare plan, month-to-date usage and headroom for
   Workers requests and R2 Class B reads. Enabling adds 48 outbound GitHub API
   calls/day inside cron invocations that already run, and the guard's own
   ~48 `GET /api/health`/day: at most ~1,500 Worker requests and ~1,500 R2
   Class B reads per month. No new binding, trigger, KV write or Durable
   Object call.
2. Create a fine-grained GitHub PAT: repository access only
   `cyberdudebivash/CYBERDUDEBIVASH-THREAT-INTEL-PLATFORM`; permission
   Actions: read and write; nothing else; expiry ≤ 90 days.
3. `cd workers/intel-gateway && npx wrangler secret put FRESHNESS_GUARD_DISPATCH_TOKEN --env production`
4. In one PR: set `FRESHNESS_GUARD_DISPATCH_ENABLED = "true"` in both
   `[vars]` and `[env.production.vars]`; change the pinned value in
   `tests/test_cloudflare_pre_revenue_guard.py`; move the entry from
   `dormant_recurring_workloads_pending_approval` to an approved list.
5. After deploy, confirm in `wrangler tail` a `freshness_guard_dispatch`
   `dispatched` line on the next :00/:30 tick and a guard run with actor = the
   PAT owner. Rollback: set the flag back to `"false"` (or delete the secret).

Overnight evidence for F3 (2026-10-01): the guard ran at 20:44Z and 00:29Z
only, the heartbeat at 19:58Z, 23:36Z and 02:23Z only; the second stale
window above fell where neither ran.

Scheduling evidence, 2026-09-28 → 2026-10-01 (Phase 6):

- The publisher's cron `17 */4 * * *` (six slots a day) was delivered three or
  four times a day, 3 minutes to about 3.5 hours late (for example the 12:17Z
  slot of 09-30 started 14:53Z; the 20:17Z slot of 09-29 started 23:40Z), and
  some slots never arrived (09-30 16:17Z; 10-01 08:17Z had not arrived by
  11:50Z).
- The publisher shares the `sentinel-data-writer` group with seven other
  writers (multi-source-intel 6/day, enterprise-intel-quality 6/day,
  dashboard-feeds-sync 4/day, detection-engine 2/day, r2-data-sync,
  report-engine, weekly-threat-brief). GitHub keeps one pending run per
  group; a later arrival cancels it before any job starts. Run 36775128978
  (scheduled, 20:47Z) waited behind dispatch run 36774798831 and was
  cancelled at 21:32Z with 0 jobs. `test_workflow_concurrency_scoping.py`
  documents the same hazard.
- The two breach windows: 15:33:57Z generation → the 16:17Z slot never ran,
  the 20:17Z slot was displaced, recovery came from the guard's 20:44Z
  dispatch (≈11 min over). 21:44:52Z generation → the 00:17Z slot did not
  run, the 04:17Z slot started 04:37Z and published at 05:15:14Z before
  failing at F13 (≈1h30m over).
- Minimum-cost remediation remains R01 (runbook above): 48 dispatches/day
  from the existing 15-minute Worker cron, about 1,500 Worker requests and
  1,500 R2 Class B reads a month, guard runs on free public-repo runners,
  occasional extra publisher runs (≤200 R2 writes each, far inside included
  allowances). Marginal cost on the current Workers Paid plan: about zero.
  Activation is a FinOps decision and was not made.
- Zero-cost hardening done: F13 (merged), F20 (PR #638), and copy that no
  longer promises a fixed cadence (Phase 6 commit `1d94967ce`).

### F4 — All four `workflow_run` chains reference workflow names that no longer exist (R10, R29) — REPORTED

| Workflow | References | Actual name | Last `workflow_run` trigger |
| --- | --- | --- | --- |
| `post-deploy-validation.yml` | `deploy-worker` | `deploy-worker v201.0` | 2026-09-24T16:01Z (run 36024460525); none after later deploys |
| `master-deployment-orchestrator.yml` | `deploy-worker` | `deploy-worker v201.0` | — |
| `autonomous-guardian.yml` | `sentinel-blogger` | `sentinel-blogger v201.0` | all recent runs are `schedule` |
| `sentinel-factory.yml` | `CDB GENESIS Intelligence Powerhouse v184.0` | `... v201.0` | — |

Not revived here: reviving would change production automation
(orchestrator, factory and guardian write to `main` or deploy), and
post-deploy validation has not run for six days, so its gates may no longer
match current responses (for example `checks.jwt_configured` left the public
`/api/health` view). Owner decision; a name-drift test should land with any
revival.

### F5 — Failing tests that CI never runs (R29) — concurrency part FIXED on branch (`494446a09`)

- Root cause: PR #563 (`d1842a138`, 2026-09-28) wrote its YAML edits with
  literal `\n` sequences. Each replacement became one line starting with `#`,
  so seven derived-writer workflows (arsenal, convergence, bughunter-recon,
  bughunter-resilient, omnishield, precognition-engine, syndicate) lost their
  concurrency block entirely and have run with no concurrency control since;
  and `tests/test_workflow_concurrency_scoping.py` sat inside a comment in the
  regression gate's suite list, so it never ran (it failed on `main`). #570
  had already repaired `weekly-analyst-briefing.yml` the same way.
- Fix: the seven blocks restored in #570's wording with #563's groups (each
  replaced line asserted byte-for-byte first); the suite line restored. The
  test passes 2/2 and now runs in the PR gate.
- Still reported: `tests/test_deploy_provenance_contract.py` and
  `tests/test_weekly_threat_brief_branch_protection.py` are in no workflow and
  fail on `main`.

### F6 — SLA measurement claims exceed the monitoring that exists (R23) — OWNER DECISION

`sla.html` and the contract's `_sla_authority` say uptime is measured "from
three independent monitoring locations". The only external prober is
`sla-heartbeat.yml` from GitHub-hosted runners, about 5 samples/day. Either
provision independent monitors or change the published method; do not report
measured availability from this sample as the SLA figure.

### F7 — Freshness promise in `sla.html` (R01, R15) — OWNER DECISION

`sla.html` promises Enterprise/MSSP data freshness "Every 4 hours"; the public
freshness contract is 6 hours and today's publication gap was 7h42m. Even with
F3 activated the guard dispatches at 4h age and the publisher takes 40–80 min.

2026-10-01: the contract's `_sla_authority` makes this a contractual term, so
it is unchanged; the pages that quote it (trust-center, compare,
alternative-to-*) still do. Everything else that promised a cadence was
corrected (`1d94967ce`: "4h REFRESH CYCLE", "6h Intel Refresh Cycle",
"every 6–8 hours", Telegram alerts "within 15 minutes"). The only interval
production demonstrably meets is daily (worst observed staleness ≈7.7h).
Decision needed: activate R01 and dispatch at ≤3h, or amend the SLA term.
Uptime is measured from health checks and `/api/health` answers 503 when
the feed is over 6h, so freshness breaches also count against uptime credits.

### F8 — Legal entity naming (R27) — OWNER DECISION

`README.md` and many footers say "CYBERDUDEBIVASH Pvt. Ltd."; the contract's
`seller_legal` is an individual ("BIVASHA KUMAR NAYAK") trading as
CYBERDUDEBIVASH(R). Invoices and terms must name the actual seller.

### F9 — Payment webhooks metered as anonymous FREE traffic (R05, R06) — MERGED, DEPLOYED; adversarial audit merged (#637); signed live delivery NOT TESTED

`/api/webhooks/razorpay` and `/api/webhooks/gumroad` are routed after the
commercial gate with no customer credential, so each provider IP got 30/min
and 50/day. With exact counters (the #596 rate authority) the 51st delivery of
a UTC day from one provider IP would be refused; a provider disables an
endpoint that keeps failing.

- Fix: `isVerifiedPaymentWebhook()` exempts a POST that passes its route
  handler's own check (Gumroad `?secret=` with `timingSafeEqual`; Razorpay
  `verifyRazorpayHmac()` over a cloned body capped at 64 KiB). Unverified,
  oversized, non-POST or unreadable deliveries are metered as before; the
  handlers still verify everything. Runs only for `/api/webhooks/*`.
- Tests: `payment-webhook-metering.test.js` (7; 3 failed before: a signed
  order and a Gumroad sale from a busy provider IP were refused with 429).
  Mutations caught: no HMAC check, no Gumroad compare, no size cap, no method
  check, every webhook exempt. Found by the oversized-body test: a cancelled
  clone branch settles only when the original is cancelled too, so the capped
  reader does not await its cancel.
- Precondition for activating `RATE_STRONG_CONSISTENCY_ENABLED`: met on branch.

### F10 — Commercial claim drift beyond the contract gate (C07, R09) — MERGED (`c14dbae11`), live on Pages; follow-up F19

`verify_commercial_contract.py` passed (4,621 checks) while README.md and ~30
deployed pages contradicted the contract. Corrected, each against
`config/commercial-contract.json` or `sla.html`'s tier table:

- Quotas: "Unlimited" Enterprise/MSSP, FREE 100/day, hourly limits
  (60/2,000/20,000 req/hr), 500/2,000 req/min → 30/120/600/1,200 per minute,
  50/5,000/50,000/50,000 per day.
- Uptime/response: 99.95%/99.99%, "15-min SLA", "dedicated support" on
  Enterprise, PRO p95 <500ms → 99.5/99.9/99.9, 48h/4h/1h, PRO <800ms.
- Seats: 5 → 1/1/10/25. MSSP "Unlimited client seats" → 25 seats.
- `security-compliance.html`: bcrypt-hashed / HMAC-signed keys, per-key IP
  CIDR allowlisting, per-key scopes and CORS, admin MFA, TLS 1.3 minimum, CSP
  Level 3, SRI, 90-day audit retention. Checked against `index.js`, the static
  header rule and live headers (static pages: HSTS only; gateway: HSTS,
  nosniff, X-Frame-Options DENY, CSP on report HTML); replaced with what is
  implemented.
- `user-test-kit.html` (live) told buyers to send ₹4,100 to a UPI handle or
  paypal.me and submit a form for manual key delivery: the retired manual
  channel, outside the Razorpay/Gumroad mandate. Now Razorpay or Gumroad with
  automatic activation. Sub-processor lists name Razorpay and Gumroad (not
  PayPal) and the email providers the code calls (SendGrid, Resend).
- Social proof on `demo.html`, `enterprise.html`, `mssp.html`,
  `global-deployment.html`, `threats.html`: testimonials, "1,200+ SOC teams",
  "80+/50+ countries", "99.97% uptime", "45K+ reports" → checkable floors from
  `config/platform-evidence.json` and the SLA commitments.

Gates: the contract gate gains README.md and four claim classes (seats,
uptime above 99.9%, sub-hour response, unlimited quota), row-aware; the
public-claims gate catches claims split across elements; new
`tests/test_commercial_claims_convergence.py` (13) pins the plan tables to
the contract and the security copy to `index.js`. Both gates and the suite
now run on pull requests. Negative controls on the pre-fix pages: contract
gate 15 failures; suite 12/13 failing (the 13th pins `sla.html`, already
correct).

### F11 — Public internal revenue dashboard shows invented subscribers (R12) — QUARANTINED in build (#637), NOT YET LIVE (F20)

`dashboard/revenue_acceleration.html` is live (HTTP 200), linked from no page,
not in `robots.txt`, and renders hard-coded plan subscriber counts
(92/71/142/71), a "Pro Subscribers 71" goal and a `SUBSCRIBERS_DEMO` table of
invented subscriber emails with MRR. `build_dist_artifact.py` copies
`dashboard/` wholesale; `HTML_EXCLUDE_PREFIXES` covers root files only, which
is how earlier internal dashboards were withdrawn (v200.1/v200.2). Options:
per-file exclusion for `dashboard/` in the build (MEDIUM: deploy builder), or
wire the page to real data. Not changed here beyond one quota label.

Update: #637 excludes it, `conversion-analytics.html` and
`demo-conversion-center.html` (both carry invented customers and MRR) from
`dist/` (`INCLUDE_DIR_FILE_EXCLUDES`, `HTML_EXCLUDE_PREFIXES`). The first
publisher run on `d80c72643` then failed STAGE 5.4.6 (F20), so all three
still answered 200 at 11:54Z. They leave the site with the first Pages
deploy after #638 merges.

### F12 — Remaining product claims with no contract source (R09, R12, R20) — OWNER DECISION

Not contract terms, so not changed without an owner source:

- Data retention disagrees across pages: `trust-center.html` 7d/90d/1y/3y;
  `security-compliance.html` 7d/90d/12mo; `get-api-key.html` Enterprise
  "Historical data access (90 days)".
- Incident notification channels (`trust-center.html` "Slack + Email +
  Webhook" for MSSP): no Slack integration verified.
- `sla.html` card says "<500ms … All paid tiers" while its tier table says
  PRO <800ms (pages now follow the table).
- AWS (ap-south-1) in the `security-compliance.html` sub-processor list: no
  code reference found; kept (over-disclosure is the safe side) until
  confirmed. 2026-10-01: the `AWS_*` workflow credentials are R2 S3-API keys
  (`endpoint_url=CF_R2_ENDPOINT`); no AWS service is in use. Architecture
  claims of AWS compute were corrected (F19); the sub-processor line is the
  owner's call.
- Procurement-pack rows still without a source (F19 left them): security
  incident notification hours, data retention per tier, "critical CVE
  real-time push", MSSP margin (pack 25%, `mssp.html` 30%).
- `eula.html` "unlimited Authorized Users" vs 1/1/10/25 seats;
  `services.html` "UNLIMITED INCIDENTS"; `global-deployment.html` "99.99%"
  attributed to Cloudflare; "compliant" statements in `README.md`/privacy.
- Undeployed pages with superseded plans (not in `dist/`, HTTP 404):
  `sales/apex-datasheet.html` (TEAM $149, 60/500/1,000 req/min),
  `api-economy/developer-portal.html` (Starter $49 500/day, Enterprise $999,
  invented usage metrics), `landing/index.html`. Fix before any is deployed.

### F13 — Archive floor fails every publisher run and skips its post-deploy gates (R10, R15, R29) — MERGED, LIVE PASS (run 36826966415)

- Run 36815948964 (2026-10-01 04:37Z): STAGE 5.4.5b logged "HOT 22, ARCHIVE
  22,433 ... ABORT: HOT tier would have only 22 reports (minimum: 500)".
  `report_archive_manager.py` classifies by (year, month), so at the month
  boundary all of August turned ARCHIVE; the R2-first publisher commits only a
  handful of reports a month, so this recurs every run, every month.
- The abort returned 1, the step failed the job, and the 8 steps left on the
  default `success()` condition were skipped: Post-Deploy Smoke Tests,
  Manifest Integrity, Runtime Stability, Enterprise Monetization Framework,
  Deployment Canary, Report URL Canary, Manifest URL Repair, Production
  Release Gates. Build and deploy carry `!cancelled()` and ran: the feed
  published at 05:15:14Z without its post-deploy validation. All 8 ran in the
  last green run (36774798831).
- Fix: at the floor nothing is untracked, a `::warning::` annotation says so,
  exit 0. A git error still returns 1. Tests: `test_report_archive_floor.py`
  (4, pinned to the incident's clock and counts; 2 failed before).
- Live proof (run 36826966415 on `c14dbae11`, success, 07:32Z): STAGE 5.4.5b
  logged `Report archive skipped: HOT tier would have only 3 reports
  (minimum 500); nothing untracked.` with a `::warning::` and completed; the
  Pages deploy and all 8 previously skipped steps (154, 163, 164, 166, 167,
  168, 176, 178) ran and passed; Production Release Gates "CERTIFIED -- all
  5 gates passed". The next run (`d80c72643`) skipped them again for a
  different reason: F20.
- Not changed, owner decision: the step runs after STAGE 4's commit, so its
  `git rm --cached` is never committed (run 36774798831 untracked 7,359
  reports; `main` still tracks them). Either retire the step or move it
  before STAGE 4, which would untrack thousands of reports from `main` and
  change `config/platform-evidence.json` counts.

### F14 — Committed certification reports are 1–5 weeks old (R30–R34) — REPORTED

Both publisher runs logged `r2_resync: skipped stale
data/quality/p36_certification_report.json` and `p37` (~859h old, limit 6h).
On `main`, `data/quality/p26`–`p32` and `p34`–`p38` certification reports all
carry `generated_at` 2026-08-26 (last written by conflict-recovery commit
`39407bc53`) and `p33` 2026-09-24. The publisher's P34–P38 stages run each time,
but their output is not what is committed. None of these files is current
certification evidence; the P33 result cited in this ledger is recomputed
locally on each run, not read from the committed report.

### F15 — FREE/anonymous responses carried IOC values in `iocs_by_type` (R12, entitlement) — MERGED (#637), DEPLOYED, LIVE PASS

`applyTierGateV2()` cleared `iocs` but copied `iocs_by_type`. Live on
`c14dbae11` (07:01Z): 55 of 57 items in anonymous `/api/feed.json` and 29 of
57 in `/api/v1/intel/latest.json` carried IOC values. Fixed in #637 (both
carriers emptied for FREE, keys kept, paywall counts what was withheld; paid
tiers unchanged). Live on `d80c72643` (11:31Z): 58/58 items with no values,
23 paywalled; `/api/preview/` and `top10` masked. Left for the owner: the
repository's committed `api/feed.json` (2026-08-26) is public with IOC values.

### F16 — IOC extraction quality (R12) — REPORTED, P1

The extractor files article URLs as `url` IOCs and Java identifiers such as
`instantbuycontroller.java` as domains. Not changed this session (P0s first).

### F17 — Revocation and lifecycle changes are not immediate (R02) — COPY FIXED in PR #638 (`1227296b6`); runtime FinOps-BLOCKED

- Certification 36827638315 (07:01Z, `c14dbae11`): after PATCH to cancelled
  the key still got 200; after reactivation it got 401 and a fresh login 401;
  rotate read a stale `refunded` record and answered 409 (the remaining
  rotation failures cascade from the empty `NEW_KEY`). Run 36839516753 (08:56Z,
  `d80c72643`) passed the same matrix: nondeterministic, as Workers KV
  read caching predicts. `/api/sla/report` is not edge-cached (BROWSER bucket),
  so the stale answers come from `API_KEYS_KV.get`.
- Not a code regression; #596's authority (`AUTH_STRONG_CONSISTENCY_ENABLED`,
  reusing the `GUMROAD_PROVISIONING_LOCK` namespace) exists and is off by
  FinOps policy. Usage if enabled: 1–2 Durable Object requests per
  authenticated API-key request plus one per state change.
- Copy: pages promised immediate revocation with no overlap; now "within about
  a minute" (tied to the flag by a test). The admin rotate message is
  conditional on the flag (2 tests).
- Also noted: `applySubscriptionStatusChange` and rotation read-modify-write
  against KV, so a status PATCH on a just-rotated key within the cache window
  could rewrite its record. Narrow; also closed by the strong authority.

### F18 — The per-minute limiter never fires in production (R03) — REPRODUCED; PRODUCT + FinOps decision

- Live: cert phase 8 `200x33` on `c14dbae11` and `d80c72643`; probe 07:26Z,
  35 sequential anonymous GETs to `/api/sla/status` from one IP, all served by
  IAD, all 200.
- Cause: `checkRateLimit` uses `bumpCounterWriteThrough` (KV get then put on
  `rl:{ip}:{minute}`); the colo's KV read cache keeps returning the window's
  first value, so the count never advances. The 2026-09-28 move from
  isolate counters to write-through traded one split for another.
- Fix options, each a decision: (a) #596 rate authority (Durable Object per
  IP-minute; FinOps); (b) a per-colo Cache API counter (no new binding, about
  zero cost) — but effective enforcement then also throttles anonymous
  `/reports/*` page views (search crawlers) and the platform's own CI probes
  (report verifiers, convergence engine, capability probes), all of which
  reach the commercial gate today. Which paths are metered is a product call.
  Each metered request also writes KV, so an unthrottled client drives KV
  write cost.
- Customers are not harmed by an unenforced limit; the platform is (abuse and
  cost). Contract copy unchanged.

### F19 — Buyer pages described controls, deployments and APIs that do not exist — FIXED in PR #638 (`1227296b6`)

`enterprise-procurement-pack.html` ("copy directly into your vendor assessment
form"), `trust-center.html`, `reference-architecture.html`,
`global-deployment.html`, `mssp.html`, `compliance.html`,
`enterprise-homepage.html`: bcrypt/PBKDF2/"hashed" key storage, TOTP MFA,
RBAC roles, per-key scopes and IP allowlists, envelope encryption, 90-day
customer access logs, anomaly/geo alerting, OWASP/Trivy deploy blocking, an
annual pen test, AWS Mumbai compute and S3, India/EU/US/APAC data residency,
private Worker instances, Docker/Kubernetes and air-gapped installs, seven
`/api/v1/*` endpoints and `POST /api/v1/webhooks` (all 404 live), an
email/password login, and `security@cyberdudebivash.in` (security.txt says
`.com`). Each was checked against code, config or a live probe and replaced
with the implemented fact or "not offered". Ten withdrawn entries in
`config/evidence-register.json`; `verify_public_claims.py` flagged 31 hits on
7 pages and passes now.

### F20 — My regression: the Phase 7 quarantine failed STAGE 5.4.6 and skipped the Pages deploy — FIX IN PR #638 (green)

sentinel-blogger 36833320633 on `d80c72643`: `build_dist_artifact.py`'s
v157.0 route validator still listed `dashboard/revenue_acceleration.html`
and hard-failed after the prune; STAGE 5 and every post-deploy gate were
skipped. The feed still reached R2 (STAGE 3.5 is earlier). Reproduced locally
(exit 1); fixed by making the validator honor `INCLUDE_DIR_FILE_EXCLUDES`
(exit 0 locally; `dist_artifact_verifier.py` 0 failed). The Phase 7 tests had
covered the prune, not the validator after it; they now run the production
order copy → prune → validate.

### F21 — Gumroad purchases are not provisioned in production (R05) — OPERATOR-BLOCKED (P0)

`POST /api/webhooks/gumroad` answers 500 "Webhook secret not configured"
(11:33Z). Gumroad provisioning is webhook-only, and `upgrade.html` links four
Gumroad products, so a Gumroad buyer is charged and receives no key. Razorpay's
webhook is configured (401 on a bad signature).

Runbook (owner): `cd workers/intel-gateway && npx wrangler secret put
GUMROAD_WEBHOOK_SECRET --env production`; set the Gumroad ping URL to
`https://intel.cyberdudebivash.com/api/webhooks/gumroad?secret=<same value>`;
optionally set `GUMROAD_SELLER_ID`; then reconcile any sales made meanwhile
from the Gumroad sales export (each needs a key provisioned through the admin
API or a replayed ping). Until then, consider whether the Gumroad buttons
should stay up; removing a mandated provider is the owner's call.

## Paying-customer lifecycle (Phase 8, 2026-10-01, deployed `d80c72643`)

| Stage | Result | Evidence / blocker |
| --- | --- | --- |
| Pricing and plan terms | PASS | Contract gate 5,366/0; F10 live; F19 corrections in PR #638 |
| Checkout: Razorpay (INR) | configured; payment NOT TESTED | webhook rejects bad signature (401); verify validates input (400). A real charge needs explicit authorization or provider test mode |
| Checkout: Gumroad (USD) | **FAIL, P0** | F21: webhook secret unset, 4 products on sale |
| Provisioning | PASS via admin API | cert "Authenticated Customer Ops"; payment-triggered provisioning NOT TESTED live |
| Key delivery email | NOT TESTED | would send real email |
| First use, tier entitlements | PASS | cert; F15 FREE masking live PASS |
| Daily quota | approximate, not certified | isolate-batched counters seeded from KV |
| Per-minute limit | FAIL | F18 |
| Renewal (Razorpay subscription, Gumroad membership) | unit-tested; live NOT TESTED | needs provider test mode |
| Past due (grace) | PASS | both cert runs |
| Suspend / cancel / expire / refund deny | INTERMITTENT | F17 (FAIL 07:01Z, PASS 08:56Z) |
| JWT invalidated on suspension | PASS | both cert runs |
| Reactivation, rotation | INTERMITTENT | F17 |
| Expiry boundary | PASS | cert phase 4 |
| MSSP tenants: isolation, self-service, rotation | PASS | cert 36839516753 |
| Enterprise signed webhooks | BLOCKED | operator sink secrets |
| SLA report (Enterprise) | PASS (access) | cert; SLA uptime measurement method F6 |
| Offboarding / data deletion | NOT TESTED | process stated in privacy.html; no automated path verified |

Live surface (Phase 3, read-only): `/api/health` 200 fresh; `/taxii/` 200,
`/taxii/collections/` 401 anonymous (PRO+); `/api/reports/latest.json`,
`/api/v1/cve/live`, `/api/v1/ioc/lookup` 200; `/api/sla/report` 401
anonymous; HSTS on the site and the API.

## R01–R35 status

| ID | Status | Evidence / next step |
| --- | --- | --- |
| R01 | Root-caused; fix prepared, FinOps-blocked | F3 (scheduling evidence added 2026-10-01); runbook above |
| R02 | Open (#596), FinOps | F17: FAIL 07:01Z / PASS 08:56Z on the same matrix; copy now says "within about a minute" |
| R03 | 500→429 deployed; limiter never reaches the cap | F1, F18 (`200x33` live on two SHAs); product + FinOps decision |
| R04 | Fixed, live PASS | F2: MSSP rotation canary PASS in cert 36839516753 |
| R05 | Gumroad FAIL (P0, operator); Razorpay webhook configured | F21; signed deliveries need provider test mode (credential) |
| R06 | Latent risk fixed on branch | F9 (`d1c8f3e65`) |
| R07 | Partial live evidence | Cert 36690549981: MSSP isolation and self-service phases PASS |
| R08 | Partial | SAST run 36744969006 on `022ecae4` success; ESLint no-undef sweep of all Worker source (F1). Dependency scan not re-run here |
| R09 | F10 live; F19 in PR #638 | F10, F19 (`1227296b6`); remaining non-contract claims F12 |
| R10 | F13 live PASS; F20 regression, fix PR #638 | F4 (post-deploy validation not chained since 2026-09-24); F13 proven on run 36826966415; F20 on run 36833320633 |
| R11 | Open (#593) | Human review pending; unchanged |
| R12 | Partial | F10; F11 quarantined (not live until #638); F15 live PASS; F16 open |
| R13 | Verify | Not examined |
| R14 | Verify | Not examined |
| R15 | Gap, FinOps + owner | F3 (scheduler evidence), F7 (sla.html 4h term); cadence copy in PR #638 |
| R16 | Verify | Not examined |
| R17 | Verify | Not examined |
| R18 | Partial | Autonomous scheduler, PRO and MSSP canaries PASS (36839516753); Enterprise signed-webhook canary BLOCKED (`CDB_WATCHDOG_SINK_*`) |
| R19 | Open (#419/#420/#422) | Not examined |
| R20 | Copy fixed on branch; runtime gap | Seat counts now 1/1/10/25 everywhere deployed (F10); `eula.html` open (F12); no runtime seat concept exists, only API keys |
| R21 | Unchanged | `ENTITLEMENT_ENFORCEMENT_RESOURCES = cve_detail_full` |
| R22 | Operator | Prepared Cloudflare header rule not applied (2026-09-28 review) |
| R23 | Gap, owner decision | F6 |
| R24 | Verify | Not examined |
| R25 | Partial | Worker bundle 1684.41 → 1687.50 KiB (+0.18%), gzip 400.54 → 401.37 KiB |
| R26 | Verify | Not examined |
| R27 | Owner decision | F8 |
| R28 | Fixed on branch | API docs, reference card, developer portal and header semantics match the gateway (F10) |
| R29 | F5, F13 merged; F20 in #638 | F3, F4, F5, F13, F20 |
| R30–R34 | Verify | F14: committed P26–P38 certification reports are 1–5 weeks old |
| R35 | This ledger | — |

## Proof Before Change (this session)

| Change | Objective | Files | Engines reused | Evidence | Risk | Rollback |
| --- | --- | --- | --- | --- | --- | --- |
| F1 `5efa55206` | 429 at the cap, never 500 | `index.js`, new test | checkRateLimit, bumpCounterWriteThrough, incrementStrongRate, buildUpgradeTrigger | no-undef; local reproduction; phase 8 never saw 429 | LOW | revert |
| F2 `5f8a3cb4f` | Operator actions not throttled by anonymous budgets | `index.js`, new test | timingSafeEqual, isWatchdogOperator, checkRateLimit, checkDailyQuota | code path; 3 live cert failures; local reproduction | LOW | revert |
| Diagnostics `89a25865a` | Certification shows what the limiter and rotation answered | commercial certification workflow | existing jobs | "0 = never seen" / "no key" hid F1 | LOW (stricter: 5xx now fails) | revert |
| F3 `8f37c95ea` | Reliable freshness self-heal trigger | new module, `index.js` cron branch, `wrangler.toml`, guard policy + test | intel_freshness_guard.py decision logic, existing cron | guard 5/48 runs/day; 07:51→15:33 gap | LOW (dormant) | revert or flag `"false"` |
| F9 `d1c8f3e65` | Provider deliveries never refused by anonymous budgets | `index.js`, new test | verifyRazorpayHmac, timingSafeEqual, F2 gate pattern | route order + resolveAuth; 3 tests 429 before | LOW (two routes; handlers unchanged) | revert |
| F13 `02128ebd7` | A protective no-op cannot fail the publisher job | `report_archive_manager.py`, `sentinel-blogger.yml` (comments, one message), new test, regression gate | the script's floor and git helpers | run 36815948964 log and skipped steps vs 36774798831 | LOW (one return path) | revert |
| F5 `494446a09` | Derived writers serialize with themselves, not the core publisher, as #563 was reviewed to do | 7 workflows, regression gate suite line | #563's groups, #570's wording | `git show d1842a138`; no `concurrency` key after YAML parse; test failed on `main` | LOW (adds per-workflow queuing; no step changes) | revert |
| F10 `b6d40c13b` | Buyer copy equals enforced terms | README.md, 30 pages, 2 gates, evidence register, new suite, regression-gate workflow | commercial-contract.json, platform-evidence.json, both gates extended in place | pages vs contract; code and live headers for security copy | LOW (static copy; CI additions only) | revert |
| F15 (#637) | No IOC value in any FREE response | `revenue-enforcement.js`, new test | applyTierGateV2, enforceTierGate (canonical mask, bug fix) | live sweep on `c14dbae11` | LOW (less data, same shape) | revert |
| Phase 7 (#637) | Invented business data off the site | `build_dist_artifact.py`, new test, regression gate | HTML_EXCLUDE_PREFIXES, copy_item | three pages with invented customers/MRR | LOW → caused F20 | revert with F20 |
| F20 `dd4eba3d3` (#638) | Pages deploys again with the quarantine | `build_dist_artifact.py`, test | INCLUDE_DIR_FILE_EXCLUDES, copy_item, prune | run 36833320633; local exit 1 → 0 | LOW (one validator branch) | revert with Phase 7 |
| F17/F19 `1227296b6` | Buyer security copy states implemented controls only | 9 pages, evidence register, convergence test, `index.js` (one string), rotation test | evidence register + verify_public_claims, sla.html, contract | per-claim code/config/live checks | LOW (copy + one response string) | revert |
| Phase 6 `1d94967ce` | No cadence promise the scheduler cannot keep | 6 pages, evidence register | evidence register + gate | scheduled-run delivery and breach windows | LOW (copy) | revert |

Blast radius (F10): no route, Worker, schema, auth or payment code; pages
only change copy; `config/frontend_checksums.json` regenerated for
`index.html`; CI gains one pytest file, one gate step and four path filters.

Blast radius (F1–F3): routes — the 429 response of every commercial-plane
route (was 500) and metering of the five operator routes; dashboards — none
changed (admin/operator pages benefit); CI — gateway regression gate,
commercial certification, R2 FinOps gate (guard test); certification reports —
none; `/api/v1/p*` shapes — unchanged; data schema — none (fewer
`RATE_LIMIT_KV` writes); workflows — commercial certification (diagnostics).

## Validation (this session, local)

- Gateway unit suite: 1620 → 1638 tests, all passing, raw and after
  `scripts/sanitize_encoding.py --fix` (deploy-pipeline replica).
- Watchdog negative controls exit 0; dashboard negative controls 31/31 caught.
- `entitlement_resource_drift_gate.py` PASS; `worker_js_integrity_gate.py`
  74/74; `verify_commercial_contract.py` 4,621/0; `verify_public_claims.py`
  5,399/0; `generate_platform_evidence.py --check` PASS.
- `regression_tests.py` 41/41 (CLAUDE.md's "21/21" is stale); P33
  WORLDWIDE_RELEASE, 0 blockers; `ci_stats_extract.py p33` valid.
- Workflow-related pytest files: 506 passed; 3 pre-existing failures (F5).
- wrangler 4.142.0 `deploy --dry-run --env production`: bundle builds.
- F9 (`d1c8f3e65`): gateway suite 1,645/1,645; watchdog (98 caught), dashboard
  31/31 and billing 101/101 negative controls; worker_js_integrity 75/75;
  ESLint no-undef 0 in `index.js`; wrangler dry-run 1,687.50 → 1,689.20 KiB
  (+0.10%), gzip 401.37 → 401.83 KiB, both measured this session.
- F13 (`02128ebd7`): PR python suites 1,843 passed; workflow-reading suites
  529 passed (1 pre-existing F5 failure, identical on HEAD); ci_preflight 9/9;
  python governance 0/482; validate_repo 9/9; regression 41/41; P33
  WORLDWIDE_RELEASE, 0 blockers.
- F5 (`494446a09`): `test_workflow_concurrency_scoping` 2/2 (1 failed on
  `main`); PR python suites 1,845 passed; workflow-hygiene gate 28 passed; all
  13 test files that read `.github/workflows` pass (197).
- R09 (`b6d40c13b`): PR python suites 1,839 passed; 27 other page-reading
  suites 502 passed / 1 skipped; gateway suite 1,638/1,638; billing negative
  controls 101/101; `verify_commercial_contract.py` 5,366/0;
  `verify_public_claims.py` 13,577/0; frontend integrity PASS; regression
  41/41; P33 WORLDWIDE_RELEASE, 0 blockers.

- 2026-10-01 (after the #636/#637 merges): F20 on a clean tree — build-script
  suites 44 passed, regression-gate Python suites 1,854 passed, regression
  41/41, ci_preflight 9/9, validate_repo 9/9, governance 0/482, P33
  WORLDWIDE_RELEASE 0 blockers; full local dist build exit 1 → 0;
  dist verifier 0 failed; PR #638 CI all green.
- F17/F19 and Phase 6 (local): gateway suite as CI runs it 1,654/1,654 (+2
  rotation tests); regression-gate and page-reading suites 1,977 and 1,965
  passed; `verify_public_claims.py` PASS after 31 + 2 hits fixed;
  `verify_commercial_contract.py` 5,366/0; frontend integrity PASS; worker JS
  integrity 75/75; entitlement drift PASS; HTML tag balance unchanged on every
  edited page.
- Live probes 2026-10-01 (read-only or rejected-input only, no transactions):
  `/api/health/live` provenance; F15 sweep; webhook configuration (unsigned
  POSTs); payment verify input validation; 35-request limiter boundary (same
  shape as certification phase 8); quick-start endpoint existence.

## Reuse report

| Metric | Result |
| --- | --- |
| Existing engines reused | checkRateLimit, bumpCounterWriteThrough, incrementStrongRate, checkDailyQuota, buildUpgradeTrigger, timingSafeEqual, isWatchdogOperator, intel_freshness_guard.py; R09: verify_commercial_contract.py and verify_public_claims.py extended in place, driven by commercial-contract.json / evidence-register.json / platform-evidence.json; F9: verifyRazorpayHmac, timingSafeEqual; F13: report_archive_manager.py floor (behaviour kept, exit status corrected); F15: applyTierGateV2 (canonical mask fixed in place); F20: INCLUDE_DIR_FILE_EXCLUDES and the v157.0 validator (refactored into a function, same messages); F17/F19/Phase 6: evidence register + verify_public_claims.py (data-driven, no new gate) |
| Existing routes extended | none added; commercial gate condition extended |
| Existing dashboards extended | none |
| New engines | 1: `freshness-guard-dispatch.js` (no GitHub-dispatch path existed in the Worker) |
| Duplicate engines / routes | 0 / 0 |
| Backward compatibility | PASS (response shapes unchanged; 500 → documented 429) |
| Certification chain | PASS (P33 WORLDWIDE_RELEASE) |
| Regression suite | 41/41 PASS |
