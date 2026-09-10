#!/usr/bin/env python3
"""
asset_publisher.py - CYBERDUDEBIVASH(R) SENTINEL APEX
COMMERCIAL ASSET PUBLICATION TO PRIVATE OBJECT STORAGE
Founder & CEO - CyberDudeBivash Pvt. Ltd.

WHY THIS MODULE EXISTS
----------------------
v184.4 moved the premium detection pack out of the public repository because it
was "fetchable by anyone with zero auth, with no route anywhere that ever checked
a caller's entitlement before serving it", and republished it to R2 behind
/api/v1/premium/detections/*.

The product factory was never migrated. sentinel-factory.yml continued to
`git add -f data/products/` and push ENTERPRISE-tier artefacts straight to the
public default branch on every run -- 699 files at the time of this change. Same
exposure class, same repository, different pipeline.

This module gives the factory the same publication path the premium pack already
uses: the existing sentinel-apex-data bucket, under the existing private
premium/ prefix, via scripts/r2_upload.py's existing credentials. No new bucket,
no new credential, no new route.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from agent.product_factory.asset_catalog_builder import ASSET_DIRS, STAGING_ROOT

log = logging.getLogger("asset_publisher")

PREMIUM_BUCKET = "sentinel-apex-data"

# R2 key prefix per asset class, under the private premium/ namespace the
# intel-gateway already serves behind an ENTERPRISE/MSSP entitlement check.
R2_PREFIXES = {
    "detection_pack": "premium/products/detections",
    "ioc_bundle": "premium/products/ioc_bundles",
    "soc_playbook": "premium/products/playbooks",
}

_CONTENT_TYPES = {
    ".zip": "application/zip", ".json": "application/json", ".csv": "text/csv",
    ".txt": "text/plain", ".md": "text/markdown", ".yml": "application/x-yaml",
    ".kql": "text/plain", ".rules": "text/plain",
}


def _iter_publishable() -> List[Tuple[str, Path]]:
    """Every artefact to publish, paired with its asset class.

    Companion deliverables (a bundle's .stix2.json / .misp.json / .csv, a
    playbook's .md / .LICENSE.txt) are published alongside their primary
    artefact -- a customer needs the STIX file, not only the JSON.
    """
    out: List[Tuple[str, Path]] = []
    for asset_class, directory in ASSET_DIRS.items():
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if not path.is_file() or path.suffix == ".tmp":
                continue
            out.append((asset_class, path))
    catalog = STAGING_ROOT / "catalog.json"
    if catalog.is_file():
        out.append(("catalog", catalog))
    return out


def publish(dry_run: Optional[bool] = None) -> Dict:
    """Publish staged commercial assets to private R2. Never raises."""
    if dry_run is None:
        dry_run = os.environ.get("DRY_RUN", "false").strip().lower() == "true"

    artefacts = _iter_publishable()
    if not artefacts:
        return {"status": "empty", "published": 0, "failed": 0,
                "message": "no staged artefacts to publish"}

    if dry_run:
        for asset_class, path in artefacts:
            log.info("[DRY RUN] would publish %s -> %s/", path.name,
                     R2_PREFIXES.get(asset_class, "premium/products"))
        return {"status": "dry_run", "published": 0, "failed": 0,
                "candidates": len(artefacts)}

    try:
        from scripts.r2_upload import get_credentials, s3_cp
    except ImportError as exc:
        return {"status": "error", "published": 0, "failed": len(artefacts),
                "message": f"r2_upload unavailable: {exc}"}

    try:
        cf_account, _, _ = get_credentials()
    except SystemExit:
        # get_credentials() exits when secrets are absent. Publication is
        # mandatory on the publishing runner, so surface it as a failure rather
        # than letting the process die mid-assembly.
        return {"status": "error", "published": 0, "failed": len(artefacts),
                "message": "R2 credentials not configured (CF_ACCOUNT_ID / AWS_ACCESS_KEY_ID)"}

    endpoint = f"https://{cf_account}.r2.cloudflarestorage.com"
    published, failed = 0, []

    for asset_class, path in artefacts:
        prefix = R2_PREFIXES.get(asset_class, "premium/products")
        key = f"{prefix}/{path.name}" if asset_class != "catalog" else "premium/products/catalog.json"
        ok = s3_cp(
            str(path), PREMIUM_BUCKET, key, endpoint,
            content_type=_CONTENT_TYPES.get(path.suffix, "application/octet-stream"),
            cache_control="private, max-age=300",
        )
        if ok:
            published += 1
        else:
            failed.append(key)
            log.error("R2 publish FAILED for %s", key)

    if failed:
        log.error("%d artefact(s) failed to publish -- paying customers will not "
                  "see updated content until this is retried", len(failed))

    return {
        "status": "success" if not failed else "partial",
        "published": published,
        "failed": len(failed),
        "failed_keys": failed,
        "bucket": PREMIUM_BUCKET,
    }


__all__ = ["PREMIUM_BUCKET", "R2_PREFIXES", "publish"]
