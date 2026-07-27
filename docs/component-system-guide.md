# SENTINEL APEX Shared Component System — Guide

`css/components.css` plus the 14 files under `components/` are the
reusable enterprise UI foundation every future landing page, feature
page, documentation page, and commercial offering is meant to consume.
This guide covers architecture, usage, migration, accessibility,
performance, repository integration, and future extension.

**Status:** infrastructure only. As of this PR, no existing page links
`css/components.css` or includes any `components/*.html` fragment —
shipping it changes zero rendered output. Pages opt in individually in
future PRs, one at a time.

**Does not touch:** `css/card_renderer_styles.css` (dashboard card
system), dashboard pages, threat cards, the intel renderer,
`platform/frontend`, generated reports, the API, `index.html`, or any
other production page. `css/tokens.css` (PR-2) and `css/hero.css`
(PR-3) are both read-only inputs to this PR — see §8 for the one
disclosed, deliberate exception (button text color).

---

## 1. Component Architecture Guide

### 1.1 Layering

```
css/tokens.css        (PR-2)  ── design tokens: color, type, space, motion
        │
        ▼
css/hero.css           (PR-3) ── landing-hero-scoped styles, consumes tokens.css
css/components.css     (PR-4) ── shared, reusable UI primitives, consumes tokens.css
        │
        ▼
components/*.html      (PR-4) ── copy-paste reference markup, one per component
```

`components.css` sits at the same layer as `hero.css` — both are
consumers of `tokens.css`, neither depends on the other. `components.css`
is broader in scope (site-wide primitives vs. one page section) and is
meant to outlive and eventually absorb `hero.css`'s button styling (see
§8).

### 1.2 Why a flat CSS file plus reference HTML, not a component
framework

This repository has no templating/include system — every page (an
`index.html`, `trust-center.html`, `mssp.html`, etc.) is a fully
self-contained HTML document, and there is no build step, bundler, or
server-side templating layer to introduce partials through. Given that
constraint, "reusable component" can only mean two things:

1. **A shared stylesheet** (`css/components.css`) whose class names any
   page can adopt, and
2. **Reference markup** (`components/*.html`) a developer copy-pastes
   into a page and adapts — not an auto-included partial, because
   nothing in this repository currently has the ability to auto-include
   anything.

This is Level 4 (Reuse) and Level 5 (Minimal Change Surface) from
Section 0 applied honestly to the actual repository shape, rather than
introducing a templating system (an architectural event, not a feature
addition) just to make "reusable" mean something more automatic.

### 1.3 What's in `css/components.css`

| Section | Selectors |
|---|---|
| Accessibility | `.sapx-skip-link` |
| Layout primitives | `.sapx-container{,-wide,-narrow}`, `.sapx-section{,-sm,-lg,-alt}`, `.sapx-section-kicker/-heading/-desc`, `.sapx-grid{,-2..-6}` |
| Button system | `.sapx-btn` + `-primary/-secondary/-ghost/-outline/-danger/-success/-icon/-disabled/-loading` |
| Badge system | `.sapx-badge` + `-neutral/-brand/-success/-warning/-danger/-info/-severity-{critical,high,medium,low}` |
| Card system | `.sapx-card` + `-feature/-research/-announcement/-metric/-integration/-enterprise/-pricing/-testimonial` variants |
| CTA banners | `.sapx-cta-banner`, `.sapx-pricing-cta-price`, `.sapx-newsletter-form/-input` |
| Announcement bar | `.sapx-announcement-bar` |
| Site header + nav | `.sapx-site-header`, `.sapx-brand`, `.sapx-nav`, `.sapx-header-ctas`, `.sapx-nav-toggle` |
| Site footer | `.sapx-site-footer`, `.sapx-footer-grid`, `.sapx-footer-social`, `.sapx-status-indicator` |

Every declaration resolves through `var(--sapx-*)` — no hardcoded
colors, spacing, radius, or typography (verified by
`tests/test_components_css.py`; see §4).

### 1.4 The 14 reference files, and why there are exactly 14

