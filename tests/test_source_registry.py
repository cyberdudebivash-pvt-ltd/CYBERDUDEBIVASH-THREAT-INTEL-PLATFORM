"""
tests/test_source_registry.py — CyberDudeBivash SENTINEL APEX
Unit + contract tests for the P40 Global Intelligence Source Fabric's
canonical Source Registry (scripts/source_registry.py,
scripts/build_source_registry.py).
"""
import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import source_registry as sr  # noqa: E402


def _minimal_valid_entry(**overrides):
    entry = {
        "source_id": "test_source",
        "canonical_name": "Test Source",
        "provider": "Test Provider",
        "description": "A test source.",
        "intelligence_domains": ["vulnerability"],
        "source_type": "GOVERNMENT_AUTHORITATIVE",
        "authority_level": "GOVERNMENT_AUTHORITATIVE",
        "geographic_scope": "GLOBAL",
        "sector_scope": ["ALL"],
        "access_type": "PUBLIC_FREE",
        "protocol": "REST_JSON",
        "authentication_type": "NONE",
        "polling_interval": "1h",
        "pagination_strategy": "NONE",
        "incremental_cursor_strategy": "PUBLISHED_TIMESTAMP",
        "response_format": "JSON",
        "licensing_class": "PUBLIC_DOMAIN",
        "redistribution_allowed": True,
        "commercial_use_allowed": True,
        "attribution_required": False,
        "retention_policy": "INDEFINITE",
        "freshness_expectation": "DAILY",
        "reliability_score": 95,
        "quality_score": 90,
        "default_confidence": 90,
        "enabled": True,
        "priority": 1,
        "criticality": "HIGH",
        "health_status": "HEALTHY",
        "records_received": 10,
        "records_accepted": 10,
        "records_rejected": 0,
        "records_deduplicated": 0,
        "implementation_status": "ACTIVE",
        "wave": 1,
        "integration_mode": "EVENT_STREAM",
        "pipeline_feed_source_key": "test_source",
    }
    entry.update(overrides)
    return entry


def _registry_of(*entries):
    return {"registry_version": "1.0.0", "sources": list(entries)}


# --- Real, checked-in registry contract tests -------------------------------

class TestRealRegistry:
    """Runs against the actual generated data/registry/source_registry.json."""

    def test_registry_loads(self):
        reg = sr.load_registry(force_reload=True)
        assert reg["total_sources"] > 0
        assert len(reg["sources"]) == reg["total_sources"]

    def test_registry_has_no_validation_errors(self):
        errors = sr.validate_registry()
        assert errors == [], f"Registry has {len(errors)} validation error(s): {errors}"

    def test_registry_covers_all_five_waves(self):
        reg = sr.load_registry(force_reload=True)
        waves = {s["wave"] for s in reg["sources"]}
        assert waves == {1, 2, 3, 4, 5}

    def test_at_least_one_source_is_active(self):
        active = sr.sources_by_status("ACTIVE")
        assert len(active) >= 1

    def test_no_source_ids_duplicated(self):
        reg = sr.load_registry(force_reload=True)
        ids = [s["source_id"] for s in reg["sources"]]
        assert len(ids) == len(set(ids))

    def test_free_noncommercial_sources_are_not_commercially_usable(self):
        """Regression guard for the licensing bug found and fixed during the
        P40 build: FREE_NONCOMMERCIAL/INTERNAL_USE_ONLY sources must never
        default to commercial_use_allowed=True."""
        reg = sr.load_registry(force_reload=True)
        for s in reg["sources"]:
            if s["licensing_class"] in ("FREE_NONCOMMERCIAL", "INTERNAL_USE_ONLY"):
                assert s["commercial_use_allowed"] is False, (
                    f"{s['source_id']}: licensing_class={s['licensing_class']} but "
                    f"commercial_use_allowed=True"
                )

    def test_non_live_sources_have_no_fabricated_health(self):
        """No-fake-integrations contract: a source that isn't ACTIVE/IMPLEMENTED
        cannot claim HEALTHY status or a nonzero reliability score."""
        reg = sr.load_registry(force_reload=True)
        for s in reg["sources"]:
            if s["implementation_status"] not in ("ACTIVE", "IMPLEMENTED"):
                assert s["health_status"] != "HEALTHY"
                assert s["reliability_score"] == 0
                assert s["enabled"] is False

    def test_get_source_known_id(self):
        assert sr.get_source("cisa_kev") is not None
        assert sr.get_source("nvd_cve")["implementation_status"] == "ACTIVE"

    def test_get_source_unknown_id_returns_none(self):
        assert sr.get_source("definitely_not_a_real_source_id") is None

    def test_domain_coverage_shape(self):
        coverage = sr.domain_coverage()
        assert "vulnerability" in coverage
        assert isinstance(coverage["vulnerability"], dict)

    def test_licensing_summary_totals_consistent(self):
        summary = sr.licensing_summary()
        assert summary["redistribution_allowed"] + summary["redistribution_restricted"] == summary["total"]


