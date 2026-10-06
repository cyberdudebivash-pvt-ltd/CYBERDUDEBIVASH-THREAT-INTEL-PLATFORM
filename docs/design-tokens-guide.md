# SENTINEL APEX Design Tokens — Guide

`css/tokens.css` is the single source of truth for typography, spacing,
radius, elevation, and color across marketing/content pages. This guide
covers naming, theming, migration, usage, compatibility, and the
regression checklist for anyone adopting it.

**Status:** infrastructure only. As of this PR, no page links this
file — it changes nothing until a future PR (starting with PR-3, the
landing page hero rebuild) opts a page in.

**Does not touch:** `css/card_renderer_styles.css` (the dashboard card
system — explicitly UI-locked and out of scope), `platform/frontend`,
dashboard rendering, generated reports, API logic, Cloudflare Workers.

---

## 1. Why this exists

The site's own pages already define `:root` custom properties inline —
and they've drifted. A few examples from the current codebase:

| Page | Accent variable | Value |
|---|---|---|
| `trust-center.html` | `--accent` | `#00d4aa` |
| `mssp.html` | `--accent` | `#00f5c4` |
| `ai-runtime-defense.html` | `--accent-cyan` | `#00d4ff` |
| `telemetry-embedding.html` | `--accent-cyan` | `#00d4ff` |

Same brand, four different accent values, none sharing a name. This
file gives future pages one canonical set to adopt instead of
inventing a fifth. It does not retroactively fix the four pages above —
that's a separate migration exercise, not part of this PR.

## 2. Naming convention

```
--sapx-<category>-<name>[-text]
```

- **Prefix `sapx-`** (Sentinel APEX) — deliberately distinct from the
  short generic names already in use per-page (`--bg`, `--accent`,
  `--text`, `--border`). Since all of these live on `:root`, a shared
  short name would silently collide with page-local tokens during the
  transition period where old and new systems coexist on the same
  site. The prefix makes it unambiguous which variables come from the
  shared system.
- **Categories:** `color`, `space`, `radius`, `font` (family/size/weight),
  `line-height`, `shadow`, `transition`, `ease`, `focus-ring`.
- **The `-text` suffix** marks a color variant whose contrast against
  `--sapx-color-bg-base` has been computed (WCAG 2.1 relative
  luminance formula) and verified safe for text, icons, or meaningful
  borders. The non-suffixed color in the same family is for
  decorative fills — badge backgrounds, large graphic blocks — where
  WCAG text-contrast rules don't apply. **Use the `-text` variant
  whenever the color itself carries readable content; use the plain
  variant for fills/backgrounds only.**

Example: `--sapx-color-brand-teal` (`#14e0ae`, a fill) vs.
`--sapx-color-brand-teal-text` (`#14e0ae` in dark mode — same value,
11.80:1 — but `#0d8f79` in light mode, 4.02:1, because the vivid hue
alone only reaches 1.71:1 against white).

## 3. Full token reference

### Typography
`--sapx-font-sans`, `--sapx-font-mono`, `--sapx-font-display` (currently
aliases `--sapx-font-sans`; a self-hosted display face can replace
this value later without renaming the token or touching consumers).
`--sapx-font-size-{xs,sm,base,lg,xl,2xl,3xl,4xl}`.
`--sapx-line-height-{tight,snug,normal}` (reused across sizes, not one
per size). `--sapx-font-weight-{regular,medium,semibold,bold,black}`.

### Spacing
`--sapx-space-{0,1,2,3,4,5,6,7,8,9}` — 4px base unit (`space-1` = 4px,
`space-4` = 16px, `space-9` = 96px).

### Radius
`--sapx-radius-{sm,md,lg,xl,full}` (4px, 8px, 12px, 20px, 9999px).

### Motion
`--sapx-transition-{fast,base,slow}` (120/200/320ms), `--sapx-ease-{standard,out,in}`.
Automatically collapse to near-zero under `prefers-reduced-motion: reduce` —
consumers get this for free by using the transition tokens, no extra
markup needed.

### Color — surfaces & text
`--sapx-color-bg-{base,surface,surface-raised}`,
`--sapx-color-border{,-strong}` (decorative dividers — see §4),
`--sapx-color-text-{primary,secondary,tertiary,inverse}`,
`--sapx-color-outline-neutral` (a real interactive boundary — inputs,
hover outlines — verified at ≥3:1, unlike the decorative border tokens).

### Color — brand
`--sapx-color-brand-{teal,indigo}` (fills) and their `-text` variants.

### Color — semantic (UI state)
`--sapx-color-{success,warning,danger,info}` (fills) and `-text` variants.

### Color — severity (content pages only)
`--sapx-color-severity-{critical,high,medium,low,info}` and `-text`
variants. **Critical/medium/low/info alias the semantic tokens above
via `var()`** rather than duplicating hex values — only `high` is a
genuinely new hue, since the 5-level severity scale doesn't map 1:1
onto the 4-level semantic scale. **This is a separate system from
`css/card_renderer_styles.css`'s dashboard severity styling** — don't
use these on dashboard cards, and don't assume the two systems'
colors match.

### Focus ring
`--sapx-focus-ring-{color,width,offset}` and the composite
`--sapx-focus-ring` (a two-layer box-shadow ring: an inner gap in the
background color, then an outer colored ring — the standard
accessible focus technique). Not applied to any selector by this PR —
consumers add `box-shadow: var(--sapx-focus-ring)` on `:focus-visible`
themselves, since this file defines tokens only, no applied rules.

### Elevation
`--sapx-shadow-{sm,md,lg}` — soft drop shadows in light mode; in dark
mode, a shadow plus a 1px translucent-white hairline, since shadows
alone barely read against a near-black background.

