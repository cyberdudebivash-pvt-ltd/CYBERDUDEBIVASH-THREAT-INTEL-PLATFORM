#!/usr/bin/env python3
"""
scripts/tlp_exposure_inventory.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- READ-ONLY historical exposure inventory (P0 #721 / #725, Phase 4)
=====================================================================================================
Builds the *private evidence ledger* of restricted-labelled (or unlabelled/invalid) advisories that the
repository / Pages artifact / R2 key-set references, so an operator can decide targeted retractions.

  * READ-ONLY.  Never deletes, purges, rewrites, uploads or calls a Cloudflare API.  The only optional network
    action is `--probe N`: at most N anonymous `HEAD` requests to public report URLs, status code only, body
    never read, never stored.  Default is 0 (fully offline).
  * The ledger holds an opaque reference (HMAC-SHA256 of the id under the operator's secret salt), the policy
    reason code, the TLP label, the public routes/object keys and operator guidance.  It NEVER holds titles,
    descriptions, IOC values or report bodies.
  * The ledger is evidence of a possible information-exposure incident: write it to a PRIVATE location.  This
    script refuses an `--out` path inside the git working tree so it cannot be committed by accident.
  * Output on stdout is counts only (safe for CI logs / public issues).

Usage:
  TLP_LEDGER_SALT=<secret> python3 scripts/tlp_exposure_inventory.py --out /secure/location/ledger.json [--probe 20]
(c) 2026 CyberDudeBivash Pvt. Ltd.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import tlp_policy  # noqa: E402
import tlp_public_boundary as tb  # noqa: E402

REPO_ROOT = _SCRIPTS_DIR.parent
PUBLIC_ORIGIN = "https://intel.cyberdudebivash.com"
# Advisory feeds/manifests whose records are reachable (or were reachable) anonymously.
FEED_SOURCES = ("api/feed.json", "feed.json", "api/feed_public.json", "api/feed_enterprise.json", "api/feed_mssp.json",
                "api/feed.baseline.json", "api/feed.trial.json", "api/apex_v2/priority.json",
                "api/apex_v2/critical.json", "api/v1/intel/latest.json", "api/v1/intel/latest_pro.json",
                "api/v1/intel/top10.json", "api/v1/intel/apex.json", "api/reports/index.json", "api/iocs/feed.json",
                "api/graph/nodes.json")
RESTRICTED_CODES = frozenset({"RESTRICTED_LABEL", "RESTRICTED_UPSTREAM_LABEL", "INVALID_LABEL", "LEGACY_LABEL_UNMIGRATED"})

# Operator guidance per artifact kind -- operations are PROPOSED, never executed here.
GUIDANCE = {
    "pages_report": {"op": "remove file from gh-pages via a reviewed commit; purge CDN URL; verify 404/410",
                     "cost": "0 R2 ops; 1 git commit; 1 URL purge (rate-limited API, no charge)",
                     "rollback": "revert the gh-pages commit (restores the SAME restricted bytes -- only do so on "
                                 "operator instruction); keep a private encrypted backup of the removed file first"},
    "pages_json": {"op": "regenerate artifact through scripts/tlp_public_boundary.py and redeploy Pages; verify feed no "
                         "longer lists the id", "cost": "0 R2 ops; 1 Pages deploy",
                   "rollback": "redeploy the previous dist artifact only on operator instruction"},
    "r2_report": {"op": "targeted DeleteObject of the exact key (no LIST, no prefix delete); purge Worker KV/CDN key",
                  "cost": "1 R2 DELETE per object (no Class A charge for DELETE; verify current R2 pricing); 1 KV "
                          "delete per cached key", "rollback": "re-PUT from the private backup taken before deletion"},
    "r2_json": {"op": "re-publish the object via scripts/r2_upload.py (TLP-verified copy overwrites the stale object)",
                "cost": "1 R2 PUT (Class A) per object, inside the existing MAX_R2_DATA_WRITES_PER_RUN budget",
                "rollback": "re-PUT the previous object from backup on operator instruction"},
}


def opaque_ref(intel_id: str, salt: bytes) -> str:
    return "ref-" + hmac.new(salt, intel_id.encode("utf-8"), hashlib.sha256).hexdigest()[:20]


def _records(doc: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(doc, list):
        for x in doc:
            if isinstance(x, dict):
                yield x
    elif isinstance(doc, dict):
        for k in ("items", "advisories", "entries", "data", "nodes", "reports", "top_critical_items"):
            v = doc.get(k)
            if isinstance(v, list):
                for x in v:
                    if isinstance(x, dict):
                        yield x


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def probe(url: str, timeout: float = 10.0) -> str:
    """One anonymous HEAD request; returns the HTTP status code as text or 'ERR'. Body is never read."""
    try:
        out = subprocess.run(["curl", "-sS", "-o", "/dev/null", "-I", "-m", str(int(timeout)), "-w", "%{http_code}", url],
                             capture_output=True, text=True, timeout=timeout + 5)
        code = out.stdout.strip()
        return code if code.isdigit() else "ERR"
    except (OSError, subprocess.SubprocessError):
        return "ERR"


def build_ledger(root: Path, salt: bytes, probe_limit: int = 0, policy: Optional[Dict[str, Any]] = None,
                 prober=probe) -> Dict[str, Any]:
    pol = policy if policy is not None else tlp_policy.load_policy()
    root = Path(root)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: Dict[str, Dict[str, Any]] = {}
    for rel in FEED_SOURCES:
        p = root / rel
        if not p.is_file():
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for rec in _records(doc):
            iid = rec.get("id")
            if iid is None:
                continue
            d = tlp_policy.publication_decision(rec, pol)
            if d["allowed"] or d["reason_code"] not in RESTRICTED_CODES:
                continue  # MISSING_LABEL is a classification gap, tracked separately -- not an exposure of a restricted label
            ref = opaque_ref(str(iid), salt)
            row = rows.setdefault(ref, {
                "opaque_ref": ref, "reason_code": d["reason_code"], "label": d["label"] or None,
                "in_public_manifests": [], "artifacts": [], "recommended_operations": [],
                "originator_notification_required": True, "evidence_timestamp": now,
                "verification_status": "NOT_VERIFIED_ANONYMOUSLY", "_id": str(iid)})
            if rel not in row["in_public_manifests"]:
                row["in_public_manifests"].append(rel)
    # reachable report pages / PDFs / JSON documents in the checkout (what Pages would serve)
    reports_dir = root / "reports"
    page_index: Dict[str, List[Path]] = {}
    if reports_dir.is_dir():
        want = {r["_id"] for r in rows.values()}
        for dp, _dn, fns in os.walk(reports_dir):
            for fn in fns:
                stem, ext = os.path.splitext(fn)
                if stem in want and ext in (".html", ".pdf"):
                    page_index.setdefault(stem, []).append(Path(dp) / fn)
    probes_left = max(0, int(probe_limit))
    for row in rows.values():
        iid = row["_id"]
        for pg in page_index.get(iid, []):
            route = "/" + pg.relative_to(root).as_posix()
            art = {"kind": "pages_report", "route": route, "storage": "GitHub Pages (gh-pages) + R2 reports bucket",
                   "access": "anonymous", "cache": "CDN edge + Worker KV (TTL not verified from the checkout)"}
            if probes_left > 0 and route.endswith(".html"):
                art["anonymous_http_status"] = prober(PUBLIC_ORIGIN + route)
                art["probed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                probes_left -= 1
                if art["anonymous_http_status"] == "200":
                    row["verification_status"] = "CONFIRMED_ANONYMOUSLY_ACCESSIBLE"
                elif row["verification_status"] == "NOT_VERIFIED_ANONYMOUSLY" and art["anonymous_http_status"] in ("404", "410"):
                    row["verification_status"] = "NOT_ACCESSIBLE_AT_PROBED_ROUTE"
            row["artifacts"].append(art)
        for m in row["in_public_manifests"]:
            row["artifacts"].append({"kind": "pages_json", "route": "/" + m, "storage": "GitHub Pages + R2 data bucket",
                                     "access": "anonymous", "cache": "see Cache-Control on the object"})
        kinds = {a["kind"] for a in row["artifacts"]}
        row["recommended_operations"] = [dict(kind=k, **GUIDANCE[k]) for k in ("pages_report", "pages_json") if k in kinds]
        if "pages_report" in kinds:
            row["recommended_operations"].append(dict(kind="r2_report", **GUIDANCE["r2_report"]))
        if row["in_public_manifests"]:
            row["recommended_operations"].append(dict(kind="r2_json", **GUIDANCE["r2_json"]))
    ledger_rows = []
    for row in sorted(rows.values(), key=lambda r: r["opaque_ref"]):
        row = {k: v for k, v in row.items() if k != "_id"}
        ledger_rows.append(row)
    return {
        "schema": "tlp_exposure_ledger/1",
        "generated_at": now,
        "classification": "PRIVATE -- possible information-exposure incident evidence; do not commit or attach to public issues",
        "policy": "config/tlp_publication_policy.json",
        "distinction": {
            "newly_prevented": "records the gates now withhold (see data/quality/*tlp*_report.json)",
            "previously_published_origin_objects": "artifacts listed below that exist in the checkout / published tree",
            "cached_historical_copies": "NOT inventoried offline -- requires CDN/KV inspection by the operator",
            "unverified_exposure": "rows with verification_status NOT_VERIFIED_ANONYMOUSLY",
            "confirmed_anonymous_accessibility": "rows with verification_status CONFIRMED_ANONYMOUSLY_ACCESSIBLE (HEAD 200)"},
        "rows": ledger_rows,
    }


def summarize(ledger: Dict[str, Any]) -> Dict[str, Any]:
    rows = ledger["rows"]
    by_label: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    pages = 0
    for r in rows:
        by_label[r["label"] or "UNLABELLED/INVALID"] = by_label.get(r["label"] or "UNLABELLED/INVALID", 0) + 1
        by_status[r["verification_status"]] = by_status.get(r["verification_status"], 0) + 1
        pages += sum(1 for a in r["artifacts"] if a["kind"] == "pages_report")
    return {"restricted_advisories": len(rows), "by_label": by_label, "by_verification_status": by_status,
            "reachable_report_files_in_tree": pages,
            "manifest_memberships": sum(len(r["in_public_manifests"]) for r in rows)}


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", type=Path, default=REPO_ROOT)
    ap.add_argument("--out", type=Path, required=True, help="PRIVATE ledger path (must be outside the git work tree)")
    ap.add_argument("--probe", type=int, default=0, help="max anonymous HEAD probes (default 0 = offline)")
    args = ap.parse_args(argv)
    salt = os.environ.get("TLP_LEDGER_SALT", "").encode("utf-8")
    if len(salt) < 16:
        print("refusing: set TLP_LEDGER_SALT (>=16 chars, operator-held secret) so opaque references cannot be "
              "reversed by guessing ids", file=sys.stderr)
        return 2
    if _inside(args.out, REPO_ROOT) or _inside(args.out, args.root):
        print("refusing: --out is inside the repository work tree; write the ledger to a private location", file=sys.stderr)
        return 2
    ledger = build_ledger(args.root, salt, args.probe)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(args.out, 0o600)
    print(json.dumps(summarize(ledger), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