# --- Validator unit tests (isolated fixture registries, not the real file) --

class TestValidateRegistryUnit:
    def test_valid_minimal_registry_has_no_errors(self):
        reg = _registry_of(_minimal_valid_entry())
        assert sr.validate_registry(reg) == []

    def test_duplicate_source_id_detected(self):
        reg = _registry_of(_minimal_valid_entry(), _minimal_valid_entry())
        errors = sr.validate_registry(reg)
        assert any("duplicate" in e.lower() for e in errors)

    def test_missing_required_field_detected(self):
        entry = _minimal_valid_entry()
        del entry["canonical_name"]
        reg = _registry_of(entry)
        errors = sr.validate_registry(reg)
        assert any("canonical_name" in e for e in errors)

    def test_invalid_implementation_status_detected(self):
        reg = _registry_of(_minimal_valid_entry(implementation_status="TOTALLY_MADE_UP"))
        errors = sr.validate_registry(reg)
        assert any("invalid implementation_status" in e for e in errors)

    def test_planned_source_claiming_healthy_is_rejected(self):
        reg = _registry_of(_minimal_valid_entry(
            implementation_status="PLANNED", enabled=False,
            health_status="HEALTHY", reliability_score=0,
        ))
        errors = sr.validate_registry(reg)
        assert any("HEALTHY" in e for e in errors)

    def test_planned_source_with_nonzero_reliability_is_rejected(self):
        reg = _registry_of(_minimal_valid_entry(
            implementation_status="PLANNED", enabled=False,
            health_status="NOT_APPLICABLE", reliability_score=42,
        ))
        errors = sr.validate_registry(reg)
        assert any("reliability_score" in e for e in errors)

    def test_planned_source_enabled_true_is_rejected(self):
        reg = _registry_of(_minimal_valid_entry(
            implementation_status="PLANNED", enabled=True,
            health_status="NOT_APPLICABLE", reliability_score=0,
        ))
        errors = sr.validate_registry(reg)
        assert any("enabled=true" in e for e in errors)

    def test_active_source_not_enabled_is_rejected(self):
        reg = _registry_of(_minimal_valid_entry(implementation_status="ACTIVE", enabled=False))
        errors = sr.validate_registry(reg)
        assert any("enabled=false" in e for e in errors)

    def test_wave_out_of_range_is_rejected(self):
        reg = _registry_of(_minimal_valid_entry(wave=9))
        errors = sr.validate_registry(reg)
        assert any("wave must be 1-5" in e for e in errors)

    def test_free_noncommercial_flagged_commercial_is_rejected(self):
        reg = _registry_of(_minimal_valid_entry(
            licensing_class="FREE_NONCOMMERCIAL", commercial_use_allowed=True,
        ))
        errors = sr.validate_registry(reg)
        assert any("licensing governance violation" in e for e in errors)

    def test_empty_registry_is_rejected(self):
        errors = sr.validate_registry({"sources": []})
        assert errors == ["registry has zero sources"]
