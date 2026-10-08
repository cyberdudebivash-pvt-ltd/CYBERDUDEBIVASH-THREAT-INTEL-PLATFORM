#!/usr/bin/env python3
"""
scripts/p0_721_dossier_integrity_audit.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Dossier Integrity Audit (P0 #721)
=====================================================================
Read-only measurement of the defect classes tracked in issue #721 across what
is ALREADY PUBLISHED in this checkout.  It reuses scripts/dossier_integrity.py
(the single authority) -- no rule is re-implemented here.

Measures
  manifest   data/apex_enriched_manifest.json
               - raw IOC entries vs qualified indicators (inflation)
               - CVSS-scored items whose severity label contradicts the CVSS band
               - unrated vulnerability records carrying a severity label
               - ID-shaped ATT&CK techniques that fail the pinned dataset
  api        api/**/*.json   -- invalid ATT&CK technique ids in published JSON
  reports    reports/**/*.html (--reports) -- rendered-page signatures of the
               pre-fix generators: placeholder IOC row, internal key labelled
               "STIX ID", unconditional "APPLIES" badges, fixed kill-chain text

Output   data/quality/p0_721_dossier_integrity_report.json
Exit     0 (report-only) unless --strict, then 1 if any customer-visible
         defect remains in the scanned artifacts.

A clean report on the *source* does not certify the deployed site: published
artifacts only change when the pipeline regenerates and redeploys them.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import dossier_integrity as di  # noqa: E402

MANIFEST = ROOT / "data" / "apex_enriched_manifest.json"
REPORT = ROOT / "data" / "quality" / "p0_721_dossier_integrity_report.json"
_TID = re.compile(r"\bT\d{4}\.\d{3}\b")

HTML_SIGNATURES = {
    "placeholder_ioc_row": re.compile(r"No IOCs in current data feed"),
    "internal_key_labelled_stix_id": re.compile(
        r"STIX ID</div><div class='kv-val'><code>(?:intel|intrusion-set)--"),
    "unconditional_applies_badge": re.compile(r"&#x25CF; APPLIES"),
    "fixed_kill_chain_template": re.compile(r"beacon interval 60s|Implant beacons to C2|Backdoor/RAT installed"),
    "css_blur_gate_with_content": re.compile(r'style="filter:blur\(4px\)'),
}


def audit_manifest() -> dict:
    if not MANIFEST.exists():
        return {"status": "BLOCKED", "reason": f"{MANIFEST.name} not present"}
    items = json.loads(MANIFEST.read_text(encoding="utf-8"))
    raw = qual = 0
    rejected: dict = {}
    inflated_items = contradiction = unrated_labelled = bad_tech = 0
    rated = 0
    for it in items:
        q = di.qualify_iocs(it.get("iocs"))
        n_raw = len(it.get("iocs") or [])
        raw += n_raw
        qual += q["count"]
        inflated_items += 1 if n_raw > q["count"] else 0
        for r in q["rejected"]:
            rejected[r["reason_class"]] = rejected.get(r["reason_class"], 0) + 1
        kev = di._ste.kev_confirmed(it)
        b = di.severity_basis(it, it.get("cvss_score"), kev)
        if it.get("cvss_score") not in (None, "", 0) and di.is_vulnerability_record(it) and not kev:
            rated += 1
            contradiction += 1 if b["conflict"] else 0
        elif not b["authoritative"] and str(it.get("severity") or "").upper() in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            unrated_labelled += 1
        _, rej = di.filter_valid_techniques(it.get("ttps") or [])
        bad_tech += len(rej)
    return {
        "status": "MEASURED", "items": len(items),
        "ioc": {"raw_entries": raw, "qualified": qual, "non_indicator_entries": raw - qual,
                "items_with_inflated_count": inflated_items, "rejected_by_class": rejected},
        "severity": {"cvss_scored_vulnerabilities": rated, "label_contradicts_cvss_band": contradiction,
                     "unrated_vulnerabilities_carrying_a_severity_label": unrated_labelled},
        "attack": {"invalid_id_shaped_techniques": bad_tech},
    }


def audit_api() -> dict:
    api = ROOT / "api"
    files = bad_files = bad_ids = 0
    examples: dict = {}
    for p in api.rglob("*.json") if api.exists() else []:
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        files += 1
        hit = [t for t in set(_TID.findall(txt)) if di.validate_technique(t)["status"] != "VALID"]
        if hit:
            bad_files += 1
            bad_ids += len(hit)
            for t in hit:
                examples.setdefault(t, str(p.relative_to(ROOT)))
    return {"status": "MEASURED", "json_files": files, "files_with_invalid_technique_ids": bad_files,
            "distinct_invalid_ids": sorted(examples), "first_seen_in": examples}


def audit_reports() -> dict:
    root = ROOT / "reports"
    counts = {k: 0 for k in HTML_SIGNATURES}
    pages = affected = bad_tid = 0
    for p in root.rglob("*.html") if root.exists() else []:
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        pages += 1
        hit = False
        for k, rx in HTML_SIGNATURES.items():
            if rx.search(txt):
                counts[k] += 1
                hit = True
        if any(di.validate_technique(t)["status"] != "VALID" for t in set(_TID.findall(txt))):
            bad_tid += 1
            hit = True
        affected += 1 if hit else 0
    return {"status": "MEASURED", "pages": pages, "pages_with_any_defect_signature": affected,
            "pages_with_invalid_technique_id": bad_tid, "signature_page_counts": counts}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--reports", action="store_true", help="also scan reports/**/*.html (~22k pages)")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any customer-visible defect remains")
    ap.add_argument("--no-write", action="store_true", help="do not write data/quality report")
    a = ap.parse_args()

    out = {
        "schema": "p0_721_dossier_integrity_report/1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "attack_dataset": di.attack_dataset_pin(),
        "manifest": audit_manifest(),
        "api": audit_api(),
        "reports": audit_reports() if a.reports else {"status": "NOT_RUN", "reason": "pass --reports"},
        "note": "Measures published artifacts in this checkout; does not certify the live deployment.",
    }
    m, api, rep = out["manifest"], out["api"], out["reports"]
    defects = (
        (m.get("ioc", {}).get("non_indicator_entries", 0)) + (m.get("severity", {}).get("label_contradicts_cvss_band", 0))
        + (m.get("severity", {}).get("unrated_vulnerabilities_carrying_a_severity_label", 0))
        + (m.get("attack", {}).get("invalid_id_shaped_techniques", 0)) + api.get("files_with_invalid_technique_ids", 0)
        + rep.get("pages_with_any_defect_signature", 0)
    )
    out["customer_visible_defects_in_scanned_artifacts"] = defects
    if not a.no_write:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("manifest", "api", "reports", "customer_visible_defects_in_scanned_artifacts")}, indent=2))
    return 1 if (a.strict and defects) else 0


if __name__ == "__main__":
    sys.exit(main())
