# GCPE Phase 2 — Enterprise Customer Experience & API Onboarding Audit

**Program**: Global Commercial Production Excellence (GCPE) v1.0, Workstream 1 continuation
**Phase**: 2 — Enterprise Customer Experience & API Onboarding
**Status**: Audit + plan only. No code changes in this phase.
**Method**: Evidence-first. Every finding below cites an exact file + line, or an exact
grep/read command and its result. Nothing in this document is estimated or assumed.
Sections with no direct evidence are marked **NOT YET ASSESSED**, not guessed at.

This audit builds on, and does not repeat, two pieces of prior work:
- `docs/enterprise-certification-report.md` (PR-10) — the original 5-page enterprise-family
  certification. Its still-valid findings are re-verified here against the current repo,
  not re-derived from scratch.
- PR #86 (merged) — already closed 5 SEO/structured-data drift items (dead `blog/sitemap.xml`
  reference, missing sitemap entries, `trust-center.html` canonical tag, enterprise-family
  JSON-LD). Those are **not** re-flagged here.

---

## 1. Executive Summary

**Overall call: Conditional GO** on continuing Phase B (Enterprise Customer Experience), with
one **CRITICAL** and one **HIGH** finding that should be fixed before any paid customer is
pointed at `api-docs.html` for integration.

Top findings, most severe first:

1. **`api-docs.html` publishes a rate-limit table that matches neither itself nor the real,
   deployed backend.** The Enterprise tier is listed as "Unlimited" in the main table and
   "10,000 req/day" in a CTA banner on the *same page* — and the actual Cloudflare Worker
   (`workers/intel-gateway/src/index.js:138`) enforces a third, different figure entirely
   (600 req/min). A prospective customer who reads this page top to bottom sees a contradiction
   before they've even signed up.
2. **Compliance/certification wording contradicts itself across 4 live pages**, with actual
   conflicting target dates (Q3 2026 vs. H2 2026 vs. "in planning") for the same SOC 2 audit,
   and one page (`trust-center.html`) still carries an outright "CERTIFIED" badge that a
   sibling page's own source comment flags as inconsistent with the rest of the site's
   deliberately hedged wording.
