#!/usr/bin/env python3
"""
scripts/dossier_integrity.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Dossier Integrity Authority (P0 #721)
=========================================================================
Single, side-effect-free authority for the evidence rules every customer
dossier renderer must obey.  It COMPOSES existing engines; it does not
re-implement them:

  * IOC syntax / non-IOC classification  -> scripts/ioc_truth_engine.classify_ioc
  * ATT&CK technique authority           -> data/attck/enterprise-attack.json
                                            (the repo's pinned MITRE sync)

What this module adds (and nothing else):

  1. qualify_iocs()          one qualified IOC collection => one count.
                             Empty collection == 0.  References, filenames,
                             software names, duplicates and AI-generated
                             candidates are NEVER counted.
  2. ioc_evidence_state()    SOURCE_REPORTED / UNVERIFIED / GENERATED.
                             "OBSERVED" is never inferred; it requires an
                             explicit observation marker plus a source.
  3. validate_technique()    ATT&CK IDs checked against the pinned dataset
                             (e.g. T1190 has no sub-techniques, so T1190.001
                             is rejected and normalised to its parent).
  4. valid_stix_id()         STIX 2.1 `object-type--UUID` check, so internal
                             report keys are never labelled "STIX ID".
  5. severity_basis()        a composite/heuristic severity is not shown as a
                             rating when no authoritative CVSS / KEV exists.
  6. tlp_public_conflict()   TLP labels that forbid public posting.

Missing data stays missing: every helper returns None / an explicit state
instead of 0, LOW, HIGH or "confirmed".

Mandatory-fix map (issue #721):  P0-1 IOC counts, P0-2 STIX ids, P0-3 ATT&CK,
P0-4 severity, P0-7 TLP.  Pure stdlib; safe to import from any renderer.
(c) 2026 CyberDudeBivash Pvt. Ltd.
"""
from __future__ import annotations

import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_REPO = Path(__file__).resolve().parent.parent
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import ioc_truth_engine as _ite  # noqa: E402  (reuse: classify_ioc is the IOC authority)
import severity_epss_truth as _ste  # noqa: E402  (reuse: cvss_rating / verified_cvss are the severity SSOT)

ATTACK_DATASET_PATH = _REPO / "data" / "attck" / "enterprise-attack.json"

# Claim / evidence states shared with the claim-ledger vocabulary in #721.
VERIFIED = "VERIFIED"
SOURCE_REPORTED = "SOURCE_REPORTED"
ANALYST_INFERENCE = "ANALYST_INFERENCE"
HYPOTHESIS = "HYPOTHESIS"
UNKNOWN = "UNKNOWN"
UNVERIFIED = "UNVERIFIED"
GENERATED = "GENERATED"
OBSERVED = "OBSERVED"

# =============================================================================
# 1. IOC qualification  (one collection -> one count)
# =============================================================================

_REFANG = (("[.]", "."), ("(.)", "."), ("{.}", "."), ("[:]", ":"), ("[://]", "://"))
_SOURCE_KEYS = ("source", "source_url", "reference", "reported_by", "feed", "origin")


def _refang(value: str) -> str:
    v = value.strip()
    for a, b in _REFANG:
        v = v.replace(a, b)
    v = re.sub(r"^hxxp", "http", v, flags=re.IGNORECASE)
    if "://" not in v and "/" not in v:
        v = v.rstrip(".")          # FQDN root-dot is not part of the identity
    return v


def _canonical_key(ioc_type: str, value: str) -> Tuple[str, str]:
    """Identity used for de-duplication (case/defang/trailing-dot insensitive)."""
    t = (ioc_type or "").upper()
    v = value.strip()
    if t in ("DOMAIN", "FQDN", "EMAIL", "MD5", "SHA1", "SHA256", "SHA512",
             "IPV6", "WALLET_ETH"):
        v = v.lower().rstrip(".")
    elif t == "URL":
        m = re.match(r"^(https?)://([^/\s]+)(.*)$", v, flags=re.IGNORECASE)
        if m:
            v = f"{m.group(1).lower()}://{m.group(2).lower().rstrip('.')}{m.group(3)}"
    return t, v


