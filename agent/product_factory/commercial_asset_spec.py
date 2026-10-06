#!/usr/bin/env python3
"""
commercial_asset_spec.py - CYBERDUDEBIVASH(R) SENTINEL APEX
COMMERCIAL ASSET SPECIFICATION - SINGLE SOURCE OF TRUTH
Founder & CEO - CyberDudeBivash Pvt. Ltd.

WHY THIS MODULE EXISTS
----------------------
Before this module, every sellable artefact produced by the product factory
carried a hand-written ``"authority": "CYBERDUDEBIVASH OFFICIAL AUTHORITY"``
string and nothing else: no price, no licence, no TLP marking, no SKU, no
entitlement tier. The prices that *were* stated lived in
``scripts/generate_detection_pack.py`` as a hardcoded literal
(``"+$149/mo add-on"``) that had already drifted away from
``config/pricing.json`` -- the file that declares itself
"THE SINGLE SOURCE OF TRUTH for all pricing".

This module is the SSOT bridge: commercial metadata for every sellable asset
class is derived here, prices are read from ``config/pricing.json`` at build
time, and every builder in ``agent/product_factory/`` stamps its output from
this one place. Adding a price change to ``config/pricing.json`` propagates to
every asset on the next factory run with no code change.

CONSUMERS
---------
  agent/product_factory/detection_pack_builder.py
  agent/product_factory/ioc_bundle_builder.py
  agent/product_factory/soc_playbook_generator.py
  agent/product_factory/asset_catalog_builder.py
  scripts/commercial_asset_audit.py
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

REPO = Path(__file__).resolve().parent.parent.parent

# config/pricing.json declares itself the authoritative pricing SSOT. Read it;
# never restate a price in Python.
PRICING_PATH = Path(os.environ.get("PRICING_PATH", str(REPO / "config" / "pricing.json")))

PLATFORM_BASE = "https://intel.cyberdudebivash.com"
VENDOR_LEGAL_NAME = "CyberDudeBivash Pvt. Ltd."
VENDOR_BRAND = "CYBERDUDEBIVASH(R) SENTINEL APEX"
VENDOR_CONTACT = "iambivash.bn@gmail.com"
VENDOR_GSTIN = "21ARKPN8270G1ZP"

SPEC_VERSION = "1.0.0"

# ── Asset classes ────────────────────────────────────────────────────────────
# Each sellable asset class maps onto an existing entitlement surface. The
# add_on_key values below must exist in config/pricing.json -> add_ons, or the
# price resolves to None and the audit gate flags the asset as unpriced rather
# than silently shipping a product with an invented price.
ASSET_CLASSES: Dict[str, Dict] = {
    "detection_pack": {
        "sku": "APEX-ASSET-DETPACK",
        "name": "SENTINEL APEX Detection Pack",
        "summary": (
            "Deployable multi-platform detection content: Sigma rules, Microsoft "
            "Sentinel/Defender KQL, Suricata and Snort signatures, firewall-ready "
            "IOC blocklists and a CVE watchlist, mapped to MITRE ATT&CK."
        ),
        "entitlement_tiers": ["enterprise", "mssp"],
        "add_on_key": "detection_pack",
        "tlp": "TLP:AMBER+STRICT",
        "delivery": "R2 private object storage via /api/v1/premium/detections/*",
        "formats": ["Sigma YAML", "KQL", "Suricata", "Snort", "JSON", "CSV", "TXT"],
        "target_platforms": [
            "Microsoft Sentinel", "Microsoft Defender XDR", "Splunk Enterprise Security",
            "Elastic Security", "CrowdStrike Falcon", "Suricata", "Snort",
            "Palo Alto PAN-OS", "Fortinet FortiGate", "Qualys VMDR", "Tenable.io",
        ],
    },
    "ioc_bundle": {
        "sku": "APEX-ASSET-IOCBNDL",
        "name": "SENTINEL APEX IOC Bundle",
        "summary": (
            "Curated, deduplicated and confidence-scored indicators of compromise "
            "delivered as a STIX 2.1 bundle, MISP event, analyst CSV and a flat "
            "blocklist ready for firewall and DNS enforcement."
        ),
        "entitlement_tiers": ["pro", "enterprise", "mssp"],
        "add_on_key": "ioc_bundle",
        "tlp": "TLP:AMBER",
        "delivery": "R2 private object storage via /api/v1/premium/detections/*",
        "formats": ["STIX 2.1", "MISP JSON", "CSV", "TXT", "JSON"],
        "target_platforms": [
            "MISP", "OpenCTI", "Anomali ThreatStream", "ThreatConnect",
            "Microsoft Sentinel TI", "Splunk ES Threat Intelligence",
            "Palo Alto PAN-OS EDL", "Fortinet FortiGate", "Pi-hole", "pfSense",
        ],
    },
    "soc_playbook": {
        "sku": "APEX-ASSET-PLAYBOOK",
        "name": "SENTINEL APEX SOC Response Playbook",
        "summary": (
            "Incident response playbook structured on the NIST SP 800-61 Rev.2 "
            "lifecycle with MITRE ATT&CK-mapped containment and eradication steps, "
            "severity-driven SLAs, evidence-collection checklists and RACI ownership."
        ),
        "entitlement_tiers": ["enterprise", "mssp"],
        "add_on_key": "soc_playbook",
        "tlp": "TLP:AMBER",
        "delivery": "R2 private object storage via /api/v1/premium/detections/*",
        "formats": ["JSON", "Markdown"],
        "target_platforms": [
            "ServiceNow SecOps", "Palo Alto Cortex XSOAR", "Splunk SOAR",
            "Microsoft Sentinel Playbooks", "TheHive",
        ],
    },
}


class PricingUnavailable(RuntimeError):
    """Raised when the pricing SSOT cannot be read.

    Deliberately fatal rather than defaulted: shipping a commercial asset
    stamped with a guessed price is a revenue-integrity defect, so the factory
    must fail loudly instead of inventing one.
    """


def load_pricing() -> Dict:
    """Read config/pricing.json (the declared pricing SSOT)."""
    try:
        return json.loads(PRICING_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PricingUnavailable(f"Pricing SSOT not found: {PRICING_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise PricingUnavailable(f"Pricing SSOT is not valid JSON: {exc}") from exc


def resolve_price(asset_class: str, pricing: Optional[Dict] = None) -> Dict:
    """Resolve the commercial price for an asset class from the pricing SSOT.

    Returns a dict with ``priced`` False (and no invented figures) when the
    add-on key is absent from config/pricing.json, so the audit gate can report
    an unpriced asset instead of the factory fabricating a number.
    """
    spec = ASSET_CLASSES.get(asset_class)
    if spec is None:
        raise KeyError(f"Unknown asset class: {asset_class}")

    pricing = pricing if pricing is not None else load_pricing()
    add_ons = pricing.get("add_ons") or {}
    entry = add_ons.get(spec["add_on_key"])

    if not isinstance(entry, dict):
        return {
            "priced": False,
            "pricing_source": str(PRICING_PATH.relative_to(REPO)),
            "add_on_key": spec["add_on_key"],
            "reason": (
                f"add_ons.{spec['add_on_key']} is absent from the pricing SSOT; "
                "no price is asserted for this asset"
            ),
        }

    tiers = pricing.get("tiers") or {}
    included_in = [
        t for t in spec["entitlement_tiers"]
        if isinstance(tiers.get(t), dict)
    ]

    return {
        "priced": True,
        "pricing_source": str(PRICING_PATH.relative_to(REPO)),
        "add_on_key": spec["add_on_key"],
        "label": entry.get("label"),
        "price_usd": entry.get("price_usd"),
        "price_inr": entry.get("price_inr"),
        "billing_period": entry.get("billing_period", "month"),
        "currency_primary": pricing.get("currency_primary"),
        "currency_secondary": pricing.get("currency_secondary"),
        "gstin": pricing.get("gstin"),
        "included_in_tiers": included_in,
        "upgrade_url": pricing.get("upgrade_url"),
    }


def license_terms(asset_class: str) -> Dict:
    """Structured commercial licence terms for a sellable asset class."""
    spec = ASSET_CLASSES[asset_class]
    return {
        "licence_id": f"CDB-COMMERCIAL-{spec['sku']}",
        "licence_name": "CYBERDUDEBIVASH Commercial Threat Intelligence Licence v1.0",
        "licensor": VENDOR_LEGAL_NAME,
        "grant": (
            "Non-exclusive, non-transferable, worldwide right to deploy, execute and "
            "operationally use the content within the licensee's own security "
            "infrastructure and, for MSSP licensees, within the infrastructure of "
            "tenants covered by an active MSSP subscription."
        ),
        "permitted": [
            "Deployment into the licensee's SIEM, EDR, IDS/IPS, firewall and TIP systems",
            "Internal modification and tuning to reduce false positives",
            "Derivation of internal alerting and reporting from the content",
            "MSSP delivery to tenants covered by an active MSSP subscription",
        ],
        "prohibited": [
            "Redistribution, resale, sublicensing or public disclosure of the content",
            "Publishing the content to any public repository, feed or dataset",
            "Use as training data for any model offered to third parties",
            "Removal or alteration of provenance, TLP or attribution markings",
        ],
        "tlp": spec["tlp"],
        "warranty": (
            "Content is provided for defensive security operations. Detection content "
            "requires environment-specific tuning before enforcement actions are "
            "automated. No warranty of fitness for a particular environment is implied."
        ),
        "term": "Coterminous with the licensee's active subscription or add-on entitlement.",
        "contact": VENDOR_CONTACT,
        "gstin": VENDOR_GSTIN,
    }


def license_text(asset_class: str) -> str:
    """Render the licence as the LICENSE.txt shipped inside every asset bundle."""
    terms = license_terms(asset_class)
    spec = ASSET_CLASSES[asset_class]
    bar = "=" * 74
    lines: List[str] = [
        bar,
        f"{terms['licence_name']}",
        f"{spec['name']}  --  SKU {spec['sku']}",
        bar,
        "",
        f"Licensor : {terms['licensor']}  (GSTIN {terms['gstin']})",
        f"Contact  : {terms['contact']}",
        f"Marking  : {terms['tlp']}",
        f"Term     : {terms['term']}",
        "",
        "1. GRANT OF LICENCE",
        f"   {terms['grant']}",
        "",
        "2. PERMITTED USE",
    ]
    lines += [f"   ({chr(97 + i)}) {p}" for i, p in enumerate(terms["permitted"])]
    lines += ["", "3. PROHIBITED USE"]
    lines += [f"   ({chr(97 + i)}) {p}" for i, p in enumerate(terms["prohibited"])]
    lines += [
        "",
        "4. WARRANTY AND OPERATIONAL NOTICE",
        f"   {terms['warranty']}",
        "",
        "5. TRAFFIC LIGHT PROTOCOL",
        f"   This bundle is marked {terms['tlp']}. Handle and share strictly in",
        "   accordance with FIRST TLP 2.0.",
        "",
        bar,
        f"(C) {datetime.now(timezone.utc).year} {terms['licensor']}. All rights reserved.",
        bar,
        "",
    ]
    return "\n".join(lines)


def commercial_metadata(asset_class: str, pricing: Optional[Dict] = None) -> Dict:
    """The commercial block stamped into every sellable asset produced.

    This replaces the previous free-text ``"authority"`` string with a
    machine-readable, auditable commercial record.
    """
    spec = ASSET_CLASSES[asset_class]
    return {
        "spec_version": SPEC_VERSION,
        "sku": spec["sku"],
        "product_name": spec["name"],
        "summary": spec["summary"],
        "vendor": {
            "legal_name": VENDOR_LEGAL_NAME,
            "brand": VENDOR_BRAND,
            "contact": VENDOR_CONTACT,
            "gstin": VENDOR_GSTIN,
            "platform": PLATFORM_BASE,
        },
        "entitlement": {
            "required_tiers": spec["entitlement_tiers"],
            "delivery": spec["delivery"],
        },
        "pricing": resolve_price(asset_class, pricing),
        "licence": license_terms(asset_class),
        "formats": spec["formats"],
        "target_platforms": spec["target_platforms"],
    }


__all__ = [
    "ASSET_CLASSES",
    "PLATFORM_BASE",
    "PRICING_PATH",
    "PricingUnavailable",
    "SPEC_VERSION",
    "VENDOR_BRAND",
    "VENDOR_CONTACT",
    "VENDOR_GSTIN",
    "VENDOR_LEGAL_NAME",
    "commercial_metadata",
    "license_terms",
    "license_text",
    "load_pricing",
    "resolve_price",
]