3. **The production homepage (`index.html`, 20,623 lines, the site's real front door) does not
   link to the 5-page enterprise family, `developer-portal.html`, or the real onboarding runbook
   at all**, except one single link to `api-docs.html` buried at line 8583. Three
   built-and-shipped customer-facing surfaces are effectively undiscoverable from the homepage.
4. Several previously-documented API facts (JWT algorithm, JWT lifetime, base domain) turn out
   to be **directly resolvable** against the real Worker source in this same repo — this audit
   did that resolution (§4) rather than leaving them as open disagreements.

None of this touches the report-engine, validators, or anything from Phase A — confirmed by
scope before starting.

---

## 2. Customer Journey Map

**Caveat, stated plainly**: this is reconstructed from link structure in the repo (what
actually hrefs to what), not from analytics or observed user sessions. No analytics access
exists in this environment. Treat it as "what the code allows," not "what users actually do."

**Journey A — Enterprise buyer landing on the homepage:**
`index.html` → real nav (`.nav-hub`, 36 items, `index.html:5374-5423`) has links to
`/contact-enterprise.html`, `/mssp.html`, `/compliance.html`, `/services.html`, `/partner.html`
and a `#contact` anchor — but **zero** links to `enterprise-homepage.html`,
`enterprise-pricing.html`, `enterprise-compliance.html`, or `trust-center.html` (confirmed:
`grep -c` for all 5 enterprise-family filenames across `index.html` = 0 for every one, and
`grep -n 'href="/enterprise\.html"' index.html` also returns 0 matches anywhere in the file).
A buyer following the real, live nav never reaches the newer enterprise-family pages at all —
they'd have to already know the exact URL.

**Journey B — Developer trying to get an API key and make a first call:**
`index.html` → one link to `api-docs.html` (`index.html:8583`) → `api-docs.html`'s own nav
(`api-docs.html:85-95`) points to the **legacy** `/pricing.html` and `/enterprise.html`, not
`enterprise-pricing.html`/`enterprise-homepage.html` → the CTA "Get API Key" on `api-docs.html`
(`api-docs.html:137`) goes to `/pricing.html`, not a dedicated key-provisioning flow →
`api-docs.html` does **not** link to `developer-portal.html` at all (`grep -in
"developer-portal" api-docs.html` → no matches). A developer following this page's own links
never discovers `developer-portal.html` (which has the more complete/self-auditing docs) or
`onboarding.html` (which has the actual step-by-step provisioning runbook) unless they already
know those URLs.

**Journey C — Existing enterprise customer needing SIEM/detection onboarding:**
`onboarding.html` (614 lines) is a real, well-built 8-step runbook (API key provisioning → first
call → SIEM integration → STIX/TAXII feed setup → detection rules → white-label → AI Cyber
Brain API → monitoring/alerting), but Step 1 assumes **an existing subscription**
(`onboarding.html:181`: *"Enterprise API keys are provisioned by the SENTINEL APEX team within 1
business day of subscription confirmation"*). It is an enterprise-onboarding runbook, not a
self-serve free-tier quickstart, and it isn't linked from `developer-portal.html` or `index.html`
(`grep -in "developer-portal" onboarding.html` → no matches).

---

## 3. Documentation Audit

- `enterprise-knowledge-center.html` (727 lines) is a real, substantial documentation hub: live
  search over 31 resource cards in 7 categories, a 15-row documentation index, a changelog
  explorer over 28 changelog files, and — notably — its own **"Known Repository Drift
  Dashboard"** (`enterprise-knowledge-center.html:588-611`) that already discloses 8 of the
  drift items this audit independently re-confirms (version number, SOC2/ISO27001 wording,
  nav mismatch, sitemap gaps, JWT algorithm, API/auth drift). **Finding**: the drift is already
  known and disclosed *inside the product*, on a page most visitors will never reach (it isn't
  linked from `index.html` — see §6) — the disclosure exists, but not where it does any good.
- A real quickstart page, `docs/quickstart.html`, is referenced pervasively (matched in
  `developer-portal.html`, `enterprise-knowledge-center.html`, footers of 3 enterprise-family
  pages, and multiple `docs/*.md` files) but its own content was **not read in this audit round**
  — out of the scope the research agents were given. **NOT YET ASSESSED**: whether
  `docs/quickstart.html`'s content agrees with `api-docs.html`, `developer-portal.html`, or the
  real backend.
- `developer-portal.html` (666 lines) is unusual: rather than being a normal doc page, its own
  body content is substantially a **self-audit of documentation drift** across `docs/api-auth-guide.md`,
  `SECURITY.md`, `apex_openapi_v3.yaml`, `README.md`, and an SDK script — it names the
  contradictions explicitly (`developer-portal.html:264-271, 561-566`). This is good discipline
  applied inconsistently: the drift is documented in prose on this one page, but not fixed at
  the source, and a visitor has no way to tell from `api-docs.html` alone that this disclosure
  page exists (see §5).

---

## 4. API Onboarding Audit — including backend cross-check

The research agents found 5 categories of disagreement across API-related docs. Rather than
leave all 5 as "disclosed but unresolved," I checked the real, deployed Worker source
(`workers/intel-gateway/src/index.js`, the actual backend named in this repo's own CLAUDE.md)
to resolve as many as possible against ground truth.

| Fact | Docs claim | **Real backend (verified)** | Verdict |
|---|---|---|---|
| Auth scheme | `api-docs.html`: only `X-API-Key`. `developer-portal.html`: "Convention A" (Bearer) vs "Convention B" (X-API-Key), presented as unresolved. | `resolveAuth()`, `index.js:319-323`: accepts **`X-API-Key` header, `Authorization: Bearer <token>`, or `?api_key=` query param — all three, in that fallback order.** | **Not a functional bug** — all documented conventions actually work. The real gap is that no doc says "we accept all three"; each shows only one, which reads as inconsistency even though nothing is broken. |
| JWT algorithm | `SECURITY.md`: HS256. `trust-center.html`: RS256 (per `developer-portal.html:562`'s own citation). | `index.js:21,212`: `alg: "HS256"`, `crypto.subtle` HMAC-SHA256, explicitly commented "Real JWT HS256... no more fake 16-char check." | **RESOLVED: SECURITY.md is correct. `trust-center.html`'s RS256 claim is wrong** and should be corrected to match reality. |
| JWT lifetime | `SECURITY.md`: 24h. `apex_openapi_v3.yaml`: 30 days (per `developer-portal.html:563`). | `index.js:97`: `JWT_EXPIRY_SEC = 86400; // 24h JWT lifetime`, used directly in `exp`/`expires_in` at issuance (`index.js:1593,1601`). | **RESOLVED: SECURITY.md is correct. `apex_openapi_v3.yaml`'s 30-day claim is wrong.** |
| Rate limits | `api-docs.html` table (L280-286): Free 100/day+10/min, Pro 5,000/day+100/min, **Enterprise Unlimited**+500/min, MSSP Unlimited+1000/min. Same file, L529/543-544: Enterprise = **"10,000 req/day."** | `index.js:138`: `RATE_LIMITS = { FREE: 30, PRO: 120, ENTERPRISE: 600, MSSP: 1200 }` — a flat **per-minute** sliding window (`index.js:293-301`), no daily cap in code at all. | **RESOLVED, and worse than it looked**: `api-docs.html` doesn't just contradict itself — neither of its own numbers matches the real enforced limit (600 req/min ≈ 864,000/day theoretical ceiling, nothing like "Unlimited" or "10,000/day"). The entire published table needs to be rebuilt from the real `RATE_LIMITS` constant, not patched to pick one of its two existing wrong answers. |
| Base domain | Majority use `intel.cyberdudebivash.com`; `docs/api-auth-guide.md` and an SDK script reference `cyberdudebivash.github.io/...` and `api.sentinelapex.cyberdudebivash.com` (per `developer-portal.html:565`). | `workers/intel-gateway/wrangler.toml:24-28`: only `intel.cyberdudebivash.com/{api,reports,taxii,auth}/*` are real, zone-routed patterns. | **RESOLVED: `intel.cyberdudebivash.com` is the only live domain.** The other two referenced elsewhere would not resolve to a working API if a developer copy-pasted them. |
| Key format | `developer-portal.html:271,561` cites 3 different prefixes shown in different files: `sa_<key>`, `SA-PRO-<hex>`, `cdb_pro_/cdb_ent_<hex>`. | `index.js`'s `resolveAuth()` does a raw `env.API_KEYS_KV.get(raw, "json")` lookup with no prefix parsing visible in the auth path itself. | **NOT RESOLVED from this check** — key format is a provisioning/generation-side question, not something the request-handling code settles. Would need the key-issuance code path, out of this audit's scope. |

**Customer impact**: a developer who reads `api-docs.html` in isolation gets a materially wrong
mental model of Enterprise-tier throughput — the real ceiling is far higher (per-minute, not
per-day) than either number the page shows, which could cause an enterprise prospect to
under-provision architecture around a false "10,000/day" ceiling, or distrust the platform for
publishing "Unlimited" and a concrete cap in the same breath.

---

## 5. Developer Experience Audit

- `api-docs.html` → `developer-portal.html`: **0 links** (`grep -in "developer-portal"
  api-docs.html` → no match). `developer-portal.html` → `api-docs.html`: **19 links**
  (nav, hero CTA, footer). The relationship is one-directional; a visitor starting from the more
  prominent, shorter-named `api-docs.html` has no path to the more complete, self-auditing
  `developer-portal.html`.
- `api-docs.html`'s own header nav (`api-docs.html:85-95`) links to the **legacy**
  `/pricing.html` and `/enterprise.html`, not `enterprise-pricing.html`/`enterprise-homepage.html`
  — inconsistent even relative to the newer page family it should arguably be part of.
- Open question, not resolved here: is `developer-portal.html` intended to be a normal
  customer-facing page, or is it functioning more like an internal drift-tracking document that
  happens to be public? Its content (a prose audit of documentation contradictions) reads
  unusually for a page meant to help a developer integrate. **NOT YET ASSESSED** — this is a
  product-intent question, not something the repo answers on its own.

---

## 6. Navigation Audit

Three mutually disconnected navigation systems exist, each internally consistent, none aware of
the others:

1. **`components/header.html` / `components/navigation.html`** (identical `.sapx-nav`, 9 items):
   5 of 9 hrefs point to files that do not exist anywhere in the repo — `products.html`,
   `api.html`, `docs.html`, `research.html`, `contact.html` (confirmed via `Glob`, each returned
   "No files found"). Re-verifies the prior certification report's item 3 exactly (still 5/9
   dead).
2. **`index.html`'s real, live navigation** — desktop `.nav-hub` (36 items, `index.html:5374-5423`)
   + mobile `.mnav-link` drawer (~28 items, `index.html:5208-5287`). Overlap with system 1: **1
   of 9** links shared (`/pricing.html`). Overlap with the enterprise-family nav (system 3):
   **0 of 7**.
3. **The 5-page enterprise family's own nav** (`enterprise-homepage.html`, `enterprise-pricing.html`,
   `enterprise-compliance.html`, `developer-portal.html`, `enterprise-knowledge-center.html` — all
   byte-identical 7-link `.sapx-nav`): links to each other and back to `/index.html`, but nothing
   in `index.html`'s real nav points back.

`trust-center.html` and `api-docs.html` each use a **fourth and fifth** distinct nav shape,
neither matching systems 1-3, and neither linking to any of the 5 enterprise-family pages
(confirmed: `grep -c` of all 5 enterprise-family filenames against both files = 0 in all 10
combinations).

**Net finding**: there is no single, live, correct primary navigation anywhere in this repo.
The "canonical" component reference is 55% dead; the real homepage nav shares almost nothing
with either the component reference or the newest page family; and the newest page family is
internally well-connected but isolated from everything built before it.

---

## 7. Information Architecture Audit

**New finding, not in the prior certification report**: three separate files carry
near-identical "Trust Center" identity:
- `trust-center.html` — `<title>` = `"Trust Center — CYBERDUDEBIVASH® SENTINEL APEX"`, legacy
  design, still shows an outright "CERTIFIED" badge (§8).
- `enterprise-compliance.html` — its own nav labels itself "Trust Center" even though the
  filename is `enterprise-compliance.html`; its own header comment (`enterprise-compliance.html:34-36`)
  explicitly notes it is a *different* file from `enterprise-trust-center.html`.
- `enterprise-trust-center.html` — a **third**, separate, live file with an identical `<title>`
  string to `trust-center.html`, but functionally different: it's a real dashboard fetching
  `/api/v1/p29/observability`, `/api/v1/p29/release-assurance`, and `/api/v1/p29/customer-value`
  (`enterprise-trust-center.html:192,285,315`).

**Customer/engineering impact**: three files with overlapping names and near-identical branding
is exactly the kind of collision that leads to a future edit landing on the wrong file, or a
customer bookmarking/sharing the wrong URL. This is an IA smell independent of any one page's
content being right or wrong.

---

## 8. Commercial Trust Audit

Re-verifies and sharpens the prior report's item 2 ("4 pages independently assert different SOC
2 / ISO 27001 status wording") — confirmed still true, and worse than "different wording": the
**dates conflict**, not just the phrasing.

| File | SOC 2 status wording | Target date |
|---|---|---|
| `trust-center.html:303-305` | "SOC 2 Type II Readiness... aligned with SOC 2 trust service criteria" | "⏳ IN PROGRESS" (no date) |
| `security-compliance.html:131,156` | "SOC 2 Type II audit in progress" | **"Q1–Q3 2026... report expected Q3 2026"** |
| `compliance.html:232-236` | "SOC 2 Type II readiness programme underway... mapping completed" | **"planned for H2 2026"** |
| `enterprise-compliance.html:404-405` | "Not yet certified by either [SOC2 or ISO27001]... certification work in progress" | no date given |

`security-compliance.html` says the SOC 2 report lands Q3 2026; `compliance.html` says the audit
itself is merely "planned for H2 2026" — two different pages describing what should be one real
external audit, with dates that can't both be describing the same timeline consistently.

`trust-center.html:281` also still reads `✅ SOVEREIGN INDIA CERTIFIED DESIGN` — a different
(sovereignty, not SOC2/ISO) claim, but `enterprise-compliance.html`'s own source comment
(`enterprise-compliance.html:86-92`) explicitly flags that this exact phrase was "deliberately
paraphrased without the word 'certified'" on the newer page, on purpose, because the newer page
treats the word "certified" as a claim requiring real backing — and then explicitly notes it
did **not** go back and fix `trust-center.html`'s stronger claim. The inconsistency is not just
present, it's self-documented and left unresolved.

`ISO 27001` status across the same 4 files: `trust-center.html` = "ROADMAP — Q3 2026" (not
started); `security-compliance.html` = "IN PROGRESS... formal audit on roadmap" (internally
tense within one file); `compliance.html` = "ALIGNED · PURSUING CERT... in planning." Three
different framings of the same not-yet-certified status.

This is a genuine commercial/legal exposure category, not just a copy-editing issue — consistent
with the anti-fabrication standard this company's own `CYBERDUDEBIVASH-ENTERPRISE-PRODUCTION`
repo governance already applies elsewhere ("aligned" is defensible, "certified" is not, unless
evidenced) — that standard is not being applied uniformly across these 4 pages today.

---

## 9. Accessibility Findings (static signals only — explicitly not a WCAG/axe audit)

No live browser or automated accessibility tool was used. These are static-code observations
only; a real WCAG 2.1 AA pass (contrast, keyboard traversal, screen-reader flow, focus order)
is **NOT YET ASSESSED** and needs a live browser.

- **No `<img>` tags exist across the 9 audited pages** — the site uses icon fonts/unicode glyphs
  throughout, so the classic "missing alt text" check doesn't apply here at all.
- **`<html lang="en">` present on all 9 files** — no gaps.
- **`index.html`'s footer social icons are missing `aria-label`** on 2 of 4: Facebook
  (`index.html:8027`) and Instagram (`index.html:8028`) have neither `title` nor `aria-label`;
  X/Twitter and GitHub (`index.html:8026,8032`) at least have a `title` attribute but not
  `aria-label`. All 6 of the newer `sapx`-templated pages (the enterprise family) do this
  correctly with `aria-label` on every social icon.
- **Heading-hierarchy issues** (3 files): `index.html`'s only `<h1>` (`index.html:5372`, the
  decorative "CYBERDUDEBIVASH®" logo text) appears *after* the page's first `<h2>`
  (`index.html:4967`) — an h2-before-h1 document order. `enterprise.html` has zero `<h3>` tags
  anywhere, jumping directly from `<h2>` (L855) to `<h4>` (L875) three times. `api-docs.html` has
  an `<h3>` (L134, inside a CTA banner) positioned *before* its own `<h1>` (L139). The other 7
  pages checked have clean, properly-nested heading sequences.

---

## 10. SEO Findings

The 5 items already closed in PR #86 (dead `blog/sitemap.xml` reference, missing sitemap
entries for the enterprise family + `api-docs.html`, `trust-center.html` canonical tag, and
enterprise-family JSON-LD) are **not repeated here**. New, this round:

