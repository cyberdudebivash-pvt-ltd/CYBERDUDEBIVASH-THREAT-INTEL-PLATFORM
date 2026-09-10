#!/usr/bin/env python3
"""
test_v40_v41_v42_modules.py — Test Suite for CORTEX, QUANTUM, SOVEREIGN
=========================================================================
Zero regression: Tests only v40-v42 modules, never modifies existing tests.
"""

import json, os, sys, pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MOCK_ENTRIES = [
    {"title": "CVE-2026-1234 — Critical RCE in Apache Struts by APT28", "risk_score": 9.5,
     "timestamp": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
     "stix_id": "indicator--test-001", "actor_tag": "APT28", "kev_present": True,
     "supply_chain": False, "epss_score": 85, "cvss_score": 9.8, "confidence_score": 90,
     "feed_source": "CISA", "blog_url": "https://test.com/1",
     "mitre_tactics": ["T1190", "T1059", "T1071"], "ioc_counts": {"domain": 5, "ipv4": 12}},
    {"title": "Ransomware LockBit targets financial sector", "risk_score": 8.2,
     "timestamp": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
     "stix_id": "indicator--test-002", "actor_tag": "LockBit", "kev_present": False,
     "supply_chain": False, "epss_score": 45, "cvss_score": 7.5, "confidence_score": 75,
     "feed_source": "BleepingComputer", "blog_url": "https://test.com/2",
     "mitre_tactics": ["T1566", "T1486"], "ioc_counts": {"domain": 8}},
    {"title": "CVE-2026-5678 — Zero-day in Cisco by APT28", "risk_score": 9.0,
     "timestamp": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
     "stix_id": "indicator--test-003", "actor_tag": "APT28", "kev_present": True,
     "supply_chain": False, "epss_score": 90, "cvss_score": 9.5, "confidence_score": 88,
     "feed_source": "CISA", "blog_url": "https://test.com/3",
     "mitre_tactics": ["T1190", "T1068", "T1573"], "ioc_counts": {"ipv4": 20}},
    {"title": "Cloud credential theft targeting AWS", "risk_score": 7.5,
     "timestamp": (datetime.now(timezone.utc) - timedelta(days=4)).isoformat(),
     "stix_id": "indicator--test-004", "actor_tag": "UNC-CDB-99", "kev_present": False,
     "supply_chain": False, "epss_score": 30, "cvss_score": 6.5, "confidence_score": 60,
     "feed_source": "DarkReading", "mitre_tactics": ["T1078"], "ioc_counts": {}},
    {"title": "Low severity info disclosure", "risk_score": 2.0,
     "timestamp": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
     "stix_id": "indicator--test-005", "actor_tag": "", "kev_present": False,
     "supply_chain": False, "epss_score": 3, "cvss_score": 2.1, "confidence_score": 20,
     "feed_source": "CVEFeed", "mitre_tactics": [], "ioc_counts": {}},
]

def _mock_entries():
    return MOCK_ENTRIES


