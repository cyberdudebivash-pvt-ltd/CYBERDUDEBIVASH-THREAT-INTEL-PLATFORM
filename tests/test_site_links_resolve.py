"""
tests/test_site_links_resolve.py

Site-wide internal link check (2026-09-26). A live crawl of every internal
href/src in the published pages found 404s customers hit:
  - /favicon.ico, referenced by 53 pages: the file never existed;
  - /blog/ (5 pages' nav) and the 11 /blog/ posts sitemap-programmatic.xml
    advertises: blog/ existed but was not in build_dist_artifact.py's
    INCLUDE_DIRS;
  - /threat/, /reports/, /intel: no such published page;
  - 41 *.md docs linked from the Knowledge Center, developer portal, pricing
    and compliance pages: dist/ never ships *.md (they now link to the
    rendered file in the public GitHub repo);
  - two hardcoded /reports/2026/05/... dossiers on methodology.html, retired
    by the 24h report retention.

This test resolves every internal link statically against what
build_dist_artifact.py actually ships (root *.html, INCLUDE_DIRS,
include_singles), so a new broken link fails CI instead of reaching
customers.
"""
import ast
from html.parser import HTMLParser
from scripts import build_dist_artifact as builder
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

REPO = Path(__file__).resolve().parent.parent
SITE = "https://intel.cyberdudebivash.com"
BUILD = REPO / "scripts" / "build_dist_artifact.py"

# Served by the Cloudflare Worker / R2 or by Cloudflare itself, not by files.
DYNAMIC_PREFIXES = ("/api/", "/auth/", "/cdn-cgi/", "/taxii/", "/v1/")
REPORT_RE = re.compile(r"^/reports/\d{4}/\d{2}/[^/]+\.html$")
# href/src attributes only (not data-src, data-href, ...), static values only.
ATTR_RE = re.compile(r'(?<![\w-])(href|src)\s*=\s*"([^"]+)"')


def _dist_rules():
    tree = ast.parse(BUILD.read_text(encoding="utf-8"))
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ("INCLUDE_DIRS", "include_singles", "DOCS_HTML_WHITELIST"):
                found[node.targets[0].id] = set(ast.literal_eval(node.value))
    assert len(found) == 3, f"build_dist_artifact.py rules not found: {sorted(found)}"
    return found["INCLUDE_DIRS"], found["include_singles"], found["DOCS_HTML_WHITELIST"]


INCLUDE_DIRS, INCLUDE_SINGLES, DOCS_WHITELIST = _dist_rules()


def _published_pages():
    pages = [p for p in sorted(REPO.glob("*.html")) if not builder.is_excluded_html(p.name)]
    for d in INCLUDE_DIRS:
        if d != "reports":
            excluded = set(builder.INCLUDE_DIR_FILE_EXCLUDES.get(d, ()))
            pages += [p for p in sorted((REPO / d).rglob("*.html"))
                      if p.relative_to(REPO / d).as_posix() not in excluded]
    pages += [REPO / "docs" / p for p in sorted(DOCS_WHITELIST)]
    return pages