- The heading-hierarchy issues in §9 are also an SEO signal, not just an accessibility one —
  search engines weight `<h1>` content meaningfully, and `index.html` effectively has no
  semantically-first heading (its one h1 is a logo, appearing after other heading content).
- `api-docs.html`'s self-contradicting rate-limit claims (§4) are a risk if this page is ever
  surfaced as a rich snippet or scraped by a documentation aggregator — publishing two different
  numbers for the same fact on one indexed page is a data-quality signal search engines and
  AI-answer engines increasingly penalize.

---

## 11. Prioritized Improvement Backlog

| # | Finding | Severity | Evidence | Requires a decision before fixing? |
|---|---|---|---|---|
| F1 | `api-docs.html` rate-limit table self-contradicts AND doesn't match real `RATE_LIMITS` | **CRITICAL** | §4 | No — real values are known (§4 table). Mechanical fix once approved. |
| F2 | Compliance wording contradicts (conflicting SOC2 dates; unresolved "CERTIFIED" badge) | **CRITICAL** | §8 | **Yes** — which target date/wording is the real one is a business/legal call, not mine to pick. |
| F3 | `trust-center.html` JWT algorithm (RS256) wrong vs. real HS256 | HIGH | §4 | No — real value known. |
| F4 | `apex_openapi_v3.yaml` JWT lifetime (30 days) wrong vs. real 24h | HIGH | §4 | No — real value known. |
| F5 | Docs referencing non-routed domains (`cyberdudebivash.github.io`, `api.sentinelapex...`) | HIGH | §4 | No — real domain known. |
| F6 | `index.html` doesn't link to enterprise family / developer-portal / onboarding | HIGH | §2, §6 | No — additive link, low risk. |
| F7 | `components/header.html`/`navigation.html` reference 5 nonexistent pages | MEDIUM | §6 | **Yes** — either build those 5 pages or replace the reference; not a 1-line fix either way. |
| F8 | `api-docs.html` nav links to legacy pricing/enterprise pages, not the new family | MEDIUM | §5 | No — additive/corrective link. |
| F9 | 3-way naming collision: `trust-center.html` / `enterprise-compliance.html` / `enterprise-trust-center.html` | MEDIUM | §7 | **Yes** — a rename/redirect/merge decision, architectural event per this repo's own governance. |
| F10 | `index.html` missing `aria-label` on 2 social icons | LOW | §9 | No — copy an existing pattern. |
| F11 | Heading-hierarchy issues (`index.html`, `enterprise.html`, `api-docs.html`) | LOW | §9 | Partial — needs a quick CSS-dependency check before relabeling tags (heading tags are often styled by selector). |
| F12 | `api-docs.html` ↔ `developer-portal.html` one-directional linking | LOW | §5 | No — additive link. |

