#!/usr/bin/env python3
"""
intel_product_factory.py - CYBERDUDEBIVASH(R) SENTINEL APEX
CENTRAL ASSEMBLY LINE ORCHESTRATOR
Founder & CEO - CyberDudeBivash Pvt. Ltd.

WHAT CHANGED AND WHY
--------------------
The previous orchestrator printed a mojibake banner, ignored every failure and
indexed ``det_result['product_id']`` unconditionally -- so a failed detection
build raised KeyError inside a success message. It also imported
``agent.revenue_engine`` at module scope without using it, which coupled the
whole factory to that module's import-time side effects for no benefit.

It now: builds the full playbook library rather than one hardcoded sample,
generates the commercial catalog, reports a non-zero exit code when any stage
fails, and never assumes a stage succeeded.
"""

from __future__ import annotations

import json
import sys
from typing import Dict, List

from agent.product_factory.asset_catalog_builder import write_catalog
from agent.product_factory.asset_publisher import publish
from agent.product_factory.commercial_asset_spec import VENDOR_BRAND
from agent.product_factory.detection_pack_builder import DETECTION_BUILDER
from agent.product_factory.ioc_bundle_builder import IOC_BUILDER
from agent.product_factory.soc_playbook_generator import PLAYBOOK_GEN


class IntelProductFactory:
    def __init__(self) -> None:
        self.authority = "CYBERDUDEBIVASH OFFICIAL AUTHORITY"

    def run_assembly_line(self) -> Dict:
        """Orchestrate creation of every sellable asset. Never raises."""
        print(f"{VENDOR_BRAND} PRODUCT FACTORY: STARTING ASSEMBLY LINE")
        failures: List[str] = []

        # 1. Detection pack ---------------------------------------------------
        det_result = DETECTION_BUILDER.build_pack(tier="enterprise")
        if det_result.get("status") == "success":
            c = det_result.get("contents", {})
            print(
                f"  [OK] Detection pack {det_result.get('product_id')} "
                f"({det_result.get('size_bytes', 0) / 1024:.1f} KB, "
                f"{c.get('sigma_rules', 0)} sigma, {c.get('suricata_rules', 0)} suricata, "
                f"{c.get('enforcement_iocs', 0)} enforcement IOCs)"
            )
        else:
            failures.append(f"detection_pack: {det_result.get('message')}")
            print(f"  [FAIL] Detection pack: {det_result.get('message')}")

        # 2. IOC bundle -------------------------------------------------------
        ioc_result = IOC_BUILDER.generate_bundle(format="json")
        if ioc_result.get("status") == "success":
            print(
                f"  [OK] IOC bundle {ioc_result.get('bundle_id')} "
                f"({ioc_result.get('count', 0)} indicators, "
                f"{ioc_result.get('enforcement_count', 0)} enforcement, "
                f"source={ioc_result.get('source')})"
            )
            if not ioc_result.get("publishable"):
                failures.append(f"ioc_bundle: {ioc_result.get('gate_reason')}")
                print(f"  [GATE] IOC bundle not publishable: {ioc_result.get('gate_reason')}")
        else:
            failures.append(f"ioc_bundle: {ioc_result.get('message')}")
            print(f"  [FAIL] IOC bundle: {ioc_result.get('message')}")

        # 3. Playbook library -------------------------------------------------
        try:
            playbooks = PLAYBOOK_GEN.generate_library(actor="Multi-Actor")
            print(f"  [OK] Playbook library ({len(playbooks)} playbooks)")
        except Exception as exc:  # noqa: BLE001
            playbooks = []
            failures.append(f"playbooks: {exc}")
            print(f"  [FAIL] Playbook library: {exc}")

        # 4. Commercial catalog ----------------------------------------------
        try:
            catalog_path = str(write_catalog())
            print(f"  [OK] Commercial catalog -> {catalog_path}")
        except Exception as exc:  # noqa: BLE001
            catalog_path = ""
            failures.append(f"catalog: {exc}")
            print(f"  [FAIL] Commercial catalog: {exc}")

        # 5. Publish to private object storage -------------------------------
        # Paid artefacts go to R2 behind the gateway's entitlement check, never
        # to the public repository (see agent/product_factory/asset_publisher.py).
        pub = publish()
        if pub.get("status") in ("success", "dry_run", "empty"):
            print(f"  [OK] Publication: {pub.get('status')} "
                  f"({pub.get('published', 0)} artefact(s) to private R2)")
        else:
            failures.append(f"publication: {pub.get('message') or pub.get('failed_keys')}")
            print(f"  [FAIL] Publication: {pub.get('message') or pub.get('failed_keys')}")

        status = "success" if not failures else "partial"
        print(f"ASSEMBLY {'COMPLETE' if not failures else 'COMPLETED WITH FAILURES'}")

        return {
            "status": status,
            "failures": failures,
            "detections": det_result,
            "iocs": ioc_result,
            "playbooks": playbooks,
            "catalog": catalog_path,
            "publication": pub,
        }


def main() -> int:
    result = IntelProductFactory().run_assembly_line()
    if result["failures"]:
        for f in result["failures"]:
            print(f"::error::product factory stage failed -- {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
