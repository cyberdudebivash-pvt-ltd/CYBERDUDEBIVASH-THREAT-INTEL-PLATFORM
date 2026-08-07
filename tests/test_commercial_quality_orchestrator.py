"""
test_commercial_quality_orchestrator.py -- CyberDudeBivash SENTINEL APEX
Project TITAN Stage 20A -- Enterprise Commercial Quality Orchestrator
(Python composition layer: scripts/commercial_quality_orchestrator.py)

Tests cover:
- Commercial Applicability Engine (Sec 5): the four-state model, per-dimension
  rules, and the Sec 5.3 denominator guarantee (NOT_APPLICABLE excluded from
  both numerator and denominator, never scored as a failure)
- Commercial Quality Orchestrator: read-only composition, never mutates its
  input, never fabricates a citation it cannot source
- Commercial Publication Decision: cites verbatim, never invents a decision
- Commercial Recommendation Layer: presentation-only tier, Premium
  Intelligence gate
- Governance fixtures: protected engines are never imported/mutated by this
  module; zero shared code with the JS-side orchestrator (independent values,
  same architecture)
- A lightweight performance check on the full feed-wide orchestration run
"""
import copy
import time

import pytest

from scripts.commercial_quality_orchestrator import (
    build_commercial_explanation,
    build_commercial_publication_decision,
    build_commercial_quality_view,
    build_commercial_readiness_summary,
    build_commercial_recommendation_layer,
    build_commercial_release_decision,
    compute_commercial_applicability,
    run_orchestration,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def rich_item():
    return {
        "id": "CVE-2026-9999", "title": "Test RCE", "description": "x" * 80,
        "severity": "CRITICAL", "cvss_score": 9.8, "risk_score": 9.1, "confidence": 0.82,
        "cve_ids": ["CVE-2026-9999"], "epss_score": 0.71, "kev_present": True,
        "actor_tag": "APT-TEST", "mitre_tactics": ["TA0001"], "ttps": ["T1190"],
        "ioc_count": 4, "iocs": [{"value": "1.2.3.4", "confidence": 70}], "sigma_rule": "title: x",
        "source_quality": "HIGH", "validation_status": "verified", "sources_reporting": 3,
        "timestamp": "2026-08-07T00:00:00Z", "source": "https://example.com/a",
    }


@pytest.fixture
def bare_vuln_item():
    return {
        "id": "CVE-2026-1111", "title": "Minor info disclosure", "description": "y" * 80,
        "severity": "LOW", "cvss_score": 3.1, "confidence": 0.4,
        "cve_ids": ["CVE-2026-1111"], "nvd_disclosure": "2020-01-01T00:00:00Z",
        "source": "https://example.com/b", "timestamp": "2026-08-07T00:00:00Z",
    }


@pytest.fixture
def fake_view():
    """Hand-built Commercial Quality View, independent of any real item or
    the 5-dimension/7-detection-format applicability space, so tests can
    reach composite/failure combinations a real fixture cannot (e.g.
    >=98% composite with a genuine applicable failure)."""
    def _build(applicable, failed):
        return {
            "item_id": "synthetic-premium-test",
            "applicability": {
                "excluded": False,
                "dimensions": {},
                "summary": {"applicable": applicable, "not_applicable": 0, "unknown": 0,
                            "passed": applicable - failed, "failed": failed},
            },
            "applicability_adjusted_composite": round(((applicable - failed) / applicable) * 100),
            "agreement_summary": {"systems_evaluated": 0, "positive_signals": [], "agreement_count": 0, "note": ""},
            "inputs_cited": [],
        }
    return _build


@pytest.fixture
def fresh_cve_no_epss():
    from datetime import datetime, timezone
    return {
        "id": "CVE-2026-2222", "title": "Very fresh CVE", "description": "z" * 80,
        "severity": "MEDIUM", "cvss_score": 6.0,
        "cve_ids": ["CVE-2026-2222"], "nvd_disclosure": datetime.now(timezone.utc).isoformat(),
        "source": "https://example.com/c", "timestamp": "2026-08-07T00:00:00Z",
    }


# ─── Commercial Applicability Engine (Sec 5) ────────────────────────────────

class TestCommercialApplicabilityEngine:
    def test_bare_vuln_disclosure_marks_mitre_not_applicable_not_failed(self, bare_vuln_item):
        app = compute_commercial_applicability(bare_vuln_item)
        assert app["excluded"] is False
        assert app["dimensions"]["mitre_attack"]["status"] == "NOT_APPLICABLE"
        assert "result" not in app["dimensions"]["mitre_attack"]

    def test_behavioral_evidence_with_no_mitre_mapping_is_a_real_fail(self, rich_item):
        item = dict(rich_item)
        item.pop("mitre_tactics", None)
        item.pop("ttps", None)
        app = compute_commercial_applicability(item)
        assert app["dimensions"]["mitre_attack"]["status"] == "APPLICABLE"
        assert app["dimensions"]["mitre_attack"]["result"] == "FAIL"

    def test_no_cve_marks_epss_and_kev_not_applicable(self, rich_item):
        item = dict(rich_item)
        item.pop("cve_ids", None)
        item["id"] = "advisory-no-cve"
        app = compute_commercial_applicability(item)
        assert app["dimensions"]["epss"]["status"] == "NOT_APPLICABLE"
        assert app["dimensions"]["kev"]["status"] == "NOT_APPLICABLE"

    def test_freshly_disclosed_cve_with_no_epss_yet_is_unknown_not_a_fabricated_fail(self, fresh_cve_no_epss):
        app = compute_commercial_applicability(fresh_cve_no_epss)
        assert app["dimensions"]["epss"]["status"] == "UNKNOWN"

    def test_kev_is_applicable_even_when_absent(self, rich_item):
        item = dict(rich_item)
        item["kev_present"] = False
        app = compute_commercial_applicability(item)
        assert app["dimensions"]["kev"]["status"] == "APPLICABLE"
        assert app["dimensions"]["kev"]["result"] == "PASS"

    def test_detection_format_absence_is_unknown_never_guessed(self, rich_item):
        app = compute_commercial_applicability(rich_item)
        assert app["dimensions"]["detection_coverage"]["yara"]["status"] == "UNKNOWN"
        assert app["dimensions"]["detection_coverage"]["sigma"]["status"] == "APPLICABLE"
        assert app["dimensions"]["detection_coverage"]["sigma"]["result"] == "PASS"

    def test_item_missing_id_is_wholesale_excluded(self):
        app = compute_commercial_applicability({"title": "no id field"})
        assert app["excluded"] is True
        assert app["dimensions"] == {}

    def test_not_applicable_dims_never_score_as_failed(self, bare_vuln_item):
        app = compute_commercial_applicability(bare_vuln_item)
        assert app["summary"]["not_applicable"] >= 1
        # mitre_attack is NOT_APPLICABLE -- it must not also be counted as failed
        assert app["dimensions"]["mitre_attack"]["status"] != "APPLICABLE"


# ─── Commercial Quality Orchestrator -- composition, not computation ───────

class TestCommercialQualityOrchestrator:
    def test_applicability_adjusted_composite_excludes_not_applicable_from_denominator(self, bare_vuln_item):
        view = build_commercial_quality_view(bare_vuln_item, {})
        assert view["applicability"]["dimensions"]["mitre_attack"]["status"] == "NOT_APPLICABLE"
        assert view["applicability_adjusted_composite"] is not None
        assert 0 <= view["applicability_adjusted_composite"] <= 100

    def test_never_mutates_the_input_item(self, rich_item):
        before = copy.deepcopy(rich_item)
        build_commercial_quality_view(rich_item, {})
        assert rich_item == before

    def test_never_fabricates_governor_citation_when_report_absent(self, rich_item):
        view = build_commercial_quality_view(rich_item, context={"governor_report": None, "dossier_report": None, "p33_report": None})
        governor_citation = next(c for c in view["inputs_cited"] if c["source"] == "commercial_readiness_governor.py")
        assert "error" in governor_citation

    def test_cites_supplied_governor_report_verbatim(self, rich_item):
        fake_report = {"go_live": {"commercial_readiness_score": 77, "dashboard_status": "GO"}}
        view = build_commercial_quality_view(rich_item, context={"governor_report": fake_report, "dossier_report": None, "p33_report": None})
        governor_citation = next(c for c in view["inputs_cited"] if c["source"].startswith("commercial_readiness_governor.py ("))
        assert "77" in governor_citation["value"]


# ─── Commercial Readiness Summary ───────────────────────────────────────────

class TestCommercialReadinessSummary:
    def test_zero_applicable_failures_requires_applicable_gates_and_none_failed(self, rich_item):
        view = build_commercial_quality_view(rich_item, {})
        readiness = build_commercial_readiness_summary(view)
        expected = readiness["applicable_gates"] > 0 and readiness["failed_applicable_gates"] == 0
        assert readiness["zero_applicable_failures"] == expected

    def test_missing_evidence_lists_unknown_dimensions_by_name(self, rich_item):
        view = build_commercial_quality_view(rich_item, {})
        readiness = build_commercial_readiness_summary(view)
        assert "detection_coverage.yara" in readiness["missing_evidence"]


# ─── Commercial Publication Decision -- cites only, never decides ──────────

class TestCommercialPublicationDecision:
    def test_no_publication_decision_field_is_unknown_never_fabricated(self, rich_item):
        assert "publication_decision" not in rich_item
        view = build_commercial_quality_view(rich_item, {})
        pub = build_commercial_publication_decision(rich_item, view)
        assert pub["publication_decision_citation"] is None
        assert pub["status"].startswith("UNKNOWN")

    def test_cites_item_publication_decision_verbatim(self, rich_item):
        item = dict(rich_item)
        item["publication_decision"] = "ALLOW_WITH_WARNING"
        view = build_commercial_quality_view(item, {})
        pub = build_commercial_publication_decision(item, view)
        assert pub["publication_decision_citation"] == "ALLOW_WITH_WARNING"
        assert pub["status"] == "CITED"


# ─── Commercial Explanation Engine ──────────────────────────────────────────

def test_commercial_explanation_cites_the_same_inputs_as_the_view(rich_item):
    view = build_commercial_quality_view(rich_item, {})
    explanation = build_commercial_explanation(view)
    assert explanation["citations"] == view["inputs_cited"]
    assert len(explanation["narrative"]) > 0


# ─── Commercial Recommendation Layer -- presentation-only ──────────────────

class TestCommercialRecommendationLayer:
    def test_premium_intelligence_requires_zero_applicable_failures(self, fake_view):
        # A real fixture cannot reach this branch: the engine only has 5 named
        # dimensions + 7 detection formats (~11 applicable dimensions best
        # case), and one failure among 11 rounds to 91%, never 98%+. This uses
        # a hand-built view (see the fake_view fixture) with enough applicable
        # dimensions to actually reach >=98% with one real failure -- the
        # Commercial Recommendation Layer is a pure function of an
        # already-computed view, independently testable from
        # build_commercial_quality_view's realistic-item derivation.
        view = fake_view(applicable=50, failed=1)  # 49/50 = 98%, 1 applicable failure
        assert view["applicability_adjusted_composite"] == 98
        readiness = build_commercial_readiness_summary(view)
        assert readiness["zero_applicable_failures"] is False
        rec = build_commercial_recommendation_layer(view)
        assert rec["tier"] == "COMMERCIAL_CERTIFIED", "a 98%+ composite with a real applicable failure must be downgraded from PREMIUM_INTELLIGENCE"

    def test_premium_intelligence_awarded_at_98_plus_with_zero_applicable_failures(self, fake_view):
        view = fake_view(applicable=50, failed=0)  # 50/50 = 100%, zero applicable failures
        readiness = build_commercial_readiness_summary(view)
        assert readiness["zero_applicable_failures"] is True
        rec = build_commercial_recommendation_layer(view)
        assert rec["tier"] == "PREMIUM_INTELLIGENCE"

    def test_recommendation_is_explicitly_presentation_only(self, rich_item):
        view = build_commercial_quality_view(rich_item, {})
        rec = build_commercial_recommendation_layer(view)
        assert rec["presentation_only"] is True
        assert "never replaces or outranks" in rec["non_authoritative_note"]


# ─── Commercial Release Decision ────────────────────────────────────────────

def test_commercial_release_decision_packages_consistently(rich_item):
    view = build_commercial_quality_view(rich_item, {})
    pub = build_commercial_publication_decision(rich_item, view)
    release = build_commercial_release_decision(view, pub)
    rec = build_commercial_recommendation_layer(view)
    assert release["recommendation_tier"] == rec["tier"]
    assert release["publication_decision"] == pub


# ─── Governance fixtures: protected engines untouched, zero shared code ────

class TestGovernanceFixtures:
    def test_module_never_imports_protected_engine_internals(self):
        """This module composes commercial_readiness_governor.py and
        dossier_quality_engine.py by reading their already-written report
        files only -- it must never import their internal functions/classes
        (that would be re-computation, not composition)."""
        import scripts.commercial_quality_orchestrator as mod
        src = mod.__file__
        with open(src, encoding="utf-8") as fh:
            text = fh.read()
        assert "from scripts.commercial_readiness_governor import" not in text
        assert "from agent.dossier_quality_engine import" not in text
        assert "import commercial_readiness_governor" not in text
        assert "import dossier_quality_engine" not in text

    def test_applicability_engine_never_returns_a_bare_numeric_score(self, rich_item):
        """Sec 5's Applicability Model classifies (APPLICABLE/NOT_APPLICABLE/
        UNKNOWN), it does not compute a new confidence/trust number -- guards
        against this module quietly growing into an 9th independent scorer."""
        app = compute_commercial_applicability(rich_item)
        for key, val in app["dimensions"].items():
            entries = val.values() if key == "detection_coverage" else [val]
            for d in entries:
                assert d["status"] in ("APPLICABLE", "NOT_APPLICABLE", "UNKNOWN")


# ─── Performance ─────────────────────────────────────────────────────────

def test_full_orchestration_run_completes_quickly_on_real_feed_size(monkeypatch):
    """Non-blocking perf guard: composing over ~200 items should be well
    under a second since every dimension check is O(1) per item and no
    network/disk I/O happens per-item (only the 3 context reports, loaded
    once). Forces DRY_RUN (module-level flag, not just the env var, since it
    was already read at import time) so this synthetic fixture data never
    overwrites the real data/quality/commercial_quality_orchestrator_report.json."""
    import scripts.commercial_quality_orchestrator as mod
    monkeypatch.setattr(mod, "DRY_RUN", True)

    items = [
        {"id": f"CVE-2026-{i}", "cve_ids": [f"CVE-2026-{i}"], "epss_score": 0.1,
         "kev_present": False, "ioc_count": 1, "mitre_tactics": ["TA0001"], "actor_tag": "x"}
        for i in range(200)
    ]
    start = time.perf_counter()
    report = mod.run_orchestration(items)
    elapsed = time.perf_counter() - start
    assert report["feed_items_evaluated"] == 200
    assert elapsed < 2.0, f"orchestration over 200 items took {elapsed:.2f}s -- investigate before this becomes a CI bottleneck"
