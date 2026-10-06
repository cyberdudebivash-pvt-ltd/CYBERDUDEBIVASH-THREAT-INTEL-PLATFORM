#!/usr/bin/env python3
"""
asset_catalog_builder.py - CYBERDUDEBIVASH(R) SENTINEL APEX
COMMERCIAL ASSET CATALOG GENERATION
Founder & CEO - CyberDudeBivash Pvt. Ltd.

The commercial catalog is generated from the assets that actually exist on disk
and from the pricing SSOT -- it is never hand-maintained. Every entry carries a
SHA-256 so a customer can verify the artefact they received, and every price is
resolved from config/pricing.json at build time.

Consumed by scripts/commercial_asset_audit.py and by the factory orchestrator.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from agent.product_factory.commercial_asset_spec import (
    ASSET_CLASSES,
    PLATFORM_BASE,
    SPEC_VERSION,
    VENDOR_LEGAL_NAME,
    commercial_metadata,
    load_pricing,
)

REPO = Path(__file__).resolve().parent.parent.parent

CATALOG_VERSION = "1.0.0"

# Where each asset class lands. Staging is gitignored: these are paid artefacts
# and must not be committed to a public repository.
STAGING_ROOT = REPO / "data" / "premium_staging" / "products"
ASSET_DIRS = {
    "detection_pack": STAGING_ROOT / "detections",
    "ioc_bundle": STAGING_ROOT / "ioc_bundles",
    "soc_playbook": STAGING_ROOT / "playbooks",
}
ASSET_GLOBS = {
    "detection_pack": "*.zip",
    "ioc_bundle": "IOC-BNDL-*.json",
    "soc_playbook": "PB-*.json",
}

# A bundle ships companion deliverables beside it (IOC-BNDL-<ts>.stix2.json,
# .misp.json) and a playbook ships .md/.LICENSE.txt. Those globs match the
# companions too, so the catalog would list a STIX file as if it were the
# bundle. Only the primary artefact -- exactly one dot before the extension --
# is a catalog entry.
_PRIMARY_ARTEFACT = {
    "ioc_bundle": re.compile(r"^IOC-BNDL-[0-9_]+\.json$"),
    "soc_playbook": re.compile(r"^PB-[A-Z0-9-]+\.json$"),
}


def is_primary_artefact(asset_class: str, name: str) -> bool:
    """True when `name` is the primary sellable artefact, not a companion file."""
    pattern = _PRIMARY_ARTEFACT.get(asset_class)
    return True if pattern is None else bool(pattern.match(name))


def build_clock() -> datetime:
    raw = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if raw:
        try:
            return datetime.fromtimestamp(int(raw), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            pass
    return datetime.now(timezone.utc)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _describe(path: Path, asset_class: str) -> Dict:
    entry = {
        "filename": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256_file(path),
    }
    # Surface the artefact's own declared counts where it publishes them, so the
    # catalog reflects the artefact rather than a separately maintained claim.
    if path.suffix == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return entry
        if asset_class == "ioc_bundle":
            entry.update({
                "bundle_id": data.get("bundle_id"),
                "format_version": data.get("bundle_format_version"),
                "indicator_count": data.get("ioc_count"),
                "enforcement_tier": (data.get("counts") or {}).get("enforcement_tier"),
                "monitoring_tier": (data.get("counts") or {}).get("monitoring_tier"),
                "publishable": data.get("publishable"),
                "tlp": data.get("tlp"),
            })
        elif asset_class == "soc_playbook":
            entry.update({
                "playbook_id": data.get("playbook_id"),
                "format_version": data.get("playbook_format_version"),
                "threat_type": data.get("threat_type"),
                "severity": data.get("severity"),
                "task_count": data.get("task_count"),
                "framework": data.get("framework"),
                "tlp": data.get("tlp"),
            })
    elif path.suffix == ".zip":
        try:
            import zipfile
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                entry["file_count"] = len(names)
                entry["has_licence"] = "LICENSE.txt" in names
                entry["has_integrity_manifest"] = "SHA256SUMS.txt" in names
                entry["has_readme"] = "README.md" in names
                if "metadata.json" in names:
                    meta = json.loads(zf.read("metadata.json").decode("utf-8"))
                    entry["format_version"] = meta.get("pack_format_version")
                    entry["pack_id"] = meta.get("pack_id")
                    entry["contents"] = meta.get("contents")
        except Exception:  # noqa: BLE001 -- a malformed archive is reported, not fatal
            entry["archive_error"] = "unreadable archive"
    return entry


def build_catalog(latest_only: bool = True) -> Dict:
    """Generate the commercial catalog from on-disk assets and the pricing SSOT."""
    now = build_clock()
    pricing = load_pricing()
    products: List[Dict] = []

    for asset_class, spec in ASSET_CLASSES.items():
        directory = ASSET_DIRS[asset_class]
        pattern = ASSET_GLOBS[asset_class]
        try:
            found = sorted(
                (p for p in directory.glob(pattern)
                 if p.is_file() and is_primary_artefact(asset_class, p.name)),
                key=lambda p: p.name,
            )
        except OSError:
            found = []

        if latest_only and asset_class == "detection_pack" and found:
            found = found[-1:]

        artefacts = [_describe(p, asset_class) for p in found]
        commercial = commercial_metadata(asset_class, pricing)
        products.append({
            "asset_class": asset_class,
            "sku": spec["sku"],
            "name": spec["name"],
            "summary": spec["summary"],
            "commercial": commercial,
            "artefact_count": len(artefacts),
            "artefacts": artefacts,
            "available": bool(artefacts),
        })

    priced = sum(1 for p in products if p["commercial"]["pricing"].get("priced"))
    return {
        "_meta": {
            "catalog": "CYBERDUDEBIVASH SENTINEL APEX Commercial Asset Catalog",
            "catalog_version": CATALOG_VERSION,
            "asset_spec_version": SPEC_VERSION,
            "generated_at": now.isoformat(),
            "vendor": VENDOR_LEGAL_NAME,
            "platform": PLATFORM_BASE,
            "pricing_source": "config/pricing.json",
            "generation": (
                "Generated from on-disk artefacts and the pricing SSOT. "
                "Never hand-maintained."
            ),
        },
        "summary": {
            "asset_classes": len(products),
            "priced_asset_classes": priced,
            "available_asset_classes": sum(1 for p in products if p["available"]),
            "total_artefacts": sum(p["artefact_count"] for p in products),
        },
        "products": products,
    }


def write_catalog(path: Optional[Path] = None) -> Path:
    """Write the catalog to the staging root and return its path."""
    catalog = build_catalog()
    target = path or (STAGING_ROOT / "catalog.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(catalog, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(target)
    return target


__all__ = ["ASSET_DIRS", "ASSET_GLOBS", "CATALOG_VERSION", "STAGING_ROOT",
           "build_catalog", "is_primary_artefact", "write_catalog"]