def _ioc_value(ioc: Any) -> str:
    if isinstance(ioc, dict):
        return str(ioc.get("value") if ioc.get("value") is not None else "")
    return "" if ioc is None else str(ioc)


def ioc_evidence_state(ioc: Any) -> str:
    """Provenance state of one IOC.  Never returns OBSERVED unless the record
    carries an explicit observation marker AND a source."""
    if not isinstance(ioc, dict):
        return UNVERIFIED          # legacy bare string: provenance not recorded
    if ioc.get("generated"):
        return GENERATED
    has_source = any(ioc.get(k) for k in _SOURCE_KEYS)
    if ioc.get("observed_in_wild") is True or ioc.get("evidence_state") == OBSERVED:
        return OBSERVED if has_source else UNVERIFIED
    if has_source:
        return SOURCE_REPORTED
    return UNVERIFIED


def qualify_iocs(raw: Any) -> Dict[str, Any]:
    """Split a raw IOC collection into the ONLY set that may be counted.

    Returns:
      actionable      list  -- original shape preserved (str stays str, dict
                               stays dict, value re-fanged); the sole input to
                               every displayed/exported count
      generated       list  -- AI-derived candidates (never counted)
      rejected        list  -- [{value, reason_class, reason}] audit trail
      duplicates      int
      count           int   -- len(actionable); the single authoritative count
      by_state        dict  -- evidence-state breakdown of `actionable`
    """
    items: List[Any] = list(raw) if isinstance(raw, (list, tuple)) else []
    actionable: List[Any] = []
    generated: List[Any] = []
    rejected: List[Dict[str, str]] = []
    seen: set = set()
    duplicates = 0

    for ioc in items:
        value = _refang(_ioc_value(ioc))
        verdict = _ite.classify_ioc(value)
        if verdict["category"] != "operational_ioc":
            rejected.append({
                "value": value[:200],
                "reason_class": verdict.get("non_ioc_class") or "invalid_indicator",
                "reason": verdict.get("rejection_reason") or "not an operational indicator",
            })
            continue
        key = _canonical_key(verdict["ioc_type"], value)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        if isinstance(ioc, dict):
            out = dict(ioc)
            out["value"] = value
            out["ioc_type"] = verdict["ioc_type"]
            out["evidence_state"] = ioc_evidence_state(ioc)
        else:
            out = value
        if ioc_evidence_state(ioc) == GENERATED:
            generated.append(out)
        else:
            actionable.append(out)

    by_state: Dict[str, int] = {}
    for a in actionable:
        s = ioc_evidence_state(a)
        by_state[s] = by_state.get(s, 0) + 1
    return {
        "actionable": actionable,
        "generated": generated,
        "rejected": rejected,
        "duplicates": duplicates,
        "count": len(actionable),
        "by_state": by_state,
    }


# =============================================================================
# 2. ATT&CK authority (pinned dataset)
# =============================================================================

_TECH_RE = re.compile(r"^T\d{4}(?:\.\d{3})?$")
_ID_LIKE_RE = re.compile(r"^T\d{3,5}(?:\.\d+)?$", re.IGNORECASE)


@lru_cache(maxsize=1)
def _attack_index() -> Optional[Dict[str, Dict[str, Any]]]:
    try:
        data = json.loads(ATTACK_DATASET_PATH.read_text(encoding="utf-8"))
        idx = {t["attck_id"]: t for t in data.get("techniques", []) if t.get("attck_id")}
        return idx or None
    except (OSError, ValueError, KeyError, TypeError):
        return None


@lru_cache(maxsize=1)
def attack_dataset_pin() -> Dict[str, Any]:
    """Identity of the dataset every technique is validated against."""
    try:
        d = json.loads(ATTACK_DATASET_PATH.read_text(encoding="utf-8"))
        return {
            "available": True,
            "source": d.get("source_bundle") or d.get("source"),
            "synced_at": d.get("synced_at"),
            "content_hash": d.get("content_hash"),
            "technique_count": len(d.get("techniques", [])),
            # The sync does not record an ATT&CK release number; never invent one.
            "attack_release": d.get("attack_release") or None,
        }
    except (OSError, ValueError):
        return {"available": False, "attack_release": None}


