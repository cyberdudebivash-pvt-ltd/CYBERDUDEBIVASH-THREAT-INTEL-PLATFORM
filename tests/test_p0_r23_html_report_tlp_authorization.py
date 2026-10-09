"""P0 R23: standalone HTML report writer cannot launder TLP into CLEAR."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import report_generator as gen
import tlp_policy


@pytest.fixture()
def fake_html(monkeypatch):
    # Synthetic HTML tests only output authorization and disk effects.
    def render(entry, *_):
        return "<!DOCTYPE html><html><body>" + str(entry.get("tlp", "")) + ("x" * 700) + "</body></html>"
    monkeypatch.setattr(gen, "_build_html", render)


@pytest.mark.parametrize("case", [
    {"id": "intel--missing", "title": "Unlabelled"},
    {"id": "intel--amber", "title": "Restricted", "tlp": "TLP:AMBER"},
    {"id": "intel--green", "title": "Restricted", "tlp": "TLP:GREEN"},
    {"id": "intel--red", "title": "Restricted", "tlp": "TLP:RED"},
    {"id": "intel--invalid", "title": "Malformed", "tlp": "TLP:UNKNOWN"},
    {"id": "intel--legacy", "title": "Old label", "tlp": "TLP:WHITE"},
    {"id": "intel--mixed", "title": "Mixed sources", "tlp": "TLP:CLEAR",
     "sources": [{"source_url": "https://private.example.test/a", "tlp": "TLP:RED"}]},
    {"id": "intel--conflict", "title": "Mixed own labels", "tlp": "TLP:CLEAR", "tlp_label": "TLP:AMBER"},
])
def test_denied_input_creates_no_html_or_directory(tmp_path, fake_html, case):
    before = copy.deepcopy(case)
    base = tmp_path / "fresh"
    ok, reason = gen.generate_report(case, reports_base=str(base))
    assert ok is False
    assert "tlp_publication_denied" in reason
    assert not base.exists(), "Denied input cannot create output directories"
    assert case == before, "Original TLP/provenance must not be rewritten"


def test_existing_public_report_not_overwritten_by_restricted_input(tmp_path, fake_html):
    base = tmp_path / "reports"
    target = base / "2026" / "10" / "intel--keep.html"
    target.parent.mkdir(parents=True)
    target.write_text("SIGNED ORIGINAL", encoding="utf-8")
    case = {"id": "intel--keep", "title": "Now restricted", "tlp": "TLP:RED",
            "report_url": "/reports/2026/10/intel--keep.html"}
    ok, _ = gen.generate_report(case, reports_base=str(base))
    assert not ok
    assert target.read_text(encoding="utf-8") == "SIGNED ORIGINAL"


def test_explicit_clear_report_uses_approved_marking(tmp_path, fake_html):
    case = {"id": "intel--clear", "title": "Public advisory", "tlp": "TLP:CLEAR"}
    original = copy.deepcopy(case)
    ok, path = gen.generate_report(case, reports_base=str(tmp_path))
    assert ok is True
    assert Path(path).is_file()
    assert "TLP:CLEAR" in Path(path).read_text(encoding="utf-8")
    assert case == original


def test_approved_public_collector_is_display_assigned_without_mutating_source(
    tmp_path, fake_html, monkeypatch,
):
    policy = {
        "legacy_white_treated_as_clear": False,
        "first_party_public_sources": [
            {"source": "internal-collector", "hosts": ["public.example.test"]}
        ],
    }
    monkeypatch.setattr(tlp_policy, "load_policy", lambda *a, **kw: policy)
    case = {"id": "intel--approved", "title": "Reviewed public source",
            "source": "internal-collector", "source_url": "https://public.example.test/news"}
    original = copy.deepcopy(case)
    ok, path = gen.generate_report(case, reports_base=str(tmp_path))
    assert ok is True
    assert "TLP:CLEAR" in Path(path).read_text(encoding="utf-8")
    assert case == original
    assert "tlp" not in case


def test_approved_source_name_with_unapproved_host_still_denied(
    tmp_path, fake_html, monkeypatch,
):
    policy = {
        "legacy_white_treated_as_clear": False,
        "first_party_public_sources": [
            {"source": "internal-collector", "hosts": ["public.example.test"]}
        ],
    }
    monkeypatch.setattr(tlp_policy, "load_policy", lambda *a, **kw: policy)
    case = {"id": "intel--impostor", "title": "Impostor",
            "source": "internal-collector", "source_url": "https://attacker.invalid/x"}
    assert gen.generate_report(case, reports_base=str(tmp_path))[0] is False
    assert not (tmp_path / "2026").exists()


def test_no_fail_open_clear_default_in_renderer():
    source = (ROOT / "scripts" / "report_generator.py").read_text(encoding="utf-8")
    assert 'or "TLP:CLEAR")' not in source
    assert "publication_decision(entry)" in source
    assert "html_content = _build_html(public_entry" in source
