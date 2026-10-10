"""P0 R37: neutralise the independently served GitHub Pages legacy feed aliases.

The authoritative LIVE intel API is the Cloudflare Worker /api/*.
GitHub Pages is not allowed to publish item arrays via legacy static root
assets, even if Cloudflare's exact Worker routes are not attached or an
expired payload is committed in git.
"""
from __future__ import annotations
import json
from pathlib import Path

LEGACY_STATIC_ALIASES = ("feed.json", "latest.json")

def neutralise_legacy_static_feeds(dist_dir: Path) -> None:
    dist_dir = Path(dist_dir)
    if not dist_dir.is_dir():
        raise ValueError("P0_STATIC_FEED_DENIAL: missing deployment directory")
    for alias in LEGACY_STATIC_ALIASES:
        path = dist_dir / alias
        payload = {
            "schema_version": "p0-legacy-static-denial-v1",
            "error": "legacy_static_feed_disabled",
            "publication_state": "UNAVAILABLE",
            "freshness_status": "UNAVAILABLE",
            "live_data_available": False,
            "items": [],
            "data": [],
            "count": 0,
            "message": "Static intelligence snapshots are disabled. Use the authoritative live API.",
            "live_endpoint": "/api/feed" if alias == "feed.json" else "/api/v1/intel/latest.json",
        }
        tmp = dist_dir / (alias + ".tmp")
        tmp.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        tmp.replace(path)
        saved = json.loads(path.read_text(encoding="utf-8"))
        if saved.get("items") != [] or saved.get("data") != [] or saved.get("live_data_available") is not False:
            raise ValueError(f"P0_STATIC_FEED_DENIAL: invalid published alias {alias}")