---

## 12. Independent PR Plan

Each PR below is scoped to be small, independent, and reversible — consistent with this repo's
governance. None are implemented yet; this is the plan, pending your go-ahead.

- **PR-A (ready to implement once you confirm)**: Rebuild `api-docs.html`'s rate-limit table
  from the real `RATE_LIMITS` constant (F1), fix `trust-center.html`'s JWT algorithm claim to
  HS256 (F3), fix `apex_openapi_v3.yaml`'s JWT lifetime to 24h (F4), and correct/flag the
  non-routed domain references (F5). All four are "make the docs match the code," single-file
  or few-file changes, zero ambiguity once you confirm you want the real values published.
- **PR-B (ready to implement)**: Add homepage discoverability links — a small, additive set of
  links from `index.html`'s existing nav/footer to the enterprise-family hub and/or
  `developer-portal.html` (F6); fix `api-docs.html`'s own nav to point at the new enterprise
  pages instead of legacy ones (F8); add a link from `api-docs.html` to `developer-portal.html`
  and vice versa where missing (F12).
- **PR-C (ready to implement)**: Accessibility quick win — add `aria-label` to `index.html`'s 2
  under-labeled social icons (F10), matching the pattern already used on the 6 newer pages.
- **PR-D (needs a quick pre-check, not a decision)**: Heading-hierarchy fixes (F11) — before
  touching tag levels, check whether `index.html`/`enterprise.html`/`api-docs.html`'s CSS styles
  headings by tag selector (`h1{...}`, `h3{...}`) rather than by class; if so, relabeling would
  need matching class additions to avoid a visual regression.