# ═══════════════════════════════════════════════════════════════════════════════
# v40 CORTEX TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntelFirehose:
    @patch("agent.v40_cortex.cortex_engine._entries", side_effect=_mock_entries)
    def test_generate_stream(self, mock):
        from agent.v40_cortex.cortex_engine import IntelFirehose
        fh = IntelFirehose()
        stream = fh.generate_stream(since_hours=168)
        assert "metadata" in stream
        assert "events" in stream
        assert stream["metadata"]["total_events"] > 0

    @patch("agent.v40_cortex.cortex_engine._entries", side_effect=_mock_entries)
    def test_stream_channels(self, mock):
        from agent.v40_cortex.cortex_engine import IntelFirehose
        fh = IntelFirehose()
        stream = fh.generate_stream(since_hours=168)
        channels = stream["metadata"]["channels"]
        assert "threat-intel" in channels
        assert channels["threat-intel"] > 0

    def test_websocket_config(self):
        from agent.v40_cortex.cortex_engine import IntelFirehose
        fh = IntelFirehose()
        config = fh.get_websocket_config()
        assert "server" in config
        assert "channels" in config
        assert config["server"]["protocol"] == "wss"

    @patch("agent.v40_cortex.cortex_engine._entries")
    def test_generate_stream_skips_non_dict_entries(self, mock):
        # P0 regression: production manifest data has contained non-dict
        # list items interleaved with valid entries, which previously crashed
        # generate_stream() with "'list' object has no attribute 'get'"
        # (live prod: "[CORTEX-C1] Firehose failed: 'list' object has no
        # attribute 'get'"). Malformed items must be skipped, not fatal.
        mock.return_value = [MOCK_ENTRIES[0], ["not", "a", "dict"], MOCK_ENTRIES[1]]
        from agent.v40_cortex.cortex_engine import IntelFirehose
        fh = IntelFirehose()
        stream = fh.generate_stream(since_hours=168)
        assert "metadata" in stream
        assert stream["metadata"]["total_events"] > 0

    @patch("agent.v40_cortex.cortex_engine._entries")
    def test_generate_stream_empty_entries_shape(self, mock):
        # P0 regression: this is the exact live prod bug -- live prod hit
        # "[CORTEX-C1] Firehose failed: 'list' object has no attribute
        # 'get'". Root cause: generate_stream() returned a bare [] on empty
        # entries, but CortexOrchestrator.execute_full_cycle() unconditionally
        # calls stream.get("metadata", {}) on the result. The empty-entries
        # shape must match the full-computation dict shape.
        mock.return_value = []
        from agent.v40_cortex.cortex_engine import IntelFirehose
        fh = IntelFirehose()
        stream = fh.generate_stream(since_hours=168)
        assert isinstance(stream, dict)
        assert stream.get("metadata", {}).get("total_events") == 0
        assert stream["events"] == []

    @patch("agent.v40_cortex.cortex_engine._entries")
    def test_generate_stream_skips_malformed_mitre_tactics_items(self, mock):
        # P0 regression: an mitre_tactics item that is neither a str nor a
        # dict (e.g. a nested list) must not crash technique extraction.
        entry = dict(MOCK_ENTRIES[0])
        entry["mitre_tactics"] = ["T1190", ["nested", "list"], {"technique_id": "T1059"}, 42]
        mock.return_value = [entry]
        from agent.v40_cortex.cortex_engine import IntelFirehose
        fh = IntelFirehose()
        stream = fh.generate_stream(since_hours=168)
        assert stream["metadata"]["total_events"] > 0
        techniques = stream["events"][0]["payload"]["techniques"]
        assert techniques == ["T1190", "T1059"]


class TestCortexOrchestrator:
    @patch("agent.v40_cortex.cortex_engine._entries")
    def test_full_cycle_with_empty_manifest_never_raises(self, mock, tmp_path, monkeypatch):
        # P0 regression: reproduces the exact live production scenario --
        # an empty/missing manifest (data/stix/feed_manifest.json absent)
        # drove IntelFirehose.generate_stream() down its empty-entries path,
        # and the orchestrator's unconditional stream.get("metadata", {})
        # turned that into a silently-caught AttributeError every cycle
        # (results["stream"] defaulted to {}). After the fix, the full cycle
        # must populate real (zero-valued but correctly shaped) results.
        import agent.v40_cortex.cortex_engine as ce
        monkeypatch.setattr(ce, "CORTEX_DIR", str(tmp_path))
        mock.return_value = []
        orch = ce.CortexOrchestrator()
        results = orch.execute_full_cycle()
        assert results["stream"] != {}
        assert results["stream"]["total_events"] == 0


class TestThreatKnowledgeGraph:
    @patch("agent.v40_cortex.cortex_engine._entries", side_effect=_mock_entries)
    def test_build_graph(self, mock):
        from agent.v40_cortex.cortex_engine import ThreatKnowledgeGraph
        g = ThreatKnowledgeGraph()
        stats = g.build_graph()
        assert stats["total_nodes"] > 0
        assert stats["total_edges"] > 0

    @patch("agent.v40_cortex.cortex_engine._entries", side_effect=_mock_entries)
    def test_get_neighbors(self, mock):
        from agent.v40_cortex.cortex_engine import ThreatKnowledgeGraph
        g = ThreatKnowledgeGraph()
        g.build_graph()
        # Get neighbors of APT28
        result = g.get_neighbors("actor--apt28", max_depth=1)
        assert "neighbors" in result
        assert len(result["neighbors"]) > 0

    @patch("agent.v40_cortex.cortex_engine._entries", side_effect=_mock_entries)
    def test_export_graph(self, mock):
        from agent.v40_cortex.cortex_engine import ThreatKnowledgeGraph
        g = ThreatKnowledgeGraph()
        g.build_graph()
        export = g.export_graph()
        assert "nodes" in export
        assert "edges" in export
        assert len(export["nodes"]) > 0

    @patch("agent.v40_cortex.cortex_engine._entries", side_effect=_mock_entries)
    def test_entity_report(self, mock):
        from agent.v40_cortex.cortex_engine import ThreatKnowledgeGraph
        g = ThreatKnowledgeGraph()
        g.build_graph()
        report = g.get_entity_report("actor--apt28")
        assert "centrality_score" in report
        assert "connection_count" in report


