"""P0 regression tests for deployment convergence report-slug classification."""
from unittest.mock import patch

from scripts import deployment_convergence_validator as dcv


def test_production_cve_suffix_slug_is_resolved_for_publication_gate():
    url = (
        "https://intel.cyberdudebivash.com/reports/2026/09/"
        "intel--1790670338_CVE-2026-86950.html"
    )
    match = dcv._HIST_REPORT_ID_RE.search(url)
    assert match is not None
    assert match.group(1) == "intel--1790670338_CVE-2026-86950"


def test_long_multi_cve_slug_is_resolved_for_publication_gate():
    url = (
        "https://intel.cyberdudebivash.com/reports/2026/09/"
        "intel--1790670330_CVE-2026-101891_CVE-2026-86102_CVE-2026-.html"
    )
    match = dcv._HIST_REPORT_ID_RE.search(url)
    assert match is not None
    assert match.group(1) == "intel--1790670330_CVE-2026-101891_CVE-2026-86102_CVE-2026-"


def test_simple_decimal_slug_is_resolved_for_publication_gate():
    url = "https://intel.cyberdudebivash.com/reports/2026/09/intel--1790670345.html"
    match = dcv._HIST_REPORT_ID_RE.search(url)
    assert match is not None
    assert match.group(1) == "intel--1790670345"


def test_gate_rejected_production_slug_is_counted_as_expected_delivery():
    url = (
        "https://intel.cyberdudebivash.com/reports/2026/09/"
        "intel--1790670338_CVE-2026-86950.html"
    )
    dcv._GATE_VERDICTS.clear()
    with patch.object(
        dcv,
        "query_publication_status",
        return_value={"state": "REJECTED", "customer_ready": False},
    ) as query:
        assert dcv._is_expected_publication_rejection(url) is True
    query.assert_called_once_with("intel--1790670338_CVE-2026-86950")


def test_customer_ready_404_is_never_hidden_as_expected_rejection():
    url = "https://intel.cyberdudebivash.com/reports/2026/09/intel--1790670345.html"
    dcv._GATE_VERDICTS.clear()
    with patch.object(
        dcv,
        "query_publication_status",
        return_value={"state": "CUSTOMER_READY", "customer_ready": True},
    ):
        assert dcv._is_expected_publication_rejection(url) is False


def test_unrelated_html_path_is_not_treated_as_report_id():
    assert dcv._HIST_REPORT_ID_RE.search(
        "https://intel.cyberdudebivash.com/reports/2026/09/index.html"
    ) is None
