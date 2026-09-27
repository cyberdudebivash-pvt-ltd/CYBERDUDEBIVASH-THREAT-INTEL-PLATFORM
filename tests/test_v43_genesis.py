#!/usr/bin/env python3
"""test_v43_genesis.py — Test Suite for all 12 GENESIS engines.

v43.1 (2026-09-27): engines compute only from feed items. Capabilities the
platform does not operate (sensors, honeypots, dark-web monitoring) report
operated=False with no invented telemetry; placeholder actor tags are not
actors; G07 counts detection rules actually attached to items.
"""
import json, os, sys, pytest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MOCK = [
    {"title": "CVE-2026-1234 Critical RCE by APT28", "risk_score": 9.5,
     "timestamp": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
     "stix_id": "indicator--001", "actor_tag": "APT28", "kev_present": True,
     "epss_score": 85, "cvss_score": 9.8, "confidence_score": 90, "feed_source": "CISA",
     "blog_url": "https://test.com/1", "mitre_tactics": ["T1190", "T1059", "T1071"],
     "ioc_counts": {"domain": 5, "ipv4": 12, "sha256": 1}, "supply_chain": False,
     "sigma_rule": "title: CVE-2026-1234\ndetection: {}", "kql_query": "DeviceProcessEvents | take 1",
     "suricata_rule": "alert http any any -> any any (sid:1;)", "exploit_maturity": "WEAPONIZED"},
    {"title": "Ransomware LockBit targets financial sector", "risk_score": 8.2,
     "timestamp": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
     "stix_id": "indicator--002", "actor_tag": "LockBit", "kev_present": False,
     "epss_score": 45, "feed_source": "BleepingComputer", "mitre_tactics": ["T1566", "T1486"],
     "ioc_counts": {"domain": 8}, "blog_url": "https://test.com/2"},
    {"title": "CVE-2026-5678 Zero-day Cisco by APT28", "risk_score": 9.0,
     "timestamp": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
     "stix_id": "indicator--003", "actor_tag": "APT28", "kev_present": True,
     "epss_score": 90, "feed_source": "CISA", "mitre_tactics": ["T1190", "T1068"],
     "ioc_counts": {"ipv4": 20}, "blog_url": "https://test.com/3"},
    {"title": "Cloud credential theft AWS exposure", "risk_score": 7.5,
     "timestamp": (datetime.now(timezone.utc) - timedelta(days=4)).isoformat(),
     "stix_id": "indicator--004", "actor_tag": "UNC-CDB-99", "kev_present": False,
     "feed_source": "DarkReading", "mitre_tactics": ["T1078"], "ioc_counts": {}},
    {"title": "Low severity WordPress info disclosure", "risk_score": 2.0,
     "timestamp": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
     "stix_id": "indicator--005", "actor_tag": "UNC-CDB-INGEST", "kev_present": False,
     "feed_source": "CVEFeed", "mitre_tactics": [], "ioc_counts": {}},
]
def _m(): return MOCK

P = "agent.v43_genesis.genesis_engine._entries"

# G01
class TestSensorNetwork:
    @patch(P, side_effect=_m)
    def test_telemetry(self, m):
        from agent.v43_genesis.genesis_engine import GlobalCyberSensorNetwork
        r = GlobalCyberSensorNetwork().generate_telemetry()
        assert r["operated"] is False and r["sensors_operated"] == 0
        assert r["source_count"] == 4  # CISA, BleepingComputer, DarkReading, CVEFeed
        assert r["advisories_total"] == 5
        assert r["advisories_7d"] == 5 and r["advisories_24h"] == 0
        assert "sensor_count" not in r and "total_events_24h" not in r

# G02
class TestHoneypotGrid:
    @patch(P, side_effect=_m)
    def test_grid(self, m):
        from agent.v43_genesis.genesis_engine import HoneypotGrid
        r = HoneypotGrid().generate_grid_telemetry()
        assert r["operated"] is False and r["honeypots_operated"] == 0
        assert r["kev_confirmed"] == 2
        assert r["public_exploit_available"] == 1 and r["weaponized"] == 1
        assert r["epss_high"] == 2  # 85 and 90 read as percentages
        assert "honeypots" not in r and "total_captures_24h" not in r

# G03
class TestMalwareCloud:
    @patch(P, side_effect=_m)
    def test_analysis(self, m):
        from agent.v43_genesis.genesis_engine import MalwareAnalysisCloud
        r = MalwareAnalysisCloud().analyze_landscape()
        assert dict(r["top_families"]) == {"Lockbit": 1}
        assert r["malware_families_detected"] == 1
        assert "sandbox_config" not in r and "analysis_capabilities" not in r

# G04
class TestActorRegistry:
    @patch(P, side_effect=_m)
    def test_registry(self, m):
        from agent.v43_genesis.genesis_engine import ThreatActorIntelRegistry
        r = ThreatActorIntelRegistry().build_registry()
        names = {a["name"] for a in r["actors"]}
        assert names == {"APT28", "LockBit"}  # placeholders are not actors
        assert r["total_actors"] == 2 and r["known_actors"] == 2
        assert r["unattributed_advisories"] == 2
        apt28 = [a for a in r["actors"] if a["name"] == "APT28"]
        assert apt28[0]["observed_advisories"] == 2

