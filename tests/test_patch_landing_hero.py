"""
test_patch_landing_hero.py — PR-3 unit + regression tests

Fixtures use tmp_path so tests never touch a real file. REAL_PAGE's
<head> tail and <header> block are the exact real content fetched from
the live index.html (bytes 0-700000 via a range request) at the time
this PR was written -- not invented markup, just trimmed around it
with a minimal synthetic body/EMBEDDED_INTEL stub, the same approach
test_patch_homepage_metadata.py (PR-1) used.
"""
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import patch_landing_hero as p  # noqa: E402


REAL_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>CYBERDUDEBIVASH&reg; SENTINEL APEX &mdash; Global Threat Intelligence Platform</title>
<!-- SENTINEL APEX CARD RENDERER — enterprise glassmorphism card system v184.0 -->
<link rel="stylesheet" href="/css/card_renderer_styles.css">
</head>
<body>
<script>
window.EMBEDDED_INTEL = [];
console.log("dashboard render stub");
</script>

<header class="apex-header">
    <div class="brand-mark">
        <h1>CYBERDUDEBIVASH<span>&reg;</span></h1>
        <p class="brand-sub">SENTINEL APEX <span id="platform-version" class="ver">v185.0</span> // AI-Powered Global Threat Intelligence</p>
        <nav class="nav-hub" id="cdb-nav-hub">
            <a href="#pricing" class="nav-chip chip-pricing chip-pulse" title="Pricing Plans">PRICING</a>
            <a href="/demo.html" class="nav-chip chip-pulse" title="Book a Live Demo">DEMO</a>
            <a href="/contact-enterprise.html" class="nav-chip" title="Enterprise Sales">ENTERPRISE</a>
            <a href="/mssp.html" class="nav-chip" title="MSSP Partner Program">MSSP</a>
        </nav>
        <button id="mobile-menu-btn" onclick="cdbMobileNavOpen()" aria-label="Open navigation menu" aria-expanded="false" aria-controls="mobile-nav-drawer" title="Navigation Menu">&#9776;</button>
    </div>
    <div id="cdb-trust-bar">
        <span>STIX 2.1 COMPLIANT</span>
        <span>UPDATES EVERY &lt;2 HOURS</span>
        <span>CISA KEV VERIFIED</span>
    </div>
    <div id="cdb-threat-map-panel">
        <canvas id="cdb-threat-canvas"></canvas>
    </div>
    <div class="header-right">
        <a href="/contact-enterprise.html" class="contact-btn">CONNECT ENTERPRISE</a>
    </div>
</header>

<!-- STATUS STRIP v73.0 -->
<div class="status-strip">
    <div>NODE: <span>CDB-GOC-01</span></div>
    <div id="sync-val">SYNC: <span>LIVE</span></div>
</div>

<!-- METRICS STRIP -->
<div class="metrics-strip" id="metrics-strip">
    <div class="metric-card"><div class="metric-val" id="m-total" data-stat="total" data-sapx-id="total-advisories">&mdash;</div><div class="metric-label">Total Advisories</div></div>
</div>

<div id="sapx-card-grid"></div>

