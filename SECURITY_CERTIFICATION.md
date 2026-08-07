# Enterprise Security Certification — v200

**Project TITAN Stage 22 Phase 5**
**Method:** direct code inspection + live tool execution (SBOM generator, npm audit, pip-audit) —
every claim below is either a file:line citation or a command's actual output, generated in this
session unless otherwise dated.

---

## 1. Dependency vulnerabilities

| Source | Result |
|---|---|
| GitHub Dependabot (repo-wide, reported on every push to this branch) | **219 vulnerabilities: 4 critical, 70 high, 96 moderate, 49 low** |
| `npm audit` (`workers/intel-gateway/`, the deployed Worker) | **6 vulnerabilities (2 moderate, 4 high)** — all in `wrangler`'s transitive dev/build tooling (`esbuild`, `miniflare`, `sharp`, `undici`, `ws`); these are build-time dependencies, not runtime dependencies of the deployed Worker artifact itself |
| `pip-audit -r requirements.txt` (root Python automation) | **98 known vulnerabilities across 13 packages** — worst: `transformers==4.37.0` (30), `torch==2.2.0` (22), `pyjwt==2.8.0` (10), `python-multipart==0.0.6` (9), `starlette==0.35.1` (9), `python-jose==3.3.0` (5), `urllib3==1.26.20` (5) |

