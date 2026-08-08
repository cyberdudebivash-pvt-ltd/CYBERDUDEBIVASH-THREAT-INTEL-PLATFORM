#!/usr/bin/env python3
"""
scripts/source_registry.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Global Intelligence Source Fabric (P40.0)
Source Registry loader, query helpers, and integrity validator.

This is the ONLY module that reads data/registry/source_registry.json at
runtime. Every consumer -- scripts/true_intel_ingestor.py (registry-driven
new sources), scripts/source_fabric_health.py, scripts/p40_production_
certification.py -- imports from here rather than re-parsing the JSON
independently. Single source of truth for the loading/query contract
(mission Principle 3).

Usage:
    from source_registry import load_registry, get_source, sources_by_status

    reg = load_registry()
    kev = get_source("cisa_kev")
    live = sources_by_status("ACTIVE")

CLI:
    python3 scripts/source_registry.py --validate   # integrity check, exit 1 on failure
    python3 scripts/source_registry.py --summary     # human-readable breakdown
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "data" / "registry" / "source_registry.json"

_VALID_STATUSES = {
    "ACTIVE", "IMPLEMENTED", "REQUIRES_CREDENTIALS",
    "REQUIRES_LICENSE", "PLANNED", "DISABLED",
}
_REQUIRED_FIELDS = (
    "source_id", "canonical_name", "provider", "description",
    "intelligence_domains", "source_type", "authority_level",
    "geographic_scope", "sector_scope", "access_type", "protocol",
    "authentication_type", "polling_interval", "pagination_strategy",
    "incremental_cursor_strategy", "response_format", "licensing_class",
    "redistribution_allowed", "commercial_use_allowed", "attribution_required",
    "retention_policy", "freshness_expectation", "reliability_score",
    "quality_score", "default_confidence", "enabled", "priority",
    "criticality", "health_status", "records_received", "records_accepted",
    "records_rejected", "records_deduplicated", "implementation_status",
    "wave", "integration_mode",
)

_cache: Optional[Dict[str, Any]] = None


def load_registry(force_reload: bool = False) -> Dict[str, Any]:
    """Load the canonical source registry. Cached in-process after first call."""
    global _cache
    if _cache is not None and not force_reload:
        return _cache
    if not REGISTRY_PATH.exists():
        raise FileNotFoundError(
            f"Source registry not found at {REGISTRY_PATH}. "
            f"Run: python3 scripts/build_source_registry.py"
        )
    _cache = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return _cache


def all_sources() -> List[Dict[str, Any]]:
    return load_registry()["sources"]


def get_source(source_id: str) -> Optional[Dict[str, Any]]:
    for s in all_sources():
        if s["source_id"] == source_id:
            return s
    return None


def sources_by_status(status: str) -> List[Dict[str, Any]]:
    return [s for s in all_sources() if s["implementation_status"] == status]


def sources_by_wave(wave: int) -> List[Dict[str, Any]]:
    return [s for s in all_sources() if s["wave"] == wave]


def sources_by_domain(domain: str) -> List[Dict[str, Any]]:
    return [s for s in all_sources() if domain in s["intelligence_domains"]]


def live_sources() -> List[Dict[str, Any]]:
    """Sources with enabled=True (actually scheduled today)."""
    return [s for s in all_sources() if s.get("enabled")]


def domain_coverage() -> Dict[str, Dict[str, int]]:
    """Per-domain count of sources by implementation_status -- feeds the
    Section 25/26 coverage dashboards."""
    out: Dict[str, Dict[str, int]] = {}
    for s in all_sources():
        for d in s["intelligence_domains"]:
            bucket = out.setdefault(d, {})
            bucket[s["implementation_status"]] = bucket.get(s["implementation_status"], 0) + 1
    return out


def licensing_summary() -> Dict[str, Any]:
    """Redistribution/commercial-use governance rollup (mission Section 23)."""
    sources = all_sources()
    return {
        "total": len(sources),
        "redistribution_allowed": sum(1 for s in sources if s["redistribution_allowed"]),
        "redistribution_restricted": sum(1 for s in sources if not s["redistribution_allowed"]),
        "commercial_use_allowed": sum(1 for s in sources if s["commercial_use_allowed"]),
        "attribution_required": sum(1 for s in sources if s["attribution_required"]),
        "by_licensing_class": _count_by(sources, "licensing_class"),
    }


def _count_by(sources: List[Dict[str, Any]], field: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for s in sources:
        out[s[field]] = out.get(s[field], 0) + 1
    return out


def validate_registry(registry: Optional[Dict[str, Any]] = None) -> List[str]:
    """Integrity + honesty-contract validation. Returns a list of error
    strings (empty list == valid). Never raises -- callers decide severity."""
    reg = registry or load_registry()
    errors: List[str] = []
    seen_ids = set()

    sources = reg.get("sources", [])
    if not sources:
        errors.append("registry has zero sources")
        return errors

    for s in sources:
        sid = s.get("source_id", "<missing source_id>")

        if s.get("source_id") in seen_ids:
            errors.append(f"{sid}: duplicate source_id")
        seen_ids.add(s.get("source_id"))

        for field in _REQUIRED_FIELDS:
            if field not in s:
                errors.append(f"{sid}: missing required field '{field}'")

        status = s.get("implementation_status")
        if status not in _VALID_STATUSES:
            errors.append(f"{sid}: invalid implementation_status {status!r}")
            continue

        # Honesty contract (mission Section 40 -- NO FAKE INTEGRATIONS):
        # a source with no live/implemented code cannot claim operational
        # health or a nonzero track-record score.
        if status not in ("ACTIVE", "IMPLEMENTED"):
            if s.get("health_status") == "HEALTHY":
                errors.append(f"{sid}: status={status} cannot have health_status=HEALTHY")
            if (s.get("reliability_score") or 0) > 0:
                errors.append(f"{sid}: status={status} cannot have reliability_score > 0")
            if s.get("enabled"):
                errors.append(f"{sid}: status={status} cannot have enabled=true")
            if (s.get("records_received") or 0) > 0:
                errors.append(f"{sid}: status={status} cannot have nonzero records_received")

        if status == "ACTIVE" and not s.get("enabled"):
            errors.append(f"{sid}: status=ACTIVE but enabled=false")

        if not (1 <= int(s.get("wave", 0) or 0) <= 5):
            errors.append(f"{sid}: wave must be 1-5, got {s.get('wave')!r}")

        if not (1 <= int(s.get("priority", 0) or 0) <= 5):
            errors.append(f"{sid}: priority must be 1-5, got {s.get('priority')!r}")

        # Licensing coherence (mission Section 23): FREE_NONCOMMERCIAL /
        # INTERNAL_USE_ONLY data must never be flagged commercially usable --
        # this is the exact "accidental redistribution of restricted data"
        # mistake Section 23 calls out.
        if s.get("licensing_class") in ("FREE_NONCOMMERCIAL", "INTERNAL_USE_ONLY") and s.get("commercial_use_allowed"):
            errors.append(
                f"{sid}: licensing_class={s.get('licensing_class')} but "
                f"commercial_use_allowed=true -- licensing governance violation"
            )

    return errors


def _print_summary() -> None:
    reg = load_registry()
    print(f"Source Registry v{reg['registry_version']} -- {reg['total_sources']} sources")
    print(f"Generated: {reg['generated_at']}")
    print(f"Status breakdown : {reg['status_breakdown']}")
    print(f"Wave breakdown   : {reg['wave_breakdown']}")
    print(f"Live (enabled)   : {len(live_sources())}")
    print()
    print("Licensing summary:")
    for k, v in licensing_summary().items():
        print(f"  {k}: {v}")


def main() -> int:
    if "--validate" in sys.argv:
        errors = validate_registry()
        if errors:
            print(f"[source-registry] VALIDATION FAILED -- {len(errors)} error(s):")
            for e in errors:
                print(f"  - {e}")
            return 1
        reg = load_registry()
        print(f"[source-registry] VALID -- {reg['total_sources']} sources, 0 errors")
        return 0

    if "--summary" in sys.argv:
        _print_summary()
        return 0

    _print_summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
