#!/usr/bin/env python3
"""
ioc_bundle_builder.py - CYBERDUDEBIVASH(R) SENTINEL APEX
COMMERCIAL IOC BUNDLE ORCHESTRATION
Founder & CEO - CyberDudeBivash Pvt. Ltd.

WHAT CHANGED AND WHY
--------------------
The previous implementation's docstring said it "transforms live STIX feeds into
curated B2B intelligence bundles". It did not produce STIX, and the objects it
bundled were not indicators.

It read the feed manifest, kept whole feed items whose article-level
``confidence`` exceeded 80, and wrote them under a ``data`` key. Inspection of a
shipped bundle (IOC-BNDL-20260822_0209.json, 15 KB) found ``ioc_count: 2`` at the
top level and ``"ioc_count": 0`` on every item inside it: the product sold as an
"IOC Bundle" contained two security news articles and zero indicators. Its source
path (data/stix/feed_manifest.json) is also gitignored and absent on the factory
runner, so on that runner the builder returned ``{"status": "error"}`` and the
customer-facing product silently did not update.

This module now:
  * Reads the live manifest when present and falls back to the certified
    baseline (api/feed.baseline.json) so a runner without the live feed still
    produces a real, certified product instead of an error.
  * Extracts actual indicators from item ``iocs`` arrays and passes every one
    through agent/product_factory/ioc_validation.py.
  * Emits genuine STIX 2.1 (bundle of Indicator SDOs with valid patterns), a MISP
    event, an analyst CSV and an enforcement blocklist -- the formats customers'
    TIPs actually ingest.
  * Applies a publishability gate: a bundle with no validated indicators is
    reported as not publishable rather than shipped as an empty product.

BACKWARD COMPATIBILITY
----------------------
The JSON bundle keeps every key it previously wrote -- ``bundle_id``,
``timestamp``, ``ioc_count``, ``data``, ``authority`` -- with ``data`` still
carrying the curated source items. generate_bundle() still returns
{status, file, count}, with additional keys alongside.
"""

from __future__ import annotations

import csv
import io
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from agent.product_factory import ioc_validation
from agent.product_factory.commercial_asset_spec import (
    PLATFORM_BASE,
    VENDOR_BRAND,
    VENDOR_LEGAL_NAME,
    commercial_metadata,
    license_text,
)

REPO = Path(__file__).resolve().parent.parent.parent

BUNDLE_FORMAT_VERSION = "2.0.0"

# Deterministic STIX identifiers: the same indicator always yields the same id
# across builds, so a customer's TIP updates an existing object instead of
# accumulating a duplicate on every sync.
_STIX_NS = uuid.UUID("6f1c0a4e-9a21-5f7b-8d3c-1b2e4a6c8d0f")

# Well-known STIX 2.1 TLP marking definition identifiers (FIRST TLP 1.0 set as
# published in the STIX 2.1 specification).
_TLP_MARKINGS = {
    "TLP:CLEAR": "marking-definition--613f2e26-407d-48c7-9eca-b8e91df99dc9",
    "TLP:WHITE": "marking-definition--613f2e26-407d-48c7-9eca-b8e91df99dc9",
    "TLP:GREEN": "marking-definition--34098fce-860f-48ae-8e50-ebd3cc5e41da",
    "TLP:AMBER": "marking-definition--f88d31f6-486f-44da-b317-01333bde0b82",
    "TLP:AMBER+STRICT": "marking-definition--f88d31f6-486f-44da-b317-01333bde0b82",
    "TLP:RED": "marking-definition--5e57c739-391a-4eb3-b6be-7d15ca92d5ed",
}

# STIX 2.1 pattern templates per indicator type.
_STIX_PATTERNS = {
    "domain": "[domain-name:value = '{v}']",
    "ipv4": "[ipv4-addr:value = '{v}']",
    "ipv6": "[ipv6-addr:value = '{v}']",
    "url": "[url:value = '{v}']",
    "md5": "[file:hashes.'MD5' = '{v}']",
    "sha1": "[file:hashes.'SHA-1' = '{v}']",
    "sha256": "[file:hashes.'SHA-256' = '{v}']",
    "sha512": "[file:hashes.'SHA-512' = '{v}']",
    "email": "[email-addr:value = '{v}']",
}

# MISP attribute type per indicator type.
_MISP_TYPES = {
    "domain": "domain", "ipv4": "ip-dst", "ipv6": "ip-dst", "url": "url",
    "md5": "md5", "sha1": "sha1", "sha256": "sha256", "sha512": "sha512",
    "email": "email-src",
}

_INDICATOR_TTL_DAYS = 90