- **Held for your decision, not planned as a PR yet**: F2 (which compliance wording/date is
  correct), F7 (build vs. retire the 5 dead nav targets), F9 (what to do about the 3-way trust
  page naming collision). These are flagged in §11 as requiring a decision before any
  implementation, per this repo's "when breaking changes are unavoidable: STOP, DOCUMENT,
  JUSTIFY, PLAN, CONFIRM" rule — none of these are mine to resolve unilaterally.

---

## 13. Implementation Roadmap

1. PR-A (API doc accuracy) — highest customer-trust impact, zero ambiguity, do first.
2. PR-B (discoverability links) — small, additive, unlocks the rest of the built-but-hidden
   customer experience.
3. PR-C (aria-label fix) — trivial, can ride alongside B.
4. PR-D (heading hierarchy) — after a quick CSS dependency check.
5. F2, F7, F9 — surfaced to you now; implementation plan to follow once you decide direction on
   each.

---

## 14. Customer Impact Matrix

| Finding | Enterprise buyer | Developer/API consumer | SOC/technical evaluator |
|---|---|---|---|
| F1 (rate limits) | Medium — could misjudge cost/fit | **High** — directly plans integration around a wrong number | Medium |
| F2 (compliance wording) | **High** — procurement/legal read this closely | Low | **High** — often the one doing vendor security review |
| F3-F5 (JWT/domain) | Low | **High** — breaks a real integration attempt if the wrong domain/algorithm is trusted | Medium |
| F6 (homepage links) | **High** — never finds the enterprise pages built for them | Medium | Medium |
| F7 (dead nav refs) | Low (invisible unless this component ships) | Low | Low |
| F9 (naming collision) | Medium — could bookmark/share the wrong URL | Low | Medium |

