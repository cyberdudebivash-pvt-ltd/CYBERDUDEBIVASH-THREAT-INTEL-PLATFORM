import unittest

from sentinel_apex_intel import apply_master_page, empty_state


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
            {"source_id": "unattributed", "url": "https://example.invalid/note", "claim": "unknown origin"},
        ],
    }],
}


class AdapterTest(unittest.TestCase):
    def test_idempotent_and_unresolved_is_not_corroboration(self):
        first = apply_master_page(empty_state(), PAGE)
        self.assertIsNone(first["error"])
        self.assertEqual(first["applied"], 1)
        row = first["state"]["records"]["CVE-2026-1"]
        self.assertEqual(row["corroborating_source_ids"], ["cisa-kev"])
        self.assertEqual(row["evidence"][1]["source_id"], "unresolved")
        self.assertEqual(row["cvss_score"], 9.8)
        self.assertEqual(row["source_published_at"], "2026-10-08T00:00:00.000Z")
        second = apply_master_page(first["state"], PAGE)
        self.assertEqual(second["applied"], 0)

    def test_rejects_without_moving_the_cursor(self):
        start = empty_state()
        self.assertEqual(apply_master_page(start, {"schema": "other", "next_cursor": 1, "records": []})["state"]["cursor"], 0)
        self.assertEqual(apply_master_page(start, {"tlp": "RED", "next_cursor": 1, "records": []})["error"], "restricted distribution")
        held = {"cursor": 9, "records": {}}
        result = apply_master_page(held, {"schema": "sentinel-apex.intel.v1", "next_cursor": 2, "records": []})
        self.assertEqual(result["state"]["cursor"], 9)

    def test_retraction_removes_without_replacement(self):
        first = apply_master_page(empty_state(), PAGE)
        retracted = apply_master_page(first["state"], {
            "schema": "sentinel-apex.intel.v1",
            "next_cursor": 5,
            "records": [],
            "events": [{"record_id": "CVE-2026-1", "visible": False, "op": "retract"}],
        })
        self.assertEqual(retracted["removed"], 1)
        self.assertNotIn("CVE-2026-1", retracted["state"]["records"])


if __name__ == "__main__":
    unittest.main()
