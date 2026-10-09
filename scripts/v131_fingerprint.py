"""Type-safe deterministic deduplication fingerprint for v131 advisory upgrades.

Does not modify advisory fields, invent CVEs, infer TLP, or grant publication.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def _normalize(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip().casefold()
    if isinstance(value, (list, tuple)):
        members = [_normalize(member) for member in value]
        # CVE and actor lists represent sets for dedup purposes. Sorting with
        # canonical JSON avoids comparing unlike types and is order invariant.
        return sorted(members, key=lambda member: json.dumps(
            member, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ))
    if isinstance(value, dict):
        return {str(key).strip().casefold(): _normalize(val)
                for key, val in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (int, float, bool)):
        return value
    return repr(value)


def advisory_fingerprint(item: dict) -> str:
    if not isinstance(item, dict):
        raise TypeError("Expected an advisory object, not an unverified record")
    structured = [
        _normalize(item.get("title")),
        _normalize(item.get("cve") or item.get("cve_id")),
        _normalize(item.get("actor_tag")),
    ]
    payload = json.dumps(structured, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