def validate_technique(tid: Any) -> Dict[str, Any]:
    """Validate one ATT&CK technique ID against the pinned dataset.

    status: VALID | SUBTECHNIQUE_NOT_DEFINED | UNKNOWN_TECHNIQUE | MALFORMED |
            DATASET_UNAVAILABLE   (callers must not claim 'validated' on the last)
    """
    t = str(tid or "").strip().upper()
    res: Dict[str, Any] = {"input": str(tid), "id": t, "status": "MALFORMED",
                           "name": None, "tactics": [], "parent_id": None}
    if not _TECH_RE.match(t):
        return res
    idx = _attack_index()
    if idx is None:
        res["status"] = "DATASET_UNAVAILABLE"
        return res
    if t in idx:
        res.update(status="VALID", name=idx[t].get("name"),
                   tactics=list(idx[t].get("tactics") or []))
        return res
    parent = t.split(".")[0]
    if "." in t and parent in idx:
        res.update(status="SUBTECHNIQUE_NOT_DEFINED", parent_id=parent,
                   name=idx[parent].get("name"))
        return res
    res["status"] = "UNKNOWN_TECHNIQUE"
    return res


def technique_name(tid: Any) -> Optional[str]:
    """Official ATT&CK name, or None -- never a made-up label."""
    r = validate_technique(tid)
    return r["name"] if r["status"] in ("VALID", "SUBTECHNIQUE_NOT_DEFINED") else None


def canonical_technique_id(tid: Any) -> Optional[str]:
    """The ID that may be published: itself if valid, its parent if the
    sub-technique does not exist, else None (suppress)."""
    r = validate_technique(tid)
    if r["status"] == "VALID":
        return r["id"]
    if r["status"] == "SUBTECHNIQUE_NOT_DEFINED":
        return r["parent_id"]
    return None


def technique_id_of(entry: Any) -> str:
    """Extract an ID from the several shapes found in feed records."""
    if isinstance(entry, dict):
        return str(entry.get("technique_id") or entry.get("id") or entry.get("attck_id") or "")
    return str(entry or "")


def filter_valid_techniques(entries: Iterable[Any]) -> Tuple[List[Any], List[Dict[str, Any]]]:
    """Return (publishable entries with canonical IDs, rejected audit rows).
    Order-preserving; duplicates after canonicalisation are dropped."""
    out: List[Any] = []
    rejected: List[Dict[str, Any]] = []
    seen: set = set()
    for e in entries or []:
        raw = technique_id_of(e)
        if not _ID_LIKE_RE.match(raw.strip()):
            out.append(e)          # a technique NAME / tactic label: not an ID, nothing to validate
            continue
        canon = canonical_technique_id(raw)
        if canon is None:
            rejected.append(validate_technique(raw))
            continue
        if canon in seen:
            continue
        seen.add(canon)
        if isinstance(e, dict):
            ne = dict(e)
            for k in ("technique_id", "id", "attck_id"):
                if k in ne:
                    ne[k] = canon
            if canon != raw.strip().upper():
                ne["normalized_from"] = raw
            out.append(ne)
        else:
            out.append(canon)
    return out, rejected


# =============================================================================
# 3. STIX identifiers
# =============================================================================

_STIX_ID_RE = re.compile(
    r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*--"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def valid_stix_id(value: Any) -> bool:
    """STIX 2.1 identifier: `object-type--<RFC-4122 UUID>`."""
    return isinstance(value, str) and bool(_STIX_ID_RE.match(value))


# =============================================================================
# 4. Severity / priority honesty
# =============================================================================

_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,}", re.IGNORECASE)
_PRECONDITION_RE = re.compile(
    r"[^.;\n]*\b(unauthenticated|without authentication|authentication bypass|"
    r"auth(?:entication)? bypass|remote code execution|arbitrary code|"
    r"sql injection|command injection)\b[^.;\n]*", re.IGNORECASE)


_VULN_CLASS_RE = re.compile(
    r"\b(vulnerabilit\w*|vulnerable|flaws?|remote (?:code|command) execution|arbitrary (?:code|command)|rce|"
    r"sql injection|sqli|auth(?:entication)? bypass|code injection|command injection|path traversal|"
    r"deserialization|buffer overflow|use-after-free|privilege escalation|xss|ssrf|zero-?day)\b",
    re.IGNORECASE)