class TestNaturalLanguageQuery:
    @patch("agent.v40_cortex.cortex_engine._entries", side_effect=_mock_entries)
    def test_process_actor_query(self, mock):
        from agent.v40_cortex.cortex_engine import NaturalLanguageQueryEngine, ThreatKnowledgeGraph
        g = ThreatKnowledgeGraph()
        g.build_graph()
        nlq = NaturalLanguageQueryEngine()
        result = nlq.process_query("Show all APT28 activity", g)
        assert result["results"]["count"] > 0

    @patch("agent.v40_cortex.cortex_engine._entries", side_effect=_mock_entries)
    def test_severity_filter_query(self, mock):
        from agent.v40_cortex.cortex_engine import NaturalLanguageQueryEngine, ThreatKnowledgeGraph
        g = ThreatKnowledgeGraph()
        g.build_graph()
        nlq = NaturalLanguageQueryEngine()
        result = nlq.process_query("Find all critical threats", g)
        assert result["results"]["count"] > 0

    @patch("agent.v40_cortex.cortex_engine._entries", side_effect=_mock_entries)
    def test_count_query(self, mock):
        from agent.v40_cortex.cortex_engine import NaturalLanguageQueryEngine, ThreatKnowledgeGraph
        g = ThreatKnowledgeGraph()
        nlq = NaturalLanguageQueryEngine()
        result = nlq.process_query("How many advisories are tracked", g)
        assert result["results"]["count"] == len(MOCK_ENTRIES)


class TestRelationshipExplorer:
    @patch("agent.v40_cortex.cortex_engine._entries", side_effect=_mock_entries)
    def test_attack_corridors(self, mock):
        from agent.v40_cortex.cortex_engine import ThreatKnowledgeGraph, RelationshipExplorer
        g = ThreatKnowledgeGraph()
        g.build_graph()
        exp = RelationshipExplorer(g)
        corridors = exp.find_attack_corridors()
        assert isinstance(corridors, list)

    @patch("agent.v40_cortex.cortex_engine._entries", side_effect=_mock_entries)
    def test_influence_scores(self, mock):
        from agent.v40_cortex.cortex_engine import ThreatKnowledgeGraph, RelationshipExplorer
        g = ThreatKnowledgeGraph()
        g.build_graph()
        exp = RelationshipExplorer(g)
        scores = exp.compute_influence_scores()
        assert isinstance(scores, list)
        assert len(scores) > 0
        assert "influence_score" in scores[0]

    @patch("agent.v40_cortex.cortex_engine._entries", side_effect=_mock_entries)
    def test_cluster_analysis(self, mock):
        from agent.v40_cortex.cortex_engine import ThreatKnowledgeGraph, RelationshipExplorer
        g = ThreatKnowledgeGraph()
        g.build_graph()
        exp = RelationshipExplorer(g)
        clusters = exp.get_cluster_analysis()
        assert "total_clusters" in clusters


# ═══════════════════════════════════════════════════════════════════════════════
# v41 QUANTUM TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnomalyDetector:
    @patch("agent.v41_quantum.quantum_engine._entries")
    def test_detect_anomalies(self, mock):
        # Need 10+ entries for anomaly detection
        expanded = MOCK_ENTRIES * 3  # 15 entries
        mock.return_value = expanded
        from agent.v41_quantum.quantum_engine import AnomalyDetector
        d = AnomalyDetector()
        result = d.detect_anomalies()
        assert "anomaly_count" in result
        assert "overall_anomaly_score" in result
        assert "baseline_stats" in result

    @patch("agent.v41_quantum.quantum_engine._entries")
    def test_baselines_computed(self, mock):
        expanded = MOCK_ENTRIES * 3
        mock.return_value = expanded
        from agent.v41_quantum.quantum_engine import AnomalyDetector
        d = AnomalyDetector()
        result = d.detect_anomalies()
        stats = result["baseline_stats"]
        assert "risk_mean" in stats
        assert stats["total_entries"] == len(expanded)

    @patch("agent.v41_quantum.quantum_engine._entries")
    def test_detect_anomalies_insufficient_data_shape(self, mock):
        # P0 regression: live prod hit "[QUANTUM-Q1] Anomaly detection
        # failed: 'anomaly_count'" because the <10-entries early return
        # omitted keys the orchestrator unconditionally indexes. The
        # early-return shape must match the full-computation shape.
        mock.return_value = MOCK_ENTRIES[:3]  # < 10 entries
        from agent.v41_quantum.quantum_engine import AnomalyDetector
        d = AnomalyDetector()
        result = d.detect_anomalies()
        assert result["anomaly_count"] == 0
        assert result["overall_anomaly_score"] == 0
        assert result["anomalies"] == []
        assert "baseline_stats" in result
        assert "analyzed_at" in result


