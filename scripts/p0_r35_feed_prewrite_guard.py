"""P0 R35: prevent publication-feed replacement with unproven intelligence.

Preserves the last known feed and never manufactures provenance.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sentinel_apex_mandate_enforcer import (
    check_mandate_1, check_mandate_3, check_mandate_4,
    check_mandate_8, check_mandate_9, check_mandate_10,
    check_mandate_11,
)
from tlp_policy import load_policy, publication_decision


def select_publishable(records: list[dict], *, limit: int = 500) -> tuple[list[dict], list[dict]]:
    """Withhold ineligible inventory before applying the public feed cap.

    Run the same strict prewrite checks on every candidate. A historical
    record with missing evidence must not poison a batch of valid new records
    or occupy their slots. Return reason metadata only; never repair claims.
    An empty selection still fails assert_publishable() before any feed write.
    """
    if not isinstance(records, list) or not isinstance(limit, int) or limit < 1:
        raise ValueError("P0_FEED_PREWRITE_BLOCKED: invalid candidates or cap")
    policy = load_policy()
    eligible, held = [], []
    for record in records:
        try:
            assert_publishable([record])
        except (ValueError, TypeError, AttributeError) as exc:
            held.append({"id": record.get("id") if isinstance(record, dict) else None,
                         "reason_code": "PREWRITE_DENIED", "reason": str(exc)})
            continue
        decision = publication_decision(record, policy)
        if not decision["allowed"]:
            held.append({"id": record.get("id"), "reason_code": decision["reason_code"],
                         "reason": decision["reason"]})
            continue
        eligible.append(record)
    return eligible[:limit], held

def assert_publishable(records: list[dict]) -> None:
    if not isinstance(records, list) or not records or any(not isinstance(r, dict) for r in records):
        raise ValueError("P0_FEED_PREWRITE_BLOCKED: empty or invalid feed")
    counts = {
        "M1": len(check_mandate_1(records)),
        "M3": len(check_mandate_3(records)),
        "M4": len(check_mandate_4(records)),
        "M8": len(check_mandate_8(records)),
        "M9": len(check_mandate_9(records)),
        "M10": len(check_mandate_10(records)),
        "M11": len(check_mandate_11(records)),
    }
    if any(counts.values()):
        raise ValueError(f"P0_FEED_PREWRITE_BLOCKED: {counts}; originals preserved")
