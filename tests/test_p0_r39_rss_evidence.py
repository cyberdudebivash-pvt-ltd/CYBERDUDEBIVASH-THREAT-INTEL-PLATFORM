"""P0 R39 — only observed source evidence may reach published manifests."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.p0_r39_evidence import capture_rss_evidence, append_fetched_article_evidence

OBSERVED = "2026-10-10T05:10:00Z"
ENTRY = {
    "title": "Original advisory",
    "link": "https://publisher.example/security/a1",
    "summary": "Original article summary",
    "published": "Sat, 10 Oct 2026 04:00:00 GMT",
}

class RSSObservationEvidenceTests(unittest.TestCase):
    def test_confirmed_observation_populates_source_and_real_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "trust.json"
            registry.write_text(json.dumps({
                "trust_scores": {"feeds.publisher.example": {"trust_score": 0.82}}
            }))
            p = capture_rss_evidence(ENTRY, "https://feeds.publisher.example/rss", OBSERVED, registry)
            self.assertEqual(p["source_name"], "feeds.publisher.example")
            self.assertEqual(p["publication_timestamp"], "2026-10-10T04:00:00Z")
            self.assertEqual(p["retrieval_timestamp"], OBSERVED)
            self.assertEqual(p["evidence_count"], 1)
            self.assertEqual(p["trust_score"], 8.2)
            self.assertEqual(p["content_hash_scope"], "rss_entry_fields_sha256")
            self.assertEqual(len(p["content_hash"]), 64)

    def test_missing_trust_or_pubdate_does_not_invent_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = capture_rss_evidence(
                {**ENTRY, "published": ""}, "https://unknown.example/rss",
                OBSERVED, Path(tmp) / "absent.json"
            )
            self.assertNotIn("publication_timestamp", p)
            self.assertNotIn("trust_score", p)
            self.assertEqual(p["evidence_count"], 1)
            self.assertNotIn("article_content_hash", p)

    def test_missing_actual_acquisition_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp) / "registry.json"
            self.assertEqual(capture_rss_evidence(ENTRY, "https://publisher.example/rss", "", registry), {})
            self.assertEqual(capture_rss_evidence(ENTRY, "", OBSERVED, registry), {})
            self.assertEqual(capture_rss_evidence({"link": ENTRY["link"]}, "https://publisher.example/rss", OBSERVED, registry), {})

    def test_future_publication_not_claimed(self):
        item = {**ENTRY, "published": "Sat, 10 Oct 2026 11:00:00 GMT"}
        p = capture_rss_evidence(item, "https://publisher.example/rss", OBSERVED)
        self.assertNotIn("publication_timestamp", p)

    def test_two_real_artifacts_count_two_no_article_no_increment(self):
        p = capture_rss_evidence(ENTRY, "https://publisher.example/rss", OBSERVED)
        no_article = append_fetched_article_evidence(p, {"fetch_status": "failed", "full_text": "invented"})
        self.assertEqual(no_article["evidence_count"], 1)
        got = append_fetched_article_evidence(p, {"fetch_status": "success", "full_text": "Actually fetched source article bytes"})
        self.assertEqual(got["evidence_count"], 2)
        self.assertEqual(got["article_content_hash"],
                         hashlib.sha256(b"Actually fetched source article bytes").hexdigest())
        self.assertEqual(p["evidence_count"], 1)  # non-mutating

    def test_real_stix_and_manifest_roundtrip_preserves_observed_evidence(self):
        from agent.export_stix import STIXExporter
        with tempfile.TemporaryDirectory() as td:
            with tempfile.TemporaryDirectory() as trustdir:
                reg = Path(trustdir) / "trust.json"
                reg.write_text(json.dumps({"trust_scores": {
                    "publisher.example": {"trust_score": 0.82}
                }}))
                observed = capture_rss_evidence(ENTRY, "https://publisher.example/feed", OBSERVED, reg)
                observed = append_fetched_article_evidence(observed, {
                    "fetch_status": "success", "full_text": "Original separately fetched text"
                })
                metadata = {"source_url": ENTRY["link"], **observed}
                STIXExporter(output_dir=td).create_bundle(
                    title="Original source report confirmed",
                    iocs={}, risk_score=5.0, metadata=metadata,
                    published_at=observed["publication_timestamp"],
                    feed_source=observed["source_name"],
                )
                bundles = sorted(Path(td).glob("CDB-APEX-*.json"))
                self.assertTrue(bundles, "STIX bundle was not actually persisted")
                stix = json.loads(bundles[-1].read_text())
                intrusion = next(v for v in stix["objects"] if v.get("type") == "intrusion-set")
                ext = intrusion["extensions"]["x-cdb-apex-1"]
                self.assertEqual(ext["x_cdb_source_name"], "publisher.example")
                self.assertEqual(ext["x_cdb_retrieval_timestamp"], OBSERVED)
                self.assertEqual(ext["x_cdb_publication_timestamp"], "2026-10-10T04:00:00Z")
                self.assertEqual(ext["x_cdb_evidence_count"], 2)
                self.assertEqual(ext["x_cdb_article_content_hash"], observed["article_content_hash"])
                manifest = json.loads((Path(td) / "feed_manifest.json").read_text())
                self.assertTrue(isinstance(manifest, list) and manifest)
                item = manifest[0]
                for key in ("source_name", "retrieval_timestamp", "publication_timestamp",
                            "content_hash", "content_hash_scope", "evidence_count",
                            "article_content_hash", "trust_score"):
                    self.assertEqual(item[key], observed[key], key)

    def test_exporter_carries_only_observed_provenance(self):
        src = (ROOT / "agent/export_stix.py").read_text(encoding="utf-8")
        self.assertIn("provenance=(metadata or {})", src)
        self.assertIn("provenance=provenance", src)
        self.assertIn('if _observed.get("content_hash_scope") == "rss_entry_fields_sha256":', src)
        self.assertIn('entry[_k] = _observed[_k]', src)
        self.assertEqual(src.count('"article_content_hash"'), 2)
        self.assertIn('_extension["x_cdb_" + _key] = _observed[_key]', src)

if __name__ == "__main__":
    unittest.main()