**Assessment**: the 6 Worker-side findings are dev-tooling-only (do not ship to production) and have
a documented fix path (`wrangler@4.120.0`, a semver-major bump — not applied here, per this
program's own rule against dependency upgrades outside an explicitly-scoped upgrade task). The 98
Python findings are more consequential: `pyjwt` and `python-jose` are JWT-handling libraries with
known CVEs — if either is on a path that validates tokens for the live API (not confirmed in this
pass; `requirements.txt` covers the broader `agent/`/automation layer, not confirmed as the same
dependency set the Worker's own `resolveAuth()` uses, since the Worker is Node/JS, not Python), that
would elevate these from "should update" to "should update before GA." **Not resolved in this
document** — flagged as a Phase 9 gate input requiring an explicit decision, not silently patched.
None of these numbers were estimated; all three are actual tool output from this session (npm/pip)
or GitHub's own continuously-updated scan (Dependabot).

## 2. SBOM

`scripts/enterprise_sbom_generator.py` exists and **runs cleanly** — executed in this session:
SPDX 2.3 (`data/sbom/sbom-latest.spdx.json`, 59 packages: 57 Python + 1 NPM + entries for 436
script components) and CycloneDX 1.4 (`data/sbom/sbom-latest.cyclonedx.json`, 58 components) were
both generated and are included with this certification. `.github/workflows/sbom-generation.yml`
runs this same generator in CI. **Gap**: the NPM package count (1) is implausibly low given 11
`package.json` files exist in this repo — the generator appears scoped to a single manifest, not
the full dependency surface; a true multi-manifest SBOM would need the generator extended, which is
out of this certification's scope (an engineering task, not an audit finding to silently fix here).

## 3. Content-Security-Policy (CSP)

A real, reasonable policy is defined (`workers/intel-gateway/src/index.js:134`:
`default-src 'self'`, `frame-ancestors 'none'`, and standard directives) but is **attached at only
3 response sites** (`index.js:3837,3851,3889` — HTML report pages). It is absent from the shared
`SECURITY_HEADERS` object used by the generic JSON response helper, meaning **every API response
and every TAXII/STIX endpoint ships with no CSP.** For a JSON API this is lower-severity than for
an HTML surface (CSP's primary purpose is mitigating script injection in rendered HTML), but it is
an inconsistency worth closing before a v200 GA — HTML surfaces beyond the 3 explicitly covered
(e.g. the frozen dashboard itself, per `UI_FREEZE_POLICY.md`) do not appear to receive it either.

## 4. Other security headers

`SECURITY_HEADERS` (`index.js:124-132`) is applied broadly (~9 response sites, including the
default JSON helper): `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`,
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`.
This set is solid and consistently applied — the strongest single security dimension in this
certification.

## 5. CORS

**Wide open, and this is the certification's most significant single finding.**
`Access-Control-Allow-Origin: "*"` (`index.js:118`) is applied to every response including OPTIONS
preflight, with **no origin allowlist or reflection logic anywhere** in
`workers/intel-gateway/src` (grep-confirmed, zero matches for any conditional origin check). The
same wildcard is independently duplicated across 7+ other handler files
(`p16-19`, `p30-32-handlers.js`, `api-extensions.js`, `dark-web-monitor.js`, `premium-reports.js`,
`credit-system.js`, `revenue-enforcement.js`) rather than centralized — meaning fixing it requires
touching 8+ files, not one. For a public threat-intel read API this is a lower-severity finding than
it would be for an application handling session cookies or sensitive user actions (the baseline API
is intentionally anonymous-accessible per §6), but it should still be scoped to expected consumer
origins before GA, particularly for any authenticated (API-key/JWT) request path, where a wildcard
CORS policy combined with credentialed requests is a materially different risk than an anonymous
public GET.

## 6. Authentication

A real, non-trivial system exists: `resolveAuth()` (`index.js:319-369`) supports API-key (KV-backed,
with expiry checking and brute-force lockout) and JWT. **By design, it is optional for the baseline
API** — no credentials presented → `tier: FREE`, request proceeds rather than being rejected
(`index.js:325`). This reads as an intentional freemium-product decision, not a defect, and is
reported as context rather than a finding. **TAXII routes hard-enforce** (401 without a PRO/
ENTERPRISE credential, `index.js:1838`). **Admin routes are properly gated** (`X-Admin-Key` +
`timingSafeEqual`, 403 otherwise, `index.js:1708-1717`).

**The one clear negative finding**: the 12 P34 "Engineering assurance" endpoints
(`/api/v1/p34/{assurance,security,reliability,performance,compliance,sbom,contracts,status,metrics,
dashboard,certification,observability}`) have **zero authentication of any kind** — independently
confirmed by direct inspection (`p34-handlers.js` contains no auth-related code at all; the
`index.js` dispatch lines for all 12 call the handler directly with no gate). ADR-0012 itself
describes this exact surface as "one of the clearest internal-only surfaces" — the shipped code does
not match that description. These endpoints return aggregate metrics rather than raw secrets or PII
(confirmed by reading `p34-handlers.js:402-429`), which limits blast radius, but a platform's own
security-posture and SBOM API being anonymously, publicly readable is not something an enterprise
security certification can pass without qualification.

## 7. Authorization / tier enforcement

Real, live code: `TIERS` constant + `enforceTierGate()`/`applyTierGateV2()`
(`revenue-enforcement.js`, imported at `index.js:95`) differentiate `api_calls_day`, `rpm`,
`stix`/`ioc` access, `ai_full`, `siem`, `detection_rules`, and `actor_attribution` per tier. This is
functioning authorization along the commercial-tier axis.

## 8. RBAC

**Not implemented.** A repository-wide search for role-based patterns (`checkRole`, `hasRole`,
`RBAC`, role-conditioned authorization beyond the single admin/non-admin and tier axes) returns no
matches in `workers/intel-gateway/src`. The platform has two authorization axes today — commercial
tier (§7) and admin-vs-not (§6) — but no granular role model (e.g., "SOC analyst" vs. "org admin"
vs. "read-only" within the same paying organization). For a single-seat API-key product this is a
reasonable v1 scope; for an "Enterprise" tier that implies multi-seat organizational access, its
absence is worth naming explicitly rather than assuming RBAC exists because "Enterprise" is in the
tier name.

## 9. Rate limiting

Real and live: `checkRateLimit(env, ip, tier)` (`index.js:293`, KV-backed sliding window) plus
brute-force lockout, invoked in the live request path. `revenue-enforcement.js`'s
`trackUsageAndEnforce()` adds daily per-tier caps, returning HTTP 402 on breach. A separate
`scripts/quota_enforcer.py` exists but was not confirmed wired to the live Worker in this pass.

## 10. Audit logging

Real: `auditLog(ctx, env, event)` (`index.js:379`) is called at **20 distinct sites** across
authentication, key provisioning, and admin actions — not a stub, not a single decorative call.

## 11. Secrets management

**No hardcoded secret-shaped literal values were found** in the Worker's source or
`wrangler.toml` (pattern-scanned; none matched). All sensitive values (`ADMIN_SECRET`,
`CDB_JWT_SECRET`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET`, `GUMROAD_WEBHOOK_SECRET`, LLM
provider API keys, `TG_BOT_TOKEN`) are referenced via `env.X`, meaning they are Cloudflare-bound
secrets (`wrangler secret put`), not repository content — correct practice. One value that looks
like a secret at first glance is not one: `RAZORPAY_KEY_ID` is set as a plain, non-secret `var` in
`wrangler.toml` — this is correct, since Razorpay Key IDs (like Stripe publishable keys) are
designed to be client-visible; the actual sensitive counterpart, `RAZORPAY_KEY_SECRET`, is
correctly kept out of the repo via `env.X`. **Supply-chain reproducibility gap**: only 1 of 11
`package.json` files in this repository has a committed `package-lock.json`
(`workers/intel-gateway/package-lock.json`) — the other 10 (frontend, web3-api, and 8 Gateway-lineage
submodules) resolve dependencies unpinned, which is a real reproducibility/supply-chain risk
independent of any specific known CVE.

## 12. Certification summary

| Dimension | Status |
|---|---|
| Dependency vulnerabilities | **Needs remediation** — 219 known (4 critical), real and tool-confirmed |
| SBOM | **Present** — real generator, runs clean, artifacts included with this certification; NPM coverage gap noted |
| CSP | **Partial** — real policy, applied to 3 of many response surfaces |
| Other security headers | **Good** — consistently applied |
| CORS | **Needs remediation** — wildcard on every response, duplicated across 8 files |
| Authentication | **Good, with one clear gap** — real system; 12 P34 assurance endpoints unauthenticated |
| Authorization (tier) | **Good** — real, live enforcement |
| RBAC | **Not implemented** — reported as a scope gap, not a defect, given current single-seat-key model |
| Rate limiting | **Good** — real, live, KV-backed |
| Audit logging | **Good** — 20 real call sites |
| Secrets management | **Good** — no hardcoded secrets found; reproducibility gap (10/11 unpinned lockfiles) noted separately |

**Overall**: this is not a security-negligent platform — headers, rate limiting, audit logging, and
secrets handling are genuinely solid. But an "Enterprise Security Certification" cannot pass
unconditionally with 4 critical known dependency vulnerabilities, a wide-open CORS policy, and a
dozen unauthenticated internal-assurance endpoints outstanding. These three are this report's
explicit inputs to Phase 9's gate and Phase 10's recommendation.
