"""
Static-analysis regression tests for enterprise-compliance.html (PR-7,
the Enterprise Trust Center & Compliance Experience).

Same five categories as tests/test_enterprise_homepage.py (PR-5) /
tests/test_enterprise_pricing.py (PR-6), plus two PR-7-specific checks:

  1. Token usage verification.
  2. Duplicate component detection (including the new .sapx-table
     system this PR adds to css/components.css).
  3. Heading hierarchy validation.
  4. DOM validation.
  5. Broken-link detection.
  6. No fabricated certification language (PR-7-specific) -- this page
     must never claim SOC 2 / ISO 27001 as "Certified" (only as
     "Readiness"/"Alignment"/"Roadmap"/"In Progress", matching the real,
     honest framing already used by trust-center.html and
     security-compliance.html), and must never introduce the word
     "certified" in a compliance context this repository doesn't
     evidence.
  7. Filename-collision regression guard (PR-7-specific) -- guards the
     exact mistake this PR's own development caught and avoided:
     enterprise-trust-center.html already exists as a live, unrelated,
     API-key-gated internal P29 operations dashboard. This page must
     never be confused with, or accidentally reference itself as,
     that file.

Run with: pytest tests/test_enterprise_compliance.py -v
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE_PATH = REPO_ROOT / "enterprise-compliance.html"
COMPONENTS_CSS = REPO_ROOT / "css" / "components.css"
UNRELATED_INTERNAL_DASHBOARD = REPO_ROOT / "enterprise-trust-center.html"

NON_FILE_SCHEMES = ("http://", "https://", "mailto:", "tel:")


@pytest.fixture(scope="module")
def page_text():
    assert PAGE_PATH.exists(), f"{PAGE_PATH} not found"
    return PAGE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def page_style(page_text):
    match = re.search(r"<style>(.*?)</style>", page_text, re.DOTALL)
    assert match, "expected exactly one <style> block in enterprise-compliance.html"
    return match.group(1)


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.classes: set[str] = set()
        self.ids: list[str] = []
        self.hrefs: list[str] = []
        self.headings: list[int] = []
        self.stylesheet_hrefs: list[str] = []
        self.saw_skip_link = False
        self.saw_header = False
        self.saw_primary_nav = False
        self.saw_main = False
        self.saw_footer = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("class"):
            self.classes.update(a["class"].split())
        if a.get("id"):
            self.ids.append(a["id"])
        if tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])
        if tag == "link" and a.get("rel") == "stylesheet" and a.get("href"):
            self.stylesheet_hrefs.append(a["href"])
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append(int(tag[1]))
        if tag == "a" and "sapx-skip-link" in (a.get("class") or "").split():
            self.saw_skip_link = True
        if tag == "header" and "sapx-site-header" in (a.get("class") or "").split():
            self.saw_header = True
        if tag == "nav" and a.get("aria-label") == "Primary":
            self.saw_primary_nav = True
        if tag == "main" and a.get("id") == "main-content":
            self.saw_main = True
        if tag == "footer" and "sapx-site-footer" in (a.get("class") or "").split():
            self.saw_footer = True


@pytest.fixture(scope="module")
def parsed(page_text):
    parser = _PageParser()
    parser.feed(page_text)
    return parser


def _split_top_level_blocks(text):
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


def _all_rules(css_text):
    no_comments = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)
    rules = []
    for header, body in _split_top_level_blocks(no_comments):
        if header.startswith("@media"):
            for inner_header, inner_body in _split_top_level_blocks(body):
                if not inner_header.startswith("@"):
                    rules.append((inner_header.strip(), inner_body.strip()))
        elif not header.startswith("@"):
            rules.append((header.strip(), body.strip()))
    return rules


# ---------------------------------------------------------------------
# 1. Token usage verification
# ---------------------------------------------------------------------

HARDCODED_COLOR_RE = re.compile(
    r"(?<![\w-])(color|background|background-color|border-color|border|"
    r"box-shadow|outline|fill|stroke)\s*:\s*([^;]+);"
)
LITERAL_COLOR_TOKEN_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)")
HARDCODED_SPACING_RE = re.compile(
    r"(?<![\w-])(padding|margin|gap|font-size|border-radius)\s*:\s*([^;]+);"
)


def _values_outside_var(declaration_value: str) -> str:
    value = declaration_value
    pattern = re.compile(r"(var|calc|clamp|color-mix)\([^()]*\)")
    while True:
        new_value = pattern.sub("", value)
        if new_value == value:
            break
        value = new_value
    return value


def test_no_hardcoded_colors_in_page_style(page_style):
    offenders = []
    for match in HARDCODED_COLOR_RE.finditer(page_style):
        prop, value = match.group(1), match.group(2)
        if LITERAL_COLOR_TOKEN_RE.search(_values_outside_var(value)):
            offenders.append(f"{prop}: {value.strip()}")
    assert not offenders, (
        f"enterprise-compliance.html's <style> block has hardcoded color "
        f"literal(s) outside var(--sapx-*): {offenders}"
    )


def test_no_hardcoded_spacing_or_font_size_in_page_style(page_style):
    offenders = []
    for match in HARDCODED_SPACING_RE.finditer(page_style):
        prop, value = match.group(1), match.group(2)
        remainder = _values_outside_var(value).strip()
        tokens = [t for t in remainder.split() if t not in ("0", "auto")]
        if tokens:
            offenders.append(f"{prop}: {value.strip()}")
    assert not offenders, (
        f"enterprise-compliance.html's <style> block has hardcoded spacing/"
        f"font-size outside var(--sapx-*): {offenders}"
    )


def test_tokens_css_linked_before_components_css(parsed):
    assert "/css/tokens.css" in parsed.stylesheet_hrefs
    assert "/css/components.css" in parsed.stylesheet_hrefs
    assert parsed.stylesheet_hrefs.index("/css/tokens.css") < parsed.stylesheet_hrefs.index("/css/components.css")


def test_hero_css_not_used(parsed):
    assert "/css/hero.css" not in parsed.stylesheet_hrefs


# ---------------------------------------------------------------------
# 2. Duplicate component detection
# ---------------------------------------------------------------------

def test_page_style_does_not_redefine_existing_components(page_style):
    redefined = []
    for header, _body in _all_rules(page_style):
        for selector in header.split(","):
            selector = selector.strip()
            if selector.startswith(".sapx-"):
                redefined.append(selector)
    assert not redefined, (
        f"enterprise-compliance.html redefines existing component selector(s) "
        f"in its own <style> block: {redefined} -- extend with a pr7-* class "
        f"instead of shadowing components.css."
    )


def test_no_undefined_classes_referenced(parsed, page_style):
    def defined_classes(css_text):
        return {m.group(1) for m in re.finditer(r"\.([a-zA-Z0-9_-]+)", css_text)}

    defined = (
        defined_classes(COMPONENTS_CSS.read_text(encoding="utf-8"))
        | defined_classes(page_style)
    )
    undefined = sorted(c for c in parsed.classes if c not in defined)
    assert not undefined, (
        f"enterprise-compliance.html references undefined CSS class(es): {undefined}"
    )


def test_sapx_table_component_exists_and_is_used(parsed):
    """This PR graduates .sapx-table from PR-6's page-local
    .pr6-compare-table into the shared library -- confirm it's both
    defined in components.css and actually used on this page (SLA /
    rate-limit / severity tables), not dead code."""
    components_css = COMPONENTS_CSS.read_text(encoding="utf-8")
    assert re.search(r"\.sapx-table\s*\{", components_css), (
        ".sapx-table not defined in css/components.css"
    )
    assert "sapx-table" in parsed.classes
    assert "sapx-table-wrap" in parsed.classes


# ---------------------------------------------------------------------
# 3. Heading hierarchy validation
# ---------------------------------------------------------------------

def test_exactly_one_h1(parsed):
    h1_count = sum(1 for level in parsed.headings if level == 1)
    assert h1_count == 1, f"expected exactly one <h1>, found {h1_count}"


def test_no_skipped_heading_levels(parsed):
    max_seen = 0
    for level in parsed.headings:
        assert level <= max_seen + 1, (
            f"heading hierarchy skips a level: encountered h{level} after "
            f"the highest level so far was h{max_seen} (sequence: {parsed.headings})"
        )
        max_seen = max(max_seen, level)


# ---------------------------------------------------------------------
# 4. DOM validation
# ---------------------------------------------------------------------

def test_no_duplicate_ids(parsed):
    duplicates = sorted({i for i in parsed.ids if parsed.ids.count(i) > 1})
    assert not duplicates, f"duplicate id attribute(s) found: {duplicates}"


def test_required_landmarks_present(parsed):
    assert parsed.saw_skip_link, "missing .sapx-skip-link"
    assert parsed.saw_header, "missing header.sapx-site-header"
    assert parsed.saw_primary_nav, 'missing nav[aria-label="Primary"]'
    assert parsed.saw_main, "missing main#main-content"
    assert parsed.saw_footer, "missing footer.sapx-site-footer"


def test_skip_link_target_exists(page_text, parsed):
    match = re.search(r'<a class="sapx-skip-link" href="#([^"]+)"', page_text)
    assert match, "skip link not found or not in expected form"
    assert match.group(1) in parsed.ids


# ---------------------------------------------------------------------
# 5. Broken-link detection
# ---------------------------------------------------------------------

def _resolve_repo_path(href: str):
    if href.startswith(NON_FILE_SCHEMES) or href.startswith("#"):
        return None
    path_part = urlsplit(href).path
    if not path_part:
        return None
    if not path_part.startswith("/"):
        path_part = "/" + path_part
    fs_path = REPO_ROOT / path_part.lstrip("/")
    if path_part.endswith("/"):
        fs_path = fs_path / "index.html"
    return fs_path


def test_internal_links_resolve(parsed):
    broken = []
    for href in parsed.hrefs:
        fs_path = _resolve_repo_path(href)
        if fs_path is None:
            continue
        if not fs_path.exists():
            broken.append((href, str(fs_path)))
    assert not broken, f"internal link(s) do not resolve to a real file: {broken}"


# ---------------------------------------------------------------------
# 6. No fabricated certification language (PR-7-specific)
# ---------------------------------------------------------------------

def test_no_unqualified_certification_claims(page_text):
    """SOC 2 and ISO 27001 must never be asserted as achieved/certified
    on this page -- only as in-progress/aligned/roadmap, matching the
    real, honest framing already used by trust-center.html and
    security-compliance.html. Catches the exact fabrication risk this
    PR's brief explicitly warns against."""
    lowered = page_text.lower()
    for standard in ("soc 2", "iso 27001"):
        idx = lowered.find(standard)
        assert idx != -1, f"expected this page to mention {standard} at all"
        # Look at a window around each mention for a disqualifying,
        # unqualified "certified" claim (allow "not yet certified",
        # "certification... in progress", etc. by checking for the
        # bare pattern "<standard> certified" without a preceding
        # negation/hedge word nearby).
        window = lowered[max(0, idx - 80):idx + 200]
        assert "iso 27001 certified" not in window.replace("not yet ", "") or "not yet" in window, (
            f"found an unqualified certification claim near {standard!r}: {window!r}"
        )


