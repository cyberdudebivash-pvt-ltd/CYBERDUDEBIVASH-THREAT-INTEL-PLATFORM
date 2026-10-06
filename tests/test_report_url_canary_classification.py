"""
tests/test_report_url_canary_classification.py — CyberDudeBivash SENTINEL APEX

Unit tests for the v187.0 P0 fix to scripts/report_url_canary.py's STAGE
5.8.1b live canary: classify_and_summarize() must classify every probed
report URL against the authoritative /api/v1/reports/{id}/publication-status
endpoint (via the shared scripts/deployment_convergence_validator.py
query_publication_status() building block -- Single Source of Truth, no
gate-scoring logic duplicated here) instead of reporting every 404 as an
ambiguous "P0 DEPLOYMENT FAILURE".

Root cause this guards against: 9 real production report URLs alarmed as
P0 deployment failures were, on live investigation, all correctly-functioning
publication-gate rejections (P20/P21/P26 below threshold) -- not deployment
bugs. classify_and_summarize() must separate a genuine published-but-broken
report (published_failed) from an expected, correct rejection
(expected_rejections), and must fail closed (unknown) when the
publication-status endpoint itself cannot be reached or parsed.

Covers the 5 states required for this fix:
  1. PUBLISHED + HTTP 200            -> published_passed
  2. PUBLISHED + HTTP 404            -> published_failed (real P0 failure)
  3. REJECTED  + HTTP 404            -> expected_rejections (not a failure)
  4. GENERATING/PENDING + HTTP 404   -> expected_rejections (see note below;
                                         the publication-status endpoint's
                                         customer_ready boolean does not
                                         currently distinguish "pending" from
                                         "rejected" -- both report
                                         customer_ready:false. Documented in
                                         classify_and_summarize()'s docstring
                                         and asserted explicitly here so a
                                         future endpoint enhancement that
                                         *does* add a real "pending" signal
                                         has a regression test to update.)
  5. UNKNOWN (endpoint unreachable/unparseable) + HTTP 404 -> unknown
                                         (fail-closed, never silently passed)
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import report_url_canary as canary  # noqa: E402

BASE = canary.PAGES_BASE_URL


def _status(customer_ready, state="REJECTED", **extra):
    payload = {"customer_ready": customer_ready, "state": state}
    payload.update(extra)
    return payload


class TestExtractReportId:
    def test_extracts_id_from_html_path(self):
        assert canary._extract_report_id("/reports/2026/08/intel--abc123.html") == "intel--abc123"

    def test_returns_none_for_non_intel_prefixed_name(self):
        assert canary._extract_report_id("/reports/2026/08/not-a-report.html") is None

    def test_strips_htm_suffix_too(self):
        assert canary._extract_report_id("/reports/2026/08/intel--abc123.htm") == "intel--abc123"


class TestClassifyAndSummarize:
    def test_published_and_200_counts_as_published_passed(self):
        rp = "/reports/2026/08/intel--published-ok.html"
        with patch.object(canary, "query_publication_status", return_value=_status(True, state="PUBLISHED")):
            summary = canary.classify_and_summarize([rp], passed_urls=[BASE + rp], failed_tuples=[])
        assert summary["published_checked"] == 1
        assert summary["published_passed"] == 1
        assert summary["published_failed"] == []
        assert summary["expected_rejections"] == []
        assert summary["unknown"] == []

    def test_published_and_404_is_a_real_deployment_failure(self):
        rp = "/reports/2026/08/intel--published-broken.html"
        with patch.object(canary, "query_publication_status", return_value=_status(True, state="PUBLISHED")):
            summary = canary.classify_and_summarize(
                [rp], passed_urls=[], failed_tuples=[(BASE + rp, 404, "not found")]
            )
        assert summary["published_checked"] == 1
        assert summary["published_passed"] == 0
        assert len(summary["published_failed"]) == 1
        assert summary["published_failed"][0][0] == rp
        assert summary["published_failed"][0][1] == 404
        assert summary["expected_rejections"] == []
        assert summary["unknown"] == []

    def test_rejected_and_404_is_an_expected_rejection_not_a_failure(self):
        rp = "/reports/2026/08/intel--rejected.html"
        with patch.object(canary, "query_publication_status", return_value=_status(False, state="REJECTED")):
            summary = canary.classify_and_summarize(
                [rp], passed_urls=[], failed_tuples=[(BASE + rp, 404, "not found")]
            )
        assert summary["published_checked"] == 0
        assert summary["published_failed"] == []
        assert summary["expected_rejections"] == [rp]
        assert summary["unknown"] == []

    def test_generating_pending_and_404_is_not_reported_as_a_real_failure(self):
        # See module docstring: the publication-status endpoint's
        # customer_ready boolean does not currently distinguish "still
        # generating" from "rejected" -- both are customer_ready:false, so
        # a pending report's 404 lands in expected_rejections today. The
        # property under test that must never regress: it must NOT be
        # counted as published_failed (a P0 alarm) and must NOT be silently
        # dropped as unknown either.
        rp = "/reports/2026/08/intel--still-generating.html"
        with patch.object(canary, "query_publication_status", return_value=_status(False, state="GENERATING")):
            summary = canary.classify_and_summarize(
                [rp], passed_urls=[], failed_tuples=[(BASE + rp, 404, "not found")]
            )
        assert summary["published_failed"] == []
        assert summary["expected_rejections"] == [rp]
        assert summary["unknown"] == []
        assert summary["pending"] == []  # documented current limitation, not a silent success

    def test_unknown_status_and_404_fails_closed(self):
        rp = "/reports/2026/08/intel--unresolvable.html"
        with patch.object(canary, "query_publication_status", return_value=None):
            summary = canary.classify_and_summarize(
                [rp], passed_urls=[], failed_tuples=[(BASE + rp, 404, "not found")]
            )
        assert summary["published_checked"] == 0
        assert summary["published_failed"] == []
        assert summary["expected_rejections"] == []
        assert summary["unknown"] == [rp]

    def test_non_intel_prefixed_path_is_unknown_not_silently_passed(self):
        rp = "/reports/2026/08/legacy-non-intel-report.html"
        with patch.object(canary, "query_publication_status") as mock_query:
            summary = canary.classify_and_summarize(
                [rp], passed_urls=[], failed_tuples=[(BASE + rp, 404, "not found")]
            )
        mock_query.assert_not_called()  # _extract_report_id returned None -> never queried
        assert summary["unknown"] == [rp]

    def test_mixed_batch_matches_real_incident_shape(self):
        # Regression fixture: 9 real report URLs from the incident that
        # originally triggered false "P0 DEPLOYMENT FAILURE" alarms, all of
        # which were confirmed live to be correct REJECTED verdicts, plus
        # one genuinely PUBLISHED+200 report from the same batch.
        rejected_ids = [
            "d6333de9ce86da0eec860464", "6f4d1b328e2da4fbafc575ab", "f3b0bdb86d0a0779dd02a55a",
            "da1f37e6d1136aa6af36adbe", "350bde1306bac950e1399955", "ed01402f842427031bd6cda0",
            "0a04900538430910b2c80981", "439c9b32164b602cd6fffea2", "8f77d2f69deecde63b657f80",
        ]
        published_id = "f294b330f0bc613cab8db64d"
        rejected_paths = [f"/reports/2026/08/intel--{rid}.html" for rid in rejected_ids]
        published_path = f"/reports/2026/08/intel--{published_id}.html"

        def fake_query(report_id):
            if report_id == f"intel--{published_id}":
                return _status(True, state="PUBLISHED")
            return _status(False, state="REJECTED")

        with patch.object(canary, "query_publication_status", side_effect=fake_query):
            summary = canary.classify_and_summarize(
                report_paths=rejected_paths + [published_path],
                passed_urls=[BASE + published_path],
                failed_tuples=[(BASE + rp, 404, "not found") for rp in rejected_paths],
            )

        assert summary["published_checked"] == 1
        assert summary["published_passed"] == 1
        assert summary["published_failed"] == []
        assert len(summary["expected_rejections"]) == 9
        assert summary["unknown"] == []
