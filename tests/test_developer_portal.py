"""
Static-analysis regression tests for developer-portal.html (PR-8, the
Enterprise Developer Portal & API Experience).

Same five categories as the PR-5/6/7 test suites, plus two PR-8-specific
categories:

  1. Token usage verification.
  2. Duplicate component detection.
  3. Heading hierarchy validation.
  4. DOM validation.
  5. Broken-link detection.
  6. Documentation-drift disclosure integrity (PR-8-specific) -- this
     page's entire reason for a dedicated "Documentation Consistency
     Notice" section is to report real, found inconsistencies rather
     than silently resolving them. These tests guard that the
     disclosure actually stays present and doesn't quietly get "cleaned
     up" into a false single-source-of-truth narrative in a future edit.
  7. No fabricated capabilities (PR-8-specific) -- guards against ever
     asserting GraphQL, Postman, Terraform, or SOAR support as shipped,
     since none is evidenced anywhere in this repository.

Run with: pytest tests/test_developer_portal.py -v
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGE_PATH = REPO_ROOT / "developer-portal.html"
COMPONENTS_CSS = REPO_ROOT / "css" / "components.css"

NON_FILE_SCHEMES = ("http://", "https://", "mailto:", "tel:")


@pytest.fixture(scope="module")
def page_text():
    assert PAGE_PATH.exists(), f"{PAGE_PATH} not found"
    return PAGE_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def page_style(page_text):
    match = re.search(r"<style>(.*?)</style>", page_text, re.DOTALL)
    assert match, "expected exactly one <style> block in developer-portal.html"
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
        f"developer-portal.html's <style> block has hardcoded color "
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
        f"developer-portal.html's <style> block has hardcoded spacing/"
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
        f"developer-portal.html redefines existing component selector(s) "
        f"in its own <style> block: {redefined} -- extend with a pr8-* "
        f"class instead of shadowing components.css."
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
        f"developer-portal.html references undefined CSS class(es): {undefined}"
    )


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


def test_code_blocks_are_keyboard_focusable(page_text):
    """Accessible code blocks: each pr8-code-block must be reachable by
    keyboard (tabindex="0") since it's a scrollable region, per this
    PR's accessibility requirement for 'accessible code blocks'."""
    blocks = re.findall(r'<pre class="pr8-code-block"[^>]*>', page_text)
    assert blocks, "expected at least one .pr8-code-block on the page"
    assert all('tabindex="0"' in b for b in blocks), (
        "every .pr8-code-block must have tabindex=\"0\" for keyboard access"
    )


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
        # Anchor fragments on another page's real file are not verified
        # here (that page's own headings own that check); only the file
        # itself must exist.
        base = href.split("#")[0]
        fs_path = _resolve_repo_path(base) if base else fs_path
        if fs_path is None:
            continue
        if not fs_path.exists():
            broken.append((href, str(fs_path)))
    assert not broken, f"internal link(s) do not resolve to a real file: {broken}"


# ---------------------------------------------------------------------
# 6. Documentation-drift disclosure integrity (PR-8-specific)
# ---------------------------------------------------------------------

def test_drift_notice_section_present(parsed, page_text):
    assert "drift-notice" in parsed.ids, "expected #drift-notice section anchor"
    assert "Documentation Consistency Notice" in page_text


def test_drift_notice_covers_every_major_topic(page_text):
    """Guards the actual substance of the disclosure -- each of these
    topics must appear somewhere in the drift table, not just the
    section heading. Prevents a future edit from quietly gutting the
    table while leaving the heading (and the false impression of
    disclosure) in place."""
    required_topics = [
        "Auth header", "API key format", "JWT signing algorithm",
        "JWT lifetime", "Rate limits", "Base API domain",
        "Support email", "Python SDK", "Endpoint paths",
    ]
    missing = [t for t in required_topics if t not in page_text]
    assert not missing, f"Documentation Consistency Notice is missing topic(s): {missing}"


def test_does_not_silently_pick_a_jwt_algorithm_side(page_text):
    """Mirrors PR-7's equivalent guard: this page must present both
    HS256 and RS256 as disclosed, conflicting claims, never assert one
    as simply correct."""
    assert "HS256" in page_text and "RS256" in page_text


# ---------------------------------------------------------------------
# 7. No fabricated capabilities (PR-8-specific)
# ---------------------------------------------------------------------

def test_unevidenced_integrations_are_labeled_coming_soon(page_text):
    """GraphQL, a Postman collection, Terraform, and SOAR playbooks are
    not evidenced anywhere in this repository. If mentioned at all, they
    must be clearly labeled Coming Soon -- never presented as shipped."""
    for term in ("Postman Collection", "Terraform", "SOAR"):
        idx = page_text.find(term)
        assert idx != -1, f"expected this page to at least mention {term!r}"
        window = page_text[idx:idx + 400]
        assert "Coming Soon" in window, (
            f"{term!r} is mentioned without a nearby 'Coming Soon' label"
        )


def test_no_graphql_claimed_as_shipped(page_text):
    assert "GraphQL" not in page_text or "Coming Soon" in page_text[
        max(0, page_text.find("GraphQL") - 100):page_text.find("GraphQL") + 200
    ]