class RouteAttributes(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
        self.redirects = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for key in ("href", "src", "action", "poster"):
            if attrs.get(key):
                self.urls.append(attrs[key])
        if tag == "meta" and attrs.get("http-equiv", "").lower() == "refresh":
            match = re.search(r";\s*url\s*=\s*(.+)", attrs.get("content", ""), re.I)
            if match:
                self.urls.append(match.group(1).strip("\"' "))
                self.redirects.append(self.urls[-1])


def _internal_links(page: Path):
    parser = RouteAttributes()
    parser.feed(page.read_text(encoding="utf-8", errors="replace"))
    base = f"{SITE}/{page.relative_to(REPO).as_posix()}"
    for raw in parser.urls:
        url = raw.strip()
        if url.startswith(("#", "mailto:", "tel:", "javascript:", "data:")) or any(c in url for c in "{}$'+` "):
            continue
        u = urlparse(urljoin(base, url))
        if u.netloc == urlparse(SITE).netloc:
            yield u.path


def _shipped_file(rel: str) -> bool:
    if not (REPO / rel).is_file():
        return False
    if "/" not in rel:
        return (rel.endswith(".html") and not builder.is_excluded_html(rel)) or rel in INCLUDE_SINGLES
    top, rest = rel.split("/", 1)
    if top == "docs":
        return rest in DOCS_WHITELIST
    return top in INCLUDE_DIRS and rest not in builder.INCLUDE_DIR_FILE_EXCLUDES.get(top, ())


def _is_shipped(path: str) -> bool:
    """Mirrors GitHub Pages: /dir/ -> dir/index.html; /name -> name.html."""
    rel = path.lstrip("/")
    if rel == "" or rel.endswith("/"):
        return _shipped_file(rel + "index.html")
    if _shipped_file(rel):
        return True
    return "." not in rel.rsplit("/", 1)[-1] and (_shipped_file(rel + ".html") or _shipped_file(rel + "/index.html"))


def test_every_internal_link_resolves_to_a_shipped_file():
    broken = {}
    for page in _published_pages():
        for path in _internal_links(page):
            if path.startswith(DYNAMIC_PREFIXES) or REPORT_RE.match(path):
                continue
            if not _is_shipped(path):
                broken.setdefault(path, set()).add(page.relative_to(REPO).as_posix())
    assert not broken, "internal links that 404 on the live site:\n" + "\n".join(
        f"  {p}  <- {', '.join(sorted(v)[:4])}" for p, v in sorted(broken.items())
    )


def test_static_pages_do_not_hardcode_individual_reports():
    """Reports are retired after the rolling window (24h), so a hardcoded
    /reports/YYYY/MM/<id>.html link on a static page eventually 404s."""
    offenders = [
        f"{page.relative_to(REPO)}: {path}"
        for page in _published_pages()
        for path in _internal_links(page)
        if REPORT_RE.match(path)
    ]
    assert offenders == []


def test_favicon_exists_and_ships():
    assert (REPO / "favicon.ico").is_file()
    assert "favicon.ico" in INCLUDE_SINGLES
    assert (REPO / "favicon.ico").read_bytes()[:4] == b"\x00\x00\x01\x00", "favicon.ico must be an ICO file"


def test_sitemap_urls_resolve_to_shipped_files():
    broken = []
    for sm in sorted(REPO.glob("sitemap*.xml")):
        for loc in re.findall(r"<loc>([^<]+)</loc>", sm.read_text(encoding="utf-8")):
            u = urlparse(loc.strip())
            if u.netloc != urlparse(SITE).netloc:
                continue
            if u.path.endswith(".xml"):
                continue
            if u.path.startswith("/reports/"):
                broken.append(f"{sm.name}: {loc.strip()} (reports retire after 24h; not for a static sitemap)")
            elif not _is_shipped(u.path):
                broken.append(f"{sm.name}: {loc.strip()}")
    assert broken == [], "sitemap URLs that 404:\n" + "\n".join(broken[:40])


def test_parser_covers_redirects_forms_and_single_quoted_links():
    parser = RouteAttributes()
    parser.feed("<a href='/missing.html'>x</a><form action='/submit'></form>"
                "<meta http-equiv='refresh' content='0; URL=/target.html'>"
                "<!-- <a href='/ignored'> -->")
    assert parser.urls == ['/missing.html', '/submit', '/target.html']


def test_quarantined_files_do_not_count_as_resolved_routes():
    assert not _is_shipped('/conversion-analytics.html')
    assert not _is_shipped('/dashboard/revenue_acceleration.html')


def test_published_meta_redirects_have_no_cycles():
    redirects = {}
    for page in _published_pages():
        parser = RouteAttributes()
        parser.feed(page.read_text(encoding='utf-8', errors='replace'))
        for target in parser.redirects:
            base = f"{SITE}/{page.relative_to(REPO).as_posix()}"
            url = urlparse(urljoin(base, target))
            if url.netloc == urlparse(SITE).netloc:
                redirects['/' + page.relative_to(REPO).as_posix()] = url.path
    for origin in redirects:
        seen = set()
        current = origin
        while current in redirects:
            assert current not in seen, f"redirect cycle starting at {origin}: {sorted(seen)}"
            seen.add(current)
            current = redirects[current]