# G05
class TestCampaignCorrelation:
    @patch(P, side_effect=_m)
    def test_correlate(self, m):
        from agent.v43_genesis.genesis_engine import CampaignCorrelationEngine
        r = CampaignCorrelationEngine().correlate()
        assert [c["actor"] for c in r["campaigns"]] == ["APT28"]
        assert r["total_campaigns"] == 1

# G06
class TestIOCReputation:
    @patch(P, side_effect=_m)
    def test_reputations(self, m):
        from agent.v43_genesis.genesis_engine import IOCReputationEngine
        r = IOCReputationEngine().compute_reputations()
        assert r["total_iocs_scored"] == 2 and r["kev_cves"] == 2
        assert r["ioc_types_scored"] == ["cve"]

# G07
class TestAutoDetection:
    @patch(P, side_effect=_m)
    def test_pack(self, m):
        from agent.v43_genesis.genesis_engine import AutoDetectionGenerator
        r = AutoDetectionGenerator().generate_full_pack()
        assert r["stats"]["total_rules"] == 3  # only rules attached to items
        assert (r["sigma_count"], r["kql_count"], r["suricata_count"], r["yara_count"]) == (1, 1, 1, 0)
        assert r["advisories_with_detections"] == 1
        assert r["high_risk_without_detections"] == 3

# G08
class TestTAXII:
    @patch(P, side_effect=_m)
    def test_config(self, m):
        from agent.v43_genesis.genesis_engine import TAXIIServer
        r = TAXIIServer().generate_server_config()
        assert r["taxii_server"]["version"] == "2.1"
        assert r["taxii_server"]["discovery"] == "/taxii/"
        assert [c["id"] for c in r["collections"]] == ["sentinel-apex-main", "sentinel-apex-kev"]
        assert r["collection_count"] == 2
        assert "rest_api" not in r

# G09
class TestDarkWeb:
    @patch(P, side_effect=_m)
    def test_report(self, m):
        from agent.v43_genesis.genesis_engine import DarkWebIntelligence
        r = DarkWebIntelligence().generate_darkweb_report()
        assert r["operated"] is False and r["sources_monitored"] == 0 and r["source_count"] == 0
        assert r["ransomware_advisories"] == 1 and r["leak_or_credential_advisories"] == 1
        assert r["relevant_advisories"] == 2
        assert "monitored_sources" not in r and "monitoring_capabilities" not in r

# G10
class TestAttackSurface:
    @patch(P, side_effect=_m)
    def test_exposure(self, m):
        from agent.v43_genesis.genesis_engine import AttackSurfaceIntelligence
        r = AttackSurfaceIntelligence().analyze_exposure()
        assert r["critical_exposures"] == 1  # "Critical RCE"
        assert "scan_capabilities" not in r

# G11
class TestAttackMap:
    @patch(P, side_effect=_m)
    def test_map(self, m):
        from agent.v43_genesis.genesis_engine import GlobalAttackMap
        r = GlobalAttackMap().generate_map_data()
        assert r["total_flows"] == 0 and r["attack_flows"] == []
        assert r["attributed_advisories"] == 0 and r["unattributed_advisories"] == 5

    def test_attribution_uses_actor_country_only(self):
        from agent.v43_genesis.genesis_engine import GlobalAttackMap
        r = GlobalAttackMap().generate_map_data([{"actor_country": "Russia"}, {"actor_country": "Unknown"}, {}])
        assert r["origin_countries"] == {"Russia": 1} and r["total_flows"] == 0

# G12
class TestAIHunter:
    @patch(P, side_effect=_m)
    def test_hunt(self, m):
        from agent.v43_genesis.genesis_engine import AIThreatHuntingEngine
        r = AIThreatHuntingEngine().execute_hunt()
        assert "threat_clusters" in r
        assert "emerging_predictions" in r
        assert r["clusters_identified"] == len(r["threat_clusters"])

# ORCHESTRATOR
class TestOrchestrator:
    @patch(P, side_effect=_m)
    @patch("agent.v43_genesis.genesis_engine._save", return_value=True)
    def test_full_cycle(self, ms, me):
        from agent.v43_genesis.genesis_engine import GenesisOrchestrator
        r = GenesisOrchestrator().execute_full_cycle()
        assert r["version"] == "43.1.0"
        assert r["engines_ok"] == 12
        assert r["engines_total"] == 12
        assert r["execution_time_ms"] > 0
        assert r["items_analyzed"] == 5

    def test_compute_takes_items_and_is_deterministic(self):
        from agent.v43_genesis.genesis_engine import GenesisOrchestrator
        a, _ = GenesisOrchestrator().compute(MOCK)
        b, _ = GenesisOrchestrator().compute(MOCK)
        strip = lambda r: {k: {kk: vv for kk, vv in v["summary"].items() if not kk.endswith("_id") and kk != "generated_at"}
                           for k, v in r["engines"].items()}
        assert strip(a) == strip(b)

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
