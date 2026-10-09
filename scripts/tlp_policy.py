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
                            commit).  An approved entry binds a source id to the hostnames that collector
                            is known to publish from; the item's source URL must resolve to one of them, so
                            a bare "source" string supplied by feed text cannot self-approve.  Policy
                            assignment never applies to an item with ANY explicit label.
  * MIXED sources        -> the effective label is the MOST RESTRICTIVE of the item's own labels
                            (`tlp`, `tlp_label`) and the labels carried by merged/evidence components
                            (COMPONENT_FIELDS).  A CLEAR aggregate never launders a restricted, invalid or
                            unmigrated-legacy upstream label.  Components that carry no label cannot be
                            proven restricted and are not counted against the item (limitation: provenance
                            that is not in the record cannot be checked here).
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
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO_ROOT / "config" / "tlp_publication_policy.json"

LABELS_V2 = ("TLP:RED", "TLP:AMBER+STRICT", "TLP:AMBER", "TLP:GREEN", "TLP:CLEAR")
RESTRICTED = frozenset(LABELS_V2) - {"TLP:CLEAR"}
LEGACY_V1 = frozenset({"TLP:WHITE"})

MISSING, VALID, LEGACY, INVALID = "MISSING", "VALID", "LEGACY_V1", "INVALID"

# Secondary label-bearing fields on the item itself, and list fields whose dict entries describe the
# upstream documents an aggregated dossier was built from.  Secondary labels can only RESTRICT.
SECONDARY_LABEL_FIELDS = ("tlp_label",)
COMPONENT_FIELDS = ("evidence_chain", "sources", "merged_from", "source_documents", "corroborating_sources")
COMPONENT_LABEL_KEYS = ("tlp", "tlp_label")

_DEFAULT_POLICY: Dict[str, Any] = {
    "legacy_white_treated_as_clear": False,
    "first_party_public_sources": [],
}


_TLP_WORD = re.compile(r"\bTLP\b", re.IGNORECASE)
_LBL = r"(?:CLEAR|WHITE|GREEN|AMBER(?:\s*\+\s*STRICT)?|RED)"
_TLP_TOKEN = re.compile(
    r"\bTLP\s*[:\-]?\s*(?:TLP\s*[:\-]?\s*)*(?P<first>[A-Za-z]+(?:\s*\+\s*STRICT)?)"
    r"(?P<more>(?:\s*(?:[/,;|&]|\band\b|\bor\b)\s*(?:TLP\s*[:\-]?\s*)?" + _LBL + r"\b)*)", re.IGNORECASE)
_MORE_LABEL = re.compile(_LBL, re.IGNORECASE)


def normalize_label_text(text: str) -> str:
    """NFKC-normalise and drop invisible/format characters (zero-width joiners, BOMs, bidi controls) so a label cannot
    be disguised from the scanners.  Look-alike letters from other scripts survive normalisation on purpose: they
    then fail to parse as a valid label and are denied."""
    t = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in t if unicodedata.category(ch) not in ("Cf", "Cc") or ch in "\t\n\r ")


def scan_tlp_tokens(text: Any, lenient: bool = False) -> List[str]:
    """Every TLP marking found in free text, in order, as canonical labels ('TLP:CLEAR', ...) or 'INVALID' for a
    marking that is not a recognised label (e.g. a look-alike).  The WORD 'TLP' with nothing parseable after it also
    yields 'INVALID'.  Never returns an empty list for text that mentions TLP at all.

    lenient=True is for running prose (HTML body text): only markings made of the label vocabulary are reported, so
    ordinary phrases such as "TLP Banner" are not mistaken for an unrecognised marking."""
    if not isinstance(text, str):
        return []
    t = normalize_label_text(text)
    if not _TLP_WORD.search(t):
        return []
    out: List[str] = []
    for m in _TLP_TOKEN.finditer(t):
        if lenient and not re.fullmatch(_LBL, m.group("first").strip(), re.IGNORECASE):
            continue
        # "TLP:CLEAR/RED", "TLP:CLEAR, AMBER", "TLP:GREEN or CLEAR": every joined label is its own marking
        words = [m.group("first")] + [x.group(0) for x in _MORE_LABEL.finditer(m.group("more") or "")]
        for word in words:
            parsed = parse_label("TLP:" + re.sub(r"\s+", "", word.upper()))
            out.append(parsed["label"] if parsed["status"] in (VALID, LEGACY) else "INVALID")
    if lenient:
        return out
    return out or ["INVALID"]


