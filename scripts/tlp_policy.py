#!/usr/bin/env python3
"""
scripts/tlp_policy.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- TLP publication policy (P0 #721)
====================================================================
The single authority that decides whether an advisory may be distributed
ANONYMOUSLY (public HTML, static API JSON, R2/CDN objects, PDFs).  FIRST TLP v2.0.

Rules (fail closed; there is no bypass flag):
  * TLP:CLEAR            -> publishable.  The only directly public state.
  * TLP:GREEN / AMBER / AMBER+STRICT / RED -> quarantined (restricted).
  * MISSING label        -> quarantined, unless the operator has approved the item's collector in
                            config/tlp_publication_policy.json::first_party_public_sources (a reviewed
                            commit).  Policy assignment never applies to an item with ANY explicit label.
  * INVALID label        -> quarantined.  Never assignable.
  * TLP:WHITE (v1)       -> quarantined until legacy_white_treated_as_clear is set by the operator.
  * Third-party content is never relabelled: a decision never rewrites `item["tlp"]`.
  * Unreadable / absent policy file -> built-in defaults (deny; empty allowlist).

Callers MUST consult publication_decision() before emitting bytes.  A decision is a pure function of
the item and the policy file, so producers, publishers and feed writers agree.
(c) 2026 CyberDudeBivash Pvt. Ltd.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO_ROOT / "config" / "tlp_publication_policy.json"

LABELS_V2 = ("TLP:RED", "TLP:AMBER+STRICT", "TLP:AMBER", "TLP:GREEN", "TLP:CLEAR")
RESTRICTED = frozenset(LABELS_V2) - {"TLP:CLEAR"}
LEGACY_V1 = frozenset({"TLP:WHITE"})

MISSING, VALID, LEGACY, INVALID = "MISSING", "VALID", "LEGACY_V1", "INVALID"

_DEFAULT_POLICY: Dict[str, Any] = {
    "legacy_white_treated_as_clear": False,
    "first_party_public_sources": [],
}


def load_policy(path: Path = POLICY_PATH) -> Dict[str, Any]:
    """Policy with fail-closed defaults: any read/shape problem yields deny + empty allowlist."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        srcs = raw.get("first_party_public_sources", [])
        if not isinstance(srcs, list) or not all(isinstance(s, str) for s in srcs):
            return dict(_DEFAULT_POLICY)
        return {"legacy_white_treated_as_clear": raw.get("legacy_white_treated_as_clear") is True,
                "first_party_public_sources": [s.strip().lower() for s in srcs if s.strip()]}
    except (OSError, ValueError, AttributeError):
        return dict(_DEFAULT_POLICY)


def parse_label(value: Any) -> Dict[str, str]:
    """Classify a raw label.  Returns {status, label}; label is canonical for VALID/LEGACY."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return {"status": MISSING, "label": ""}
    if not isinstance(value, str):
        return {"status": INVALID, "label": ""}
    v = re.sub(r"\s+", "", value.strip().upper()).replace("TLP-", "TLP:")
    v = v.replace("AMBER+STRICT", "AMBER+STRICT")
    if v in LABELS_V2:
        return {"status": VALID, "label": v}
    if v in LEGACY_V1:
        return {"status": LEGACY, "label": v}
    return {"status": INVALID, "label": ""}


def publication_decision(item: Any, policy: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Decide anonymous publication for one advisory.

    Returns {allowed, state (PUBLISH|QUARANTINE), label, assignment, reason_code, reason}.
    `label` is the label that may be DISPLAYED if allowed (never invented for a denied item).
    """
    pol = policy if policy is not None else load_policy()
    it = item if isinstance(item, dict) else {}
    p = parse_label(it.get("tlp"))

    def deny(code: str, reason: str) -> Dict[str, Any]:
        return {"allowed": False, "state": "QUARANTINE", "label": p["label"], "assignment": None,
                "reason_code": code, "reason": reason}

    def allow(label: str, assignment: str) -> Dict[str, Any]:
        return {"allowed": True, "state": "PUBLISH", "label": label, "assignment": assignment,
                "reason_code": "OK", "reason": ""}

    if p["status"] == VALID:
        if p["label"] == "TLP:CLEAR":
            return allow("TLP:CLEAR", "explicit")
        return deny("RESTRICTED_LABEL", f"{p['label']} does not permit anonymous public distribution")
    if p["status"] == LEGACY:
        if pol.get("legacy_white_treated_as_clear"):
            return allow("TLP:CLEAR", "legacy_white_operator_migration")
        return deny("LEGACY_LABEL_UNMIGRATED", "TLP:WHITE (TLP v1) has not been migrated by the operator")
    if p["status"] == INVALID:
        return deny("INVALID_LABEL", "unrecognised TLP label; invalid labels are never assignable")
    # MISSING: only an operator-approved first-party-public collector may be policy-assigned
    src = str(it.get("source") or it.get("feed_source") or "").strip().lower()
    if src and src in pol.get("first_party_public_sources", []):
        return allow("TLP:CLEAR", "policy_first_party_public_source")
    return deny("MISSING_LABEL", "no TLP label and collector not approved as first-party public")


def partition_publishable(items: Iterable[Any], policy: Dict[str, Any] | None = None
                          ) -> Tuple[List[Any], List[Dict[str, Any]]]:
    """(publishable items, quarantine rows) -- for feed/export writers."""
    pol = policy if policy is not None else load_policy()
    ok: List[Any] = []
    held: List[Dict[str, Any]] = []
    for it in items or []:
        d = publication_decision(it, pol)
        if d["allowed"]:
            ok.append(it)
        else:
            iid = it.get("id") if isinstance(it, dict) else None
            held.append({"id": iid, "reason_code": d["reason_code"], "reason": d["reason"],
                         "label": d["label"] or None})
    return ok, held


class PublicationDenied(Exception):
    """Raised by emitters that were handed an item the policy does not allow to be published."""

    def __init__(self, decision: Dict[str, Any]):
        super().__init__(f"{decision['reason_code']}: {decision['reason']}")
        self.decision = decision
