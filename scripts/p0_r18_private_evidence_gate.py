#!/usr/bin/env python3
"""P0 R18: fail-closed, PRIVATE eight-dossier evidence-integrity preflight.

This does not validate source assertions, authorize publication, change R2, or grant GO.
Never store restricted evidence bundles or manifest data in the public repository.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import sys
from pathlib import Path
from typing import Any

REQUIRED_CVES = frozenset({
    "CVE-2026-71183", "CVE-2026-89191", "CVE-2026-12260",
    "CVE-2026-4894", "CVE-2026-105110", "CVE-2026-107466",
    "CVE-2026-87426", "CVE-2026-107510",
})
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_SHA = re.compile(r"^[a-f0-9]{40}$")
_STIX_ID = re.compile(
    r"^[a-z][a-z0-9-]*--[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def _read_ref(root: Path, ref: Any, label: str, seen: set[str], errors: list[str]) -> bytes | None:
    if not isinstance(ref, dict) or set(ref) != {"path", "sha256"}:
        errors.append(f"{label}: path and sha256 required")
        return None
    name, digest = ref["path"], ref["sha256"]
    if not isinstance(name, str) or not name or not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        errors.append(f"{label}: malformed relative path or sha256")
        return None
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts or relative == Path("."):
        errors.append(f"{label}: unsafe evidence path")
        return None
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        errors.append(f"{label}: evidence missing or outside private root")
        return None
    if str(target) in seen:
        errors.append(f"{label}: evidence path reused")
        return None
    seen.add(str(target))
    try:
        actual = target.read_bytes()
    except OSError:
        errors.append(f"{label}: unreadable evidence")
        return None
    if not actual or not hmac.compare_digest(hashlib.sha256(actual).hexdigest(), digest):
        errors.append(f"{label}: empty evidence or SHA-256 mismatch")
        return None
    return actual


def verify_bundle(root: Path, expected_deployment_sha: str) -> dict[str, Any]:
    """Verify exact case membership, private artifact bytes, basic format, and SHA binding.

    This is a necessary preflight, never sufficient proof of factual CTI claims.
    """
    errors: list[str] = []
    root = root.resolve()
    if not isinstance(expected_deployment_sha, str) or not _SHA.fullmatch(expected_deployment_sha):
        return {"status": "BLOCKED", "cases_verified": 0, "errors": ["Invalid expected deployment SHA"]}
    manifest = root / "index.json"
    if not manifest.is_file():
        return {"status": "BLOCKED", "cases_verified": 0, "errors": ["Private evidence index.json absent"]}
    try:
        index = json.loads(manifest.read_text(encoding="utf-8"))
    except (ValueError, OSError, UnicodeError):
        return {"status": "BLOCKED", "cases_verified": 0, "errors": ["Private evidence index unreadable or malformed"]}
    if not isinstance(index, dict) or index.get("schema_version") != 1 or not isinstance(index.get("cases"), list):
        return {"status": "BLOCKED", "cases_verified": 0, "errors": ["Evidence index schema invalid"]}
    if index.get("deployment_sha") != expected_deployment_sha:
        errors.append("Evidence deployment SHA does not equal checked deployment")
    cases = index["cases"]
    cves = [row.get("cve") for row in cases if isinstance(row, dict)]
    if (len(cases) != 8 or len(cves) != 8 or\n            any(not isinstance(cve, str) for cve in cves) or\n            set(cves) != REQUIRED_CVES or len(set(cves)) != 8):
        errors.append("Eight unique, exact target CVE records are required")
    seen: set[str] = set()
    completed = 0
    for row in cases:
        if not isinstance(row, dict) or row.get("cve") not in REQUIRED_CVES:
            errors.append("Invalid target CVE case")
            continue
        cve = row["cve"]
        before = len(errors)
        blobs: dict[str, bytes | None] = {}
        for kind in ("record", "html", "pdf", "stix"):
            blobs[kind] = _read_ref(root, row.get(kind), f"{cve}/{kind}", seen, errors)
        proof = row.get("source_evidence")
        if not isinstance(proof, list) or not proof:
            errors.append(f"{cve}: independently reviewable source evidence required")
        else:
            for n, entry in enumerate(proof):
                _read_ref(root, entry, f"{cve}/source_evidence_{n}", seen, errors)
        if blobs["record"] is not None:
            try:
                rec = json.loads(blobs["record"])
                if not isinstance(rec, dict) or rec.get("cve_id") != cve or rec.get("tlp") != "TLP:CLEAR":
                    errors.append(f"{cve}: mismatched CVE or non-public TLP record")
            except (ValueError, UnicodeError):
                errors.append(f"{cve}: invalid source record JSON")
        if blobs["html"] is not None:
            try:
                page = blobs["html"].decode("utf-8")
                if "<html" not in page.lower() or cve not in page:
                    errors.append(f"{cve}: HTML document or CVE identifier missing")
            except UnicodeError:
                errors.append(f"{cve}: non-UTF8 HTML")
        if blobs["pdf"] is not None and not blobs["pdf"].startswith(b"%PDF-"):
            errors.append(f"{cve}: PDF signature invalid")
        if blobs["stix"] is not None:
            try:
                stix = json.loads(blobs["stix"])
                if not isinstance(stix, dict) or stix.get("type") != "bundle" or stix.get("spec_version") not in (None, "2.1") or not isinstance(stix.get("objects"), list) or not stix["objects"]:
                    errors.append(f"{cve}: invalid STIX 2.1 bundle structure")
                elif any(not isinstance(obj, dict) or not _STIX_ID.fullmatch(str(obj.get("id", ""))) for obj in stix["objects"]):
                    errors.append(f"{cve}: invalid STIX object identifier")
            except (ValueError, UnicodeError):
                errors.append(f"{cve}: malformed STIX JSON")
        if len(errors) == before:
            completed += 1
    return {"status": "EVIDENCE_BYTES_VERIFIED_NOT_RELEASE_GO" if not errors else "BLOCKED",
            "cases_verified": completed, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-evidence-root", type=Path, required=True)
    parser.add_argument("--expected-deployment-sha", required=True)
    args = parser.parse_args()
    result = verify_bundle(args.private_evidence_root, args.expected_deployment_sha)
    # Never print private record values, IOC contents, analyst names or evidence bytes.
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "EVIDENCE_BYTES_VERIFIED_NOT_RELEASE_GO" else 2


if __name__ == "__main__":
    sys.exit(main())
