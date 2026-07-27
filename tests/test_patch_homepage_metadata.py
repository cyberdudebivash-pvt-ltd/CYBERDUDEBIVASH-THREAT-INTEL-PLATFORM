"""
test_patch_homepage_metadata.py — RB-35 (PR-1) unit + regression tests

Fixtures use tmp_path so tests never touch a real file. The base fixture's
metadata block is the exact real content fetched from the live index.html
head (title/description/og:*/twitter:* fields) at the time this PR was
written, wrapped in a minimal synthetic body -- not a copy of the real
1.3MB file, but not invented copy either.
"""
import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import patch_homepage_metadata as p  # noqa: E402


REAL_HEAD = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CYBERDUDEBIVASH&reg; SENTINEL APEX v184.0 | AI-Powered Global Threat Intelligence &mdash; 74 Live Feeds &middot; 2,600+ Reports</title>
    <meta name="description" content="CyberDudeBivash SENTINEL APEX v184.0 &mdash; AI-Powered Threat Intelligence Platform. 74 live intel feeds, STIX 2.1 exports. API from $49/mo.">
    <link rel="canonical" href="https://intel.cyberdudebivash.com/">
    <meta property="og:type" content="website">
    <meta property="og:title" content="CYBERDUDEBIVASH&#174; SENTINEL APEX v184.0 | &#9889; 77+ Live Advisories &middot; 74 Active Intel Feeds &mdash; AI-Powered Global Threat Intelligence">
    <meta property="og:description" content="LIVE NOW: 77+ advisories, 74 intel feeds, CISA KEV verified, 2,600+ intelligence reports.">
    <meta property="og:url" content="https://intel.cyberdudebivash.com/">
    <meta property="og:image" content="https://intel.cyberdudebivash.com/assets/sentinel-apex-thumbnail.jpg">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    <meta property="og:image:type" content="image/jpeg">
    <meta property="og:image:alt" content="CYBERDUDEBIVASH SENTINEL APEX dashboard">
    <meta property="og:site_name" content="CYBERDUDEBIVASH&#174; SENTINEL APEX">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="CYBERDUDEBIVASH&#174; SENTINEL APEX v184.0 | LIVE - 77+ Advisories &middot; 74 Intel Feeds">
    <meta name="twitter:description" content="LIVE: 77+ advisories, 74 feeds active, CISA KEV, STIX 2.1.">
    <meta name="twitter:image" content="https://intel.cyberdudebivash.com/assets/sentinel-apex-thumbnail.jpg">
    <style>body{background:#050a14}</style>
</head>
<body>
<div id="app">
    <script>
    window.EMBEDDED_INTEL = [];
    console.log("dashboard render stub");
    </script>
</div>
</body>
</html>
"""


def _write_fixture(tmp_path, content=REAL_HEAD):
    index = tmp_path / "index.html"
    index.write_text(content, encoding="utf-8")
    return index


def _patch(monkeypatch, tmp_path, content=REAL_HEAD):
    index = _write_fixture(tmp_path, content)
    monkeypatch.setattr(p, "INDEX_HTML", index)
    return index


# ─── RB-35 / PR-1: core behavior ────────────────────────────────────────────

def test_dry_run_reports_all_nine_fields_without_writing(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    before = index.read_text()
    new_content, applied, warnings = p.apply_patches(before)
    assert set(applied) == {
        "title", "meta description", "og:title", "og:description",
        "og:image", "og:image:alt", "twitter:title", "twitter:description",
        "twitter:image",
    }
    assert index.read_text() == before  # apply_patches never writes


def test_applied_content_has_no_version_number_or_emoji(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    new_content, _, _ = p.apply_patches(index.read_text())
    assert not re.search(r"v\d+\.\d+", new_content)
    assert "⚡" not in new_content  # no lightning-bolt emoji
    assert p.ALREADY_PATCHED_MARKER in new_content


def test_og_image_repointed_to_new_banner_not_old_thumbnail(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    new_content, _, _ = p.apply_patches(index.read_text())
    assert "sentinel-apex-og-banner.jpg" in new_content
    assert "sentinel-apex-thumbnail.jpg" not in new_content


def test_exactly_one_of_each_field_after_patch(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    new_content, _, _ = p.apply_patches(index.read_text())
    for label, pattern in [
        ("<title>", re.compile(r"<title>")),
        ("og:title", re.compile(r'property="og:title"')),
        ("og:description", re.compile(r'property="og:description"')),
        ("twitter:title", re.compile(r'name="twitter:title"')),
        ("twitter:description", re.compile(r'name="twitter:description"')),
    ]:
        assert len(pattern.findall(new_content)) == 1, f"{label} should appear exactly once"


def test_integrity_checks_pass_on_real_patch(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    before = index.read_text()
    after, _, _ = p.apply_patches(before)
    p.run_integrity_checks(before, after)  # raises on failure; no exception = pass


def test_embedded_intel_untouched(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    new_content, _, _ = p.apply_patches(index.read_text())
    assert "window.EMBEDDED_INTEL = [];" in new_content


def test_script_and_body_tag_counts_unchanged(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    before = index.read_text()
    after, _, _ = p.apply_patches(before)
    assert before.count("<script") == after.count("<script")
    assert before.count("<body") == after.count("<body")


# ─── CLI-level: dry-run vs apply, idempotency, backup ───────────────────────

def test_dry_run_writes_nothing(monkeypatch, tmp_path, capsys):
    index = _patch(monkeypatch, tmp_path)
    original = index.read_text()
    monkeypatch.setattr(sys, "argv", ["patch_homepage_metadata.py", "--dry-run"])
    exit_code = p.main()
    assert exit_code == 0
    assert index.read_text() == original
    assert not list(tmp_path.glob("index.html.backup.*"))


def test_apply_creates_timestamped_backup_and_writes_new_content(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", ["patch_homepage_metadata.py", "--apply"])
    exit_code = p.main()
    assert exit_code == 0
    backups = list(tmp_path.glob("index.html.backup.*"))
    assert len(backups) == 1
    assert "v184.0" in backups[0].read_text()  # backup preserves pre-patch state
    assert "v184.0" not in index.read_text()   # live file is patched


def test_second_apply_is_idempotent_no_op(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", ["patch_homepage_metadata.py", "--apply"])
    assert p.main() == 0
    patched_once = index.read_text()
    backups_after_first = list(tmp_path.glob("index.html.backup.*"))

    assert p.main() == 0  # second run
    assert index.read_text() == patched_once  # unchanged
    assert list(tmp_path.glob("index.html.backup.*")) == backups_after_first  # no new backup


def test_rollback_from_backup_restores_exact_original(monkeypatch, tmp_path):
    index = _patch(monkeypatch, tmp_path)
    original = index.read_text()
    monkeypatch.setattr(sys, "argv", ["patch_homepage_metadata.py", "--apply"])
    p.main()
    backup = list(tmp_path.glob("index.html.backup.*"))[0]
    index.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
    assert index.read_text() == original


# ─── Failure scenarios: must abort safely, never write partial state ───────

def test_duplicate_field_aborts_without_writing(monkeypatch, tmp_path):
    broken = REAL_HEAD.replace(
        '<meta property="og:type" content="website">',
        '<meta property="og:type" content="website">\n'
        '    <meta property="og:title" content="DUPLICATE">',
    )
    index = _patch(monkeypatch, tmp_path, broken)
    original = index.read_text()
    monkeypatch.setattr(sys, "argv", ["patch_homepage_metadata.py", "--apply"])
    assert p.main() == 1
    assert index.read_text() == original
    assert not list(tmp_path.glob("index.html.backup.*"))


def test_missing_required_field_aborts_without_writing(monkeypatch, tmp_path):
    broken = re.sub(r"<title>.*?</title>", "", REAL_HEAD, count=1)
    index = _patch(monkeypatch, tmp_path, broken)
    original = index.read_text()
    monkeypatch.setattr(sys, "argv", ["patch_homepage_metadata.py", "--apply"])
    assert p.main() == 1
    assert index.read_text() == original


def test_missing_index_html_aborts_cleanly(monkeypatch, tmp_path):
    monkeypatch.setattr(p, "INDEX_HTML", tmp_path / "does_not_exist.html")
    monkeypatch.setattr(sys, "argv", ["patch_homepage_metadata.py", "--dry-run"])
    assert p.main() == 1


def test_integrity_check_catches_lost_embedded_intel():
    before = "<html><body><script>window.EMBEDDED_INTEL = [];</script></body></html>"
    after = "<html><body><script>console.log('oops');</script></body></html>"
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


# ─── Regression: the exact bug this PR fixes must not reappear ─────────────

def test_regression_no_version_number_survives_in_any_crawler_facing_field(monkeypatch, tmp_path):
    """The original defect: a version number and live counts baked into
    every crawler-facing field. This must never regress."""
    index = _patch(monkeypatch, tmp_path)
    new_content, _, _ = p.apply_patches(index.read_text())
    for field_re in (p.TITLE_RE, p.OG_TITLE_RE, p.TWITTER_TITLE_RE):
        match = field_re.search(new_content)
        assert match is not None
        assert not re.search(r"v\d+\.\d+", match.group(0))
        assert "77+" not in match.group(0)
        assert "74 " not in match.group(0)