---

## 15. Commercial Value Matrix

| Fix | Revenue/trust value category |
|---|---|
| PR-A (API doc accuracy) | Reliability/SLA trust signal; reduces integration support burden; protects enterprise sales conversations from being undercut by self-contradicting docs |
| PR-B (discoverability) | Direct commercial value — connects real traffic on `index.html` to purpose-built enterprise conversion pages that currently get near-zero homepage-driven traffic |
| PR-C (a11y label fix) | Trust/compliance posture; low cost, non-zero enterprise-procurement relevance |
| F2 resolution (compliance wording) | **Highest-value item on this list** if resolved correctly — directly protects against a procurement/legal objection during enterprise sales |

---

## 16. Success Metrics

- PR-A: `api-docs.html`'s rate-limit table contains exactly one number per tier, matching
  `RATE_LIMITS` in `index.js` byte-for-byte; 0 remaining internal contradictions (grep-verifiable).
- PR-B: `index.html` contains ≥1 real `<a href>` to each of `enterprise-homepage.html` and
  `developer-portal.html` (grep-verifiable); `api-docs.html`'s nav contains 0 remaining links to
  legacy `/pricing.html` or `/enterprise.html` in favor of their `enterprise-*` equivalents.
- PR-C: `index.html`'s 4 footer social icons each carry an `aria-label`, matching the other 6
  pages (grep-verifiable count = 4/4).