def build_clock() -> datetime:
    """Single build timestamp, honouring SOURCE_DATE_EPOCH for reproducibility."""
    raw = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if raw:
        try:
            return datetime.fromtimestamp(int(raw), tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            pass
    return datetime.now(timezone.utc)


def _stix_escape(value: str) -> str:
    """Escape a value for a single-quoted STIX pattern literal."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


class IOCBundleBuilder:
    def __init__(self) -> None:
        self.output_dir = os.environ.get(
            "IOC_BUNDLE_OUTPUT_DIR",
            str(REPO / "data" / "premium_staging" / "products" / "ioc_bundles"),
        )
        # Preserved: the live manifest remains the preferred source.
        self.stix_manifest = str(REPO / "data" / "stix" / "feed_manifest.json")
        # Added: certified fallback so a runner without the live feed still
        # produces a real product instead of returning an error.
        self.baseline_fallback = str(REPO / "api" / "feed.baseline.json")
        os.makedirs(self.output_dir, exist_ok=True)

    # ── Source resolution ────────────────────────────────────────────────────
    def _load_source(self) -> Tuple[List[Dict], str]:
        for path, label in ((self.stix_manifest, "live_feed_manifest"),
                            (self.baseline_fallback, "certified_baseline")):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                data = data.get("items") or data.get("data") or []
            if isinstance(data, list) and data:
                return data, label
        return [], "unavailable"

    # ── Indicator extraction ─────────────────────────────────────────────────
    @staticmethod
    def _extract_candidates(items: List[Dict]) -> List[Dict]:
        """Pull indicator candidates out of feed items, carrying provenance."""
        out: List[Dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            iocs = item.get("iocs")
            if not isinstance(iocs, list):
                continue
            context = {
                "source_id": item.get("id") or item.get("stix_id") or "",
                "source_title": str(item.get("title") or "")[:160],
                "source_feed": item.get("source") or item.get("feed_source") or "",
                "source_url": item.get("source_url") or "",
                "severity": item.get("severity") or "",
                "cve_id": item.get("cve_id") or "",
                "kev": item.get("kev") is True,
                "published_at": item.get("published_at") or item.get("timestamp") or "",
            }
            for entry in iocs:
                if isinstance(entry, dict):
                    cand = {
                        "value": entry.get("value"),
                        "type": entry.get("type") or "indicator",
                        "confidence": entry.get("confidence"),
                    }
                elif isinstance(entry, str):
                    cand = {"value": entry, "type": "indicator", "confidence": None}
                else:
                    continue
                cand.update(context)
                out.append(cand)
        return out

    # ── Output formats ───────────────────────────────────────────────────────
    def _stix_bundle(self, indicators: List[ioc_validation.ValidationResult],
                     now: datetime, tlp: str) -> Dict:
        ts = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        valid_until = (now + timedelta(days=_INDICATOR_TTL_DAYS)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        identity_id = f"identity--{uuid.uuid5(_STIX_NS, 'cyberdudebivash-identity')}"
        marking_ref = _TLP_MARKINGS.get(tlp, _TLP_MARKINGS["TLP:AMBER"])

        objects: List[Dict] = [{
            "type": "identity",
            "spec_version": "2.1",
            "id": identity_id,
            "created": "2024-01-01T00:00:00.000Z",
            "modified": "2024-01-01T00:00:00.000Z",
            "name": VENDOR_LEGAL_NAME,
            "identity_class": "organization",
            "sectors": ["technology"],
            "contact_information": PLATFORM_BASE,
        }]

        for res in indicators:
            template = _STIX_PATTERNS.get(res.ioc_type)
            if not template:
                continue  # no valid STIX pattern for this type -- omit rather than emit invalid STIX
            pattern = template.format(v=_stix_escape(res.normalized))
            ind_id = f"indicator--{uuid.uuid5(_STIX_NS, f'{res.ioc_type}:{res.normalized}')}"
            obj = {
                "type": "indicator",
                "spec_version": "2.1",
                "id": ind_id,
                "created_by_ref": identity_id,
                "created": ts,
                "modified": ts,
                "name": f"{res.ioc_type.upper()}: {res.normalized[:120]}",
                "description": (
                    f"Indicator distributed by {VENDOR_BRAND}. Delivery tier: "
                    f"{res.tier} ({'blockable' if res.tier == 'enforcement' else 'hunt only'})."
                ),
                "indicator_types": ["malicious-activity"],
                "pattern": pattern,
                "pattern_type": "stix",
                "pattern_version": "2.1",
                "valid_from": ts,
                "valid_until": valid_until,
                "object_marking_refs": [marking_ref],
                "labels": [f"tier:{res.tier}", f"ioc-type:{res.ioc_type}"],
            }
            if res.confidence is not None:
                # STIX 2.1 confidence is an integer 0-100.
                obj["confidence"] = max(0, min(100, int(round(res.confidence))))
            objects.append(obj)

        return {
            "type": "bundle",
            "id": f"bundle--{uuid.uuid5(_STIX_NS, 'bundle:' + ts)}",
            "objects": objects,
        }

    def _misp_event(self, indicators: List[ioc_validation.ValidationResult],
                    now: datetime, bundle_id: str, tlp: str) -> Dict:
        attributes = []
        for res in indicators:
            misp_type = _MISP_TYPES.get(res.ioc_type)
            if not misp_type:
                continue
            attributes.append({
                "uuid": str(uuid.uuid5(_STIX_NS, f"misp:{res.ioc_type}:{res.normalized}")),
                "type": misp_type,
                "category": "Network activity" if res.ioc_type in (
                    "domain", "ipv4", "ipv6", "url") else "Payload delivery",
                "value": res.normalized,
                "to_ids": res.tier == "enforcement",
                "comment": f"SENTINEL APEX tier={res.tier} confidence={res.confidence}",
                "timestamp": str(int(now.timestamp())),
            })
        return {
            "Event": {
                "uuid": str(uuid.uuid5(_STIX_NS, f"event:{bundle_id}")),
                "info": f"{VENDOR_BRAND} IOC Bundle {bundle_id}",
                "date": now.strftime("%Y-%m-%d"),
                "threat_level_id": "2",
                "analysis": "2",
                "published": True,
                "Orgc": {"name": VENDOR_LEGAL_NAME,
                         "uuid": str(uuid.uuid5(_STIX_NS, "orgc"))},
                "Tag": [{"name": f'tlp:{tlp.split(":", 1)[1].lower()}'},
                        {"name": "source:CYBERDUDEBIVASH-SENTINEL-APEX"}],
                "Attribute": attributes,
            }
        }

    @staticmethod
    def _analyst_csv(indicators: List[ioc_validation.ValidationResult],
                     provenance: Dict[str, Dict]) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Value", "Type", "Tier", "Blockable", "Confidence",
                    "Severity", "CVE", "KEV", "Source_Feed", "Source_Title",
                    "Source_URL", "First_Seen"])
        for res in indicators:
            ctx = provenance.get(f"{res.ioc_type}:{res.normalized}", {})
            w.writerow([
                res.normalized, res.ioc_type, res.tier,
                "YES" if res.tier == "enforcement" else "NO",
                res.confidence if res.confidence is not None else "",
                ctx.get("severity", ""), ctx.get("cve_id", ""),
                "YES" if ctx.get("kev") else "NO",
                ctx.get("source_feed", ""), str(ctx.get("source_title", ""))[:100],
                ctx.get("source_url", ""), ctx.get("published_at", ""),
            ])
        return buf.getvalue()

    @staticmethod
    def _blocklist(indicators: List[ioc_validation.ValidationResult],
                   now: datetime, tlp: str) -> str:
        enforce = [r for r in indicators if r.tier == "enforcement"]
        lines = [
            f"# {VENDOR_BRAND} -- IOC ENFORCEMENT BLOCKLIST",
            f"# Bundle format : {BUNDLE_FORMAT_VERSION}",
            f"# Generated     : {now.isoformat()}",
            f"# Indicators    : {len(enforce)}",
            f"# Marking       : {tlp}",
            "# Validated, benign-suppressed and above the enforcement confidence",
            "# floor. Run in monitor mode for 48h before switching to deny.",
            "",
        ]
        by_type: Dict[str, List[str]] = {}
        for r in enforce:
            by_type.setdefault(r.ioc_type, []).append(r.normalized)
        for t, vals in sorted(by_type.items()):
            lines.append(f"# ── {t.upper()} ({len(vals)})")
            lines.extend(sorted(set(vals)))
            lines.append("")
        return "\n".join(lines)

    # ── Build ────────────────────────────────────────────────────────────────
    def generate_bundle(self, format: str = "json") -> Dict:
        """Build a commercially deliverable, multi-format IOC bundle."""
        now = build_clock()
        timestamp = now.strftime("%Y%m%d_%H%M")
        bundle_id = f"IOC-BNDL-{timestamp}"

        try:
            items, source_label = self._load_source()
            if not items:
                return {
                    "status": "error",
                    "message": (
                        "No intelligence source available: neither "
                        f"{self.stix_manifest} nor {self.baseline_fallback} could be read"
                    ),
                    "bundle_id": bundle_id,
                    "publishable": False,
                }

            commercial = commercial_metadata("ioc_bundle")
            tlp = commercial["licence"]["tlp"]

            # Preserved 1.x behaviour: the curated high-confidence source items
            # still populate `data`, so any consumer of the old shape keeps working.
            curated_items = [
                i for i in items
                if isinstance(i, dict) and (i.get("confidence") or 0) > 80
            ]

            candidates = self._extract_candidates(items)
            validated, report = ioc_validation.validate_batch(candidates)

            provenance: Dict[str, Dict] = {}
            for cand in candidates:
                res = ioc_validation.validate(
                    str(cand.get("value") or ""), str(cand.get("type") or "indicator"),
                    cand.get("confidence"))
                if res.accepted:
                    provenance.setdefault(f"{res.ioc_type}:{res.normalized}", cand)

            enforcement = [r for r in validated if r.tier == "enforcement"]
            monitoring = [r for r in validated if r.tier == "monitoring"]

            # Publishability gate: never ship an empty product as if it were full.
            publishable = len(validated) > 0
            gate_reason = (
                "ok" if publishable
                else "no indicator survived validation -- bundle is not publishable"
            )

            stix = self._stix_bundle(validated, now, tlp)
            misp = self._misp_event(validated, now, bundle_id, tlp)
            analyst_csv = self._analyst_csv(validated, provenance)
            blocklist = self._blocklist(validated, now, tlp)

            bundle_content = {
                # ---- keys preserved from bundle format 1.x ----
                "bundle_id": bundle_id,
                "timestamp": now.isoformat(),
                "ioc_count": len(validated),
                "data": curated_items,
                "authority": "CYBERDUDEBIVASH OFFICIAL",
                # ---- added ----
                "bundle_format_version": BUNDLE_FORMAT_VERSION,
                "sku": commercial["sku"],
                "tlp": tlp,
                "source": source_label,
                "publishable": publishable,
                "gate_reason": gate_reason,
                "counts": {
                    "source_items": len(items),
                    "curated_source_items": len(curated_items),
                    "indicator_candidates": len(candidates),
                    "validated_indicators": len(validated),
                    "enforcement_tier": len(enforcement),
                    "monitoring_tier": len(monitoring),
                },
                "validation": report.as_dict(),
                "commercial": commercial,
                "indicators": [
                    {
                        "value": r.normalized,
                        "type": r.ioc_type,
                        "confidence": r.confidence,
                        "tier": r.tier,
                        "blockable": r.tier == "enforcement",
                        "provenance": {
                            k: v for k, v in
                            provenance.get(f"{r.ioc_type}:{r.normalized}", {}).items()
                            if k in ("source_id", "source_feed", "source_url",
                                     "source_title", "severity", "cve_id", "kev",
                                     "published_at")
                        },
                    }
                    for r in validated
                ],
                "deliverables": {
                    "stix_2_1": f"{bundle_id}.stix2.json",
                    "misp_event": f"{bundle_id}.misp.json",
                    "analyst_csv": f"{bundle_id}.csv",
                    "enforcement_blocklist": f"{bundle_id}.blocklist.txt",
                    "licence": f"{bundle_id}.LICENSE.txt",
                },
            }

            out_dir = Path(self.output_dir)
            written: Dict[str, str] = {}
            for name, payload in (
                (f"{bundle_id}.{format}", json.dumps(bundle_content, indent=4, ensure_ascii=False)),
                (f"{bundle_id}.stix2.json", json.dumps(stix, indent=2, ensure_ascii=False)),
                (f"{bundle_id}.misp.json", json.dumps(misp, indent=2, ensure_ascii=False)),
                (f"{bundle_id}.csv", analyst_csv),
                (f"{bundle_id}.blocklist.txt", blocklist),
                (f"{bundle_id}.LICENSE.txt", license_text("ioc_bundle")),
            ):
                path = out_dir / name
                tmp = path.with_suffix(path.suffix + ".tmp")
                tmp.write_text(payload, encoding="utf-8")
                tmp.replace(path)
                written[name] = str(path)

            return {
                # Original response keys -- unchanged for existing callers.
                "status": "success",
                "file": written[f"{bundle_id}.{format}"],
                "count": len(validated),
                # Additive.
                "bundle_id": bundle_id,
                "bundle_format_version": BUNDLE_FORMAT_VERSION,
                "sku": commercial["sku"],
                "publishable": publishable,
                "gate_reason": gate_reason,
                "source": source_label,
                "enforcement_count": len(enforcement),
                "monitoring_count": len(monitoring),
                "stix_object_count": len(stix["objects"]),
                "misp_attribute_count": len(misp["Event"]["Attribute"]),
                "files": written,
                "validation": report.as_dict(),
            }
        except Exception as e:  # noqa: BLE001 -- preserved contract: never raise
            return {"status": "error", "message": str(e), "bundle_id": bundle_id}


# Global Instance
IOC_BUILDER = IOCBundleBuilder()
