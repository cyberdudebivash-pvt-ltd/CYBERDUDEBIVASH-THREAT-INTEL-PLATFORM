# Customer release ledger — Sentinel APEX

The one living task ledger for customer-release acceptance (backlog R01–R35 of
the 2026-09-30 handoff). Dated reviews such as
[CUSTOMER_RELEASE_REVIEW_20260928.md](CUSTOMER_RELEASE_REVIEW_20260928.md)
stay as point-in-time records; this file carries current status. Update it in
the same PR as the change that moves a row. Historic evidence is never reused
as current certification.

Last updated: 2026-10-01T06:05Z, branch `claude/charming-thompson-ptma8e`.

## Decision

**HOLD** global customer-release certification. Nothing below is deployed until
the branch is merged and `deploy-worker.yml` ships it; then the commercial
certification workflow must run on the exact deployed SHA.

| SKU / capability | Status | Blocking evidence |
| --- | --- | --- |
| FREE API | HOLD | Rate-limit 429 fix (F1) not yet deployed; live phase 8 never observed a 429 |
| PRO | HOLD | Lifecycle consistency #596 intermittent under KV; F1/F2 pending deploy |
| ENTERPRISE | HOLD | As PRO, plus Watchdog signed-webhook canary `BLOCKED_BY_SINK` |
| MSSP | HOLD | MSSP rotation canary failing live (F2 fix pending deploy) |
| Malware review package | HOLD | #593: independent human review pending |
| Swarm live operations | HOLD | #419/#420/#422 not re-verified this session |
| Publisher post-deploy validation | DEGRADED since 2026-10-01T04:37Z | Every `sentinel-blogger` run fails at STAGE 5.4.5b and skips 8 post-deploy gates (F13). Fix on branch; it takes effect only once merged to `main` |

## Provenance at this update

