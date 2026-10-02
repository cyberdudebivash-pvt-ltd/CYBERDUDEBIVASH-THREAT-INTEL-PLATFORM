# Customer release ledger — Sentinel APEX

The one living task ledger for customer-release acceptance (backlog R01–R35 of
the 2026-09-30 handoff). Dated reviews such as
[CUSTOMER_RELEASE_REVIEW_20260928.md](CUSTOMER_RELEASE_REVIEW_20260928.md)
stay as point-in-time records; this file carries current status. Update it in
the same PR as the change that moves a row. Historic evidence is never reused
as current certification.

Last updated: 2026-10-02T12:45Z, branch `claude/charming-thompson-ptma8e`.
The payment and commercial release blocker closure merged as #643 →
`b516e7bb2` and is deployed. This change adds its post-merge verification
and the F26 fix, which is not yet merged.

## Decision

**HOLD.** Not RELEASE or CONDITIONAL RELEASE. Here is why:

- The certification run against the deployed SHA fails (Phase 8) and has a
  BLOCKED mandatory canary.
- No payment has gone end to end through either provider. The Razorpay
  checkout, webhook activation and key display are proven by tests and by
  configuration probes only; a live run needs provider test mode or explicit
  authorization (checkout P0).
- Gumroad purchases are not provisioned in production (F21). The checkout
  has not offered Gumroad since #639, and after this pass no page offers
  it unconditionally. The four access products can still be bought by
  direct link until the owner unpublishes them or sets the webhook secret
  ([runbook §1](PAYMENT_RELEASE_OPERATOR_RUNBOOK.md#1-f21-gumroad-production-safety)).
- F22 is decided: on 2026-10-02 the owner ruled that a raw API key is
  never emailed. This pass implements it: an email carries only a
  one-time link that reveals the key once, at the gateway. Merged as #643
  and deployed at 12:23Z. The Razorpay activation notice stays off until the
  owner sets `KEY_EMAIL_DELIVERY_ENABLED` and `SENDGRID_API_KEY`.
- Payment release closure P0 (#641 → `acc38a24d`, deployed 04:03Z) fixes
  three P0 payment-to-entitlement defects found in this pass (P0-1 legacy
  Razorpay webhook provisioned any captured payment; P0-2 the daily check
  locked out paying Razorpay subscribers; P0-3 a failed Gumroad
  provisioning was never retried). Proven by tests and negative controls;
  no live payment has exercised them.
- Lifecycle state changes are only eventually consistent (F17).
- The per-minute limiter does not fire (F18).
- The feed breached its freshness threshold twice overnight (F3).
- The Enterprise and MSSP premium feeds (`/api/v1/premium/feed/*`) are
  rebuilt every run from items published 2026-08-19 to 2026-08-26 (F26,
  measured this pass).
- `main` has no required status checks, so GitHub does not stop a merge
  while a check is red or pending. Changing that needs a repository
  admin.

Pages deploys again: #638 merged as `8b2d82862`, publisher run 36859743101
passed STAGE 5.4.6 and ran STAGE 5 and every post-deploy gate (F20 resolved).

Checkout P0 is live: #639 merged as `aa97c8366`, and the gateway, the revenue
engine and Pages deployed it. The live checks pass (127/127 browser checks at six
widths, 30/30 static checks, billing canary 14/15 with F21 the only failure).
That verifies the checkout's presentation and gating. It does not verify payment to
entitlement: no live payment was run.

### Release evidence matrix (2026-10-01, deployed `aa97c8366`)

| Control | Implemented | Tested | Deployed | Live verified | Blocker | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| FREE responses carry no IOC values (F15) | yes | 6 tests, 3 fail pre-fix | `d80c72643` | PASS | — | 11:31Z: `/api/feed.json`, `/api/v1/intel/latest.json` 58 items, 0 with values, 23 paywalled; `/api/preview/` and `top10` masked |
| 429 at the per-minute cap (F1) | yes | 4 tests | yes | FAIL: limiter never reaches the cap | product + FinOps (F18) | cert 36839516753 phase 8 `200x33`; probe 07:26Z 35/35 200 in IAD |
| Operator calls not metered (F2) | yes | 7 tests | yes | PASS | — | cert 36839516753: "MSSP rotation preserves membership: PASS" |
| Verified webhooks not metered (F9) | yes | 10 tests | yes | NOT TESTED with signed deliveries | credential (provider test mode) | — |
| Razorpay webhook configured | yes | — | yes | PASS | — | 11:33Z unsigned POST → 401 "Signature mismatch" |
| Gumroad webhook configured | code yes | — | secret missing | FAIL (P0) | operator secret (F21) | 11:33Z, 12:17Z and 19:30Z (billing canary, public mode) → 500 "Webhook secret not configured". Since 19:36Z the live checkout does not offer Gumroad: `/api/pricing` reports `available: false` and the button is hidden at every width |
| Lifecycle deny/reactivate/rotate takes effect immediately | KV only; strong authority dormant | cert matrix | yes | INTERMITTENT: FAIL 07:01Z, PASS 08:56Z | FinOps (#596 auth authority) | F17 |
| Expiry boundary, tier entitlements, MSSP isolation and self-service | yes | cert | yes | PASS | — | cert 36839516753 |
| Enterprise signed-webhook canary | yes | cert | yes | BLOCKED | operator (`CDB_WATCHDOG_SINK_*`) | `OPERATOR_WEBHOOK_SINK_REQUIRED` |
| Publisher post-deploy gates run (F13) | yes | 4 tests | `8b2d82862` | PASS on c14dbae11 and 8b2d82862 | — | runs 36826966415, 36859743101 (steps 153–186 success, 13:24Z) |
| Pages deploys | yes | 9 tests | `8b2d82862` | PASS | — | run 36859743101: STAGE 5.4.6, STAGE 5 success (F20) |
| Feed age ≤ 6h | publisher on GitHub cron | — | — | FAIL twice overnight | FinOps (R01 activation) | F3, F7 |
| Buyer security/compliance copy matches implementation (F17, F19) | yes | gates + tests | `8b2d82862` | PASS | — | 18:16Z procurement pack: no bcrypt / scope-bitmap / request-signing claims, security contact decodes to the .com address; 18:58Z security page says "about a minute" |
| No fixed refresh cadence outside sla.html (Phase 6) | yes | gates | `8b2d82862` | PASS | — | 18:58Z executive-briefing and pricing carry no fixed cadence |
| Invented business data off the site (Phase 7) | yes | 9 tests | `8b2d82862` | PASS | — | 18:16Z: all three pages 404 |
| Checkout: Razorpay the one primary path, Gumroad offered only when it can activate access, assisted note only, inline failures (checkout P0) | yes | 95 browser checks, 12 static, 3 gateway, 2 revenue; 10/10 page mutations and 2 billing controls caught | `aa97c8366` (Pages run 36914356330) | PASS | — | 127/127 live browser checks (320–1280 px), 30/30 static; Checkout P0 → Post-merge verification |
| A paid checkout's retry cannot open a second payment (checkout P0) | yes | 2 tests + control | `aa97c8366` (revenue run 36914355894) | NOT TESTED live (needs a paid checkout) | provider test mode or explicit authorization | tests and the negative control ran in CI on the merged head |
| Payment → entitlement → key, live | yes | cross-worker certified in tests | yes | NOT TESTED | provider test mode or explicit authorization | no real charge was made |
| Key delivery email (Razorpay) | sender fixed, off by default (F22) | 6 tests, 2 controls | `acc38a24d` | NOT TESTED (would send real email) | owner flag + `SENDGRID_API_KEY` (F22) | before: `queueEmail` without `send_at` was never selected by `runDailyOutreach`. Superseded by the next row: the notice now carries a one-time link, never the key |
| No raw API key in any email; one-time key link (F22, owner decision 2026-10-02) | yes | 12 tests; 9 controls | `b516e7bb2` (gateway run 37006160812, revenue run 37006160913) | PASS for every refusal path (12:23Z); a live redemption NOT TESTED (needs an issued link) | — | Post-merge verification (#643) |
| Gumroad not offered while it cannot provision (F21) | yes | withdrawn-claim gate (17 variants) | `b516e7bb2` (Pages run 37006160911) | PASS: 12:26Z, none of the 17 variants on any of the 15 pages; checkout `available: false`. The four access products still answer 200 by direct link (08:33Z) | owner: unpublish, or set the secret | [runbook §1](PAYMENT_RELEASE_OPERATOR_RUNBOOK.md#1-f21-gumroad-production-safety) |
| Premium feeds current (F26) | yes (this PR) | 10 tests; 3 workflow mutations caught | publisher, first run after merge | FAIL until then: the 05:58Z run uploaded all four from items dated 2026-08-19 to 08-26 | merge, then the next publisher run | F26 |
| Required status checks on `main` | readiness yes: both gates report on every PR (CI-reporting change) | 3 readiness tests | CI | FAIL: ruleset 21556637 has no required-status-checks rule | repository admin ([runbook §8](PAYMENT_RELEASE_OPERATOR_RUNBOOK.md#8-required-status-checks-on-main-repository-admin)) | Payment and commercial release blocker closure |
| Legacy Razorpay Orders provision only this gateway's Orders at the exact price (P0-1) | yes | 7 tests, 4 controls | `acc38a24d` | NOT TESTED live | — | payment release closure P0 |
| Razorpay renewals: no lockout after the daily check, renewal grace, Plan binding, claim release, one key per subscription (P0-2, P1-1..4) | yes | 14 tests, 8 controls | `acc38a24d` | NOT TESTED live | provider test mode | payment release closure P0 |
| Gumroad provisioning failure retried with one key (P0-3) | yes | 5 tests, 2 controls | `acc38a24d` | NOT TESTED live | F21 secret | payment release closure P0 |
| SAST classifier without full-history checkout | yes | 33 tests + 16 subtests, mutations caught | `acc38a24d` (CI) | PASS: classify step 1 s on PR run 1134 (2 commits fetched in 1 s), 0 s on push run 1135; was 207 s of checkout | — | payment release closure P0 → SAST classifier |

| SKU / capability | Status | Blocking evidence |
| --- | --- | --- |
| FREE API | HOLD | Per-minute limit not enforced live (F18) |
| PRO | HOLD | Lifecycle immediacy intermittent (F17); Gumroad checkout unprovisioned (F21; not offered on the live checkout since #639); payment E2E not tested; one-time key link (F22) not yet deployed |
| ENTERPRISE | HOLD | As PRO; signed-webhook canary BLOCKED; 4-hour freshness term unsupported (F7); premium feeds serve August items (F26) |
| MSSP | HOLD | As ENTERPRISE (rotation canary now PASS) |
| Malware review package | HOLD | #593: independent human review pending |
| Swarm live operations | HOLD | #419/#420/#422 not re-verified |
| Publisher post-deploy validation | Restored | F20 resolved: run 36859743101 ran every post-deploy gate |

## Provenance at this update

| Component | Value | Evidence |
| --- | --- | --- |
| `main` | `b516e7bb2` | #636 → `c14dbae11` (tree = reviewed head `82d9b7b5c`); #637 → `d80c72643` (tree = `ce348b2a2`); #638 → `8b2d82862` (tree `fa08a0feb`); #639 squash-merged 19:26Z → `aa97c8366` (tree `6cfc4fa5f` = reviewed head `baaf2ffee`); #640 (ledger only) → `5911a9722`, which deploys no Worker; #641 squash-merged 04:01:40Z by the repository owner → `acc38a24d` (tree `150d41a13` = reviewed head `5c6c6a8ad`); #642 squash-merged 07:02:33Z → `fcb252bd7` (tree `fe9f549e2` = reviewed head `2d4f922ae`; regression gate on `main` green, run 36976506794), which deploys no Worker; #643 squash-merged 12:21:02Z → `b516e7bb2` (tree `f1df2be36` = reviewed head `578fdaa49`) |
| Deployed gateway | `b516e7bb2bd0b1c1d0c8ba6c7f939830ac9ce3d6`, deploy run 37006160812 (12:23Z) | `GET /api/health/live` 12:23Z: `deploy_commit_sha`, `deploy_run_id` 37006160812 |
| Deployed revenue engine | `b516e7bb2`, deploy run 37006160913 (12:22Z) | run conclusion success |
| Pages | `b516e7bb2`, pages-fast-publish run 37006160911 (all pre-deploy browser gates) | live pages checked 12:26Z (Post-merge verification (#643)) |
| Live health | 200 `ok`, freshness FRESH; feed generated 2026-10-01T21:36:32Z (age 4h13m, limit 6h), 61 items. At 19:38Z: generated 16:01:55Z (age 3h37m), 63 items | `GET /api/health`, `/api/watchdog/health` 2026-10-02T01:50Z and 2026-10-01T19:38Z |
| Re-check 2026-10-02T01:50Z | gateway still `aa97c8366`; `/api/pricing` `checkout` block unchanged; live `upgrade.html` still the #639 page | read-only GETs |
| Re-check 2026-10-02T03:17Z | gateway still `aa97c8366` | `GET /api/health/live` |
| Open PR | F26 premium baseline fix and #643 post-merge verification (this change) | — |

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

### F20 — My regression: the Phase 7 quarantine failed STAGE 5.4.6 and skipped the Pages deploy — RESOLVED, LIVE PASS

sentinel-blogger 36833320633 on `d80c72643`: `build_dist_artifact.py`'s
v157.0 route validator still listed `dashboard/revenue_acceleration.html`
and hard-failed after the prune; STAGE 5 and every post-deploy gate were
skipped. The feed still reached R2 (STAGE 3.5 is earlier). Reproduced locally
(exit 1); fixed by making the validator honor `INCLUDE_DIR_FILE_EXCLUDES`
(exit 0 locally; `dist_artifact_verifier.py` 0 failed). The Phase 7 tests had
covered the prune, not the validator after it; they now run the production
order copy → prune → validate.

Post-merge (#638 → `8b2d82862`): deploy-worker 36859743117 success (12:10Z);
sentinel-blogger 36859743101 success (13:24Z) with STAGE 5.4.6, 5.4.6b,
5.4.7, STAGE 5 and the post-deploy gates (steps 153, 154, 163, 164, 166,
167, 168, 176, 178, 186) all success. Live at 18:16Z: the three quarantined
pages answer 404.

### F21 — Gumroad purchases are not provisioned in production (R05) — OPERATOR-BLOCKED (P0); recovery defect P0-3 fixed and deployed (#641); unconditional Gumroad copy removed (#643, live 12:26Z)

`POST /api/webhooks/gumroad` answers 500 "Webhook secret not configured"
(11:33Z, still at 19:30Z). Gumroad provisioning is webhook-only. Until #639,
`upgrade.html` linked four Gumroad products, so a Gumroad buyer was charged
and received no key. Razorpay's webhook is configured (401 on a bad signature).

Since #639 (live 19:36Z) the checkout hides Gumroad while the gateway reports it
cannot provision, and no shipped page links the four access products. They
are still purchasable by direct URL (`/l/pxyfcb`, `/l/xtnzu`, `/l/cdedlo`,
`/l/vxoczs` answer 200 at 19:33Z). The storefront's server-rendered list
shows nine other products, none of them access grants; Gumroad delivers
those itself. Until the secret is set, the owner may unpublish the four
access products on Gumroad so an old link cannot take a payment.

Runbook (owner): `cd workers/intel-gateway && npx wrangler secret put
GUMROAD_WEBHOOK_SECRET --env production`; set the Gumroad ping URL to
`https://intel.cyberdudebivash.com/api/webhooks/gumroad?secret=<same value>`;
optionally set `GUMROAD_SELLER_ID`; then reconcile any sales made meanwhile
from the Gumroad sales export (each needs a key provisioned through the admin
API or a replayed ping). Until then, consider whether the Gumroad buttons
should stay up; removing a mandated provider is the owner's call.

Audit 2026-10-02 ([runbook §1](PAYMENT_RELEASE_OPERATOR_RUNBOOK.md#1-f21-gumroad-production-safety)):

- The four access products still answered 200 at 08:33Z.
- Only `upgrade.html` links them, and it shows the Gumroad button only
  while `/api/pricing` reports Gumroad available (fail-closed).
- Ten pages and the PRO and Enterprise structured data on `pricing.html`
  still offered Gumroad unconditionally ("checkout via Razorpay or
  Gumroad", "30-day access grant via Gumroad"). This PR rewrites them.
  A withdrawn entry in `config/evidence-register.json` makes
  `verify_public_claims.py` fail if that wording returns.
- Unpublishing the products was not authorized here; it stays with the
  owner.
- Historical sales need the owner's Gumroad sales export. No transaction
  was created or replayed.

### F22 — The paid-key welcome email is never sent (R05) — sender FIXED and deployed (#641), off by default; OWNER DECIDED 2026-10-02 (never email a raw key); one-time key link MERGED (#643 → `b516e7bb2`) and DEPLOYED 12:23Z

Razorpay activation calls `provisionCustomer()` (revenue engine), which
queues `welcome_provisioned` (the API key) with `queueEmail()` and no
`send_at`. The only sender, `runDailyOutreach()` (cron `0 9 * * *`), selects
messages with `msg.send_at <= now`; with `send_at` undefined that comparison
is always false, so the message is never sent. `SENDGRID_API_KEY` presence is
also unverified. Consequence: a buyer whose checkout tab closes before
activation has no copy of the key. The checkout no longer claims an emailed
key; it shows the key on the page, keeps the payment proof for the tab so a
reload resumes, and names checkout support. Fix proposal (not made here:
enabling it sends customer email and could flush 30 days of queued messages):
set `send_at` at queue time for transactional templates only, send them on
activation rather than at the 09:00 cron, and confirm the provider key.

Decision and implementation (2026-10-02): no email carries an API key.
See "Payment and commercial release blocker closure" below and
`docs/COMMERCIAL_POLICY_V1.md` ("Key delivery").

### F24 — The revenue engine's deploy never shows the commercial readiness verdict (R10, R29) — step FIXED (#641); live run shows the repository secret rejected (HTTP 401); OPERATOR

`deploy-revenue-engine.yml` "Commercial readiness report" printed "NOTE:
readiness endpoint not reachable yet" on 2026-09-28 (run 36460344094) and
again on 2026-10-01 (run 36914355894). The repository secret is set (masked
in the log), and `GET /api/v2/billing/admin/readiness` exists on both hosts
(401 without the secret, 19:31Z). So the call is most likely refused (the
repository `REVENUE_ADMIN_SECRET` differs from the Worker's), and the step
cannot say so: `curl -sf` drops the status, a non-JSON body prints the
"not reachable" note, and the step exits 0. The deploy is not gated by this
step, but a BLOCKED verdict (for example F21) never reaches the deploy log.
Fix (operator check plus a small workflow change): confirm the two secrets
match, and print the HTTP status instead of the generic note.

Authority audit 2026-10-02
([runbook §3](PAYMENT_RELEASE_OPERATOR_RUNBOOK.md#3-f24-revenue_admin_secret)):

- The canonical value is the revenue engine's Worker secret. The gateway
  and the repository hold copies.
- The runbook gives commands for both remediation options, and probes
  that prove 200 with the secret and 401 without it.
- **BLOCKED — OPERATOR SECRET REQUIRED.** Nothing in this session can read
  or set a Worker or repository secret.

### F23 — Authenticated `/api/v1/p33/metrics` returns uncontracted tier prices (R09) — REPORTED, P2

`handleP33Metrics()` returns `marketplace_tiers` of $499 / $1,999 / $4,999 /
$9,999 per month with "SLA guarantee" and "Dedicated analyst". The contract
prices are $49 / $499 / $999. The route answers 401 anonymously (probed
2026-10-01) and the page that reads it never renders the block (it expects an
array and gets an object), so no buyer page shows it. Fix: derive the block
from `config/commercial-contract.json` or remove it, in a P33 bug-fix PR.

### F25 — The publisher cannot persist its committed state to `main` (R10, R15) — PARTLY ADDRESSED: the premium baseline persists in R2 (#644); STAGE 4 and two internal quality files await the owner

`safe_git_commit.py` in `sentinel-blogger` commits the run's STIX bundles,
reports, `index.html` and `data/cache/feed_state.json`. Its push to `main`
has been rejected on every run checked (2026-10-01 06:50Z and 15:25Z,
2026-10-02 03:13Z and 06:04Z): `GH013: Repository rule violations found
for refs/heads/main`. Ruleset 21556637 ("SENTINEL APEX Production Main
Protection", created 2026-08-26 11:39Z) requires a pull request and linear
history. The last publisher commit on `main` is 2026-08-26 10:30Z. The
step logs an error but does not fail the job, and each run starts from
`main`'s 26 August state. Customer feeds are served from R2 and the
Worker, and stayed fresh (`public_feed_freshness_gate` PASS, 06:22Z), so
the visible impact is limited to state the publisher reads back from git.
That impact was not measured. This is an owner decision: give the
publisher's token a ruleset bypass, or stop committing pipeline state to
`main`. No code change was made.

Measured 2026-10-02 (publisher run 36969320297, started 05:31Z):

- STAGE 4 committed locally at 06:04:47Z. Four pushes were refused with
  GH013, and the retries took 98 s (to 06:06:25Z).
- The dist build at 06:07Z records `git rev-parse HEAD`
  (`build_dist_artifact.py` `_resolve_git_sha`). So the deployed
  `deployment_manifest.json` names a commit that exists only on the
  runner.
- Most runtime state already lives in R2: `scripts/r2_state_sync.py`
  `STATE_FILES`, since 2026-09-08.
- Still read back from `main`, so frozen at 26 August:
  - `api/feed.baseline.json` (985 items), which drives F26;
  - `data/quality/quality_drift_report.json`;
  - `data/quality/report_engine_ledger.json`.

This is an architectural event under CLAUDE.md. Proposed architecture:

1. No pipeline state in git. The three files above move to the existing
   `r2_state_sync.py` (same bucket and credentials; one GET and one PUT
   per file per run).
2. STAGE 4 keeps its guards but stops committing and pushing.
3. Provenance comes from the checked-out commit.

Requirements check:

- **Freshness:** with F26 fixed.
- **Commit churn:** none.
- **Secrets in git:** none (unchanged).
- **Observable failure:** an R2 sync error fails its step.
- **Recovery:** the baseline rebuilds from the live feed.

Item 2 changes STAGE 4, which CLAUDE.md marks "never modify", so it
needs the owner's confirmation and is not made here. Main branch
protection stays as it is.

### F26 — Enterprise and MSSP premium feeds serve August intel (R12, R15) — MEASURED 2026-10-02, P1; FIX in PR (this change), not yet merged

Where the feeds come from:

- `/api/v1/premium/feed/{gold,silver,standard,executive}` (ENTERPRISE and
  MSSP keys) serves R2 `premium/feeds/feed.*.json`.
- `generate_tiered_feeds.py` rebuilds those files every run from
  `api/feed.baseline.json`, as it does the detection pack and the trial
  preview.
- That baseline is read from the run's checkout of `main`. It holds 985
  items published 2026-08-19 18:16Z to 2026-08-26 08:50Z, last committed
  2026-08-26 (`39407bc53`).

`premium_feed_baseline.py` refused every update this morning:

- "SHRINKAGE GUARD: new baseline (77) is 8% of prior (985)" (run
  36956080062, 02:59Z);
- "(42) is 4% of prior (985)" (run 36969320297, 05:58Z).

The 05:58Z run then uploaded all four premium feeds from the 985-item
baseline (05:58:27–36Z). Each file gets a new generation time; its
items do not change.

Root cause:

1. `_merge` keeps prior items only if they were published within
   `MERGE_WINDOW_HOURS` (96).
2. The guard divides by the whole prior baseline, including the items
   the merge just dropped as too old.
3. While the publisher persisted its baseline every run, the prior was
   at most a few hours old. It stopped persisting on 26 August (F25).
   From about 30 August every prior item was older than 96 h, so no
   update can pass.

`/api/feed.baseline.json` and `/api/feed.trial.json` answer 404 on the
public host, so no premium content is exposed.

Fix (this PR, not yet merged):

- **`premium_feed_baseline.py`.** The guard compares against the prior items
  the merge can keep (shared `_merge_cutoff_ts` and `_in_merge_window`). A
  prior entirely outside the window is rebuilt from the live feed, with a
  warning. An in-window loss below the floor is still refused. The report
  gains `prior_in_window`.
- **`r2_state_sync.py`.** `api/feed.baseline.json` becomes an owner-only
  state file at `premium/state/feed.baseline.json`. No route serves that
  prefix, and broad sweeps skip it. Worst case 1,680 Class A and 1,260
  Class B operations a month (0.168% and 0.0126% of R2's allowances).
- **`sentinel-blogger.yml`.**
  - STAGE 3.1.18d downloads the baseline with `--only` before STAGE 3.1.19.
  - STAGE 3.1.19 reports `updated=true` only when it wrote a new baseline.
  - STAGE 3.1.19b uploads only when the download succeeded and the
    baseline was updated.
  - All three steps are non-blocking; STAGE 4 is unchanged.
- **`generate_tiered_feeds.py`.** `feed.standard.json` claimed "all 176
  quality-gated items" while it held 985. It no longer states a number;
  `_meta.item_count` carries the count.
- **Tests:**
  - guard, 4 tests: 2 fail on the old code, and the 2 guard-preservation
    controls pass on both;
  - workflow wiring, 5 tests: 3 workflow mutations caught;
  - metadata, 1 test: fails on the old code;
  - R2 state-file pin: 22 → 23, with the FinOps justification.

Expected on the first publisher run after the merge (which the merge itself
triggers):

1. STAGE 3.1.18d finds no R2 copy and keeps the checkout's copy.
2. STAGE 3.1.19 logs that the 985-item prior is entirely outside the window
   and writes a baseline from the live feed.
3. STAGE 3.1.19b uploads it.
4. STAGE 3.1.20 builds the premium feeds from it.

### F28 — The certification canary step loses a failing canary's result (R10, R18) — P2; FIX in the CI-reporting change

`commercial-customer-ops-certification.yml`, Phases 8-15, runs under
`bash -e`. Its `canary()` helper does
`out=$(node deploy/cyber-watchdog/canary.mjs "$mode" 2>/dev/null); rc=$?`.
Under `-e`, a non-zero exit from the canary aborts the script at that
assignment. The `case` that records FAIL, or OPERATOR_WEBHOOK_SINK_REQUIRED,
never runs, and neither does the summary.

Observed in runs 37006162439 and 37006645392: the job ended with exit code
1, with nothing after "ENTERPRISE denied MSSP tenant management: PASS". The
canary-key cleanup still ran, through the step's EXIT trap.

The run still fails closed, as it should, but the reason is lost.

Fix (CI-reporting change): `out=$(...) && rc=0 || rc=$?`, which captures the
exit code without tripping `-e`.
`tests/test_certification_canary_step_records_failures.py` runs the step's
own `record()` and `canary()` functions under `bash -e` with a stub canary:

- a failure is recorded with its reason;
- a blocked canary is recorded as blocked;
- a pass is recorded as a pass;
- in every case the step continues to its summary.

On the old line, the failure and blocked cases abort.

### F27 — The daily full secret scan never completes (R08) — REPORTED, P2

The scheduled SAST runs on 2026-09-30 (failure), 10-01 and 10-02
(cancelled) did not finish. On 10-02 (run 36979405084), TruffleHog's
full-filesystem scan hit its job limit after 20 min 14 s. `SAST Gate
(required)` then failed closed, as designed. Push and PR runs scan only
their diff range and pass. No full-repository secret scan has completed
in the last three days. The fix (scan budget or scope) is not made here.

## Checkout P0: Razorpay primary, Gumroad secondary, assisted note only (2026-10-01) — MERGED (#639 → `aa97c8366`), DEPLOYED, LIVE PASS (presentation and gating); payment E2E BLOCKED

Owner instruction: Razorpay is the primary checkout, Gumroad the secondary;
assisted payments are one low-prominence note with two contact addresses;
no manual-payment mechanism is presented as self-service.

### Root causes

1. `upgrade.html` put an "INSTANT CHECKOUT" Gumroad panel above Razorpay,
   promising "API key delivered to your email upon payment" while
   production could not provision a Gumroad sale (F21).
2. A wall of wallet badges (GPay, PhonePe, Paytm, BHIM, Amazon Pay, PayPal)
   next to a recurring Razorpay subscription, which does not offer them as
   such; the same wall on pricing, index, services and store.
3. MSSP's "secondary checkout" was a `mailto:` (email-to-buy).
4. Every failure was an `alert()`; the pending view promised an emailed key
   the revenue engine never sends (F22); the success view put the full key
   in the DOM and in code snippets.
5. A retry of a checkout Razorpay had already charged (reload, second tab)
   created a second subscription the buyer could pay again.
6. `subscriptions/create` returned Razorpay's raw error body to the browser.
7. The funnel contradicted the checkout: `get-api-key.html` took paid-plan
   "requests" promising a key by email within 2 hours, with WhatsApp
   "assisted activation"; "instant" checkout/access/provisioning claims on 22
   pages; `trial-center.html` said billing does not recur and GST is added
   on top (the INR charge includes it: `gst.js` `splitInclusiveTax`);
   `enterprise-pricing.html` offered EMI and automatic GST invoices for every
   plan; `pricing.html` said bank transfer is available only against a PO,
   contradicting the owner's assisted-payment note.
8. Dead manual-payment CSS/JS (UPI/QR/NEFT/PayPal/crypto/direct-gateway) and
   stray markup after the layout.

### Before / after

```
BEFORE  upgrade.html
          Gumroad panel (first, "INSTANT", per-plan buttons, MSSP mailto)
          Razorpay panel ── POST /api/v2/billing/subscriptions/create ── modal
              handler → poll status ×15 → key | "emailed to you" (never sent)
          alert() on every failure; wallet badge wall; urgency shimmer bar

AFTER   upgrade.html
          1 plan (radio group)   2 what you get (= commercial contract)
          3 pay  [Continue with Razorpay]  PRIMARY
                    create (server-set price) → modal → handler
                    → proof kept for this tab → poll → ACTIVE (key masked, reveal/copy)
                                                    └ ACTIVATION_PENDING (rechecks; reload resumes)
                 "Prefer another checkout?" [Continue with Gumroad]  SECONDARY
                    shown only if GET /api/pricing .checkout.gumroad.available
                    (gateway: GUMROAD_WEBHOOK_SECRET and RESEND_API_KEY set)
                 Alternative payment methods: one note, two mailto links, no controls
          4 what happens after you pay
          inline aria-live messages, field errors next to fields; no alert()
        revenue engine: 409 checkout_in_progress for an already-paid pending
          checkout; provider error text stays in the Worker log
        gateway: additive `checkout` block on /api/pricing (no new route)
```

### Phase 1 classification (every shipped page, 146 scanned)

| Where | Terms | Class | Action |
| --- | --- | --- | --- |
| `upgrade.html` CSS/JS (upi/qr/neft/paypal/crypto/dgw, `updateDGW`, `hidden-plan`, `payment_date`) | UPI, QR, NEFT, PayPal, crypto | DEAD CODE | removed |
| `upgrade.html` badge wall, Gumroad "instant / emailed key", MSSP `mailto:` | Paytm, Amazon Pay, PayPal, email-to-buy | ACTIVE CUSTOMER FLOW | removed / gated |
| gateway `POST /api/payment/manual-notify`, revenue `POST /api/payments/submit` | manual payment | LEGACY (410 since 2026-09-24; canary 12:17Z) | unchanged |
| gateway `GET /api/payment/status?review_id=` and `api-key-manager.html` lookup | payment pending, review | LEGACY (read-only, issued ids) | subtitle no longer advertises BNB/UPI/PayPal/bank tracking |
| `payment-status-dashboard.html`, `admin.html` | proof, screenshot, retired notes | ADMIN (login) / DOCUMENTATION | unchanged |
| `get-api-key.html` paid-plan form | "within 2 hours", "assisted activation", email in checkout URL | ACTIVE CUSTOMER FLOW (manual) | continues to checkout; no emailed-key promise; no email in URL |
| pricing, index, services, store strips | GPay, PhonePe, Paytm, BHIM, Amazon Pay | ACTIVE (unsupported) | payment rails per checkout |
| trial-center, enterprise-pricing, compare, docs/faq, landing and 14 marketing pages | instant, EMI, "+18% GST", "no recurring billing" | ACTIVE (unsupported) | corrected; withdrawn-claim entry in `evidence-register.json` |
| `referral.html`, `mssp-partner-onboarding.html` | UPI, PayPal, NEFT | PARTNER PAYOUT INFORMATION (not a checkout) | unchanged |
| `store.html`, `index.html` mailto for packs and kits | email-to-buy | SALES-QUOTED PRODUCTS (owner decision 2026-09-28) | unchanged |
| enterprise pages "Contact Sales" | mailto | SALES CONTACT | unchanged |
| `enterprise-cyber-intelligence-os.html` tier mailto | email-to-buy | DEAD CODE (never renders; F23) | reported |
| `docs/COMMERCIAL_POLICY_V1.md`, tests, validators | all | DOCUMENTATION / TEST | policy amended for the assisted note |

### Evidence

Razorpay (primary):

| Step | Evidence | Status |
| --- | --- | --- |
| Plan + cycle → Razorpay Plan server-side; page sends no price | `billing-go-live` "browser cannot set the price"; browser check with `?amount&price&tier&currency&plan_id` in the URL | PASS (tests) |
| Plan charges the canonical INR price | `verifyPlanPrice` (S19), `pricing-fail-closed` tests | PASS (tests); live Plan config needs the admin secret |
| Create → Razorpay modal; failures inline, no payment taken | 95 browser checks (stubbed provider) | PASS (local) |
| Status needs payment id + HMAC signature | `subscription-engine` tests (401, IDOR) | PASS (tests) |
| Webhook authenticity | live 12:17Z unsigned → 401, wrong type → 415; tests | PASS (live config) |
| Replay / idempotency; second payment refused | event-id/body-hash claim tests; new 409 `checkout_in_progress` test + control | PASS (tests) |
| Entitlement across both Workers; refund / cancel / halt revoke | `cross-worker-revocation` tests | PASS (tests) |
| Nothing shown as success before the backend confirms | state machine checks; mutation "success before confirmation" caught | PASS (local) |
| A real payment end to end | — | BLOCKED: provider test mode or explicit authorization |

Gumroad (secondary):

| Step | Evidence | Status |
| --- | --- | --- |
| Missing / wrong secret | live 500 (unset, F21); metering tests (wrong, encoded, NUL) | FAIL live config; PASS tests |
| Unknown product, content product, price below catalog, wrong currency, seller | `gumroad-products` tests | PASS (tests) |
| Refund revokes, dispute suspends, cancel vs end, renewal extends once | `gumroad-membership` tests | PASS (tests) |
| Duplicate / replayed sale | sale claim + Durable Object lock tests | PASS (tests) |
| Malformed ping (no sale_id, email or subscription_id) → 400, nothing changes | new `gumroad-membership` test + control | PASS (tests) |
| Offered on the checkout only when provisioning and delivery are configured | 3 gateway tests; browser checks (available / unavailable / unreachable / 404) | PASS (local); live PASS: hidden since 19:36Z (`available: false`, `automated_provisioning_not_configured`) |

Screenshots (desktop 1280; mobile 320/360/390/430/768; pending, active,
503 inline): produced by `render-test/verify_upgrade_checkout.js` with
`CHECKOUT_SCREENSHOT_DIR`; not committed.

### Post-merge verification (Phase 12, 2026-10-01)

#639 was squash-merged at 19:26Z as `aa97c8366`, tree `6cfc4fa5f` = reviewed
head `baaf2ffee`. Every check on that head passed first:
- Python suites 1,913, including the three checkout suites
- gateway 1,660/1,660
- billing canary 7/7
- billing negative controls 104/104, including the three new ones
- SAST gate, TruffleHog and GitGuardian

Nothing below made a payment or changed production state. The canary's POSTs
are rejected-input probes (unknown tier, bad signature, retired routes). The
browser probe aborted and listed every non-GET request the page attempted.

| Check (live, read-only) | Result | Evidence |
| --- | --- | --- |
| Gateway runs the merge | PASS | deploy-worker 36914355832 (gates, full suite, exact-commit smoke); `/api/health/live` `deploy_commit_sha` = `aa97c8366` from 19:29:12Z |
| Revenue engine runs the merge | PASS (deploy) | deploy-revenue-engine 36914355894: lifecycle gate, deploy and smoke success at 19:28Z |
| Pages serves the merge | PASS | pages-fast-publish 36914356330 success at 19:36Z, including the pre-deploy checkout render test on dist and the post-deploy freshness gate; `gh-pages` `9fb3a5532` ("Deploying ... @aa97c83660"); `upgrade.html`, `pricing.html`, `get-api-key.html`, `trial-center.html` and `index.html` byte-equal to the merge |
| Served page equals the merged source | PASS | 19:37Z: identical once Cloudflare's edge rewrites are undone (email obfuscation, its email-decode script, the Web Analytics beacon) |
| `/api/pricing` checkout block | PASS | `razorpay`: primary, INR, subscription. `gumroad`: secondary, USD, `available: false`, `automated_provisioning_not_configured`. No other fields and no configuration values |
| Browser at 320/360/390/430/768/1280 px | PASS, 127/127 (19:38Z) | see the list below the table |
| Nothing payment-related fires on load | PASS | four requests, all aborted, none to a billing or payment endpoint: two Formspree page-view beacons (`apex-track.js`, unchanged, sends no email or payment id), Razorpay's script telemetry (`lumberjack.razorpay.com`), Cloudflare RUM |
| Buyer copy on other pages | PASS | `pricing.html` shows "Razorpay (primary)" and the assisted-payment FAQ; no "within 2 hours" or "assisted activation" on `get-api-key.html`; no "no automated recurring billing" on `trial-center.html` |
| Billing canary, public mode | 14/15 (19:30Z) | the one failure is F21 (Gumroad webhook 500). Passing: unknown tier 400; Razorpay bad signature 401, wrong type 415; manual payment 410 on both Workers; admin routes 401/403 |
| A paid checkout's retry gets 409; provider error text stays server-side | NOT TESTED live | needs a paid checkout or a provider error; covered by tests and negative controls on the merged head |
| A real payment end to end | BLOCKED | provider test mode or explicit authorization |

The 127 browser checks cover:
- **Primary checkout:** Razorpay is the one primary CTA, 61 px tall and
  keyboard-reachable; PRO is preselected from `?plan=pro`; the charge reads
  ₹4,100.
- **Gumroad:** hidden, with the "temporarily unavailable" note.
- **Assisted note:** verbatim, two mailto links, no controls, below both
  checkouts.
- **No manual payment:** no file input, UTR, QR, IFSC or UPI URI.
- **Page health:** Cloudflare-obfuscated addresses decode; no dialog or page
  error.
- **Layout:** no horizontal overflow at any width. The same probe on the old
  live page at 19:17Z measured 82, 42 and 12 px of overflow at 320, 360 and
  390 px, and 69 of 121 checks failed.

The probe also took screenshots of the live page at 390 and 1280 px; they are
not committed.

### Blockers (not code)

- Provider test mode or explicit authorization for a live payment run
  (no real charge was made).
- `GUMROAD_WEBHOOK_SECRET` (and Gumroad's ping URL) for Gumroad to be offered
  again (F21); `RESEND_API_KEY` presence is required by the same gate.
- F22 owner decision on transactional email.
- Payment release closure P0: merge and deploy (both Workers); the owner
  may confirm `RENEWAL_GRACE_HOURS` (default 96).

## Payment release closure P0 (2026-10-02) — MERGED (#641 → `acc38a24d`), DEPLOYED; live payment E2E BLOCKED

Base: `main` `5911a9722`. The deployed gateway is still `aa97c8366` (`/api/health/live`
03:17Z). This section covers F21/F22/F24 (Task 1), payment-to-entitlement
proof (Task 2), the SAST classifier (Task 3) and the commercial truth
recheck (Task 4). Every defect below was reproduced by a test that fails on
the pre-fix code, fixed, and is now caught by a negative control in
`billing-negative-controls.mjs`.

### Defects found and fixed

| ID | Severity | Defect (before) | Fix | Proof |
| --- | --- | --- | --- | --- |
| P0-1 | P0 | The gateway's legacy Razorpay webhook (`payment.captured` / `order.paid`) minted a key for **any** captured payment on the account (payment links, pages): tier defaulted to PRO, email to `unknown@razorpay`, and amount and currency were never checked. `/verify` took the key's billing cycle from the browser, so a monthly price could yield an annual key | new pure `legacy-order-authority.js`: only an Order this gateway created (`notes.platform`), with a known tier and cycle, in INR, at exactly that price, with the Order's email | `legacy-order-authority.test.js` (7); 4 controls |
| P0-2 | P0 | The 09:00 UTC daily check expired every active subscription at `current_period_end`, Razorpay-managed ones included. `expired` is terminal, so a renewal webhook that arrived after the run could not restore access: a paying customer was locked out for good | Razorpay-managed subscriptions expire there only after the period plus the renewal grace; others unchanged | `renewal-and-key-email.test.js` (3); 1 control |
| P0-3 | P0 | Gumroad with the sale lock bound (production): any failure after the claim kept the sale claimed, so every Gumroad retry got `already_provisioned` and the buyer was charged with no key | the claim is released (`claim_release`), `gumroad_failed:<sale_id>` recorded, operator alerted, 500 so Gumroad retries; the retry reuses a key already minted | `gumroad-provisioning-recovery.test.js` (5); 2 controls |
| P1-1 | P1 | Activation with no server link took the tier from the subscription's notes; a link's Plan was never compared with the activated Plan | Plan binding: the link's Plan must match; otherwise only a configured Plan ID grants, and notes cannot raise the tier | 5 tests; 2 controls |
| P1-2 | P1 | A store error reading the provider link happened before the `try`, so the event claim was never released and Razorpay's retries were answered `already_processed` | read moved inside the `try` | 1 test; 1 control |
| P1-3 | P1 | A retry after an activation that failed part-way minted a second live key | `rzp_sub_provisioned:<id>` marker; the retry reuses the key | 1 test; 1 control |
| P1-4 | P1 | The activation key lasted now + 30 / 365 days whatever Razorpay's paid period, and every key lapsed exactly at period end while Razorpay was still retrying the card (the policy table promises access while `pending`) | key valid to `current_end` + `RENEWAL_GRACE_HOURS` (default 96, bounded 0–336) | 3 tests; 2 controls |

Residual, not fixed here: `renewal_count` counts a renewal again when the
same charge is redelivered under a new event id (metadata only; expiry is
absolute and tested); there is no admin replay for a failed Razorpay event
(Razorpay's own retries recover it); if `provisionCustomer()` throws after
minting a key but before the retry marker is written, a retry can mint a
second key (the first is never returned to anyone); a failed Gumroad claim
release is logged, not retried; the dormant welcome email's "Valid until"
still shows `provisionCustomer`'s 30/365-day date.

### F21, F22, F24

| | Definition (above) | Why it blocks release | Class | Done in code | Owner action |
| --- | --- | --- | --- | --- | --- |
| F21 | `POST /api/webhooks/gumroad` answers 500 "Webhook secret not configured"; Gumroad sales are never provisioned | the four access products are still purchasable by direct URL: a buyer pays and gets no key | CREDENTIAL (secret, ping URL) + PRODUCT (keep or unpublish the four products; reconcile past sales) | the #639 gate keeps Gumroad off the checkout; P0-3 means a transient failure no longer strands a sale once the secret is set | set `GUMROAD_WEBHOOK_SECRET` and the ping URL; decide on the four products; reconcile sales since 2026-09-25 |
| F22 | the paid-key welcome email is queued without `send_at` and never sent | a Razorpay buyer who loses the checkout tab has no copy of the key | PRODUCT (email a raw API key or not) + CREDENTIAL (`SENDGRID_API_KEY`); sender was ENGINEERING | sender fixed but **off** unless `KEY_EMAIL_DELIVERY_ENABLED="true"`: sent once at activation, one retry, then `failed`; `sent` only on provider success; older queued keys never flushed; readiness warning | decide whether paid keys are emailed; if yes, set the flag and the SendGrid key |
| F24 | the revenue deploy's readiness step printed "not reachable" instead of the verdict | a BLOCKED readiness verdict (e.g. F21) never reaches the deploy log | ENGINEERING (step) + CREDENTIAL (repository secret probably differs from the Worker's) | the step prints the verdict or the HTTP status, says when the secret was rejected or an edge block answered, retries 5xx and no-response 3 times, never prints the secret; still informational | set the repository `REVENUE_ADMIN_SECRET` to the Worker's value: deploy run 36962733371 (04:03Z) printed "HTTP 401: the revenue engine rejected the REVENUE_ADMIN_SECRET repository secret" |

### Payment to entitlement: deterministic proof

Paths traced: `upgrade.html` → `POST /api/v2/billing/subscriptions/create`
(server Plan, S19 Plan price check) → Razorpay checkout → status poll
(signature-checked, read-only) → signed webhook → event claim →
`provisionCustomer` / renewal → `API_KEYS_KV` key → gateway
`evaluateKeyRecordAccess`; audit through `trackEvent` anomalies and the
billing ledger. Gumroad: catalog permalink → gateway webhook (`?secret=`) →
Durable Object claim → key → emailed by the gateway. Legacy gateway Orders:
verify / webhook → Order authority → key.

| Property | Razorpay subscriptions | Legacy Razorpay Orders | Gumroad |
| --- | --- | --- | --- |
| Browser cannot set price or raise tier | server Plan, S19 check; Plan binding (4 tests) | Order authority; verify ignores the browser's cycle, tier and email (2 tests) | catalog permalink and price (existing) |
| Bad signature or secret cannot provision | 401, nothing written (existing) + control | control | control |
| Return or callback alone cannot provision | status endpoint read-only; `created` never returns a key (existing) | verify needs signature, captured payment, Order authority | webhook only |
| Duplicate webhook, one entitlement | event-id claim (existing); retry marker (new) | `rzp_payment:` idempotency (existing) | DO claim + sale map (new, 5 tests) |
| Replay cannot extend | absolute expiry, replays and older events (new test + control; existing out-of-order test) | one-time | redelivered charge extends once (existing) |
| Unknown order or product | unknown Plan (new) | not created by this gateway (new) | `unknown_product` held (existing) |
| Amount, currency or product mismatch fails closed | Plan mismatch (new); Plan amount at checkout (existing) | amount, currency, tier (new) | below price or non-USD held (existing) |
| Refund and cancellation per contract | `refund.created` / `processed` revoke, `refund.failed` changes nothing (new test + 2 controls); halted / cancelled deny (existing cross-worker) | `refund.*` revokes (existing) | refunded / disputed / cancelled / ended (existing) |
| Provisioning failure recoverable and auditable | claim released, 500, anomaly events (new) | — | `gumroad_failed` + alert + retry (new) |
| Verified payment gives exactly the intended entitlement | tier and cycle from the Plan, expiry `current_end` + 96 h (new) | ENTERPRISE annual ≈365 d, PRO monthly ≈30 d (new) | catalog tier and cycle (existing) |

Provider-level E2E: **BLOCKED — AUTHORIZED TEST CREDENTIALS REQUIRED.** No
Razorpay test-mode key or Plans and no Gumroad test sale were available; no
live transaction was attempted.

### SAST classifier (Task 3)

Root cause: `Classify Changed Surfaces` cloned the full history
(`fetch-depth: 0`) to compare two trees. Before, over 37 PR runs
(2026-09-30 to 10-02): job median 211 s, p90 234 s, max 304 s; the checkout
was a median 207 s of it (max 299 s), and the 5-minute timeout cancelled it
twice (runs 1125 and 1133 attempt 1, ≈5%), failing the required gate with
no finding. Now the step fetches only the PR's base and head commits and
their trees (`--depth=1 --filter=blob:none`, 3 attempts, token passed by
environment and masked): 0.53–0.83 s and 2.4 MiB locally against this
repository. The comparison is unchanged (base tip vs head, a superset of
what the merge changes, no merge-base needed). A malformed SHA, a fetch or
diff failure fails the job, and the SAST Gate fails closed on it.
Regression tests run the real step against a local bare remote: docs-only →
code scanners skipped; Python → Bandit and Semgrep required; each
dependency manifest → the dependency scanner; mixed → code scanners;
deletion and rename in or out of `agent/`; unusual paths; unreachable
remote, missing commit, malformed SHAs → failure; and the real gate script
fails on every non-success classification.

### Post-merge verification (2026-10-02)

- **Merge.** #641 was squash-merged at 04:01:40Z by the repository owner
  as `acc38a24d`, whose tree equals the reviewed head `5c6c6a8ad`. 16 of
  17 checks on that head were green, `SAST Gate (required)` included. One
  was red since 03:30Z: `workers/intel-gateway -- full unit suite`. Its
  Cyber Watchdog negative-control step reported 2 of 98 controls as
  `MUTATION_ANCHOR_MISSING`: `razorpay_verify_mssp_parity_broken` and
  `gumroad_mssp_parity_broken`. #641 rewrote the two `provisionApiKey`
  calls those controls mutate, and my local validation had not run that
  harness. Every later step in the job was skipped. The follow-up PR
  re-anchors both controls with the same mutation and the same test.
  Locally: 98/98 caught, dashboard controls 31/31, rollback artifact builds.
- **Main after the merge.**
  - deploy-worker 36962733324 succeeded; deploy-revenue-engine
    36962733371 succeeded (deploy gate 198/198).
  - SAST 1135 succeeded; the regression gate failed for the anchor reason
    above.
  - Commercial certification 36962733292 failed only on the Enterprise
    signed-webhook canary, which is BLOCKED (`OPERATOR_WEBHOOK_SINK_REQUIRED`).
    Every other live canary and phase passed against `acc38a24d`: PRO,
    MSSP self-service, MSSP rotation, autonomous scheduler, authenticated
    customer ops, lifecycle matrix, expiry boundary, MSSP isolation and
    the FREE rate-limit boundary.
- **Live (read-only or rejected input, 06:47–06:48Z).**
  - `/api/health/live` reports `acc38a24d`.
  - `/api/pricing` `checkout`: Razorpay primary; Gumroad
    `available: false` (`automated_provisioning_not_configured`).
  - Billing canary, public mode: 14/15. The only failure is F21.
- **Scheduled publisher.** Run 36969320297 (05:31Z) failed at STAGE 5:
  its `gh-pages` push lost a ref race ("cannot lock ref ... expected").
  Its push to `main` was also rejected by the ruleset, as on every run
  since 26 Aug (F25). Neither is caused by #641.

### Commercial truth recheck (Task 4)

Shipped payment surfaces (`upgrade.html`, `pricing.html`, `billing.html`,
`customer/api-keys.html`, `payment-status-dashboard.html`,
`PAYMENT-GATEWAY.html`, `testimonials.html`, `case-studies.html`) in a fresh
`dist/` build: no manual payment form, UTR field, QR code, UPI ID, IFSC or
bank detail; `PAYMENT-GATEWAY.html` only redirects to `/upgrade.html`;
assisted payment is one contact-only note ("Access is provisioned only after
payment verification"), and production answers 410 to
`POST /api/payments/submit` and `/api/payments/approve/*`
(`production-entry.js`). "Payment confirmed" appears only after Razorpay's
own success callback and says access is not yet on. "Secure checkout" is
backed by statements that are true in code (card details only in
Razorpay's window, server-set amount, access only after the signed
webhook). Refund, SLA and price wording match `terms.html`, `sla.html` and
the contract (`verify_commercial_contract.py` 5,366/0,
`verify_public_claims.py` 29,933/0, checkout and claims suites 40/40).
Testimonials and case-study pages state that no customer evidence is
published. `payment-status-dashboard.html` (admin-only) still shows
approve buttons that now answer 410; left as is (deprecation, not deletion).

## Payment and commercial release blocker closure (2026-10-02) — MERGED (#643 → `b516e7bb2`), DEPLOYED; provider E2E BLOCKED

- Base: `main` `fcb252bd7`.
- Deployed Workers: `acc38a24d`.
- Owner commands, and the audits behind them, are in
  [PAYMENT_RELEASE_OPERATOR_RUNBOOK.md](PAYMENT_RELEASE_OPERATOR_RUNBOOK.md).

### F22: no API key in any email (owner decision 2026-10-02)

Before:

- The gateway's Gumroad activation email (`sendActivationEmail`) carried
  the full key in its body and its quick-start commands.
- Five revenue-engine templates rendered a key: `welcome_provisioned`,
  `key_rotated`, `free_key_welcome`, `mssp_tenant_welcome` and
  `trial_welcome`.
- The email queue kept those variables for 30 days.
- The SendGrid request copied every queued variable into
  `dynamic_template_data`.

After:

**One-time redemption.** The gateway gains a pure module,
`key-redemption.js`, and `POST /api/keys/redeem`.

- **Token.** 32 random bytes, base64url. Only its SHA-256 is stored, in
  `API_KEYS_KV` as `key_redeem:<hash>` with a 72 h TTL.
- **Link.** The token travels in the URL fragment
  (`/customer/api-keys.html#redeem=<token>`). Browsers never send a fragment
  to a server, so it stays out of access logs and Referer headers. The page
  clears the fragment and redeems only on a click: a POST with
  `cache: no-store` and no credentials.
- **Route.** The token is read from a JSON body only. Other methods get
  405, other content types 415, a malformed token 400. Bodies are capped at
  2 KB.
- **Order of checks.**
  1. The record exists and is unexpired.
  2. The key still authenticates (the gateway's own access decision).
  3. The one-time claim is taken atomically on the existing
     `GumroadProvisioningLock` Durable Object (`redeem:<hash>`; no new
     binding).
  4. The key is returned with `Cache-Control: no-store`.
- **Refusals.** These all get the same 410: a replay, an unknown or expired
  token, and a revoked, suspended, lapsed or deleted key. An authority or
  lock outage answers 503 and spends nothing, so the same link works later.
- **Audit.** The log keeps a 12-character reference of the token hash,
  never the token or the key.

**Emails.**

- The gateway's activation email says access is active. It carries the
  one-time link and its expiry, and its commands use `$CDB_API_KEY`.
- The five revenue templates are key-free, their callers no longer pass
  keys, and the SendGrid request carries no queued variables.

**Razorpay activation notice.** Off by default.

- With the owner flag on, it carries a one-time link to the same contract.
  `issueActivationLink` mirrors the gateway record, and
  `activation-link.test.js` redeems one at the real gateway.
- With the flag off, no link is issued, and the queued notice holds
  neither key nor link.
- SendGrid stays optional. Without it nothing is sent, and no other
  protection changes.

**Re-issue.** `POST /api/admin/keys/{key}/redemption` uses admin auth with
the existing lockout. It sends a new link only to the address on the key
record. It answers 404 for an unknown key, 409 for a key that no longer
authenticates, and 422 when no address is recorded.

**Rotation and MSSP tenants.** The new key goes only to the authenticated
caller. The MSSP dashboard shows a rotated tenant key once.

**Pages.** No page promises an emailed key, and the withdrawn-claim gate
now covers that wording.

**Tests and controls.**

- Gateway `key-redemption.test.js`: 8 tests.
- Revenue `activation-link.test.js`: 4 tests.
- One readiness test updated.
- 9 new billing negative controls, all caught:
  - redemption replay allowed;
  - redemption expiry not checked;
  - redemption reveals a revoked key;
  - redemption without the claim lock allowed (fail open);
  - token accepted from the query string;
  - activation email carries the raw key;
  - welcome template renders a key;
  - queued variables shipped to the email provider;
  - activation notice queues the raw key.

### Controls after the #643 deploy (2026-10-02T12:45Z)

| Control | Status | Evidence | Blocker |
| --- | --- | --- | --- |
| Razorpay checkout | PASS | Presentation and gating live since #639 (127/127 browser checks); bad signature → 401 | — |
| Razorpay payment authority | PASS | Server Plan and price, Plan binding, Order authority; tests and controls (payment release closure P0); live unsigned webhook → 401 | — |
| Razorpay entitlement | BLOCKED | Cross-worker tests: tier, cycle, expiry, one key per subscription. No live payment | Authorized provider test credentials |
| Gumroad availability | PASS | No platform page or response offers Gumroad: checkout `available: false`; 12:26Z, none of the 17 withdrawn variants on the 15 pages. The four products still sell by direct link on Gumroad's own store | Owner: unpublish, or set the secret ([runbook §1](PAYMENT_RELEASE_OPERATOR_RUNBOOK.md#1-f21-gumroad-production-safety)) |
| Gumroad provisioning | BLOCKED | Webhook answers 500 "Webhook secret not configured" | Operator secret `GUMROAD_WEBHOOK_SECRET`, ping URL, `RESEND_API_KEY` |
| Gumroad refund/revocation | BLOCKED | Tests: refunded, disputed and ended revoke | F21 secret, then a Gumroad test sale |
| Secure credential delivery | PASS | Deployed `b516e7bb2`. Live refusals 12:23Z: GET 405, text/plain 415, malformed 400, unknown token 410, query-string token 400, admin re-issue without auth 403, all `no-store`. A live redemption needs an issued link (CI proves it: 12 tests, 9 controls) | — |
| `REVENUE_ADMIN_SECRET` alignment | BLOCKED | Deploy run 36962733371: HTTP 401 | Operator secret ([runbook §3](PAYMENT_RELEASE_OPERATOR_RUNBOOK.md#3-f24-revenue_admin_secret)) |
| Enterprise certification canary | BLOCKED | `OPERATOR_WEBHOOK_SINK_REQUIRED` (runs 36962733292, 36984546750) | Operator secrets `CDB_WATCHDOG_SINK_URL`, `CDB_WATCHDOG_SINK_INSPECT_URL`, `CDB_WATCHDOG_SINK_TOKEN` |
| Publisher runtime state | FAIL | F25: every push refused since 2026-08-26; F26: premium feeds built from August items | Owner (STAGE 4); engineering (F26) |
| Main branch required checks | BLOCKED | Ruleset 21556637 has no required-status-checks rule | Repository admin |
| 96 h renewal grace | PASS | A confirmed refund, cancellation or halt denies at once; test and control ([runbook §6](PAYMENT_RELEASE_OPERATOR_RUNBOOK.md#6-96-hour-renewal-grace-audit)) | — |
| Provider E2E transaction | BLOCKED | Procedure in [runbook §5](PAYMENT_RELEASE_OPERATOR_RUNBOOK.md#5-provider-e2e-test-procedure). No real charge made | Authorized provider test credentials |
| Customer access after verified payment | BLOCKED | Cross-worker tests only | Authorized provider test credentials |
| Customer revocation after refund | BLOCKED | Cross-worker refund tests and controls only | Authorized provider test credentials |
| Production certification | FAIL | Run 37006645392 on deployed `b516e7bb2` (12:26Z): every non-canary phase passed, lifecycle matrix included. The PRO canary refused a STALE feed (F3); the Enterprise canary is BLOCKED (no sink). Earlier run 36984546750 (08:31Z): lifecycle matrix FAIL (F17) | Fresh feed (F3); operator secrets; F17 (FinOps) |

### Required status checks on `main` — BLOCKED — REPOSITORY ADMIN ACTION REQUIRED

Ruleset 21556637 ("SENTINEL APEX Production Main Protection") has three
rules: deletion, required linear history and pull request. It has no
required-status-checks rule. That is why GitHub let #641 merge while the
regression gate was red. No tool in this session can change a ruleset.

Can each check be required today?

- **`SAST Gate (required)`** (`sast-security-scan.yml`): yes. Its
  `pull_request` trigger has no path filter, so it reports on every PR to
  `main`.
- **`workers/intel-gateway -- full unit suite (1121 tests)`** and
  **`scripts/ + tests/ -- Python unit and regression suites`**
  (`intel-gateway-regression-gate.yml`): yes, after the CI-reporting change.
  - Before it, the `pull_request` trigger had a path filter. A PR that
    touched none of those paths never started the gate, so a required check
    would have waited forever.
  - The change removes that filter for pull requests; pushes to `main` keep
    it.
  - `tests/test_regression_gate_required_check_readiness.py` pins both
    workflows: they report on every PR to `main`, their check names stay
    stable, and no job-level `if:` can skip a required job.

Admin action ([runbook §8](PAYMENT_RELEASE_OPERATOR_RUNBOOK.md#8-required-status-checks-on-main-repository-admin)):

- Add "Require status checks to pass" to SENTINEL APEX Production Main
  Protection.
- Require the three checks above, with GitHub Actions as their source.
- Do not add a bypass for the publisher (F25).

Until then, release discipline is manual: no merge while any applicable
check is queued, in progress, failed or cancelled.

### Observed on `main` after #642

- **Regression gate:** push run 36976506794, success.
- **Commercial certification:** schedule run 36984546750 (08:31Z, deployed
  `acc38a24d`), FAIL.
  - Enterprise canary BLOCKED: no sink secrets.
  - Lifecycle matrix FAIL. A JWT issued before suspension was still
    allowed 0.3 s after it. A rotation right after reactivation returned no
    key (the status is not logged), so the rotation checks after it
    failed. Both are consistent with F17; the 04:03Z run on the same
    deployed SHA passed.
  - Every other canary and phase passed.
- **SAST:** schedule run 36979405084. TruffleHog was cancelled at its job
  limit, and the gate failed closed (F27).
- **Live, 11:56Z:** the feed was generated at 06:04:31Z, 5 h 52 min old
  against the 6 h limit. No publisher run had started since 05:31Z (F3).

### Post-merge verification (#643, 2026-10-02)

- **Merge.** #643 was squash-merged at 12:21:02Z as `b516e7bb2`, whose tree
  equals the reviewed head `578fdaa49`. Before the merge, all 15 checks on
  that head were complete. Each was green, or skipped where the SAST gate
  verified it did not apply (Bandit, Safety and Semgrep: no Python or
  dependency change).
- **Deploys.**
  - deploy-worker 37006160812: succeeded.
  - deploy-revenue-engine 37006160913: succeeded.
  - pages-fast-publish 37006160911: succeeded, with every pre-deploy browser
    gate.
  - `/api/health/live` reported `b516e7bb2` at 12:23Z.
- **Live F22 (12:23Z, rejected input only).** Every answer was `no-store`:
  - `GET /api/keys/redeem`: 405;
  - `text/plain` body: 415;
  - malformed token: 400;
  - unknown well-formed token: 410;
  - token only in the query string: 400;
  - `POST /api/admin/keys/{key}/redemption` without credentials: 403.
- **Live F21 (12:26Z).** None of the 17 withdrawn variants appears on any of
  the 15 pages the register lists. `customer/api-keys.html` serves the
  redemption card.
- **Billing canary, public mode (12:23Z).** 14/15. The only failure is F21:
  `gumroad_webhook_requires_secret` returns 500.
- **Certification.**
  - The push-triggered run 37006162439 started its live phases at 12:21:14Z,
    before the gateway deploy finished (12:23:02Z). It therefore tested the
    previous deploy.
  - Its canary job stopped at 12:22:04Z without a result line, inside the
    deploy window.
  - Run 37006645392 was dispatched on `main` at 12:26Z to certify the
    deployed `b516e7bb2`. It failed.
    - Every phase except the live canaries passed: lifecycle matrix, JWT
      and rotation (F17 passed this time), expiry boundary, MSSP isolation,
      MSSP self-service, FREE rate-limit boundary, authenticated customer
      ops, customer core flow and static checks.
    - The canary job stopped in the PRO canary. That canary exits 1 with
      `NO_GO_FEED_NOT_FRESH` when the feed is not FRESH
      (`deploy/cyber-watchdog/canary.mjs` lines 56-57).
      `/api/watchdog/health` reported STALE at 12:30Z (6 h 25 min old,
      F3).
    - The run log does not show that reason (F28). The cause comes from the
      canary's code and the live health read, not from #643: the PRO canary
      passed at 08:33Z on the previous deploy, while the feed was fresh.
- **Regression gate on `main`:** push run 37006160789, success.
- **Feed freshness.** `/api/health` answered 503 at 12:27Z. The feed was
  generated at 06:04:31Z, 6 h 22 min earlier against a 6 h limit. No
  publisher run had started since 05:31Z: the 08:17 and 12:17 schedules did
  not start. This is F3's third breach. The publisher run that this change's
  merge triggers is the next one expected.

## Paying-customer lifecycle (Phase 8, 2026-10-01, deployed `d80c72643`)

| Stage | Result | Evidence / blocker |
| --- | --- | --- |
| Pricing and plan terms | PASS | Contract gate 5,366/0; F10 live; F19 corrections in PR #638 |
| Checkout: Razorpay (INR) | configured; payment NOT TESTED | webhook rejects bad signature (401); verify validates input (400). A real charge needs explicit authorization or provider test mode |
| Checkout: Gumroad (USD) | **FAIL, P0** | F21: webhook secret unset; not offered on the checkout since #639, access products still purchasable by direct URL |
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
| R05 | Gumroad FAIL (P0, operator; not offered on the live checkout since #639; unconditional copy removed, #643); Razorpay webhook configured; F22 decided (no key by email), deployed (#643); P0-1..3 fixed and deployed (#641) | F21, F22, Checkout P0, payment release closure P0; signed deliveries and a live payment need provider test mode (credential) |
| R06 | Latent risk fixed on branch | F9 (`d1c8f3e65`) |
| R07 | Partial live evidence | Cert 36690549981: MSSP isolation and self-service phases PASS |
| R08 | Partial | SAST run 36744969006 on `022ecae4` success; ESLint no-undef sweep of all Worker source (F1). Dependency scan not re-run here. The required SAST gate's classifier no longer times out on checkout (payment release closure P0). The daily full TruffleHog scan has not completed since 2026-09-30 (F27) |
| R09 | F10, F19 and checkout copy live (#639) | F10, F19, Checkout P0 (instant / EMI / GST / recurring-billing claims); F12, F23 open |
| R10 | F13 live PASS; F20 resolved | F4 (post-deploy validation not chained since 2026-09-24); F13 proven on runs 36826966415 and 36859743101; F24 (step fixed in #641; it now shows HTTP 401, a repository secret mismatch); F25 (publisher push to `main` rejected since 2026-08-26; measured, architectural event) |
| R11 | Open (#593) | Human review pending; unchanged |
| R12 | Partial | F10; F11 quarantined, live 404 (18:16Z); F15 live PASS; F16 open; F26 (premium feeds built from August items) |
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
| R29 | F5, F13, F20 merged; checkout suites now in CI | F3, F4, F5, F13, F20; `test_funnel_truth.py`, `test_gumroad_and_razorpay.py` ran in no workflow before the checkout PR |
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
| Checkout P0 (#639, `aa97c8366`) | One automated primary checkout, a gated secondary, an assisted note, truthful copy, no double payment | `upgrade.html`; revenue `subscription-engine.js`; gateway `index.js` (one route line, one import) + new `checkout-providers.js`; 24 pages' copy; evidence register; policy doc; tests, render test, 3 negative controls, regression-gate suite list | resolveCheckoutPlan, checkout state machine, js/checkout.js (validateTaxId, bindPaymentFailedHandler), S5 pending reuse, S19 Plan price check, getPricingSnapshot, gumroad-products catalog, verify_public_claims | audit above; F21 live 500; F22 by inspection | MEDIUM (customer checkout page; one revenue branch; additive API field) | revert the squash commit; Pages and both Workers redeploy from main |
| Payment release closure P0 (2026-10-02) | A verified payment gives exactly its entitlement, once, and keeps it through renewal; failures recover; CI's required SAST gate stops timing out | gateway `index.js` (one import, verify / legacy webhook / Gumroad sale), new `legacy-order-authority.js`, `gumroad-provisioning-lock.js` (additive action); revenue `subscription-engine.js`, `index.js`, `commercial-readiness.js`; 3 workflows; tests; harness; policy doc | verifyRazorpayHmac, RAZORPAY_TIER_PRICES, provisionApiKey, GumroadProvisioningLock, provisionCustomer, patchApiKeyEntitlement, PLAN_ID_ENV_KEYS, evaluateKeyRecordAccess, queueEmail, sendEmailViaProvider, the SAST gate script | failing tests on the pre-fix code for P0-1..3 and P1-1..4; 37-run SAST timing; F24 run logs | MEDIUM (payment paths of both Workers; no route, schema, auth or price change) | revert the squash commit; both Workers redeploy from main |
| Payment and commercial release blocker closure (2026-10-02) | No API key in any email (owner decision); Gumroad never advertised while it cannot provision; an owner runbook for every operator-blocked control | gateway `index.js` (one import, one route line, redeem handler, activation email, admin re-issue route) and new `key-redemption.js`; revenue `index.js` (templates, callers, `issueActivationLink`, SendGrid request) and `commercial-readiness.js`; `customer/api-keys.html`; 15 pages' copy; evidence register; policy doc; runbook; ledger; 2 test files; harness; revenue deploy-gate list | evaluateKeyRecordAccess, strongAuthStates, GumroadProvisioningLock claim, readBodyCapped, auditLog, the admin auth and lockout, sendActivationEmail, queueEmail, sendEmailViaProvider, verify_public_claims.py and the evidence register | owner decision F22 (2026-10-02); F21 live 500 and product pages at 200; ten pages offering Gumroad unconditionally | MEDIUM (two new routes; customer email content; no entitlement, schema, auth or price change) | revert the squash commit; both Workers and Pages redeploy from main |
| F26 premium baseline (2026-10-02) | The premium feeds are built from current intel, and the baseline survives between runs without git | `premium_feed_baseline.py` (guard denominator, two shared helpers, one report field), `generate_tiered_feeds.py` (one description), `r2_state_sync.py` (one owner-only entry), `sentinel-blogger.yml` (two non-blocking steps, one step id and output), regression-gate suite list, 3 new test files, the R2 state-file count pin | `_merge` and its window (shared, not re-implemented), `r2_state_sync.py` owner-only mechanism (`STATE_FILES`, `BROAD_SWEEP_EXCLUDED_PATHS`, `--only`), `r2_upload.s3_get`/`s3_cp` | runs 36956080062 and 36969320297 (guard refused 985 → 77 and 42); baseline items dated 2026-08-19..26; 2 tests fail on the old code | MEDIUM (premium feed content changes from 985 August items to the current window; publisher workflow gains two non-blocking steps; STAGE 4 untouched) | revert the squash commit; the next publisher run reads the checkout's copy again; delete `premium/state/feed.baseline.json` in R2 only if a corrupt copy must be discarded |
| CI reporting (2026-10-02) | Both gates can be required without deadlocking any PR; a failing certification canary records why | `intel-gateway-regression-gate.yml` (`pull_request` trigger, suite list), `commercial-customer-ops-certification.yml` (one line), `test_security_txt.py` (one assertion), 2 new tests, ledger, runbook §8 | the SAST gate's always-reporting pattern; the step's own `record()`/`canary()` | ruleset audit (no status-check rule); #641 merged red; runs 37006162439 and 37006645392 lost the canary's reason | LOW (CI only; the gate runs on every PR; no production code) | revert the squash commit |

Blast radius (CI reporting):

- **Files:** as listed.
- **Imports, routes, dashboards, certification reports, `/api/v1/p*` and
  data:** none.
- **CI:**
  - the regression gate now runs on every pull request to `main`, docs-only
    ones included: about 7 minutes of public-repository runner time each, at
    no cost;
  - pushes to `main` keep the path filter;
  - the certification's canary step behaves the same, except that it now
    records a failing or blocked canary instead of aborting.
- **Workflows:** the two listed.

Blast radius (F26 premium baseline):

- **Files:** as listed.
- **Imports:** none added. The tests import the scripts as modules.
- **Routes:** none changed. `/api/v1/premium/feed/*` serves the same R2
  keys, now built from the current baseline.
- **Dashboards:** none.
- **CI:** the regression gate gains 3 Python suites. The R2 FinOps gate
  runs `test_r2_state_sync.py` (count pin 22 → 23).
- **Certification reports:** none.
- **`/api/v1/p*`:** unchanged.
- **Data schema:**
  - one new R2 object, `premium/state/feed.baseline.json`, in the existing
    `sentinel-apex-data` bucket;
  - no KV or D1 change;
  - `data/baseline_report.json` gains the additive field `prior_in_window`.
- **Workflows:**
  - `sentinel-blogger.yml`: STAGE 3.1.18d and 3.1.19b are added, and STAGE
    3.1.19 gains an id and one output line;
  - `intel-gateway-regression-gate.yml`: suite list only.

Blast radius (payment and commercial release blocker closure):

- **Files:** as listed.
- **Imports:** gateway `index.js` imports `key-redemption.js`, after the
  last import.
- **Routes:**
  - new `POST /api/keys/redeem` (public, one-time token);
  - new `POST /api/admin/keys/{key}/redemption` (admin);
  - no route removed or changed.
- **Dashboards:** `customer/api-keys.html` gains a redemption card;
  `mssp-tenant-dashboard.html` shows a rotated tenant key once.
- **CI:** billing negative controls gain 9 controls and 2 suites; the
  revenue deploy gate gains 1 test file.
- **Certification reports:** none.
- **`/api/v1/p*`:** unchanged.
- **Data schema:** a new KV prefix, `key_redeem:` (72 h TTL), in the
  existing `API_KEYS_KV`; new Durable Object names, `redeem:`, on the
  existing lock class. No D1 or R2 change.
- **Workflows:** `deploy-revenue-engine.yml` (test list only).

Blast radius (checkout P0): files as listed; imports: `index.js` imports
`checkout-providers.js` (after the last import); routes: `GET /api/pricing`
gains an additive `checkout` field, `POST /api/v2/billing/subscriptions/create`
gains a 409 `checkout_in_progress` and drops the 502 `detail` field (no
consumer read it); dashboards: none; CI: gateway regression gate (+3 Python
suites), billing negative controls (+3), pages-fast-publish runs the
rewritten checkout render test; certification reports: none;
`/api/v1/p*`: unchanged; data schema: none (reuses the S5 pending key);
workflows: regression-gate suite list only. Bundle 1,690.07 → 1,691.09 KiB
(+0.06%), gzip 402.16 → 402.41 KiB.

Blast radius (payment release closure P0): files as listed; imports:
gateway `index.js` imports `legacy-order-authority.js` (after the last
import); revenue `index.js` imports `keyAccessUntil`; routes: no new or
removed route; legacy verify adds a 400 `ORDER_NOT_ELIGIBLE` and the legacy
webhook an `ignored_not_activatable` answer for payments it must not
activate; the Gumroad webhook can answer 500 (so Gumroad retries) after a
provisioning failure; dashboards: none; CI: SAST classifier job (no
checkout), regression gate (+1 Python suite, deploy-revenue-engine path
filter), billing negative controls +21; certification reports: none;
`/api/v1/p*`: unchanged; data schema: new KV keys only
(`rzp_sub_provisioned:`, `gumroad_failed:`), no D1 or R2 change; workflows:
`sast-security-scan.yml`, `deploy-revenue-engine.yml` (informational step),
`intel-gateway-regression-gate.yml`.

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
- Checkout P0 (local, 2026-10-01): gateway suite as CI runs it 1,659/1,659
  (one timing-budget test missed 300 ms once while the mutation harness
  loaded the machine; it passes alone and in the unloaded full run);
  revenue engine 177/177; billing canary 7/7; js 189/189; billing negative
  controls 104/104 (3 new); regression-gate Python suites (52 files) 1,913
  passed (1,940 with the mojibake and integrity-resync suites); checkout render test on dist
  95/95; 10/10 checkout page mutations caught; the new test rejects the
  pre-change page; all pages-fast-publish render tests on dist pass
  (Billing Center failed once under the same load, 3/3 reruns pass, page
  unchanged); `verify_public_claims.py` 29,933/0 (it found 2 pages the
  sweep missed); `verify_commercial_contract.py` 5,366/0; monetization,
  pricing, release-label, version, capability-registry, pre-deploy, worker
  JS integrity 76/76 and entitlement-drift gates PASS; regression 41/41;
  P33 WORLDWIDE_RELEASE, 0 blockers; `ci_stats_extract.py p33` valid.
- Checkout P0, CI on `baaf2ffee` (2026-10-01):
  - regression-gate Python suites 1,913 passed;
  - gateway 1,660/1,660, raw and after encoding sanitization;
  - billing canary 7/7 and billing negative controls 104/104.
- Checkout P0, after the merge (2026-10-01):
  - deploy-worker, deploy-revenue-engine and pages-fast-publish succeeded on
    `aa97c8366`;
  - Phase 12 live: static 30/30, browser 127/127, billing canary 14/15 (the
    failure is F21).
- Live probes 2026-10-01 (read-only or rejected-input only, no transactions):
  `/api/health/live` provenance; F15 sweep; webhook configuration (unsigned
  POSTs); payment verify input validation; 35-request limiter boundary (same
  shape as certification phase 8); quick-start endpoint existence; billing
  canary public mode 12:17Z and 19:30Z (14/15 both times, the failure is
  F21); #638 post-merge checks 18:16–18:58Z; #639 post-merge checks
  19:29–19:38Z (no POST from the browser probe; every non-GET request the page
  attempted was aborted and listed).

- Payment release closure P0 (local, 2026-10-02, on `5911a9722` plus this
  change):
  - gateway suite as CI runs it 1,672/1,672; revenue engine 198/198 (the
    deploy gate now lists every revenue test file); billing canary 7/7;
    js 189/189;
  - billing negative controls 125/125 (21 new) in 3 min 6 s locally; `main`
    runs 104 in 2 min 12 s here, so the regression-gate job (232–314 s on
    the last 8 runs, limit 600 s) should take about 380 s;
  - regression-gate Python suites and the SAST workflow-hygiene suites
    1,968 passed + 20 subtests (SAST classifier 33 + 16 subtests, readiness
    step 9/9);
  - `verify_public_claims.py` 29,933/0; `verify_commercial_contract.py`
    5,366/0; checkout and claims suites 40/40;
  - regression 41/41; P33 WORLDWIDE_RELEASE, 0 blockers;
    `ci_stats_extract.py p33` valid; worker JS integrity 77/77;
    entitlement drift PASS; no conflict markers; no secret patterns in the
    diff;
  - wrangler 4.142.0 dry-run: gateway 1,691.09 → 1,695.09 KiB (+0.24%), gzip
    402.41 → 403.27 KiB; revenue engine 251.78 → 256.44 KiB (+1.85%), gzip
    58.40 → 59.70 KiB.

- Payment and commercial release blocker closure (local, 2026-10-02, on
  `fcb252bd7` plus this change):
  - **Unit suites:**
    - gateway suite as CI runs it: 1,680/1,680 (8 new), raw and after
      `sanitize_encoding.py --fix`;
    - revenue deploy-gate list: 202/202 (4 new);
    - billing canary 7/7; demo-key contract 4/4; js 189/189.
  - **Negative controls:**
    - billing 134/134 (9 new), in 258 s;
    - watchdog 98/98; dashboard 31/31; health clock 4/4;
    - the safe-rollback artifact builds.
  - **Pages:** on a fresh dist build, all ten pre-deploy render tests pass
    (upgrade checkout 95/95).
  - **Python and certification:**
    - regression-gate Python suites: 1,922 passed and 4 subtests;
    - regression 41/41;
    - P33 WORLDWIDE_RELEASE, 0 blockers;
    - `ci_stats_extract.py p33` valid.
  - **Gates:**
    - `verify_public_claims.py` 35,849/0;
    - `verify_commercial_contract.py` 5,366/0;
    - release label 135/0;
    - worker JS integrity 78/78;
    - entitlement drift PASS; frontend integrity PASS;
    - no conflict markers, and no secret patterns in the diff.
  - **Bundles** (wrangler 4.142.0 dry-run):
    - gateway 1,695.09 → 1,703.28 KiB (+0.48%), gzip 403.27 → 405.50 KiB;
    - revenue engine 256.44 → 258.57 KiB (+0.83%), gzip 59.70 → 60.40 KiB.

- F26 premium baseline (local, 2026-10-02, on `b516e7bb2` plus this change):
  - **New tests:**
    - guard: 4/4; on the old code 2 fail and the 2 guard-preservation
      controls pass;
    - wiring: 5/5; 3 workflow mutations caught (upload without the download
      condition, `updated=true` on failure, download without `--only`);
    - metadata: 1/1; fails on the old code.
  - **Related suites:** every test file that reads the publisher workflow,
    the state sync, the baseline or the gate list, 581 passed across 39
    files. `test_r2_state_sync.py` 53/53.
  - **Gates:**
    - public-repo workflow hygiene: 46 passed and 16 subtests;
    - regression 41/41;
    - `test_severity_epss_truth.py` 17/17.

- CI reporting (local, 2026-10-02, on the F26 head plus this change):
  - **New tests:**
    - readiness: 3/3; the pull-request filter test fails on the old
      trigger;
    - certification canary step: 3/3; the failure and blocked cases fail on
      the old line.
  - **Existing suites:**
    - `test_security_txt.py` 18/18;
    - regression-gate Python job: 1,938 passed and 4 subtests.
  - **Workflow-reading tests:** 39 files, 539 passed and 20 subtests.
    - 2 failures, identical on the unchanged head and run by no workflow:
      `test_deploy_provenance_contract.py`, which expects a
      `SHA="${GITHUB_SHA}"` line that `deploy-worker.yml` no longer has,
      and `test_weekly_threat_brief_branch_protection.py`.
    - These are pre-existing; the same class as F5.

## Reuse report

| Metric | Result |
| --- | --- |
| Existing engines reused | checkRateLimit, bumpCounterWriteThrough, incrementStrongRate, checkDailyQuota, buildUpgradeTrigger, timingSafeEqual, isWatchdogOperator, intel_freshness_guard.py; R09: verify_commercial_contract.py and verify_public_claims.py extended in place, driven by commercial-contract.json / evidence-register.json / platform-evidence.json; F9: verifyRazorpayHmac, timingSafeEqual; F13: report_archive_manager.py floor (behaviour kept, exit status corrected); F15: applyTierGateV2 (canonical mask fixed in place); F20: INCLUDE_DIR_FILE_EXCLUDES and the v157.0 validator (refactored into a function, same messages); F17/F19/Phase 6: evidence register + verify_public_claims.py (data-driven, no new gate); checkout P0: resolveCheckoutPlan and the checkout state machine (kept, extended with resume), js/checkout.js validateTaxId and bindPaymentFailedHandler, S5 pending-checkout key, S19 Plan price check, getPricingSnapshot, the gumroad-products catalog, evidence register + verify_public_claims.py; F22: evaluateKeyRecordAccess, strongAuthStates, GumroadProvisioningLock (no-action claim), readBodyCapped, auditLog, the admin auth and lockout, sendActivationEmail, queueEmail, sendEmailViaProvider |
| Existing routes extended | none added; commercial gate condition extended; checkout P0: `GET /api/pricing` gains an additive `checkout` field; F22: two new routes (`POST /api/keys/redeem`, `POST /api/admin/keys/{key}/redemption`), neither duplicating an existing route |
| Existing dashboards extended | none |
| New engines | 4: `freshness-guard-dispatch.js` (no GitHub-dispatch path existed in the Worker); `checkout-providers.js` (pure, 20 lines: no availability signal existed for the checkout); `legacy-order-authority.js` (pure: no Order-eligibility check existed; it reads the existing `RAZORPAY_TIER_PRICES`); `key-redemption.js` (pure: no one-time credential delivery existed; it calls the gateway's own access decision and the existing lock). The revenue engine's `issueActivationLink` mirrors its record, as that Worker mirrors other gateway code; a cross-worker test pins the two |
| Duplicate engines / routes | 0 / 0 (F26 shares `_merge`'s window through `_in_merge_window` instead of copying it, and reuses the owner-only R2 state mechanism) |
| Backward compatibility | PASS (response shapes unchanged; 500 → documented 429) |
| Certification chain | PASS (P33 WORLDWIDE_RELEASE) |
| Regression suite | 41/41 PASS |