The task scope names 14 files. Three `css/components.css` card
variants — research, enterprise, testimonial — don't have a 15th file
of their own; they're demonstrated inside `feature-card.html` instead
(disclosed in that file's own header comment), since `feature-card.html`
is the named file closest to "the card system" and the spec is explicit
about the file count. Metric cards, integration cards, pricing cards,
and the announcement card each keep their own dedicated file because
they're named as distinct components in their own right.

| File | Demonstrates |
|---|---|
| `header.html` | `.sapx-site-header`, `.sapx-skip-link`, mobile nav toggle (JS) |
| `footer.html` | `.sapx-site-footer` full grid + social + status indicator |
| `navigation.html` | `.sapx-nav` in isolation from the rest of the header |
| `cta.html` | Generic `.sapx-cta-banner` |
| `feature-card.html` | `.sapx-card` base + feature/research/enterprise/testimonial variants |
| `metric-card.html` | `.sapx-metric-card` statistics grid |
| `integration-grid.html` | `.sapx-integration-card` partner grid |
| `announcement.html` | `.sapx-announcement-bar` + `.sapx-announcement-card` |
| `button.html` | Full button system, every state |
| `section.html` | `.sapx-section` + spacing/background modifiers |
| `container.html` | `.sapx-container` + width modifiers |
| `badge.html` | Full badge system |
| `pricing-cta.html` | `.sapx-pricing-card` grid + `.sapx-pricing-cta-price` banner |
| `newsletter.html` | `.sapx-newsletter-form` inside a CTA banner |

---

## 2. Developer Usage Guide

1. Link both stylesheets, tokens first:
   ```html
   <link rel="stylesheet" href="/css/tokens.css">
   <link rel="stylesheet" href="/css/components.css">
   ```
2. Open the matching file under `components/` for the piece you need,
   copy the fragment, and drop it into your page.
3. Adjust copy, `href`s, and ARIA labels for your page's actual content
   — every placeholder link (`/docs.html`, `/pricing.html`, etc.) is a
   best-effort guess at real routing, not a guarantee it matches; the
   testimonial card's quote/name are explicit placeholders, not real
   customer content (see §5).
4. Do not copy `<html>`/`<head>`/`<body>` boilerplate from a reference
   file into a page that already has its own — each `components/*.html`
   file is a complete, standalone document only so it can be opened
   directly in a browser for preview; the actual reusable part is
   everything between (and including) its outermost component tag.

### Example: a feature grid

```html
<section class="sapx-section">
  <div class="sapx-container">
    <p class="sapx-section-kicker">Capabilities</p>
    <h2 class="sapx-section-heading">Why SENTINEL APEX</h2>
    <div class="sapx-grid sapx-grid-3">
      <div class="sapx-card sapx-feature-card">
        <div class="sapx-card-icon" aria-hidden="true">&#9889;</div>
        <h3 class="sapx-card-title">Real-Time Correlation</h3>
        <p class="sapx-card-desc">...</p>
      </div>
      <!-- repeat sapx-card sapx-feature-card ... -->
    </div>
  </div>
</section>
```

### The one piece of JavaScript: mobile nav toggle

`css/components.css` itself has zero JavaScript dependency. `header.html`
carries one small, essential script (`sapxToggleNav()`) that flips
`aria-expanded` on the toggle button and a `data-nav-open` attribute on
`.sapx-site-header`, which `components.css`'s
`.sapx-site-header[data-nav-open="true"] .sapx-nav` selector keys off
of. This mirrors the repository's existing onclick-handler convention
(`index.html`'s `cdbMobileNavOpen()`) rather than introducing a new JS
pattern, and is the only interactivity anywhere in this component
system.

---

## 3. Migration Guide (for a page adopting this system)

1. Add both `<link>` tags (tokens.css, then components.css) in `<head>`.
2. Replace the page's own header/footer/button markup incrementally —
   one component at a time, verified in the browser after each swap —
   rather than all at once. A page migration is its own PR per the
   "one production problem per PR" discipline already established in
   this engagement; this PR ships the library, not any page migration.
3. If the page already defines a class name that collides with an
   `.sapx-*` class (unlikely, given the `sapx-` prefix, but check), the
   later `<link>` wins by source order — put `components.css` after any
   page-specific stylesheet if the page's own rule must take priority
   during a partial migration.
4. `css/card_renderer_styles.css`, dashboard rendering, and
   `platform/frontend` are a separate, independent styling system —
   never migrate dashboard/threat-card markup onto `.sapx-card` or any
   other selector in this file.

---

## 4. Accessibility Report

Verified in real headless Chromium via Playwright
(`render-test/verify_components.py`, run against the actual
`components.css` + `tokens.css` + a composite page assembling every
component), not reasoned about abstractly:

| Check | Result |
|---|---|
| Heading hierarchy (exactly one h1, no skipped levels) | PASS |
| Keyboard Tab reaches primary CTA within 30 stops | PASS |
| `:focus-visible` shows the token-driven two-layer ring | PASS |
| Mobile nav toggle: `aria-expanded` flips, nav becomes visible | PASS |
| `.sapx-status-dot-live` pulse does NOT run under `prefers-reduced-motion: reduce` | PASS |
| `.sapx-status-dot-live` pulse DOES run under `prefers-reduced-motion: no-preference` | PASS |
| `.sapx-btn-loading::after` spinner slows (not just freezes) under reduced motion | Verified by inspection of the `@media (prefers-reduced-motion: reduce)` rule (1.4s vs. 0.6s) — a spinner communicates real in-flight state, so slowing rather than freezing avoids a misleading "stuck" appearance while still respecting the preference |

**Static structure**, verified by inspection of every `components/*.html`
file: semantic landmarks (`<header>`, `<nav aria-label="Primary">`,
`<main>`, `<footer>`), `aria-label`s on icon-only buttons and social
links, `aria-hidden="true"` on decorative glyphs, a real `<label>` (visually
hidden, not `aria-label`-only) on the newsletter email input, and a
`.sapx-skip-link` targeting `#main-content`.

### WCAG 2.1 contrast — computed, not estimated

Every color pairing below was computed with the same relative-luminance
formula used in PR-2/PR-3, then independently re-verified against the
real rendered `getComputedStyle()` output in all 4 theme combinations
(OS dark, OS light, OS dark + forced light, OS light + forced dark):

| Pairing | Dark theme | Light theme |
|---|---|---|
| `.sapx-btn-primary` text (`--sapx-color-text-on-bright`) on brand-teal | 11.80:1 | 11.80:1 |
| `.sapx-btn-danger` text on danger fill | 7.28:1 | 7.28:1 |
| `.sapx-btn-success` text on success fill | 10.87:1 | 10.87:1 |
| `.sapx-integration-card-mark` text on brand-indigo | 7.07:1 | 7.07:1 |
| `.sapx-btn-ghost` / `.sapx-btn-outline` resting text (`--sapx-color-text-primary`) on `bg-surface-raised` | 14.76:1 | 15.88:1 |

All ≥4.5:1 (WCAG AA, normal text) in both themes, confirmed by the
Playwright run in `render-test/verify_components.py`, not just the
standalone Python calculation.

### Known issue found and fixed during this PR

Designing the button system's contrast surfaced a real, pre-existing
defect: `css/hero.css`'s `.sapx-btn-primary` (PR-3, already merged) uses
`--sapx-color-text-inverse`, which is `#ffffff` in light theme —
**1.71:1 against `--sapx-color-brand-teal`, a WCAG AA failure**. This is
currently inert in production because the hero itself has not yet been
patched into `index.html` (confirmed by direct inspection of `main`'s
live file during PR-3's certification). Two more would-have-been
failures were caught before shipping: a danger button at 2.77:1 and a
success button at 1.85:1 in light theme, had this system reused
`text-inverse` instead of introducing a fix.

**Fix applied in this PR:** one new theme-invariant token,
`--sapx-color-text-on-bright: #05070d`, added additively to
`css/tokens.css` (no existing token renamed or changed — see that
file's own PR-4 comment block for the full numeric justification).
`components.css`'s button/integration-mark rules use this new token.
**`css/hero.css` itself is NOT modified by this PR** — per the "do not
revisit completed work" constraint, fixing PR-3's shipped file is out
of scope here. The recommended follow-up (tracked, not yet
implemented): change `css/hero.css`'s `.sapx-btn-primary` `color` from
`var(--sapx-color-text-inverse)` to `var(--sapx-color-text-on-bright)` —
a one-line, backward-compatible change, since the token now exists.

### Deliberate, disclosed divergence

`components.css` restates `.sapx-btn` / `.sapx-btn-primary` /
`.sapx-btn-secondary` (same class names as `hero.css`, intentionally —
one canonical button system for all future pages). The base and
`.sapx-btn-secondary` rules are value-identical between the two files.
`.sapx-btn-primary`'s `color` differs on purpose: `hero.css` keeps its
existing (buggy) `--sapx-color-text-inverse`; `components.css` uses the
new, correct `--sapx-color-text-on-bright`. **Do not load both files on
the same page until `hero.css` is patched to match** — until then,
whichever stylesheet loads last wins the cascade for that one property,
which is a genuine (if narrow and disclosed) conflict, not a silent bug.

---

## 5. Performance Report

- **Zero JavaScript** in `css/components.css` itself. The only script
  anywhere in this PR is the ~10-line mobile nav toggle in `header.html`
  (essential, not decorative).
- **Zero new HTTP requests for images** — the integration "logos" are
  text/monogram marks (`.sapx-integration-card-mark`), not image assets.
  This session's GitHub file-write tools store `content` as literal
  text and cannot reliably transfer binary files (confirmed during
  PR-1's OG-banner attempt), so real vendor logo assets are explicitly
  deferred rather than shipped broken or fabricated.
- **No new fonts, no web font loading** — typography resolves through
  `--sapx-font-sans` / `--sapx-font-mono` / `--sapx-font-display`,
  unchanged from `tokens.css`.
- **No layout-shift risk from the one animation that exists**: the
  status-dot pulse animates `box-shadow` only (not `width`/`height`/
  `margin`), so it cannot trigger reflow; it's also opt-in only via
  `@media (prefers-reduced-motion: no-preference)`.
- **Bundle size**: `css/components.css` is a single, uncompressed
  ~27KB file, additive to the existing `tokens.css` (~14KB) and
  `hero.css`. Nothing currently links it, so it adds 0 bytes to any
  page's actual transfer weight until a future PR opts a page in.
- Grid layouts use native CSS Grid (`display: grid`), not a JS layout
  library; responsive collapse is two `@media` breakpoints (900px,
  560px) per grid, matching `hero.css`'s already-established breakpoint
  values for consistency across the two files.

---

## 6. Repository Integration Guide

- **New files only**: `css/components.css` plus 14 files under
  `components/`, plus this guide and its test files. Zero existing
  files modified except the single additive token described in §4 and
  in `css/tokens.css`'s own PR-4 comment.
- **Never touches**: `index.html`, any other production page,
  `css/card_renderer_styles.css`, `platform/frontend`, generated
  reports, the API, Cloudflare Workers config, or CI/CD workflow
  definitions.
- **Idempotent by construction**: this PR only adds new files (plus one
  additive CSS custom property). There is no patch script to re-run,
  no anchor-matching, and no risk of a second application producing a
  different result — re-running "apply this PR" is just "these files
  exist with this content," which is trivially idempotent.
- **Rollback**: revert the PR's commits (or delete the new files and
  the one added token) to fully restore the prior state. No page
  references any of these files, so rollback carries zero risk to
  production rendering.

---

## 7. Future Extension Guide

- **Adopting the system on a real page** is the natural next PR:
  migrate one page's header/footer/buttons at a time (see §3), each as
  its own reviewed change.
- **Converging `hero.css` onto `--sapx-color-text-on-bright`** (§4) is
  a recommended, low-risk, one-line follow-up — tracked here rather
  than implemented in this PR, since PR-4's scope is additive
  infrastructure, not modifying PR-3's shipped file.
- **Real logo assets** for `.sapx-integration-card-mark` can replace
  the text/monogram placeholder once binary assets can be committed
  through a reliable path (e.g. a human contributor pushing image
  files directly, rather than through this session's text-only file
  tools).
- **Testimonial content**: `.sapx-testimonial-card` is intentionally
  structure-only in this PR (per the original task scope). Populating
  it requires a real, attributed customer quote — never a fabricated
  one — sourced through the founder or sales/customer-success team.
- **New components** should extend this file (additive) rather than
  starting a second stylesheet; anything that duplicates an existing
  `.sapx-*` selector's role is a Level 4 (Reuse) violation per Section 0.

---

## 8. Regression checklist (for this PR)

- [x] `css/components.css` added; only one existing file modified
      (`css/tokens.css`, additive-only — one new token, documented
      inline with its full WCAG justification).
- [x] No page currently references `css/components.css` or any
      `components/*.html` fragment — confirmed no existing render is
      affected.
- [x] `css/card_renderer_styles.css`, dashboard pages, threat cards,
      the intel renderer, `platform/frontend`, generated reports, the
      API, and `index.html` — all untouched.
- [x] Zero hardcoded colors/spacing/typography outside `var(--sapx-*)`
      in `css/components.css` — enforced by
      `tests/test_components_css.py` (static analysis).
- [x] Zero *unintentional* duplicate selectors within `components.css`
      itself — same test, explicitly distinguishing legitimate
      `@media`-scoped responsive overrides from real duplication.
- [x] The disclosed `.sapx-btn` / `-primary` / `-secondary` overlap with
      `css/hero.css` is the only cross-file duplication, and it's
      intentional, documented, and guarded by a dedicated test
      confirming it stays present and doesn't silently disappear.
- [x] All 4 theme-cascade combinations, 3 responsive breakpoints, both
      `prefers-reduced-motion` states, heading hierarchy, keyboard
      focus, and real computed WCAG contrast verified in actual
      Chromium via Playwright — not just reasoned about.
- [x] The `--sapx-color-text-inverse` contrast defect in already-shipped
      `css/hero.css` is disclosed as a known issue with a recommended
      one-line follow-up, not silently left undocumented and not
      fixed directly (out of scope for this PR).
