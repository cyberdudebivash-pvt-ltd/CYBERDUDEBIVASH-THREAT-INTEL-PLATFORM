#!/usr/bin/env python3
"""Flag-gated boundary in front of the existing public freshness gate.

Uses the merged adapter at integrations/sentinel-apex-ai-intel.
Does not open the platform database, write api/feed.json, or upload to R2.
A master HTTP 200 is not customer publication. Freshness remains the
existing public_feed_freshness_gate decision, which this module does not call
and does not weaken.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = REPO_ROOT / "integrations" / "sentinel-apex-ai-intel" / "sentinel_apex_intel.py"
SCHEMA = "sentinel-apex.intel.v1"


def _adapter():
    spec = importlib.util.spec_from_file_location("sentinel_apex_intel_merged", ADAPTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("merged SENTINEL APEX adapter is missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def activation_status(env: dict) -> dict:
    enabled = env.get("SENTINEL_APEX_AI_INTEL") == "1"
    base = str(env.get("SENTINEL_APEX_AI_INTEL_BASE_URL") or "").strip()
    common = {"schema": SCHEMA, "customer_visible": False, "public_feed_write": False, "end_to_end_verified": False}
    if not enabled:
        return {**common, "status": "NOT_CONFIGURED", "enabled": False, "reason": "SENTINEL_APEX_AI_INTEL is not 1"}
    if not base:
        return {**common, "status": "NOT_CONFIGURED", "enabled": False, "reason": "SENTINEL_APEX_AI_INTEL_BASE_URL is unset"}
    parsed = urlparse(base)
    if parsed.scheme != "https" or parsed.username or parsed.password or not parsed.hostname:
        return {**common, "status": "FAILED", "enabled": True, "reason": "base url must be https without credentials"}
    return {**common, "status": "CONFIGURED", "enabled": True, "base_host": parsed.hostname}


def publication_decision(adapter_error: str | None, freshness_state: str | None) -> str:
    """The existing freshness gate remains authoritative. This function never writes."""
    if adapter_error:
        return "FAILED"
    if freshness_state != "FRESH":
        return "BLOCKED_BY_FRESHNESS_GATE"
    return "ELIGIBLE_FOR_EXISTING_PIPELINE"


def stage_page(env: dict, state: dict, page: dict, freshness_state: str | None) -> dict:
    status = activation_status(env)
    if status["status"] != "CONFIGURED":
        return {**status, "state": state, "applied": 0, "removed": 0, "release": "NOT_AUTHORIZED"}
    result = _adapter().apply_master_page(state, page)
    decision = publication_decision(result["error"], freshness_state)
    release = "NOT_AUTHORIZED"
    return {
        "status": "CONTRACT_VERIFIED" if result["error"] is None else "FAILED",
        "schema": SCHEMA,
        "customer_visible": False,
        "public_feed_write": False,
        "end_to_end_verified": False,
        "freshness_decision": decision,
        "release": release,
        "error": result["error"],
        "applied": result["applied"] if result["error"] is None else 0,
        "removed": result["removed"] if result["error"] is None else 0,
        "state": result["state"],
        "base_host": status.get("base_host"),
    }


def stage_report(env: dict) -> str:
    """Operator telemetry. Does not fetch and does not publish."""
    return json.dumps(activation_status(env), sort_keys=True)
