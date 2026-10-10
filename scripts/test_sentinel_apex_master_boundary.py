import unittest
from pathlib import Path

from sentinel_apex_master_boundary import activation_status, publication_decision, stage_page

ENV = {
    "SENTINEL_APEX_AI_INTEL": "1",
    "SENTINEL_APEX_AI_INTEL_BASE_URL": "https://ai-intel.example",
}
PAGE = {
    "schema": "sentinel-apex.intel.v1",
    "tlp": "CLEAR",
    "next_cursor": 4,
    "records": [{
        "id": "CVE-2026-1",
        "primary_source_id": "cisa-kev",
        "canonical_source_url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
        "source_published_at": "2026-10-08T00:00:00.000Z",
        "cvss_score": 9.8,
        "kev_status": True,
        "evidence": [
            {"source_id": "cisa-kev", "url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog", "claim": "listed"},
            {"source_id": "unattributed", "url": "https://example.invalid/n", "claim": "unknown"},
        ],
    }],
}


class BoundaryTest(unittest.TestCase):
    def test_flag_off_does_not_stage(self):
        result = stage_page({}, {"cursor": 2, "records": {}}, PAGE, "FRESH")
        self.assertEqual(result["status"], "NOT_CONFIGURED")
        self.assertEqual(result["state"]["cursor"], 2)
        self.assertFalse(result["public_feed_write"])
        self.assertEqual(result["release"], "NOT_AUTHORIZED")

    def test_contract_keeps_provenance_and_still_does_not_publish(self):
        result = stage_page(ENV, {"cursor": 0, "records": {}}, PAGE, "FRESH")
        self.assertEqual(result["status"], "CONTRACT_VERIFIED")
        self.assertEqual(result["freshness_decision"], "ELIGIBLE_FOR_EXISTING_PIPELINE")
        self.assertEqual(result["release"], "NOT_AUTHORIZED")
        self.assertFalse(result["customer_visible"])
        row = result["state"]["records"]["CVE-2026-1"]
        self.assertEqual(row["primary_source_id"], "cisa-kev")
        self.assertEqual(row["cvss_score"], 9.8)
        self.assertEqual(row["source_published_at"], "2026-10-08T00:00:00.000Z")
        self.assertEqual(row["corroborating_source_ids"], ["cisa-kev"])
        self.assertEqual(row["evidence"][1]["source_id"], "unresolved")
        self.assertFalse((Path(__file__).resolve().parents[1] / "api" / "feed.json").exists())

    def test_stale_or_restricted_pages_cannot_pass_on_http_success(self):
        stale = stage_page(ENV, {"cursor": 0, "records": {}}, PAGE, "EXPIRED")
        self.assertEqual(stale["freshness_decision"], "BLOCKED_BY_FRESHNESS_GATE")
        self.assertEqual(stale["release"], "NOT_AUTHORIZED")
        restricted = stage_page(ENV, {"cursor": 5, "records": {}}, {**PAGE, "tlp": "AMBER"}, "FRESH")
        self.assertEqual(restricted["status"], "FAILED")
        self.assertEqual(restricted["state"]["cursor"], 5)
        self.assertEqual(publication_decision(None, None), "BLOCKED_BY_FRESHNESS_GATE")
        self.assertEqual(activation_status({"SENTINEL_APEX_AI_INTEL": "1", "SENTINEL_APEX_AI_INTEL_BASE_URL": "http://insecure"} )["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
