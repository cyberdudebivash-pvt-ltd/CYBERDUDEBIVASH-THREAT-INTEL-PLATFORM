"""
tests/test_true_intel_ingestor_p40.py — CyberDudeBivash SENTINEL APEX
Unit + failure-scenario tests for the 3 new P40 Global Intelligence Source
Fabric additions to scripts/true_intel_ingestor.py: enrich_with_epss(),
ingest_openphish(), sync_mitre_attack() — plus the verified URLhaus
Auth-Key regression fix.

All HTTP is mocked (no live network in the automated suite — see the
`network` pytest marker in pytest.ini for the separate live-verification
path already exercised manually during development). Covers mission
Section 37's required failure scenarios: empty response, malformed JSON,
timeout/network failure, and auth failure (401).
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import true_intel_ingestor as tii  # noqa: E402


# --- enrich_with_epss ---------------------------------------------------

class TestEnrichWithEpss:
    def test_no_cves_returns_zero_without_network_call(self, monkeypatch):
        called = {"n": 0}
        monkeypatch.setattr(tii, "_get_json", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
        items = [{"title": "no cve", "cves": []}]
        assert tii.enrich_with_epss(items) == 0
        assert called["n"] == 0

    def test_successful_enrichment_attaches_scores(self, monkeypatch):
        def fake_get_json(url, timeout=None):
            assert "CVE-2021-44228" in url
            return {"data": [{"cve": "CVE-2021-44228", "epss": "0.94", "percentile": "0.99"}]}

        monkeypatch.setattr(tii, "_get_json", fake_get_json)
        items = [{"title": "log4shell", "cves": ["CVE-2021-44228"]}]
        n = tii.enrich_with_epss(items)
        assert n == 1
        assert items[0]["epss_score"] == 0.94
        assert items[0]["epss_percentile"] == 0.99

    def test_cve_not_in_epss_response_left_unenriched(self, monkeypatch):
        monkeypatch.setattr(tii, "_get_json", lambda *a, **k: {"data": []})
        items = [{"title": "x", "cves": ["CVE-2099-00001"]}]
        n = tii.enrich_with_epss(items)
        assert n == 0
        assert "epss_score" not in items[0]

    def test_malformed_epss_row_does_not_crash(self, monkeypatch):
        """FIRST API returning a non-numeric epss value must not raise."""
        monkeypatch.setattr(tii, "_get_json", lambda *a, **k: {
            "data": [{"cve": "CVE-2021-44228", "epss": "not-a-number", "percentile": "also-bad"}]
        })
        items = [{"title": "x", "cves": ["CVE-2021-44228"]}]
        n = tii.enrich_with_epss(items)  # must not raise
        assert n == 0

    def test_network_failure_returns_zero_not_raise(self, monkeypatch):
        monkeypatch.setattr(tii, "_get_json", lambda *a, **k: None)  # _get_json's real failure contract
        items = [{"title": "x", "cves": ["CVE-2021-44228"]}]
        assert tii.enrich_with_epss(items) == 0

    def test_batches_over_100_cves(self, monkeypatch):
        calls = []

        def fake_get_json(url, timeout=None):
            calls.append(url)
            return {"data": []}

        monkeypatch.setattr(tii, "_get_json", fake_get_json)
        items = [{"cves": [f"CVE-2024-{i:05d}"]} for i in range(150)]
        tii.enrich_with_epss(items)
        assert len(calls) == 2  # 100 + 50


# --- ingest_openphish -----------------------------------------------------

class TestIngestOpenphish:
    def test_parses_plaintext_feed(self, monkeypatch):
        monkeypatch.setattr(tii, "_get_text", lambda *a, **k: "http://evil1.example/\nhttp://evil2.example/\n")
        feed_state = tii.FeedState()
        feed_state._state = {"sources": {}}
        items = tii.ingest_openphish(feed_state)
        assert len(items) == 2
        assert items[0]["feed_source"] == "openphish"
        assert items[0]["iocs"][0]["type"] == "url"
        assert items[0]["threat_type"] == "PHISHING-URL"

    def test_empty_response_returns_no_items(self, monkeypatch):
        monkeypatch.setattr(tii, "_get_text", lambda *a, **k: None)
        feed_state = tii.FeedState()
        feed_state._state = {"sources": {}}
        assert tii.ingest_openphish(feed_state) == []

    def test_non_url_lines_are_ignored(self, monkeypatch):
        monkeypatch.setattr(tii, "_get_text", lambda *a, **k: "not a url\n\nhttp://evil.example/\n")
        feed_state = tii.FeedState()
        feed_state._state = {"sources": {}}
        items = tii.ingest_openphish(feed_state)
        assert len(items) == 1

    def test_capped_at_50_items(self, monkeypatch):
        text = "\n".join(f"http://evil{i}.example/" for i in range(200))
        monkeypatch.setattr(tii, "_get_text", lambda *a, **k: text)
        feed_state = tii.FeedState()
        feed_state._state = {"sources": {}}
        items = tii.ingest_openphish(feed_state)
        assert len(items) == 50


# --- sync_mitre_attack ------------------------------------------------------

_MINI_ATTACK_BUNDLE = {
    "type": "bundle",
    "spec_version": "2.1",
    "objects": [
        {
            "type": "attack-pattern",
            "id": "attack-pattern--test-0001",
            "name": "Test Technique",
            "description": "A test technique.",
            "kill_chain_phases": [{"kill_chain_name": "mitre-attack", "phase_name": "initial-access"}],
            "external_references": [{"source_name": "mitre-attack", "external_id": "T9999"}],
        },
        {
            "type": "intrusion-set",
            "id": "intrusion-set--test-0001",
            "name": "Test Group",
            "aliases": ["TG-Alias"],
            "description": "A test group.",
            "external_references": [{"source_name": "mitre-attack", "external_id": "G9999"}],
        },
        {
            "type": "attack-pattern",
            "id": "attack-pattern--revoked-0001",
            "name": "Revoked Technique",
            "revoked": True,
        },
    ],
}


class TestSyncMitreAttack:
    def test_dry_run_never_writes_files(self, monkeypatch, tmp_path):
        out_path = tmp_path / "enterprise-attack.json"
        state_path = tmp_path / "attck_state.json"
        monkeypatch.setattr(tii, "ATTCK_OUTPUT_PATH", out_path)
        monkeypatch.setattr(tii, "ATTCK_STATE_PATH", state_path)
        monkeypatch.setattr(tii, "_get_text", lambda *a, **k: json.dumps(_MINI_ATTACK_BUNDLE))

        result = tii.sync_mitre_attack(dry_run=True)

        assert result["changed"] is True
        assert result["dry_run"] is True
        assert result["techniques"] == 1  # revoked one excluded
        assert result["groups"] == 1
        assert not out_path.exists()
        assert not state_path.exists()

    def test_real_run_writes_files_and_preserves_stix_ids(self, monkeypatch, tmp_path):
        out_path = tmp_path / "enterprise-attack.json"
        state_path = tmp_path / "attck_state.json"
        monkeypatch.setattr(tii, "ATTCK_OUTPUT_PATH", out_path)
        monkeypatch.setattr(tii, "ATTCK_STATE_PATH", state_path)
        monkeypatch.setattr(tii, "_get_text", lambda *a, **k: json.dumps(_MINI_ATTACK_BUNDLE))

        result = tii.sync_mitre_attack(dry_run=False)

        assert result["changed"] is True
        assert out_path.exists()
        written = json.loads(out_path.read_text())
        assert written["techniques"][0]["id"] == "attack-pattern--test-0001"  # original STIX id preserved verbatim
        assert written["techniques"][0]["attck_id"] == "T9999"
        assert written["groups"][0]["id"] == "intrusion-set--test-0001"
        # Revoked objects excluded
        assert len(written["techniques"]) == 1

    def test_unchanged_bundle_skips_rewrite(self, monkeypatch, tmp_path):
        out_path = tmp_path / "enterprise-attack.json"
        state_path = tmp_path / "attck_state.json"
        monkeypatch.setattr(tii, "ATTCK_OUTPUT_PATH", out_path)
        monkeypatch.setattr(tii, "ATTCK_STATE_PATH", state_path)
        monkeypatch.setattr(tii, "_get_text", lambda *a, **k: json.dumps(_MINI_ATTACK_BUNDLE))

        first = tii.sync_mitre_attack(dry_run=False)
        mtime_after_first = out_path.stat().st_mtime

        second = tii.sync_mitre_attack(dry_run=False)

        assert first["changed"] is True
        assert second["changed"] is False
        assert out_path.stat().st_mtime == mtime_after_first  # not rewritten

    def test_fetch_failure_does_not_raise(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tii, "ATTCK_OUTPUT_PATH", tmp_path / "x.json")
        monkeypatch.setattr(tii, "ATTCK_STATE_PATH", tmp_path / "s.json")
        monkeypatch.setattr(tii, "_get_text", lambda *a, **k: None)
        result = tii.sync_mitre_attack()
        assert result["changed"] is False
        assert result["error"] == "fetch_failed"

    def test_malformed_json_does_not_raise(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tii, "ATTCK_OUTPUT_PATH", tmp_path / "x.json")
        monkeypatch.setattr(tii, "ATTCK_STATE_PATH", tmp_path / "s.json")
        monkeypatch.setattr(tii, "_get_text", lambda *a, **k: "{not valid json")
        result = tii.sync_mitre_attack()
        assert result["changed"] is False
        assert result["error"] == "parse_failed"


# --- URLhaus Auth-Key regression fix ----------------------------------------

class TestUrlhausAuthKeyFix:
    def test_missing_auth_key_skips_fetch_without_network_call(self, monkeypatch):
        """The exact bug this change fixes: verify the source now reports an
        explicit credentials-required state instead of silently attempting
        (and failing) a request abuse.ch will reject with HTTP 401."""
        monkeypatch.setattr(tii, "ABUSECH_AUTH_KEY", "")
        called = {"n": 0}

        class _Boom:
            def __call__(self, *a, **k):
                called["n"] += 1
                raise AssertionError("must not attempt network call without an Auth-Key")

        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", _Boom())

        feed_state = tii.FeedState()
        feed_state._state = {"sources": {}}
        items = tii.ingest_urlhaus(feed_state)

        assert items == []
        assert called["n"] == 0

    def test_auth_key_present_sends_header(self, monkeypatch):
        monkeypatch.setattr(tii, "ABUSECH_AUTH_KEY", "test-key-123")
        captured_request = {}

        class _FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return json.dumps({"query_status": "ok", "urls": []}).encode()

        def fake_urlopen(req, timeout=None):
            captured_request["headers"] = dict(req.header_items())
            return _FakeResponse()

        import urllib.request
        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        feed_state = tii.FeedState()
        feed_state._state = {"sources": {}}
        tii.ingest_urlhaus(feed_state)

        assert captured_request["headers"].get("Auth-key") == "test-key-123"


# --- _parse_ts NVD timestamp format regression -------------------------------
#
# Verified live against the real NVD CVE API v2 response on 2026-08-08: its
# `cve.published` / `cve.lastModified` fields are formatted
# "YYYY-MM-DDTHH:MM:SS.mmm" — fractional seconds, NO trailing "Z". Before this
# fix, _parse_ts() had no matching pattern, so every NVD item's timestamp
# silently parsed to None. That made ingest_nvd_cves() always treat items as
# "new" (is_new() short-circuits True on a None timestamp) but never advance
# feed_state's nvd_cve cursor (the "if newest_ts:" guard was never true), so
# data/cache/feed_state.json never once recorded an nvd_cve entry across
# dozens of live production runs — confirmed via GitHub Actions job logs and
# the committed feed_state.json history. NVD itself was never the problem
# (live API check returned 200 with fresh CVEs); the parser was silently
# discarding every timestamp it saw.

class TestParseTsNvdFormat:
    def test_parses_nvd_fractional_seconds_without_z(self):
        dt = tii._parse_ts("2026-08-06T22:16:40.020")
        assert dt is not None
        assert dt.year == 2026 and dt.month == 8 and dt.day == 6
        assert dt.hour == 22 and dt.minute == 16 and dt.second == 40

    def test_still_parses_github_advisory_format(self):
        """Regression guard: the fix must not break the format other
        sources already rely on (GitHub Advisory's published_at)."""
        assert tii._parse_ts("2026-08-07T19:29:09Z") is not None

    def test_still_parses_cisa_kev_date_only_format(self):
        assert tii._parse_ts("2026-08-07") is not None


class TestIngestNvdCves:
    def _fake_response(self, cves):
        return {
            "vulnerabilities": [
                {"cve": {
                    "id": cve_id,
                    "published": published,
                    "descriptions": [{"lang": "en", "value": "desc"}],
                    "metrics": {},
                }}
                for cve_id, published in cves
            ]
        }

    def test_feed_state_cursor_advances_with_real_nvd_timestamp_format(self, monkeypatch):
        """The actual regression this change fixes: before the _parse_ts
        fix, this cursor never advanced no matter how many runs executed."""
        monkeypatch.setattr(tii, "_get_json", lambda *a, **k: self._fake_response(
            [("CVE-2024-0001", "2026-08-06T22:16:40.020"),
             ("CVE-2024-0002", "2026-08-07T09:05:12.500")]
        ))
        feed_state = tii.FeedState()
        feed_state._state = {"sources": {}}

        items = tii.ingest_nvd_cves(feed_state)

        assert len(items) == 2
        cursor = feed_state.get_last_seen("nvd_cve")
        assert cursor is not None
        assert cursor.day == 7 and cursor.hour == 9  # advanced to the newest item, not left at None

    def test_second_run_excludes_items_at_or_before_the_cursor(self, monkeypatch):
        feed_state = tii.FeedState()
        feed_state._state = {"sources": {}}

        monkeypatch.setattr(tii, "_get_json", lambda *a, **k: self._fake_response(
            [("CVE-2024-0001", "2026-08-06T22:16:40.020")]
        ))
        tii.ingest_nvd_cves(feed_state)
        assert feed_state.get_last_seen("nvd_cve") is not None

        # A clearly-later (by whole seconds, not sub-second) timestamp so
        # this test isn't sensitive to _ts_to_str()'s separate, pre-existing
        # whole-second persistence precision (already safety-netted at the
        # manifest merge stage by the fingerprint-based DedupState).
        monkeypatch.setattr(tii, "_get_json", lambda *a, **k: self._fake_response(
            [("CVE-2024-0003", "2026-08-08T01:00:00.000")]
        ))
        items = tii.ingest_nvd_cves(feed_state)
        assert [i["cves"][0] for i in items] == ["CVE-2024-0003"]

    def test_network_failure_returns_empty_not_raise(self, monkeypatch):
        monkeypatch.setattr(tii, "_get_json", lambda *a, **k: None)
        feed_state = tii.FeedState()
        feed_state._state = {"sources": {}}
        assert tii.ingest_nvd_cves(feed_state) == []