class TestAdversarialFeedGuard:
    @patch("agent.v41_quantum.quantum_engine._entries", side_effect=_mock_entries)
    def test_analyze_feeds(self, mock):
        from agent.v41_quantum.quantum_engine import AdversarialFeedGuard
        g = AdversarialFeedGuard()
        result = g.analyze_feeds()
        assert "feed_scores" in result
        assert "overall_trust" in result
        assert result["feed_count"] > 0

    @patch("agent.v41_quantum.quantum_engine._entries")
    def test_analyze_feeds_empty_shape(self, mock):
        # P0 regression: live prod hit "[QUANTUM-Q2] Feed guard failed:
        # 'overall_trust'" because the empty-entries early return omitted
        # the key the orchestrator unconditionally indexes.
        mock.return_value = []
        from agent.v41_quantum.quantum_engine import AdversarialFeedGuard
        g = AdversarialFeedGuard()
        result = g.analyze_feeds()
        assert result["overall_trust"] == 0
        assert result["feed_count"] == 0
        assert result["alerts"] == []


class TestFalsePositiveReducer:
    @patch("agent.v41_quantum.quantum_engine._entries", side_effect=_mock_entries)
    def test_analyze(self, mock):
        from agent.v41_quantum.quantum_engine import FalsePositiveReducer
        r = FalsePositiveReducer()
        result = r.analyze()
        assert "entries_analyzed" in result
        assert result["entries_analyzed"] == len(MOCK_ENTRIES)
        assert "estimated_fp_rate_pct" in result

    @patch("agent.v41_quantum.quantum_engine._entries")
    def test_analyze_empty_shape(self, mock):
        # P0 regression: live prod hit "[QUANTUM-Q3] FP reduction failed:
        # 'estimated_fp_rate_pct'" because the empty-entries early return
        # omitted the key the orchestrator unconditionally indexes.
        mock.return_value = []
        from agent.v41_quantum.quantum_engine import FalsePositiveReducer
        r = FalsePositiveReducer()
        result = r.analyze()
        assert result["estimated_fp_rate_pct"] == 0
        assert result["fp_candidate_count"] == 0


class TestDetectionABTester:
    @patch("agent.v41_quantum.quantum_engine._entries", side_effect=_mock_entries)
    def test_generate_experiments(self, mock):
        from agent.v41_quantum.quantum_engine import DetectionABTester
        t = DetectionABTester()
        result = t.generate_experiments()
        assert "experiments" in result
        assert result["total_experiments"] > 0
        assert "variant_a" in result["experiments"][0]
        assert "variant_b" in result["experiments"][0]

    @patch("agent.v41_quantum.quantum_engine._entries")
    def test_generate_experiments_no_high_risk_shape(self, mock):
        # P0 regression: live prod hit "[QUANTUM-Q4] A/B testing failed:
        # 'total_experiments'" because the no-high-risk-entries early
        # return omitted the key the orchestrator unconditionally indexes.
        mock.return_value = [e for e in MOCK_ENTRIES if e["risk_score"] < 7]
        from agent.v41_quantum.quantum_engine import DetectionABTester
        t = DetectionABTester()
        result = t.generate_experiments()
        assert result["total_experiments"] == 0
        assert result["experiments"] == []
        assert "framework_config" in result


class TestQuantumOrchestrator:
    @patch("agent.v41_quantum.quantum_engine._entries")
    def test_full_cycle_with_sparse_data_never_keyerrors(self, mock, tmp_path, monkeypatch):
        # P0 regression: reproduces the exact live production scenario —
        # a sparse manifest (< 10 entries, as NEXUS/CORTEX starvation
        # caused) drove all four QUANTUM sub-engines down their
        # inconsistent-shape early-return path simultaneously, and the
        # orchestrator's direct key indexing turned that into 4 silently
        # caught KeyErrors every single cycle (results defaulted to {}).
        # After the fix, the full cycle must populate real (zero-valued
        # but correctly shaped) results with no exception swallowed.
        import agent.v41_quantum.quantum_engine as qe
        monkeypatch.setattr(qe, "QUANTUM_DIR", str(tmp_path))
        mock.return_value = MOCK_ENTRIES[:3]  # sparse: < 10 entries, no high-risk A/B subset issue
        orch = qe.QuantumOrchestrator()
        results = orch.execute_full_cycle()
        assert results["anomalies"] != {}
        assert results["feed_trust"] != {}
        assert results["false_positives"] != {}
        assert results["ab_tests"] != {}
        assert results["anomalies"]["count"] == 0
        assert results["feed_trust"]["overall"] >= 0


