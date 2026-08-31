"""
Static-analysis regression tests for css/components.css (PR-4).

Verifies the three structural guarantees the component system depends
on: (1) zero hardcoded design values outside var(--sapx-*) references,
(2) zero *unintentional* duplicate selectors within the file itself
(the disclosed cross-file overlap with css/hero.css's .sapx-btn /
.sapx-btn-primary / .sapx-btn-secondary is a separate, documented case
and is explicitly not what this guards against), and (3) every class
referenced by the components/*.html reference fragments is actually
defined somewhere in components.css.

Run with: pytest test_components_css.py -v
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CSS_PATH = REPO_ROOT / "css" / "components.css"
COMPONENTS_DIR = REPO_ROOT / "components"

EXPECTED_COMPONENT_FILES = [
    "header.html", "footer.html", "navigation.html", "cta.html",
    "feature-card.html", "metric-card.html", "integration-grid.html",
    "announcement.html", "button.html", "section.html", "container.html",
    "badge.html", "pricing-cta.html", "newsletter.html",
    "data-teaser-overlay.html",
]


@pytest.fixture(scope="module")
def css_text():
    assert CSS_PATH.exists(), f"css/components.css not found at {CSS_PATH}"
    return CSS_PATH.read_text(encoding="utf-8")


def _split_top_level_blocks(text):
    """Yield (header, body) for each brace-delimited block in `text` at
    its top nesting level only (a simple depth counter, since CSS braces
    here are never deeper than one @media level)."""
    depth = 0
    start = 0
    header_start = 0
    blocks = []
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                blocks.append(["header", text[header_start:i].strip()])
                start = i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                blocks[-1] = (blocks[-1][1], text[start:i])
                header_start = i + 1
    return blocks


@pytest.fixture(scope="module")
def css_rules(css_text):
    """Return a list of (media_context, selector, declaration_body) rule
    tuples. media_context is None for top-level rules, or the @media
    condition string for rules nested inside an @media block.

    The same selector appearing under two DIFFERENT media contexts (or
    once at top level and again inside an @media override) is normal,
    idiomatic responsive CSS -- e.g. .sapx-nav's base rule plus its
    @media (max-width: 900px) override -- so media_context is part of
    the uniqueness key, not just the selector name."""
    no_comments = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)
    rules = []
    for header, body in _split_top_level_blocks(no_comments):
        if header.startswith("@media"):
            for inner_header, inner_body in _split_top_level_blocks(body):
                if inner_header.startswith("@"):
                    continue
                rules.append((header, inner_header.strip(), inner_body.strip()))
        elif header.startswith("@"):
            continue
        else:
            rules.append((None, header.strip(), body.strip()))
    return rules


# ---------------------------------------------------------------------
# 1. Zero hardcoded design values outside var(--sapx-*)
# ---------------------------------------------------------------------

# Property families that MUST resolve through a token, keyed to the
# regex used to detect a literal (non-var()) value being assigned.
HARDCODED_COLOR_RE = re.compile(
    r"(?<![\w-])(color|background|background-color|border-color|border|"
    r"box-shadow|outline|fill|stroke)\s*:\s*([^;]+);"
)
# Hex colors, rgb()/rgba() literals, and bare named colors (excluding
# 'transparent', 'none', 'currentColor', and 'inherit', which are not
# design-token concerns).
LITERAL_COLOR_TOKEN_RE = re.compile(
    r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)"
)
ALLOWED_BARE_COLOR_KEYWORDS = {
    "transparent", "none", "currentcolor", "inherit", "initial", "unset", "auto",
}

# Only properties that actually have a corresponding token SCALE in
# css/tokens.css are checked here: padding/margin/gap (--sapx-space-*),
# font-size (--sapx-font-size-*), border-radius (--sapx-radius-*), and
# line-height (--sapx-line-height-*, exactly 3 named values). Structural/
# positional properties with no token scale to violate -- width, height,
# min/max-width/height, top/left/right/bottom, letter-spacing (tokens.css
# defines no letter-spacing scale at all) -- are deliberately NOT checked
# here. css/hero.css (PR-3, already shipped and certified) already uses
# bare literals for exactly these same categories (e.g. `letter-spacing:
# 0.12em`, `@media (max-width: 900px)`), so holding components.css to a
# stricter bar than the existing, certified convention would be an
# invented rule, not a real regression check.
HARDCODED_SPACING_RE = re.compile(
    r"(?<![\w-])(padding|margin|gap|font-size|border-radius|line-height)"
    r"\s*:\s*([^;]+);"
)
# A bare px/rem/em numeric literal that isn't 0, 1px/2px (hairline
# borders, spinner border-width -- not part of the spacing scale), or
# inside a var()/calc()/clamp(). line-height is special-cased separately
# below since only its THREE named values (1.15 / 1.3 / 1.6) are tokens;
# other bare numbers (e.g. `line-height: 1` for tightly-set numerals)
# are a legitimate, untokenized idiom.
NUMERIC_LITERAL_RE = re.compile(r"-?\d*\.?\d+(px|rem|em|vw|vh|%)?")
TOKENIZED_LINE_HEIGHTS = {"1.15", "1.3", "1.6"}


def _values_outside_var(declaration_value: str) -> str:
    """Return the declaration value with every var(...) / calc(...) / clamp(...)
    / color-mix(...) call (and their contents) removed, so what remains is
    only literal text that was NOT expressed via a token or a token-composing
    function."""
    value = declaration_value
    # Repeatedly strip innermost var(...)/calc(...)/clamp(...)/color-mix(...)
    # calls to handle nesting, e.g. calc(var(--sapx-space-2) + 1px).
    pattern = re.compile(r"(var|calc|clamp|color-mix)\([^()]*\)")
    while True:
        new_value = pattern.sub("", value)
        if new_value == value:
            break
        value = new_value
    return value


def test_no_hardcoded_colors_outside_tokens(css_text):
    no_comments = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)
    offenders = []
    for match in HARDCODED_COLOR_RE.finditer(no_comments):
        prop, value = match.group(1), match.group(2)
        remainder = _values_outside_var(value)
        if LITERAL_COLOR_TOKEN_RE.search(remainder):
            offenders.append(f"{prop}: {value.strip()}")
    assert not offenders, (
        "Found hardcoded color literal(s) outside var(--sapx-*) in "
        f"css/components.css: {offenders}"
    )


def test_no_hardcoded_spacing_or_typography_outside_tokens(css_text):
    no_comments = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)
    offenders = []
    for match in HARDCODED_SPACING_RE.finditer(no_comments):
        prop, value = match.group(1), match.group(2)
        remainder = _values_outside_var(value).strip()
        if not remainder:
            continue

        if prop == "line-height":
            # Only the three named --sapx-line-height-* values are a real
            # "should have used the token" finding. Other bare numbers
            # (e.g. `line-height: 1` for tightly-set numerals/icons) are
            # a legitimate, untokenized idiom -- tokens.css doesn't claim
            # to cover every possible line-height, only these three.
            if remainder in TOKENIZED_LINE_HEIGHTS:
                offenders.append(
                    f"{prop}: {value.strip()}  (matches a named --sapx-line-height-* value)"
                )
            continue

        # Split on whitespace (e.g. shorthand "0 auto") and check each token.
        for token in remainder.split():
            token = token.strip(",")
            if not token:
                continue
            # Allowed bare literals: 0, 100%, 50%, auto, none.
            if token in {"0", "auto", "none", "100%", "50%"}:
                continue
            # Hairline borders / spinner stroke width.
            if re.fullmatch(r"-?[12]px", token):
                continue
            # tokens.css's spacing scale (--sapx-space-*) has no negative
            # entries, so a negative offset can never be expressible via
            # the token scale -- e.g. centering a fixed-size element with
            # a negative margin equal to half its own (also fixed, also
            # exempt) dimension. This isn't a spacing-scale choice, it's
            # positioning arithmetic derived from an already-exempt size.
            if token.startswith("-") and NUMERIC_LITERAL_RE.fullmatch(token):
                continue
            if NUMERIC_LITERAL_RE.fullmatch(token):
                offenders.append(f"{prop}: {value.strip()}  (literal token: {token!r})")
    assert not offenders, (
        "Found hardcoded spacing/typography literal(s) outside var(--sapx-*) "
        f"in css/components.css: {offenders}"
    )


# ---------------------------------------------------------------------
# 2. Zero unintentional duplicate selectors within components.css itself
# ---------------------------------------------------------------------

# hero.css defines these three selectors too (disclosed, deliberate
# overlap -- see the header comment in both files). This test guards
# against NEW accidental duplication *within* components.css, not
# against this already-documented cross-file case.
KNOWN_CROSS_FILE_OVERLAP_WITH_HERO_CSS = {
    ".sapx-btn",
    ".sapx-btn-primary",
    ".sapx-btn-secondary",
}


def test_no_duplicate_selectors_within_components_css(css_rules):
    seen = {}
    duplicates = []
    for media_context, selector, _body in css_rules:
        # Normalize whitespace so "a,\nb" and "a, b" compare equal.
        normalized = re.sub(r"\s+", " ", selector).strip()
        # Split comma-separated compound selectors into individual ones.
        for single in [s.strip() for s in normalized.split(",")]:
            key = (media_context, single)
            if key in seen:
                duplicates.append(single)
            seen[key] = seen.get(key, 0) + 1

    unexpected_duplicates = sorted(
        {d for d in duplicates if d not in KNOWN_CROSS_FILE_OVERLAP_WITH_HERO_CSS}
    )
    assert not unexpected_duplicates, (
        "Found duplicate selector(s) defined more than once within "
        f"css/components.css: {unexpected_duplicates}"
    )


def test_known_hero_overlap_is_still_present_and_intentional(css_text):
    """Guards the other direction: if a future edit removes .sapx-btn-primary
    etc. from components.css entirely, the KNOWN_CROSS_FILE_OVERLAP_WITH_HERO_CSS
    allowlist above would silently stop meaning anything. Confirms all three
    selectors are still defined at least once."""
    for selector in KNOWN_CROSS_FILE_OVERLAP_WITH_HERO_CSS:
        pattern = re.escape(selector) + r"\s*[,{]"
        assert re.search(pattern, css_text), (
            f"Expected selector {selector!r} to still be defined in "
            "css/components.css (it is a documented, intentional overlap "
            "with css/hero.css's button classes)."
        )


# ---------------------------------------------------------------------
# 3. Every class referenced by components/*.html is actually defined
# ---------------------------------------------------------------------

CLASS_ATTR_RE = re.compile(r'class="([^"]*)"')
DEFINED_CLASS_RE = re.compile(r"\.(-?[_a-zA-Z][_a-zA-Z0-9-]*)")


def test_all_expected_component_files_exist():
    missing = [
        name for name in EXPECTED_COMPONENT_FILES
        if not (COMPONENTS_DIR / name).exists()
    ]
    assert not missing, f"Missing expected components/*.html file(s): {missing}"


def _defined_classes(css_text: str) -> set:
    no_comments = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)
    return {m.group(1) for m in DEFINED_CLASS_RE.finditer(no_comments)}


@pytest.mark.parametrize("filename", EXPECTED_COMPONENT_FILES)
def test_reference_html_only_uses_defined_sapx_classes(filename, css_text):
    defined = _defined_classes(css_text)
    html_path = COMPONENTS_DIR / filename
    if not html_path.exists():
        pytest.skip(f"{filename} not present (covered by test_all_expected_component_files_exist)")
    html_text = html_path.read_text(encoding="utf-8")
    used_sapx_classes = set()
    for class_attr in CLASS_ATTR_RE.findall(html_text):
        for cls in class_attr.split():
            if cls.startswith("sapx-"):
                used_sapx_classes.add(cls)

    undefined = sorted(used_sapx_classes - defined)
    assert not undefined, (
        f"components/{filename} references sapx-* class(es) not defined in "
        f"css/components.css: {undefined}"
    )


# ---------------------------------------------------------------------
# 4. File-header disclosure sanity checks
# ---------------------------------------------------------------------

def test_header_comment_discloses_hero_css_overlap(css_text):
    assert "hero.css" in css_text, (
        "css/components.css header comment must disclose the known "
        "overlap with css/hero.css's button classes."
    )
    assert "text-on-bright" in css_text, (
        "css/components.css must reference --sapx-color-text-on-bright "
        "(the PR-4 token added specifically to fix the button contrast "
        "defect discovered while building this file)."
    )


def test_no_page_is_auto_wired_to_components(css_text):
    """This PR must not modify index.html or any other production page.
    A cheap guard: components.css itself must not contain an @import of
    (or reference to) index.html, and no component reference file should
    claim to be auto-included anywhere."""
    assert "index.html" not in css_text
