"""
sdk/tests/test_client.py — regression tests for the 2026-09-01 fix that
pointed sentinel_sdk at the real, live API.

Before that fix, _DEFAULT_BASE_URL was a domain
(api.sentinelapex.cyberdudebivash.com) with no configured route anywhere in
the platform's deployment, and most methods called paths that don't exist
in workers/intel-gateway/src/index.js. These tests assert the real domain
and real paths directly, and mock urllib at the transport layer (matching
this SDK's actual stdlib-only implementation) rather than the network, so
they run with zero external dependencies and no live network access.
"""
import io
import json
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, __file__.rsplit("/sdk/tests/", 1)[0] + "/sdk")

from sentinel_sdk.client import SentinelClient  # noqa: E402
from sentinel_sdk.exceptions import NotFoundError  # noqa: E402


def _fake_response(payload):
    """Build an object usable as a `with urlopen(...) as resp:` context manager."""
    body = json.dumps(payload).encode("utf-8")

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return _Resp(body)


class TestBaseUrl(unittest.TestCase):
    def test_default_base_url_is_the_real_live_domain(self):
        client = SentinelClient(api_key="cdb_pro_test")
        self.assertEqual(client._base_url, "https://intel.cyberdudebivash.com")

    def test_default_billing_base_url_is_the_real_revenue_engine_domain(self):
        client = SentinelClient(api_key="cdb_pro_test")
        self.assertEqual(client._billing_base_url, "https://revenue.intel.cyberdudebivash.com")


class TestUrlConstruction(unittest.TestCase):
    """Every path here is a route confirmed live in
    workers/intel-gateway/src/index.js (or workers/revenue-engine for the
    billing ones) as of the 2026-09-01 monetization audit."""

    def setUp(self):
        self.client = SentinelClient(api_key="cdb_pro_test")

    def test_health_uses_real_path(self):
        self.assertEqual(self.client._build_url("/api/health"),
                          "https://intel.cyberdudebivash.com/api/health")

    def test_ioc_lookup_uses_q_param_not_value(self):
        # The live route (index.js) reads url.searchParams.get("q"), never "value".
        url = self.client._build_url("/api/v1/ioc/lookup", {"q": "1.2.3.4"})
        self.assertIn("q=1.2.3.4", url)
        self.assertNotIn("value=", url)

    def test_feed_path_is_real(self):
        self.assertEqual(self.client._build_url("/api/feed"),
                          "https://intel.cyberdudebivash.com/api/feed")

    def test_search_path_is_real(self):
        url = self.client._build_url("/api/search", {"q": "log4shell", "limit": 10})
        self.assertTrue(url.startswith("https://intel.cyberdudebivash.com/api/search?"))

    def test_taxii_collection_path_is_real(self):
        url = self.client._build_url("/taxii/collections/sentinel-apex-main/objects/")
        self.assertEqual(url, "https://intel.cyberdudebivash.com/taxii/collections/sentinel-apex-main/objects/")

    def test_billing_calls_use_the_billing_base_url_not_the_main_one(self):
        # /api/apikeys/self-rotate and /api/apikeys/validate only match
        # revenue-engine's route (its own custom domain); they do NOT match
        # intel-gateway's main-domain route pattern (/api/v2/billing/*).
        url = self.client._build_url("/api/apikeys/validate", base_url=self.client._billing_base_url)
        self.assertEqual(url, "https://revenue.intel.cyberdudebivash.com/api/apikeys/validate")


class TestAdvisoryItemFieldMapping(unittest.TestCase):
    """A live feed export (api/feed_public.json) uses field names that
    disagree with what this model originally assumed (tlp vs tlp_label,
    confidence vs confidence_score, cve_id vs cve_ids) -- verify both are
    accepted so the SDK doesn't silently return zeroed-out fields."""

    def test_reads_legacy_field_names_from_a_real_sample_shape(self):
        from sentinel_sdk.models import AdvisoryItem
        real_sample = {
            "id": "intel--76c15a2d904f1085b58b0d18",
            "stix_id": "intel--76c15a2d904f1085b58b0d18",
            "title": "Example advisory",
            "severity": "MEDIUM",
            "risk_score": 7.0,
            "confidence": 12,
            "tlp": "TLP:AMBER",
            "cve_id": "CVE-2026-65105",
            "kev": "NO",
        }
        item = AdvisoryItem.from_dict(real_sample)
        self.assertEqual(item.confidence_score, 12)
        self.assertEqual(item.tlp_label, "TLP:AMBER")
        self.assertEqual(item.cve_ids, ["CVE-2026-65105"])
        self.assertFalse(item.kev_present)

    def test_reads_documented_field_names_too(self):
        from sentinel_sdk.models import AdvisoryItem
        item = AdvisoryItem.from_dict({
            "stix_id": "x", "confidence_score": 0.9, "tlp_label": "TLP:GREEN",
            "cve_ids": ["CVE-2026-1"], "kev_present": True,
        })
        self.assertEqual(item.confidence_score, 0.9)
        self.assertEqual(item.tlp_label, "TLP:GREEN")
        self.assertEqual(item.cve_ids, ["CVE-2026-1"])
        self.assertTrue(item.kev_present)


class TestGetAdvisoriesPagination(unittest.TestCase):
    """/api/feed has no server-side pagination -- get_advisories() slices
    client-side. Regression test for a bug caught during this same fix:
    offset was briefly (re-)derived from FeedMetadata, which has no limit
    field, instead of being passed through from the actual slice."""

    def _feed_of(self, n):
        return {"items": [{"id": f"item-{i}", "severity": "HIGH"} for i in range(n)]}

    @patch("sentinel_sdk.client.urlopen")
    def test_offset_and_has_more_are_correct_across_pages(self, mock_urlopen):
        client = SentinelClient(api_key="cdb_pro_test")
        mock_urlopen.return_value = _fake_response(self._feed_of(250))

        page1 = client.get_advisories(limit=100, page=1)
        self.assertEqual(page1.offset, 0)
        self.assertEqual(len(page1.items), 100)
        self.assertTrue(page1.has_more)

        mock_urlopen.return_value = _fake_response(self._feed_of(250))
        page3 = client.get_advisories(limit=100, page=3)
        self.assertEqual(page3.offset, 200)
        self.assertEqual(len(page3.items), 50)
        self.assertFalse(page3.has_more)

    @patch("sentinel_sdk.client.urlopen")
    def test_get_advisory_raises_not_found_for_unknown_id(self, mock_urlopen):
        client = SentinelClient(api_key="cdb_pro_test")
        mock_urlopen.return_value = _fake_response(self._feed_of(5))
        with self.assertRaises(NotFoundError):
            client.get_advisory("does-not-exist")


if __name__ == "__main__":
    unittest.main()