## 4. Accessibility notes

Every `-text` color's contrast ratio against `--sapx-color-bg-base` was
computed with the WCAG 2.1 relative-luminance formula (not estimated),
and is cited inline in `tokens.css` as a comment next to the value. All
clear at least 4.5:1 (AA, normal text) except:

- `--sapx-color-text-tertiary` in dark mode (4.43:1) and
  `--sapx-color-brand-teal-text` / `--sapx-color-severity-high-text`
  variants that land in the 4.0–4.8 range in one theme — these clear
  the AA large-text/UI-component threshold (3:1) but not the AA
  normal-text threshold (4.5:1) in every case. Comments in the CSS
  flag exactly which ones; don't use them for small body copy.

`--sapx-color-border` / `--sapx-color-border-strong` are intentionally
low-contrast decorative dividers. WCAG 1.4.11 (non-text contrast)
applies to essential UI components and graphical objects, not purely
decorative separators, so these aren't tuned to 3:1. If you need a
border that must be perceivable — an input outline, a required
boundary — use `--sapx-color-outline-neutral` (verified ≥3:1 in both
themes) or one of the `-text` colors instead.

## 5. Theme guide

No JavaScript required.

- **Default:** dark. This brand is dark-first, so dark values live in
  the un-scoped `:root` rather than behind their own media query.
- **Automatic:** `@media (prefers-color-scheme: light)` switches to
  light for users whose OS/browser requests it.
- **Manual override:** set `data-theme="light"` or `data-theme="dark"`
  on `<html>` (or any ancestor) to force a theme regardless of OS
  preference. An explicit `data-theme="dark"` is guarded against by
  the automatic light block (`:not([data-theme="dark"])`), so manual
  intent always wins over OS preference in both directions.
- Verified against real Chromium (Playwright) across all 4 combinations
  (OS dark/no override, OS light/no override, OS dark + forced light,
  OS light + forced dark) plus `prefers-reduced-motion` — see PR
  description for the exact resolved values from each run.

## 6. Migration guide (for a page adopting this file)

1. Add `<link rel="stylesheet" href="/css/tokens.css">` in `<head>`,
   before the page's own `<style>` block (so page-specific overrides,
   if any remain during a partial migration, still win via source
   order).
2. Replace the page's local `:root { --accent: ...; --bg: ...; }`
   declarations with references to `--sapx-color-*` tokens instead of
   redefining them locally — e.g. `--accent: var(--sapx-color-brand-teal)`
   as a transitional shim, or replace every raw `var(--accent)` call
   site with `var(--sapx-color-brand-teal)` directly and remove the
   local `:root` block entirely.
3. Do this one page at a time, in its own PR, so a regression in one
   page's migration doesn't block or get confused with another's.
4. `css/card_renderer_styles.css` and anything under `platform/frontend`
   are not in scope for this migration — they have their own
   independent, UI-locked styling system.

## 7. Example usage

```css
.btn-primary {
  background: var(--sapx-color-brand-teal);
  color: var(--sapx-color-text-inverse);
  padding: var(--sapx-space-3) var(--sapx-space-5);
  border-radius: var(--sapx-radius-md);
  font-family: var(--sapx-font-sans);
  font-weight: var(--sapx-font-weight-semibold);
  transition: opacity var(--sapx-transition-fast) var(--sapx-ease-standard);
}
.btn-primary:hover { opacity: 0.88; }
.btn-primary:focus-visible {
  outline: none;
  box-shadow: var(--sapx-focus-ring);
}

.severity-badge--high {
  background: color-mix(in srgb, var(--sapx-color-severity-high) 15%, transparent);
  color: var(--sapx-color-severity-high-text);
  border: 1px solid var(--sapx-color-severity-high);
}
```

## 8. Compatibility notes

- Pure CSS custom properties — no build step, no preprocessor, no
  JavaScript dependency for theming.
- Custom properties and `prefers-color-scheme`/`prefers-reduced-motion`
  media queries are supported in all evergreen browsers (Chrome/Edge
  79+, Firefox 67+, Safari 12.1+ for custom properties; Safari 14+ for
  `prefers-reduced-motion`). No fallback is provided for older
  browsers — consistent with the rest of this site's baseline.
- `color-mix()` (used only in the example above, not in `tokens.css`
  itself) needs Chrome/Edge 111+, Firefox 113+, Safari 16.2+ — a page
  using it should have its own fallback if it needs to support older
  browsers; that's the consuming page's decision, not this file's.

## 9. Regression checklist (for this PR)

- [x] `css/tokens.css` added; zero existing files modified.
- [x] No page currently references `css/tokens.css` — confirmed no
      existing render is affected.
- [x] `css/card_renderer_styles.css` untouched.
- [x] `platform/frontend`, dashboard rendering, generated reports, API
      logic, Cloudflare Workers, Python, metadata — untouched.
- [x] All 4 theme-cascade combinations verified in real Chromium via
      Playwright (not just reasoned about) — OS dark, OS light, OS
      dark + forced light, OS light + forced dark.
- [x] `prefers-reduced-motion` verified to collapse transition tokens
      only, leaving color/spacing/radius tokens unaffected.
- [x] Every `-text` color's contrast ratio computed via the WCAG 2.1
      formula, not estimated; sub-4.5:1 values explicitly flagged as
      large-text/UI-only in both the CSS comments and this guide.
- [x] No duplicate color values: severity critical/medium/low/info
      alias semantic tokens via `var()` instead of repeating hex
      values; the dark-mode "real interactive boundary" outline color
      reuses `text-tertiary`'s value rather than introducing a
      near-duplicate gray.