def is_vulnerability_record(item: Dict[str, Any]) -> bool:
    """A CVE id OR vulnerability-class language (news items often carry no CVE id).
    Such a record has a CVSS/KEV-backed severity or no severity rating at all."""
    text = f"{item.get('title') or ''} {item.get('description') or ''}"
    return bool(item.get("cve_id")) or bool(_CVE_RE.search(text)) or bool(_VULN_CLASS_RE.search(text))


_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def severity_basis(item: Dict[str, Any], cvss: Any, kev: bool) -> Dict[str, Any]:
    """What may be displayed as this record's severity, and why.

    * non-vulnerability record  -> pipeline label as-is (no CVSS exists for it)
    * CISA KEV listed           -> pipeline label as-is (platform KEV policy)
    * CVSS score present        -> the CVSS qualitative band of that score
      (severity_epss_truth.cvss_rating -- the repo's SSOT band function). The
      pipeline's composite label is disclosed when it disagrees.  Production
      data carries no CVSS vector, so the existing vector-verification stage
      cannot correct these; the basis text says the score is as reported.
    * otherwise (vulnerability, no CVSS, no KEV) -> UNRATED; the composite
      heuristic is not a rating and drives no patch deadline.
    A CVSS score of 0/blank is treated as missing (never as a rating).
    """
    sev = str(item.get("severity") or "UNKNOWN").upper()
    base = {"composite": sev, "conflict": False, "note": ""}
    if not is_vulnerability_record(item):
        return {**base, "authoritative": True, "display": sev, "basis": "non-vulnerability record"}
    try:
        score = float(cvss) if cvss not in (None, "") else None
    except (TypeError, ValueError):
        score = None
    band = _ste.cvss_rating(score) if score is not None else None
    if kev:
        # KEV keeps the platform's severity policy; a reported CVSS band may only RAISE it
        # (never show 'HIGH' beside a CVSS 9.8).
        if band and _RANK.get(band, 0) > _RANK.get(sev, 0):
            return {"authoritative": True, "display": band, "composite": sev, "conflict": True,
                    "basis": f"CISA KEV; CVSS {score:g} ({band})",
                    "note": f"CISA KEV listed; CVSS {score:g} is {band}; the APEX composite label {sev} is superseded"}
        return {**base, "authoritative": True, "display": sev, "basis": "CISA KEV"}
    if band:
        verified = _ste.verified_cvss(dict(item, cvss_score=score)) is not None
        basis = f"CVSS {score:g} ({'vector-verified' if verified else 'score as reported by source; vector unavailable to verify'})"
        conflict = band != sev
        return {"authoritative": True, "display": band, "composite": sev, "conflict": conflict, "basis": basis,
                "note": (f"{basis}; the APEX composite label {sev} disagrees and is superseded") if conflict else ""}
    return {"authoritative": False, "display": "UNRATED", "composite": sev, "conflict": False,
            "basis": "no authoritative CVSS or KEV listing available",
            "note": f"no authoritative CVSS or KEV listing available; APEX composite heuristic: {sev} (not a rating)"}


def source_stated_conditions(item: Dict[str, Any], limit: int = 2) -> List[str]:
    """Attack conditions the SOURCE text states, quoted (SOURCE_REPORTED).
    Used to inform triage without overriding or inventing a severity."""
    text = str(item.get("description") or item.get("title") or "")
    out: List[str] = []
    for m in _PRECONDITION_RE.finditer(text):
        s = re.sub(r"\s+", " ", m.group(0)).strip(" -:,")
        if s and s not in out:
            out.append(s[:220])
        if len(out) >= limit:
            break
    return out


# =============================================================================
# 5. TLP publication policy
# =============================================================================

_PUBLIC_TLP = {"TLP:CLEAR", "TLP:WHITE"}


def normalize_tlp(value: Any) -> str:
    v = str(value or "TLP:CLEAR").strip().upper().replace("TLP-", "TLP:")
    return v if v.startswith("TLP:") else f"TLP:{v}"


def tlp_public_conflict(value: Any) -> bool:
    """True when the label forbids unrestricted public posting (GREEN/AMBER/RED)."""
    return normalize_tlp(value) not in _PUBLIC_TLP