- F2 (once a direction is chosen): the 4 compliance pages state one consistent target date and
  one consistent status framing — verifiable by re-running the same grep this audit used.

---

## 17. NOT YET ASSESSED (explicit register)

- `docs/quickstart.html`'s actual content and whether it agrees with the real backend or with
  `api-docs.html`/`developer-portal.html`.
- Whether `/index.html#threat-intelligence`'s anchor id exists in the DOM.
- API key *format* provisioning (the `sa_`/`SA-PRO-`/`cdb_pro_` prefix question) — needs the
  key-issuance code path, not just `resolveAuth()`.
- A real WCAG/axe-core accessibility pass (contrast, keyboard nav, focus order, screen-reader
  flow) — needs a live browser.
- Actual observed customer behavior for the Customer Journey Map — this document only reflects
  link-structure analysis, not analytics.
- Search functionality, localization readiness, and live SOC/threat-hunting/case-management
  workflows — these are running-application behaviors, out of a static-file audit's reach.
- All GCPE workstreams beyond this Phase 2 slice (Intelligence Quality, Platform Reliability,
  Commercial Platform/Phase C, Trust Center content beyond wording, Performance, Security beyond
  JWT/auth, Observability, Customer Success, Global Scale/Phase D) — per standing instruction,
  marked not yet assessed rather than estimated.