def load_policy(path: Path = POLICY_PATH) -> Dict[str, Any]:
    """Policy with fail-closed defaults: any read/shape problem yields deny + empty allowlist."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        srcs = raw.get("first_party_public_sources", [])
        if not isinstance(srcs, list):
            return dict(_DEFAULT_POLICY)
        entries = []
        for e in srcs:
            # every entry must be {"source": str, "hosts": [str, ...]}; any malformed entry fails the whole policy closed
            if (not isinstance(e, dict) or not isinstance(e.get("source"), str) or not e["source"].strip()
                    or not isinstance(e.get("hosts"), list) or not e["hosts"]
                    or not all(isinstance(h, str) and h.strip() for h in e["hosts"])):
                return dict(_DEFAULT_POLICY)
            entries.append({"source": e["source"].strip().lower(),
                            "hosts": sorted({h.strip().lower().lstrip(".") for h in e["hosts"]})})
        return {"legacy_white_treated_as_clear": raw.get("legacy_white_treated_as_clear") is True,
                "first_party_public_sources": entries}
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


def _source_host(item: Dict[str, Any]) -> str:
    for k in ("source_url", "link", "url"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            try:
                return (urlsplit(v.strip()).hostname or "").lower()
            except ValueError:
                return ""
    return ""


def _approved_collector(item: Dict[str, Any], pol: Dict[str, Any]) -> bool:
    """True only when the item's source id AND its source-URL host both match one operator-approved entry."""
    src = str(item.get("source") or item.get("feed_source") or "").strip().lower()
    host = _source_host(item)
    if not src or not host:
        return False
    for e in pol.get("first_party_public_sources", []):
        if not isinstance(e, dict) or e.get("source") != src:
            continue
        if any(host == h or host.endswith("." + h) for h in e.get("hosts", [])):
            return True
    return False


def _upstream_labels(item: Dict[str, Any]) -> List[Any]:
    """Raw labels carried by secondary fields and by merged/evidence components (None entries are skipped)."""
    out: List[Any] = [item.get(k) for k in SECONDARY_LABEL_FIELDS if item.get(k) is not None]
    for f in COMPONENT_FIELDS:
        comps = item.get(f)
        if isinstance(comps, list):
            for c in comps:
                if isinstance(c, dict):
                    out.extend(c.get(k) for k in COMPONENT_LABEL_KEYS if c.get(k) is not None)
    return out


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

    # Most-restrictive-wins: an upstream/secondary label may only tighten the decision, never loosen it.
    # Free-text classification fields (e.g. "TLP:CLEAR; TLP:RED"): every marking counts, any restriction or any
    # CONFLICT between markings denies -- the first token never decides.
    for key in ("classification",):
        toks = scan_tlp_tokens(it.get(key))
        if not toks:
            continue
        distinct = set(toks)
        if distinct - {"TLP:CLEAR"}:
            bad = distinct - {"TLP:CLEAR"}
            if bad == {"TLP:WHITE"} and pol.get("legacy_white_treated_as_clear") and len(distinct) == 1:
                continue
            if "INVALID" in bad:
                return deny("INVALID_LABEL", f"{key} carries an unrecognised TLP marking")
            if distinct & {"TLP:WHITE"} and not pol.get("legacy_white_treated_as_clear"):
                return deny("LEGACY_LABEL_UNMIGRATED", f"{key} carries TLP:WHITE (TLP v1) not migrated by the operator")
            return deny("RESTRICTED_UPSTREAM_LABEL", f"{key} carries a restricted or conflicting TLP marking")
    for raw in _upstream_labels(it):
        q = parse_label(raw)
        if q["status"] == VALID and q["label"] != "TLP:CLEAR":
            return deny("RESTRICTED_UPSTREAM_LABEL",
                        f"an included source or secondary label is {q['label']}; the aggregate cannot be CLEAR")
        if q["status"] == INVALID:
            return deny("INVALID_LABEL", "unrecognised TLP label on an included source; invalid labels are never assignable")
        if q["status"] == LEGACY and not pol.get("legacy_white_treated_as_clear"):
            return deny("LEGACY_LABEL_UNMIGRATED", "an included source carries TLP:WHITE (TLP v1) not migrated by the operator")
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
    if _approved_collector(it, pol):
        return allow("TLP:CLEAR", "policy_first_party_public_source")
    return deny("MISSING_LABEL", "no TLP label and collector (source id + source-URL host) not approved as first-party public")


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