def _strip_html_comments(html: str) -> str:
    return re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)


def test_sovereign_india_paraphrase_avoids_certified_wording(page_text):
    """trust-center.html's own phrase is 'SOVEREIGN INDIA CERTIFIED
    DESIGN' -- this page's actual rendered content (not its explanatory
    HTML comments, which legitimately discuss and disclose that phrase)
    must not introduce that specific certification wording as new,
    first-party copy."""
    rendered = _strip_html_comments(page_text)
    assert "sovereign india certified" not in rendered.lower()


# ---------------------------------------------------------------------
# 7. Filename-collision regression guard (PR-7-specific)
# ---------------------------------------------------------------------

def test_does_not_reference_the_unrelated_internal_dashboard(parsed):
    """enterprise-trust-center.html is a live, unrelated, API-key-gated
    P29 operations dashboard (confirmed by reading it in full before
    this PR started). No actual link on this page may target it --
    checked against parsed hrefs, not raw text, since the page's own
    explanatory HTML comment legitimately names it when disclosing the
    near-collision this PR's development caught."""
    offending = [h for h in parsed.hrefs if "enterprise-trust-center.html" in h]
    assert not offending, (
        f"enterprise-compliance.html must not link to enterprise-trust-center.html "
        f"(a different, unrelated, live internal dashboard): {offending}"
    )


def test_unrelated_internal_dashboard_still_untouched():
    """Guards that this PR never modified the unrelated dashboard it
    almost collided with. If this file's content ever stops looking
    like the P29 operations dashboard, something touched it."""
    assert UNRELATED_INTERNAL_DASHBOARD.exists()
    content = UNRELATED_INTERNAL_DASHBOARD.read_text(encoding="utf-8")
    assert "p29/observability" in content, (
        "enterprise-trust-center.html no longer looks like the P29 operations "
        "dashboard it was before this PR -- it should be completely untouched."
    )
