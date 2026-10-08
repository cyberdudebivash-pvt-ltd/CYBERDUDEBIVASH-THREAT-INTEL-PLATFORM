#!/usr/bin/env python3
"""
scripts/attack_release_pin.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- ATT&CK release pin generator (P0 #721)
==========================================================================
Writes data/attck/attack_release_pin.json: the identity of the official MITRE
ATT&CK Enterprise release that data/attck/enterprise-attack.json (the repo's
condensed sync) has been VERIFIED against, plus the list of retired (revoked)
technique ids and the explicitly approved legacy aliases.

Why a separate pin: the condensed sync records no ATT&CK release number, so no
version could honestly be claimed. This script derives one by exact comparison
against an operator-supplied official release file -- it never trusts a label.

Usage (offline; the official file is downloaded by the operator, e.g.):
  curl -o /tmp/ea.json https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack-19.2.json
  python3 -I scripts/attack_release_pin.py --official /tmp/ea.json

Fails (exit 1, writes nothing) if the snapshot's current-technique id/name set
differs from the official release -- i.e. the snapshot is stale or wrong.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "data" / "attck" / "enterprise-attack.json"
PIN = ROOT / "data" / "attck" / "attack_release_pin.json"

# Legacy ids this platform published that are NOT in the official release. ONLY ids listed
# here may be normalised; every other unknown/retired id is suppressed for review.
APPROVED_LEGACY_ALIASES = {
    "T1190.001": {
        "maps_to": "T1190",
        "reason": "Internal 'SQL Injection' alias used by apex_mitre_attack_engine before P0 #721; "
                  "T1190 has no sub-techniques (absent from every official release).",
    },
}


def _ext(o: dict):
    for r in o.get("external_references", []):
        if r.get("source_name") == "mitre-attack":
            return r.get("external_id")
    return None


def build(official_path: Path) -> dict:
    raw = official_path.read_bytes()
    official = json.loads(raw)
    objs = official["objects"]
    coll = [o for o in objs if o.get("type") == "x-mitre-collection"]
    if len(coll) != 1:
        raise SystemExit("official file must contain exactly one x-mitre-collection")
    byid = {o["id"]: o for o in objs}
    cur, retired = {}, {}
    rel = [o for o in objs if o.get("type") == "relationship" and o.get("relationship_type") == "revoked-by"]
    for o in objs:
        if o.get("type") != "attack-pattern":
            continue
        eid = _ext(o)
        if not eid:
            continue
        if o.get("revoked"):
            rb = sorted({_ext(byid[r["target_ref"]]) for r in rel
                         if r["source_ref"] == o["id"] and r["target_ref"] in byid} - {None})
            retired[eid] = {"name": o["name"], "revoked_by": rb}
        elif not o.get("x_mitre_deprecated"):
            cur[eid] = o["name"]

    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    snap_map = {t["attck_id"]: t["name"] for t in snap["techniques"]}
    if snap_map != cur:
        only_s, only_o = sorted(set(snap_map) - set(cur)), sorted(set(cur) - set(snap_map))
        diff_names = sorted(i for i in set(snap_map) & set(cur) if snap_map[i] != cur[i])
        raise SystemExit(f"snapshot != official {coll[0]['x_mitre_version']}: only-in-snapshot={only_s[:8]} "
                         f"only-in-official={only_o[:8]} name-diffs={diff_names[:8]}")
    return {
        "schema": "attack_release_pin/1",
        "framework": "MITRE ATT&CK Enterprise",
        "release": coll[0]["x_mitre_version"],
        "release_major": coll[0]["x_mitre_version"].split(".")[0],
        "release_modified": coll[0].get("modified"),
        "official_source": "https://github.com/mitre-attack/attack-stix-data (enterprise-attack/enterprise-attack-"
                           f"{coll[0]['x_mitre_version']}.json)",
        "official_file_sha256": hashlib.sha256(raw).hexdigest(),
        "snapshot_file": "data/attck/enterprise-attack.json",
        "snapshot_content_hash": snap.get("content_hash"),
        "snapshot_verified_equal_to_official": True,
        "current_technique_count": len(cur),
        "verified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "approved_legacy_aliases": APPROVED_LEGACY_ALIASES,
        "retired_techniques": dict(sorted(retired.items())),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--official", required=True, type=Path, help="official enterprise-attack-<release>.json")
    ap.add_argument("--out", type=Path, default=PIN)
    a = ap.parse_args()
    pin = build(a.official)
    a.out.write_text(json.dumps(pin, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"pinned ATT&CK {pin['release']} ({pin['current_technique_count']} current, "
          f"{len(pin['retired_techniques'])} retired) -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