| Component | Value | Evidence |
| --- | --- | --- |
| `main` | `1b8098c96` | Dependabot action bumps after `f59387a` (#633–#635); no gateway source change; this branch merges cleanly |
| Deployed gateway | `f59387a735e34b75bdaf9a8523c75040fe2eae29`, deploy run 36688506844 | `GET /api/health/live` 2026-09-30 16:59Z–18:23Z and 2026-10-01 05:50Z |
| Live health | 200, `ok`, generated 2026-10-01T05:15:14Z, 57 advisories | `GET /api/health` at 2026-10-01T05:50Z |
| Branch commits | `5efa55206`, `5f8a3cb4f`, `89a25865a`, `8f37c95ea`, `a3f8d851c` (ledger), `b6d40c13b` (R09), `481319176` (ledger), `d1c8f3e65` (F9), `02128ebd7` (F13) | `git log` |

Overnight 2026-09-30/10-01, from `generated_at` values the publisher's own
freshness gate logged (no probe sampled either window; this session
triggered no production pipeline):

| Window (UTC) | Feed | Evidence |
| --- | --- | --- |
| 21:33:57 → ~21:45 (≈11 min) | over the 6h contract | guard run 36774781090 (20:44:53Z) dispatched publisher 36774798831; new generation 21:44:52Z |
| 03:44:52 → ~05:15 (≈1h30m) | over the 6h contract | guard's last run 00:29:47Z (36796464941); SLA heartbeat's last 02:23:40Z; next generation 05:15:14Z (scheduled run 36815948964) |

## Findings and changes this session

### F1 — Commercial rate limit answered HTTP 500 instead of 429 (C02, R03) — FIXED on branch

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

### F2 — Operator control-plane calls metered as anonymous FREE traffic (C05, R02, R04) — FIXED on branch

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

### F5 — Failing tests that CI never runs (R29) — REPORTED

- `tests/test_workflow_concurrency_scoping.py` is in the
  `intel-gateway-regression-gate.yml` suite list, but inside one bash comment
  line that contains literal `\n` sequences, so it is never executed. It fails
  today (`arsenal.yml: missing top-level concurrency.group`).
- `tests/test_deploy_provenance_contract.py` and
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

### F8 — Legal entity naming (R27) — OWNER DECISION

`README.md` and many footers say "CYBERDUDEBIVASH Pvt. Ltd."; the contract's
`seller_legal` is an individual ("BIVASHA KUMAR NAYAK") trading as
CYBERDUDEBIVASH(R). Invoices and terms must name the actual seller.

### F9 — Payment webhooks metered as anonymous FREE traffic (R05, R06) — FIXED on branch (`d1c8f3e65`)

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

### F10 — Commercial claim drift beyond the contract gate (C07, R09) — FIXED on branch (`b6d40c13b`)

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

### F11 — Public internal revenue dashboard shows invented subscribers (R12) — REPORTED, OWNER DECISION

`dashboard/revenue_acceleration.html` is live (HTTP 200), linked from no page,
not in `robots.txt`, and renders hard-coded plan subscriber counts
(92/71/142/71), a "Pro Subscribers 71" goal and a `SUBSCRIBERS_DEMO` table of
invented subscriber emails with MRR. `build_dist_artifact.py` copies
`dashboard/` wholesale; `HTML_EXCLUDE_PREFIXES` covers root files only, which
is how earlier internal dashboards were withdrawn (v200.1/v200.2). Options:
per-file exclusion for `dashboard/` in the build (MEDIUM: deploy builder), or
wire the page to real data. Not changed here beyond one quota label.

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
  confirmed.
- `eula.html` "unlimited Authorized Users" vs 1/1/10/25 seats;
  `services.html` "UNLIMITED INCIDENTS"; `global-deployment.html` "99.99%"
  attributed to Cloudflare; "compliant" statements in `README.md`/privacy.
- Undeployed pages with superseded plans (not in `dist/`, HTTP 404):
  `sales/apex-datasheet.html` (TEAM $149, 60/500/1,000 req/min),
  `api-economy/developer-portal.html` (Starter $49 500/day, Enterprise $999,
  invented usage metrics), `landing/index.html`. Fix before any is deployed.

### F13 — Archive floor fails every publisher run and skips its post-deploy gates (R10, R15, R29) — FIXED on branch (`02128ebd7`)

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
- Not changed, owner decision: the step runs after STAGE 4's commit, so its
  `git rm --cached` is never committed (run 36774798831 untracked 7,359
  reports; `main` still tracks them). Either retire the step or move it
  before STAGE 4, which would untrack thousands of reports from `main` and
  change `config/platform-evidence.json` counts.

### F14 — P36/P37 certification reports are 35 days old (R30–R34) — REPORTED

Both publisher runs logged `r2_resync: skipped stale
data/quality/p36_certification_report.json` and `p37` (`generated_at`
2026-08-26, ~859h old, limit 6h): the pipeline does not regenerate them, so
they are not current certification evidence.

## R01–R35 status

| ID | Status | Evidence / next step |
| --- | --- | --- |
| R01 | Root-caused; fix prepared, operator-blocked | F3; runbook above |
| R02 | Open (#596) | Intermittent under KV; strong authority dormant by FinOps policy. F2 removes a confounder for admin lifecycle calls |
| R03 | Defect fixed on branch; live proof pending | F1; next certification phase 8 histogram |
| R04 | Probable cause fixed on branch | F2; next certification rotation status |
| R05 | Not verified live | Needs authorized Razorpay/Gumroad test mode; webhook metering fixed on branch (F9) |
| R06 | Latent risk fixed on branch | F9 (`d1c8f3e65`) |
| R07 | Partial live evidence | Cert 36690549981: MSSP isolation and self-service phases PASS |
| R08 | Partial | SAST run 36744969006 on `022ecae4` success; ESLint no-undef sweep of all Worker source (F1). Dependency scan not re-run here |
| R09 | Fixed on branch; deploy pending | F10 (`b6d40c13b`); remaining non-contract claims F12 |
| R10 | Gap reported; publisher gap fixed on branch | F4 (post-deploy validation not chained since 2026-09-24); F13 (publisher's own post-deploy gates skipped since 2026-10-01 04:37Z); deploy-worker exact-SHA smoke still runs |
| R11 | Open (#593) | Human review pending; unchanged |
| R12 | Partial | README metrics now point to live endpoints (F10); internal revenue dashboard F11 |
| R13 | Verify | Not examined |
| R14 | Verify | Not examined |
| R15 | Gap | F3, F7; two over-contract windows overnight 2026-10-01 (see provenance) |
| R16 | Verify | Not examined |
| R17 | Verify | Not examined |
| R18 | Partial | Autonomous scheduler canary PASS (36690549981); Enterprise webhook canary needs `CDB_WATCHDOG_SINK_*` secrets |
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
| R29 | Gaps reported; F13 fixed on branch | F3, F4, F5, F13 |
| R30–R34 | Verify | F14: P36/P37 certification reports stale |
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
| F10 `b6d40c13b` | Buyer copy equals enforced terms | README.md, 30 pages, 2 gates, evidence register, new suite, regression-gate workflow | commercial-contract.json, platform-evidence.json, both gates extended in place | pages vs contract; code and live headers for security copy | LOW (static copy; CI additions only) | revert |

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
- R09 (`b6d40c13b`): PR python suites 1,839 passed; 27 other page-reading
  suites 502 passed / 1 skipped; gateway suite 1,638/1,638; billing negative
  controls 101/101; `verify_commercial_contract.py` 5,366/0;
  `verify_public_claims.py` 13,577/0; frontend integrity PASS; regression
  41/41; P33 WORLDWIDE_RELEASE, 0 blockers.

## Reuse report

| Metric | Result |
| --- | --- |
| Existing engines reused | checkRateLimit, bumpCounterWriteThrough, incrementStrongRate, checkDailyQuota, buildUpgradeTrigger, timingSafeEqual, isWatchdogOperator, intel_freshness_guard.py; R09: verify_commercial_contract.py and verify_public_claims.py extended in place, driven by commercial-contract.json / evidence-register.json / platform-evidence.json; F9: verifyRazorpayHmac, timingSafeEqual; F13: report_archive_manager.py floor (behaviour kept, exit status corrected) |
| Existing routes extended | none added; commercial gate condition extended |
| Existing dashboards extended | none |
| New engines | 1: `freshness-guard-dispatch.js` (no GitHub-dispatch path existed in the Worker) |
| Duplicate engines / routes | 0 / 0 |
| Backward compatibility | PASS (response shapes unchanged; 500 → documented 429) |
| Certification chain | PASS (P33 WORLDWIDE_RELEASE) |
| Regression suite | 41/41 PASS |
