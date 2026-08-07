# UI Freeze Policy — v200

**Project TITAN Stage 22 Phase 3 — Customer Experience Freeze**

---

## 1. A decision this policy surfaces rather than silently makes

Before anything can be "frozen as canonical," the platform needs to agree on what the current
customer dashboard actually is — and the evidence shows **two different, non-trivial answers**,
not one:

| Candidate | Evidence for | Evidence against |
|---|---|---|
| **`dashboard/enterprise_dashboard.html`** (71.2KB) | **Actually linked from `index.html`** — the one real customers can navigate to today. 45 live `/api/*` fetch calls (data-driven, not static). Has some semantic/ARIA markup (3 instances). | Single 768px breakpoint only (no tablet-specific tier). Not the file P33's own certification script checks for. |
| **`enterprise-cyber-intelligence-os.html`** (ECIOS, 39.9KB) | The file `p33_production_certification.py` gate G24 explicitly checks for. Most complete: 10 live tabs against `/api/v1/p33/*`. Two breakpoints (1024px/768px — a real tablet tier). Extensively documented across the `P33_*.md` audit family as canonical. | **Linked from nowhere** — a repo-wide grep for its filename across every other `*.html` file returns zero matches. No real customer reaches it through the live site today. |

Both are real, functioning, non-trivial pages — this is not a "one is fake" situation. It is a
platform that built a more complete dashboard (ECIOS) and a certification process that recognizes
it, without ever linking it into the customer-facing navigation that ships. **This policy resolves
the "which one" question the plain-English way**: *current* means what a customer can reach today,
so `dashboard/enterprise_dashboard.html` is the artifact this freeze protects. ECIOS is documented
below as a second, real asset whose promotion (replacing the linked dashboard, or being properly
linked alongside it) is exactly the kind of decision this policy requires an ADR for — not something
an audit should decide unilaterally. If the business intends ECIOS to be the actual v200 flagship,
say so explicitly and this document's freeze target changes; until then, the reachable page is the
one being frozen.

At least 28 other dashboard-named `.html` files exist elsewhere in the repo (13 in `dashboard/`
alone: `web3_dashboard.html`, `analyst_dashboard.html`, `threat_graph_dashboard.html`,
`enterprise-command-center.html`, etc., plus ~15–20 more at the repo root). None of these are
addressed by this freeze — they are out of scope unless and until they are linked into the live
customer navigation, at which point they'd need their own audit before joining the frozen set.

## 2. What is frozen (v200 baseline)

`dashboard/enterprise_dashboard.html`, as it exists on `main` at the time of this policy, is the
**canonical v200 customer dashboard baseline.** Audited properties:

| Property | Finding |
|---|---|
| Layout | Single self-contained HTML file, no external template/build system (`docs/component-system-guide.md` confirms this repo has no templating/include mechanism for pages) |
| Responsiveness | 1 `@media` breakpoint (`max-width: 768px`) — mobile/desktop split exists; no distinct tablet tier |
| Navigation | Reachable via `index.html`'s live link; internal navigation not independently re-audited in this pass (out of scope for a freeze decision — content correctness is a separate concern from freeze eligibility) |
| Data source | Live, `fetch()`-driven against production API endpoints (45 call sites) — not a static mockup |
| Accessibility | 3 semantic/ARIA hits found — thin, but non-zero; better than ECIOS's zero |
| Desktop / Tablet / Mobile | Desktop and mobile (<768px) both have explicit CSS handling; no dedicated tablet breakpoint means tablet viewports inherit desktop layout, which may not be intentional — flagged as a pre-GA enhancement candidate, not a freeze blocker (enhancements remain allowed under §3) |

## 3. Freeze rules (effective for v200 and all v200.x patches)

1. **No redesign after v200.** Layout structure, navigation model, and information architecture of
   the frozen dashboard do not change for the lifetime of the v200 major version.
2. **Enhancement only.** Bug fixes, accessibility improvements, performance optimization, and
   content/data updates are permitted and encouraged — they do not require an ADR. Adding the
   missing tablet breakpoint noted in §2 is an example of a permitted enhancement, not a freeze
   violation.
3. **ADR required for any breaking UI change** — defined here as: removing or restructuring an
   existing navigation element, changing the page's primary layout grid, replacing the dashboard
   file itself (including promoting ECIOS or any other candidate to replace it), or any change that
   would require a returning customer to relearn where existing information lives. Follow the
   existing ADR process (`docs/adr/`, mirroring ADR-0007–0013's format) — Current
   Architecture / Proposed Architecture / Reason / Expected Benefits / Compatibility Assessment /
   Migration Plan / Rollback Plan, per this repository's own `CLAUDE.md` Architecture Preservation
   Rule, which already governs backend changes and is extended here to the frozen UI surface.
4. **Data/API contract changes that alter what the dashboard displays are exempt from the freeze
   itself** but remain subject to ADR-0012's own compatibility rules (additive fields = fine;
   removing/retyping a field the dashboard reads = a breaking API change requiring its own
   process, independent of this UI freeze).
5. **The freeze does not extend to the ~28 unlinked dashboard-named files.** They are neither
   protected nor endorsed by this policy. Linking any of them into live navigation is itself a
   navigation-model change under rule 3 and requires an ADR before it ships.

## 4. Known pre-existing gaps carried forward, not silently fixed by this policy

Consistent with `TITAN_V200_RELEASE_AUDIT.md` §7 and this program's "document, don't silently
resolve" convention:
- No dedicated tablet breakpoint (both dashboard candidates).
- Thin-to-zero accessibility markup on both candidates — a real gap for any enterprise customer
  under accessibility procurement requirements (e.g. VPAT/WCAG contractual obligations common in
  enterprise SaaS deals).
- The ECIOS/linked-dashboard duplication itself (§1) is the most consequential open item this phase
  surfaces — recommended for explicit resolution before, not after, a v200.0.0 tag.

## 5. Compliance checkpoint

This policy does not itself change any file — it is a declaration + rule set, per Phase 3's charter
("the current dashboard becomes canonical," not "the current dashboard becomes redesigned"). No
code changes accompany this document.