# ═══════════════════════════════════════════════════════════════════════════════
# v42 SOVEREIGN TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestTenantManager:
    def test_create_tenant(self):
        from agent.v42_sovereign.sovereign_engine import TenantManager
        with patch("agent.v42_sovereign.sovereign_engine._load", return_value=None), \
             patch("agent.v42_sovereign.sovereign_engine._save", return_value=True):
            tm = TenantManager()
            result = tm.create_tenant("Test Corp", "pro", "admin@test.com")
            assert "tenant_id" in result
            assert "api_key" in result
            assert result["tier"] == "pro"

    def test_check_access_allowed(self):
        from agent.v42_sovereign.sovereign_engine import TenantManager, Tenant
        with patch("agent.v42_sovereign.sovereign_engine._load", return_value=None), \
             patch("agent.v42_sovereign.sovereign_engine._save", return_value=True):
            tm = TenantManager()
            tm.create_tenant("Enterprise Corp", "enterprise", "admin@ent.com")
            tid = list(tm.tenants.keys())[0]
            result = tm.check_access(tid, "executive_briefings")
            assert result["allowed"] is True

    def test_check_access_denied(self):
        from agent.v42_sovereign.sovereign_engine import TenantManager
        with patch("agent.v42_sovereign.sovereign_engine._load", return_value=None), \
             patch("agent.v42_sovereign.sovereign_engine._save", return_value=True):
            tm = TenantManager()
            tm.create_tenant("Free Corp", "free", "admin@free.com")
            tid = list(tm.tenants.keys())[0]
            result = tm.check_access(tid, "executive_briefings")
            assert result["allowed"] is False


class TestBillingEngine:
    def test_compute_mrr(self):
        from agent.v42_sovereign.sovereign_engine import BillingEngine, Tenant
        be = BillingEngine()
        tenants = {
            "t1": Tenant(tenant_id="t1", org_name="Pro Corp", tier="pro"),
            "t2": Tenant(tenant_id="t2", org_name="Ent Corp", tier="enterprise"),
            "t3": Tenant(tenant_id="t3", org_name="Free Corp", tier="free"),
        }
        mrr = be.compute_mrr(tenants)
        assert mrr["total_mrr"] == 49 + 499  # pro + enterprise
        assert mrr["arr"] == (49 + 499) * 12

    def test_stripe_config(self):
        from agent.v42_sovereign.sovereign_engine import BillingEngine
        be = BillingEngine()
        config = be.get_stripe_config()
        assert "stripe_integration" in config
        assert "products" in config["stripe_integration"]


class TestComplianceAutomation:
    @patch("agent.v42_sovereign.sovereign_engine._entries", side_effect=_mock_entries)
    def test_soc2_report(self, mock):
        from agent.v42_sovereign.sovereign_engine import ComplianceAutomation
        ca = ComplianceAutomation()
        report = ca.generate_compliance_report("SOC2")
        assert report["compliance_score_pct"] > 0
        assert report["total_controls"] == 10
        assert report["framework"] == "SOC2"

    @patch("agent.v42_sovereign.sovereign_engine._entries", side_effect=_mock_entries)
    def test_nist_report(self, mock):
        from agent.v42_sovereign.sovereign_engine import ComplianceAutomation
        ca = ComplianceAutomation()
        report = ca.generate_compliance_report("NIST_CSF")
        assert report["compliance_score_pct"] > 0


class TestOnboardingPortal:
    def test_generate_flow(self):
        from agent.v42_sovereign.sovereign_engine import OnboardingPortal
        op = OnboardingPortal()
        flow = op.generate_onboarding_flow("Demo Corp", "enterprise")
        assert flow["total_steps"] == 8
        assert "quick_start_guide" in flow
        assert "integration_templates" in flow


class TestWhiteLabelEngine:
    def test_generate_config(self):
        from agent.v42_sovereign.sovereign_engine import WhiteLabelEngine
        wl = WhiteLabelEngine()
        config = wl.generate_whitelabel_config("TestMSSP", "intel.testmssp.com")
        assert config["mssp_name"] == "TestMSSP"
        assert config["branding"]["domain"] == "intel.testmssp.com"
        assert "dns_config" in config
        assert "sub_tenant_management" in config


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
