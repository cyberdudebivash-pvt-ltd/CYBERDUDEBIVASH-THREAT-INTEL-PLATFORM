#!/usr/bin/env python3
"""
SENTINEL APEX - Commercial Asset Audit Gate
============================================
PURPOSE:
  Audits every sellable asset the product factory produces against the criteria
  that separate a commercial product from a build artefact, and emits a
  certification report to data/quality/.

  This exists because the pre-audit asset set failed on all of them: detection
  packs shipped empty Sigma/YARA arrays and unloadable IDS stubs with duplicate
  SIDs, IOC "bundles" contained news articles and zero indicators, the blocklist
  documented for firewall enforcement was dominated by CVE reference databases
  and source-code symbols, and no asset carried a licence, a price, an integrity
  manifest or deployment instructions.

GATES:
  ASSET-1  Every asset class is priced from the pricing SSOT
  ASSET-2  Every artefact carries commercial licence terms
  ASSET-3  Detection packs carry deployable content, not empty arrays
  ASSET-4  IDS rules parse as rule syntax with collision-free SIDs
  ASSET-5  IOC bundles contain validated indicators, not feed articles
  ASSET-6  Enforcement blocklists are free of benign reference infrastructure
  ASSET-7  Every artefact carries an integrity manifest / checksum
  ASSET-8  Every artefact carries deployment documentation
  ASSET-9  Playbooks cover the full NIST SP 800-61 lifecycle
  ASSET-10 No paid artefact is committed to the public repository

EXIT: 0 = PASS (warnings allowed), 1 = FAIL (blocking findings)
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from agent.product_factory import ioc_validation  # noqa: E402
from agent.product_factory.asset_catalog_builder import (  # noqa: E402
    ASSET_DIRS,
    STAGING_ROOT,
    build_catalog,
    is_primary_artefact,
)
from agent.product_factory.commercial_asset_spec import ASSET_CLASSES  # noqa: E402

QUALITY_DIR = REPO / "data" / "quality"
REPORT_PATH = QUALITY_DIR / "commercial_asset_audit.json"
AUDIT_VERSION = "1.0.0"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("asset_audit")

_SID_RE = re.compile(r"\bsid:(\d+);")
_RULE_RE = re.compile(r"^alert\s+\S+\s+\S+\s+\S+\s*->\s*\S+\s+\S+\s*\(.*\)\s*$")


class Gate:
    def __init__(self, gate_id: str, title: str) -> None:
        self.gate_id = gate_id
        self.title = title
        self.blockers: List[str] = []
        self.warnings: List[str] = []
        self.evidence: Dict = {}

    def block(self, msg: str) -> None:
        self.blockers.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def status(self) -> str:
        return "FAIL" if self.blockers else ("WARN" if self.warnings else "PASS")

    def as_dict(self) -> Dict:
        return {
            "gate_id": self.gate_id, "title": self.title, "status": self.status,
            "blockers": self.blockers, "warnings": self.warnings,
            "evidence": self.evidence,
        }


def _latest(directory: Path, pattern: str, asset_class: Optional[str] = None) -> Optional[Path]:
    """Newest primary artefact, excluding companion deliverables."""
    try:
        found = sorted(
            (p for p in directory.glob(pattern)
             if p.is_file() and (asset_class is None or is_primary_artefact(asset_class, p.name))),
            key=lambda p: p.name,
        )
    except OSError:
        return None
    return found[-1] if found else None


# ── Gates ────────────────────────────────────────────────────────────────────
def gate_pricing(catalog: Dict) -> Gate:
    g = Gate("ASSET-1", "Every asset class is priced from the pricing SSOT")
    for product in catalog["products"]:
        price = product["commercial"]["pricing"]
        if not price.get("priced"):
            g.block(f"{product['sku']}: unpriced -- {price.get('reason', 'no price resolved')}")
            continue
        if not isinstance(price.get("price_usd"), (int, float)) or price["price_usd"] <= 0:
            g.block(f"{product['sku']}: non-positive USD price {price.get('price_usd')!r}")
        if not isinstance(price.get("price_inr"), (int, float)) or price["price_inr"] <= 0:
            g.block(f"{product['sku']}: non-positive INR price {price.get('price_inr')!r}")
        if price.get("pricing_source") != "config/pricing.json":
            g.block(f"{product['sku']}: price not sourced from the SSOT")
    g.evidence = {
        p["sku"]: {
            "usd": p["commercial"]["pricing"].get("price_usd"),
            "inr": p["commercial"]["pricing"].get("price_inr"),
            "included_in": p["commercial"]["pricing"].get("included_in_tiers"),
        }
        for p in catalog["products"]
    }
    return g


def gate_licensing(catalog: Dict) -> Gate:
    g = Gate("ASSET-2", "Every artefact carries commercial licence terms")
    for product in catalog["products"]:
        lic = product["commercial"].get("licence") or {}
        for field in ("licence_id", "licensor", "grant", "permitted", "prohibited", "tlp"):
            if not lic.get(field):
                g.block(f"{product['sku']}: licence missing '{field}'")
        if lic.get("tlp") and not str(lic["tlp"]).startswith("TLP:"):
            g.block(f"{product['sku']}: invalid TLP marking {lic['tlp']!r}")
    pack = _latest(ASSET_DIRS["detection_pack"], "*.zip")
    if pack:
        with zipfile.ZipFile(pack) as zf:
            if "LICENSE.txt" not in zf.namelist():
                g.block(f"{pack.name}: archive ships no LICENSE.txt")
            else:
                g.evidence["detection_pack_licence_bytes"] = zf.getinfo("LICENSE.txt").file_size
    return g


def gate_detection_content() -> Gate:
    g = Gate("ASSET-3", "Detection packs carry deployable content, not empty arrays")
    pack = _latest(ASSET_DIRS["detection_pack"], "*.zip")
    if not pack:
        g.warn("no detection pack present to audit")
        return g
    with zipfile.ZipFile(pack) as zf:
        names = set(zf.namelist())
        required = {"README.md", "LICENSE.txt", "SHA256SUMS.txt", "manifest.json",
                    "metadata.json", "suricata/cdb-apex.rules", "snort/cdb-apex.rules",
                    "ioc/enforcement_blocklist.txt", "mitre/attack_navigator_layer.json"}
        for r in sorted(required - names):
            g.block(f"{pack.name}: missing required artefact '{r}'")

        meta = json.loads(zf.read("metadata.json").decode("utf-8")) if "metadata.json" in names else {}
        contents = meta.get("contents") or {}
        g.evidence = {"pack": pack.name, "file_count": len(names), "contents": contents,
                      "size_bytes": pack.stat().st_size}

        # The precise defect this gate exists for: content arrays that ship empty.
        for key in ("sigma_rules", "kql_queries", "suricata_rules", "enforcement_iocs"):
            if contents.get(key, 0) <= 0:
                g.block(f"{pack.name}: '{key}' is {contents.get(key, 0)} -- pack ships no {key}")

        if "sigma/sigma_rules.yml" in names:
            body = zf.read("sigma/sigma_rules.yml").decode("utf-8", "replace")
            if "detection:" not in body or "logsource:" not in body:
                g.block(f"{pack.name}: sigma bundle lacks detection/logsource blocks")
        else:
            g.block(f"{pack.name}: no sigma/sigma_rules.yml in archive")
    return g


def gate_ids_rules() -> Gate:
    g = Gate("ASSET-4", "IDS rules parse as rule syntax with collision-free SIDs")
    pack = _latest(ASSET_DIRS["detection_pack"], "*.zip")
    if not pack:
        g.warn("no detection pack present to audit")
        return g
    with zipfile.ZipFile(pack) as zf:
        for engine in ("suricata", "snort"):
            path = f"{engine}/cdb-apex.rules"
            if path not in zf.namelist():
                g.block(f"{pack.name}: no {path}")
                continue
            body = zf.read(path).decode("utf-8", "replace")
            rules = [ln.strip() for ln in body.splitlines()
                     if ln.strip().startswith("alert ")]
            if not rules:
                g.block(f"{pack.name}: {engine} ruleset contains zero rules")
                continue
            malformed = [r for r in rules if not _RULE_RE.match(r)]
            if malformed:
                g.block(f"{pack.name}: {engine} has {len(malformed)} malformed rule(s); "
                        f"first: {malformed[0][:100]}")
            sids = [int(m.group(1)) for r in rules if (m := _SID_RE.search(r))]
            if len(sids) != len(rules):
                g.block(f"{pack.name}: {engine} has {len(rules) - len(sids)} rule(s) without a sid")
            dupes = len(sids) - len(set(sids))
            if dupes:
                # Suricata refuses to load a ruleset with duplicate SIDs.
                g.block(f"{pack.name}: {engine} has {dupes} duplicate SID(s) -- ruleset will not load")
            for r in rules:
                if "msg:" not in r or "rev:" not in r or "classtype:" not in r:
                    g.block(f"{pack.name}: {engine} rule missing msg/rev/classtype: {r[:90]}")
                    break
            drops = [r for r in rules if r.startswith("drop ")]
            if drops:
                g.warn(f"{pack.name}: {engine} ships {len(drops)} inline-drop rule(s); "
                       "shipped content should alert until the customer tunes it")
            g.evidence[engine] = {"rules": len(rules), "unique_sids": len(set(sids))}
    return g


def gate_ioc_bundle() -> Gate:
    g = Gate("ASSET-5", "IOC bundles contain validated indicators, not feed articles")
    bundle = _latest(ASSET_DIRS["ioc_bundle"], "IOC-BNDL-*.json", "ioc_bundle")
    if not bundle:
        g.warn("no IOC bundle present to audit")
        return g
    data = json.loads(bundle.read_text(encoding="utf-8"))
    counts = data.get("counts") or {}
    g.evidence = {"bundle": bundle.name, "counts": counts,
                  "publishable": data.get("publishable")}

    indicators = data.get("indicators") or []
    if not indicators:
        g.block(f"{bundle.name}: bundle contains zero indicators")
    if data.get("ioc_count", 0) != len(indicators):
        g.block(f"{bundle.name}: ioc_count={data.get('ioc_count')} disagrees with "
                f"{len(indicators)} indicator objects")
    if not data.get("publishable", False):
        g.block(f"{bundle.name}: marked not publishable -- {data.get('gate_reason')}")

    # STIX companion must exist and be a real bundle of Indicator SDOs.
    stix_path = bundle.parent / f"{data.get('bundle_id')}.stix2.json"
    if not stix_path.exists():
        g.block(f"{bundle.name}: no STIX 2.1 companion at {stix_path.name}")
    else:
        stix = json.loads(stix_path.read_text(encoding="utf-8"))
        if stix.get("type") != "bundle":
            g.block(f"{stix_path.name}: not a STIX bundle")
        inds = [o for o in stix.get("objects", []) if o.get("type") == "indicator"]
        if not inds:
            g.block(f"{stix_path.name}: STIX bundle contains no Indicator objects")
        for obj in inds[:200]:
            if obj.get("spec_version") != "2.1":
                g.block(f"{stix_path.name}: indicator {obj.get('id')} is not spec_version 2.1")
                break
            pattern = obj.get("pattern") or ""
            if not (pattern.startswith("[") and pattern.endswith("]")):
                g.block(f"{stix_path.name}: malformed STIX pattern {pattern[:60]!r}")
                break
        g.evidence["stix_indicators"] = len(inds)
    return g


def gate_blocklist_hygiene() -> Gate:
    g = Gate("ASSET-6", "Enforcement blocklists are free of benign reference infrastructure")
    checked = 0
    pack = _latest(ASSET_DIRS["detection_pack"], "*.zip")
    sources: List[Tuple[str, str]] = []
    if pack:
        with zipfile.ZipFile(pack) as zf:
            if "ioc/enforcement_blocklist.txt" in zf.namelist():
                sources.append((f"{pack.name}:ioc/enforcement_blocklist.txt",
                                zf.read("ioc/enforcement_blocklist.txt").decode("utf-8", "replace")))
    bundle = _latest(ASSET_DIRS["ioc_bundle"], "IOC-BNDL-*.json", "ioc_bundle")
    if bundle:
        data = json.loads(bundle.read_text(encoding="utf-8"))
        bl = bundle.parent / f"{data.get('bundle_id')}.blocklist.txt"
        if bl.exists():
            sources.append((bl.name, bl.read_text(encoding="utf-8")))

    if not sources:
        g.warn("no enforcement blocklist present to audit")
        return g

    for label, body in sources:
        offenders: List[str] = []
        non_routable: List[str] = []
        for line in body.splitlines():
            v = line.strip()
            if not v or v.startswith("#"):
                continue
            checked += 1
            host = v
            if v.startswith(("http://", "https://")):
                from urllib.parse import urlsplit
                host = (urlsplit(v).hostname or "").lower()
            if host and ioc_validation.is_benign_host(host):
                offenders.append(v)
            res = ioc_validation.validate(v, ioc_validation.infer_type(v))
            if not res.accepted and res.reason.startswith("non_routable"):
                non_routable.append(v)
        if offenders:
            # Enforcing these would block the customer's own security workflow.
            g.block(f"{label}: {len(offenders)} benign/reference indicator(s) in an "
                    f"ENFORCEMENT list, e.g. {offenders[:5]}")
        if non_routable:
            g.block(f"{label}: {len(non_routable)} non-routable address(es), e.g. {non_routable[:3]}")
    g.evidence["indicators_checked"] = checked
    return g


def gate_integrity() -> Gate:
    g = Gate("ASSET-7", "Every artefact carries an integrity manifest / checksum")
    pack = _latest(ASSET_DIRS["detection_pack"], "*.zip")
    if not pack:
        g.warn("no detection pack present to audit")
    else:
        import hashlib
        with zipfile.ZipFile(pack) as zf:
            names = zf.namelist()
            if "SHA256SUMS.txt" not in names:
                g.block(f"{pack.name}: no SHA256SUMS.txt")
            else:
                declared = {}
                for line in zf.read("SHA256SUMS.txt").decode("utf-8").splitlines():
                    if "  " in line:
                        digest, name = line.split("  ", 1)
                        declared[name.strip()] = digest.strip()
                covered = set(declared) & set(names)
                uncovered = set(names) - set(declared) - {"SHA256SUMS.txt"}
                if uncovered:
                    g.block(f"{pack.name}: {len(uncovered)} file(s) absent from SHA256SUMS.txt: "
                            f"{sorted(uncovered)[:5]}")
                mismatched = [
                    n for n in sorted(covered)
                    if hashlib.sha256(zf.read(n)).hexdigest() != declared[n]
                ]
                if mismatched:
                    g.block(f"{pack.name}: checksum mismatch on {mismatched[:5]}")
                g.evidence["checksums_verified"] = len(covered)
    # The catalog must carry a SHA-256 per artefact so a customer can verify it.
    catalog_path = STAGING_ROOT / "catalog.json"
    if catalog_path.exists():
        cat = json.loads(catalog_path.read_text(encoding="utf-8"))
        for product in cat["products"]:
            for art in product["artefacts"]:
                if not art.get("sha256"):
                    g.block(f"catalog: {product['sku']}/{art['filename']} has no sha256")
    return g


def gate_documentation() -> Gate:
    g = Gate("ASSET-8", "Every artefact carries deployment documentation")
    pack = _latest(ASSET_DIRS["detection_pack"], "*.zip")
    if not pack:
        g.warn("no detection pack present to audit")
        return g
    with zipfile.ZipFile(pack) as zf:
        names = zf.namelist()
        guides = [n for n in names if n.startswith("deployment/") and n.endswith(".md")]
        if len(guides) < 3:
            g.block(f"{pack.name}: only {len(guides)} deployment guide(s); a multi-platform "
                    "product needs per-platform instructions")
        if "README.md" not in names:
            g.block(f"{pack.name}: no README.md")
        else:
            readme = zf.read("README.md").decode("utf-8", "replace")
            for token in ("SHA256SUMS", "enforcement", "monitoring", "LICENSE"):
                if token.lower() not in readme.lower():
                    g.block(f"{pack.name}: README does not cover '{token}'")
        g.evidence["deployment_guides"] = sorted(guides)
    return g


def gate_playbooks() -> Gate:
    g = Gate("ASSET-9", "Playbooks cover the full NIST SP 800-61 lifecycle")
    directory = ASSET_DIRS["soc_playbook"]
    try:
        books = sorted(p for p in directory.glob("PB-*.json")
                       if p.is_file() and is_primary_artefact("soc_playbook", p.name))
    except OSError:
        books = []
    if not books:
        g.warn("no playbooks present to audit")
        return g

    required = {"Preparation", "Detection and Analysis",
                "Containment, Eradication, and Recovery", "Post-Incident Activity"}
    for book in books:
        data = json.loads(book.read_text(encoding="utf-8"))
        phases = {ph.get("nist_phase") for ph in (data.get("phases") or [])}
        missing = required - phases
        if missing:
            g.block(f"{book.name}: missing NIST phase(s) {sorted(missing)}")
        if (data.get("task_count") or 0) < 20:
            g.block(f"{book.name}: only {data.get('task_count')} tasks -- not an operational playbook")
        if not data.get("mitre_attack"):
            g.block(f"{book.name}: no MITRE ATT&CK mapping")
        if not data.get("sla"):
            g.block(f"{book.name}: no response SLA")
        for legacy_key in ("title", "authority", "steps", "last_updated"):
            if legacy_key not in data:
                g.block(f"{book.name}: dropped backward-compatible key '{legacy_key}'")
    g.evidence = {"playbooks": len(books),
                  "threat_types": sorted(
                      json.loads(b.read_text(encoding='utf-8')).get("threat_type", "?")
                      for b in books)}
    return g


def gate_public_exposure() -> Gate:
    g = Gate("ASSET-10", "No paid artefact is committed to the public repository")
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "data/products", "data/premium_staging"],
            cwd=str(REPO), capture_output=True, text=True, timeout=60,
        ).stdout.split()
    except (subprocess.SubprocessError, OSError) as exc:
        g.warn(f"could not enumerate tracked files: {exc}")
        return g

    paid = [f for f in tracked if f.startswith("data/premium_staging/")]
    if paid:
        g.block(f"{len(paid)} paid artefact(s) tracked in git: {paid[:5]}")

    legacy = [f for f in tracked if f.startswith("data/products/")]
    if legacy:
        # Pre-existing 1.x artefacts. They contain no customer data and their
        # content is low value, but an ENTERPRISE-tier product directory in a
        # public repo is the same exposure class that was fixed for
        # premium/detections in v184.4.
        g.warn(f"{len(legacy)} legacy 1.x artefact(s) still tracked under data/products/; "
               "the factory no longer writes there (see sentinel-factory.yml)")
    g.evidence = {"tracked_paid": len(paid), "tracked_legacy": len(legacy)}
    return g


# ── Runner ───────────────────────────────────────────────────────────────────
def main() -> int:
    log.info("=" * 68)
    log.info("SENTINEL APEX -- Commercial Asset Audit v%s", AUDIT_VERSION)
    log.info("=" * 68)

    catalog = build_catalog()

    gates: List[Gate] = [
        gate_pricing(catalog),
        gate_licensing(catalog),
        gate_detection_content(),
        gate_ids_rules(),
        gate_ioc_bundle(),
        gate_blocklist_hygiene(),
        gate_integrity(),
        gate_documentation(),
        gate_playbooks(),
        gate_public_exposure(),
    ]

    blockers = sum(len(g.blockers) for g in gates)
    warnings = sum(len(g.warnings) for g in gates)
    passed = sum(1 for g in gates if g.status == "PASS")

    for g in gates:
        log.info("  [%s] %s -- %s", g.status.ljust(4), g.gate_id, g.title)
        for b in g.blockers:
            log.error("        BLOCKER: %s", b)
        for w in g.warnings:
            log.warning("        WARNING: %s", w)

    certification = "COMMERCIAL_RELEASE" if blockers == 0 else "BLOCKED"
    report = {
        "_meta": {
            "report": "SENTINEL APEX -- Commercial Asset Audit",
            "audit_version": AUDIT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "ioc_validation_engine": ioc_validation.ENGINE_VERSION,
        },
        "certification": certification,
        "summary": {
            "gates_total": len(gates),
            "gates_passed": passed,
            "blockers": blockers,
            "warnings": warnings,
            "asset_classes_audited": len(ASSET_CLASSES),
        },
        "catalog_summary": catalog["summary"],
        "gates": [g.as_dict() for g in gates],
    }

    QUALITY_DIR.mkdir(parents=True, exist_ok=True)
    tmp = REPORT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(REPORT_PATH)

    log.info("=" * 68)
    log.info("CERTIFICATION : %s", certification)
    log.info("GATES         : %d/%d passed, %d blocker(s), %d warning(s)",
             passed, len(gates), blockers, warnings)
    log.info("REPORT        : %s", REPORT_PATH.relative_to(REPO))
    log.info("=" * 68)
    return 0 if blockers == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