</body>
</html>
"""


def _write_fixture(tmp_path, content=REAL_PAGE):
    index = tmp_path / "index.html"
    index.write_text(content, encoding="utf-8")
    return index


def _patch(monkeypatch, tmp_path, content=REAL_PAGE):
    index = _write_fixture(tmp_path, content)
    monkeypatch.setattr(p, "INDEX_HTML", index)
    return index


# ─── Core behavior ──────────────────────────────────────────────────────────────

def test_apply_patch_inserts_both_link_tags_exactly_once(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    new_content = p.apply_patch(index.read_text())
    assert new_content.count('<link rel="stylesheet" href="/css/tokens.css">') == 1
    assert new_content.count('<link rel="stylesheet" href="/css/hero.css">') == 1


def test_apply_patch_inserts_hero_section_exactly_once(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    new_content = p.apply_patch(index.read_text())
    assert new_content.count('id="sapx-hero"') == 1
    assert new_content.count(p.ALREADY_PATCHED_MARKER) == 1


def test_hero_inserted_after_header_before_status_strip(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    new_content = p.apply_patch(index.read_text())
    header_close = new_content.index("</header>")
    hero_pos = new_content.index('id="sapx-hero"')
    status_strip_pos = new_content.index("STATUS STRIP")
    assert header_close < hero_pos < status_strip_pos


def test_apply_patch_never_touches_existing_header_content(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    before = index.read_text()
    after = p.apply_patch(before)
    # every existing nav link, trust bar item, and canvas survives untouched
    for marker in (
        'id="cdb-nav-hub"', "PRICING", "DEMO", "ENTERPRISE", "MSSP",
        "STIX 2.1 COMPLIANT", 'id="cdb-threat-canvas"', "CONNECT ENTERPRISE",
    ):
        assert marker in before and marker in after


def test_apply_patch_never_touches_dashboard_content_below(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    before = index.read_text()
    after = p.apply_patch(before)
    for marker in (
        "CDB-GOC-01", 'data-sapx-id="total-advisories"', 'id="sapx-card-grid"',
    ):
        assert marker in before and marker in after


def test_integrity_checks_pass_on_real_patch(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    before = index.read_text()
    after = p.apply_patch(before)
    p.run_integrity_checks(before, after)  # raises on failure; no exception = pass


def test_script_html_body_tag_counts_unchanged(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    before = index.read_text()
    after = p.apply_patch(before)
    assert before.count("<script") == after.count("<script")
    assert before.count("<html") == after.count("<html")
    assert before.count("<body") == after.count("<body")


def test_embedded_intel_untouched(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    after = p.apply_patch(index.read_text())
    assert "window.EMBEDDED_INTEL = [];" in after


def test_no_javascript_added(monkeypatch, tmp_path):
    """PR-3 explicitly requires no unnecessary JavaScript in the hero."""
    index = _patch(monkeypatch, tmp_path)
    after = p.apply_patch(index.read_text())
    assert "<script" not in p.HERO_FRAGMENT


# ─── CLI-level: dry-run vs apply, idempotency, backup ───────────────────────

def test_dry_run_writes_nothing(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    original = index.read_text()
    monkeypatch.setattr(sys, "argv", ["patch_landing_hero.py", "--dry-run"])
    exit_code = p.main()
    assert exit_code == 0
    assert index.read_text() == original
    assert not list(tmp_path.glob("index.html.backup.*"))


def test_apply_creates_timestamped_backup_and_writes_new_content(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", ["patch_landing_hero.py", "--apply"])
    exit_code = p.main()
    assert exit_code == 0
    backups = list(tmp_path.glob("index.html.backup.*"))
    assert len(backups) == 1
    assert p.ALREADY_PATCHED_MARKER not in backups[0].read_text()  # backup is pre-patch
    assert p.ALREADY_PATCHED_MARKER in index.read_text()           # live file is patched


def test_second_apply_is_idempotent_no_op(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", ["patch_landing_hero.py", "--apply"])
    assert p.main() == 0
    patched_once = index.read_text()
    backups_after_first = list(tmp_path.glob("index.html.backup.*"))

    assert p.main() == 0  # second run
    assert index.read_text() == patched_once
    assert list(tmp_path.glob("index.html.backup.*")) == backups_after_first  # no new backup


def test_rollback_from_backup_restores_exact_original(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    original = index.read_text()
    monkeypatch.setattr(sys, "argv", ["patch_landing_hero.py", "--apply"])
    p.main()
    backup = list(tmp_path.glob("index.html.backup.*"))[0]
    index.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
    assert index.read_text() == original


# ─── Failure scenarios: must abort safely, never write partial state ───────

def test_duplicate_header_close_aborts_without_writing(monkeypatch, tmp_path):
    broken = REAL_PAGE.replace("</body>\n</html>", "</header>\n</body>\n</html>")
    index = _patch(monkeypatch, tmp_path, broken)
    original = index.read_text()
    monkeypatch.setattr(sys, "argv", ["patch_landing_hero.py", "--apply"])
    assert p.main() == 1
    assert index.read_text() == original
    assert not list(tmp_path.glob("index.html.backup.*"))


def test_missing_head_close_aborts_without_writing(monkeypatch, tmp_path):
    broken = REAL_PAGE.replace("</head>\n<body>", "<body>")
    index = _patch(monkeypatch, tmp_path, broken)
    original = index.read_text()
    monkeypatch.setattr(sys, "argv", ["patch_landing_hero.py", "--apply"])
    assert p.main() == 1
    assert index.read_text() == original


def test_missing_index_html_aborts_cleanly(monkeypatch, tmp_path):
    monkeypatch.setattr(p, "INDEX_HTML", tmp_path / "does_not_exist.html")
    monkeypatch.setattr(sys, "argv", ["patch_landing_hero.py", "--dry-run"])
    assert p.main() == 1


def test_integrity_check_catches_lost_embedded_intel():
    before = "<html><body><script>window.EMBEDDED_INTEL = [];</script></body></html>"
    after = before.replace("window.EMBEDDED_INTEL = [];", "console.log('oops');")
    # manually inject the other required post-conditions so only the
    # EMBEDDED_INTEL check is exercised
    after = after.replace(
        "</body>",
        '<link rel="stylesheet" href="/css/tokens.css"><link rel="stylesheet" href="/css/hero.css">'
        '<div id="sapx-hero">SAPX-HERO-V1</div></body>',
    )
    try:
        p.run_integrity_checks(before, after)
        assert False, "should have raised PatchError"
    except p.PatchError as exc:
        assert "EMBEDDED_INTEL" in str(exc)


def test_integrity_check_catches_script_tag_count_change():
    before = "<html><body><script>a</script></body></html>"
    after = "<html><body><script>a</script><script>b</script></body></html>"
    try:
        p.run_integrity_checks(before, after)
        assert False, "should have raised PatchError"
    except p.PatchError as exc:
        assert "script" in str(exc)


def test_integrity_check_rejects_oversized_delta():
    # Satisfies every other check (head/header structure, links, hero
    # marker, tag counts) so the oversized-delta path is the one
    # actually being isolated/tested.
    before = "<html><head></head><body><header></header></body></html>"
    after = (
        '<html><head><link rel="stylesheet" href="/css/tokens.css">'
        '<link rel="stylesheet" href="/css/hero.css"></head>'
        f'<body><header></header><div id="sapx-hero">{p.ALREADY_PATCHED_MARKER}</div>'
        + ("x" * 20000)
        + "</body></html>"
    )
    try:
        p.run_integrity_checks(before, after)
        assert False, "should have raised PatchError"
    except p.PatchError as exc:
        assert "delta" in str(exc)


# ─── Regression: hero content covers the required communication points ────

def test_hero_covers_all_required_messaging_pillars():
    """PR-3's mission lists 8 things the hero must communicate. Confirm
    each is present somewhere in the fragment, so a future edit can't
    silently drop one."""
    required_substrings = [
        "AI-Powered Threat Intelligence",  # AI-powered threat intel
        "Enterprise SOC",                   # enterprise SOC
        "real-time",                        # real-time intelligence (case-insensitive check below)
        "API-First Architecture",           # API-first architecture
        "STIX 2.1",                         # STIX 2.1 support
        "MITRE ATT",                        # MITRE ATT&CK
        "Splunk",                           # enterprise integrations
        "Free Trial",                       # free trial
        "Live Demo",                        # demo booking
    ]
    fragment_lower = p.HERO_FRAGMENT.lower()
    for s in required_substrings:
        assert s.lower() in fragment_lower, f"missing required messaging pillar: {s!r}"


def test_hero_stats_are_stable_sla_figures_not_live_counts():
    """Regression guard tying back to PR-1's root cause: a live count
    baked in at generation time (e.g. '74 feeds') goes stale. The hero
    must not reintroduce that pattern -- only SLA/format figures.

    Checks realistic stale-count phrasings rather than a bare '74'
    substring, since '74' also appears incidentally inside unrelated
    numeric HTML entity codes (&#127470; is half of the India flag
    emoji, not the number 74)."""
    stale_count_phrasings = ["74 feeds", "74 live", "74 intel", "74+", "2,600", "2600+"]
    fragment_lower = p.HERO_FRAGMENT.lower()
    for phrase in stale_count_phrasings:
        assert phrase.lower() not in fragment_lower, f"reintroduced a stale live-count phrasing: {phrase!r}"
    assert "&lt;2h" in p.HERO_FRAGMENT  # HTML-entity-encoded "<2h", not literal "<2h"
    assert "99.9%" in p.HERO_FRAGMENT
