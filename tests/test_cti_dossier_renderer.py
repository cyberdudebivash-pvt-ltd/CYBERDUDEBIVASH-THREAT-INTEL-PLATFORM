from scripts.cti_dossier_renderer import MARKER, ROOT_CLASS, decorate_html


SAMPLE = """<!doctype html><html><head><title>Spring Ring Campaign Uses Teams Vishing</title></head><body>
<h1>Spring Ring Campaign Uses Teams Vishing</h1>
<p>Report ID CDB-CTI-2026-C51BE2974378</p>
<p>Severity: HIGH | Confidence: Medium | TLP:CLEAR</p>
<h3>Executive Summary</h3>
<p>A coordinated social-engineering operation abused Microsoft Teams external accounts.</p>
<h3>Verified Facts</h3>
<ul><li>Source publisher: GBHackers Security</li><li>Source published: 2026-09-03T07:16:23+00:00</li></ul>
<h3>Executive Decision Matrix</h3>
<table><tr><th>Decision</th><th>Recommendation</th></tr><tr><td>Teams External Access</td><td>Restrict to specific domains</td></tr></table>
<h3>Provenance and Certification</h3>
<p>Generated UTC 2026-09-05T08:43:47Z</p><p>Certification FLASH_READY</p>
</body></html>"""


def test_decorates_full_document_without_content_loss():
    rendered = decorate_html(SAMPLE)
    assert MARKER in rendered
    assert ROOT_CLASS in rendered
    assert "ADVANCED CTI DOSSIER" in rendered
    assert "CDB-CTI-2026-C51BE2974378" in rendered
    assert "GBHackers Security" in rendered
    assert "Spring Ring Campaign Uses Teams Vishing" in rendered
    assert "Restrict to specific domains" in rendered


def test_metadata_is_evidence_derived_not_fabricated():
    rendered = decorate_html(SAMPLE)
    assert ">HIGH<" in rendered
    assert ">MEDIUM<" in rendered
    assert ">TLP:CLEAR<" in rendered

    no_severity = "<h1>Intel</h1><h3>Executive Summary</h3><p>No severity field exists here.</p>"
    rendered_unknown = decorate_html(no_severity)
    assert ">UNSPECIFIED<" in rendered_unknown
    assert ">CRITICAL<" not in rendered_unknown


def test_idempotent():
    once = decorate_html(SAMPLE)
    twice = decorate_html(once)
    assert once == twice
    assert twice.count(MARKER) == 1


def test_blogger_fragment_supported():
    fragment = "<h3>Executive Summary</h3><p>Source-linked intelligence.</p>"
    rendered = decorate_html(fragment)
    assert rendered.startswith(MARKER)
    assert '<div class="cdb-cti-report">' in rendered
    assert 'id="executive-summary"' in rendered


def test_mobile_print_and_scoped_css_are_present():
    rendered = decorate_html(SAMPLE)
    assert "@media (max-width:640px)" in rendered
    assert "@media print" in rendered
    assert ".cdb-cti-report table" in rendered
    assert ".cdb-kpi-grid" in rendered
    assert "<script" not in rendered.lower()


def test_navigation_anchors_report_sections():
    rendered = decorate_html(SAMPLE)
    assert 'href="#executive-summary"' in rendered
    assert 'href="#verified-facts"' in rendered
    assert 'href="#executive-decision-matrix"' in rendered
    assert 'href="#provenance-and-certification"' in rendered
