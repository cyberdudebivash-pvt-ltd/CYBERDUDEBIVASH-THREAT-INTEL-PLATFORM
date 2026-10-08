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
# 1. IOC qualification -- observables vs validated actionable indicators
# =============================================================================
# Two DIFFERENT facts are kept apart (P0 #721 review, point 3):
#   observable          a syntactically valid, publicly routable network/file observable extracted from a
#                       record (IP, domain, URL, hash, e-mail ...).  Syntax only -- NOT evidence of malice.
#   validated actionable an observable that ALSO has (a) provenance corroborated by the record's own
#                       collector metadata and (b) an explicit maliciousness assertion.  Only these may be
#                       presented as indicators of compromise to block/hunt on with confidence.
# Evidence states (per observable):
#   GENERATED        AI-derived candidate -- never counted.
#   OBSERVED         observed_in_wild marker AND corroborated source.
#   SOURCE_REPORTED  claimed source is corroborated by the record's collector metadata.
#   SOURCE_CLAIMED   a source is claimed on the IOC but NOT corroborated (could be spoofed feed text).
#   UNVERIFIED       no provenance recorded.
# A domain-shaped string is preserved as an observable only when its last label is a real IANA TLD and it
# is not a known product domain, platform-owned domain or advisory/reference host.

_REFANG = (("[.]", "."), ("(.)", "."), ("{.}", "."), ("[:]", ":"), ("[://]", "://"))
_SOURCE_KEYS = ("source", "source_url", "reference", "reported_by", "feed", "origin")
_MALICIOUS_VERDICTS = {"malicious", "c2", "phishing", "malware", "botnet", "ransomware", "exploit"}
_PLATFORM_DOMAINS = ("cyberdudebivash.com", "cyberdudebivash.in")
IANA_TLD_PATH = _REPO / "data" / "reference" / "iana_tlds.txt"


@lru_cache(maxsize=1)
def _iana_tlds() -> frozenset:
    """Official IANA TLD list (verbatim file with its version header). Missing -> empty (fail closed:
    no bare-domain promotion)."""
    try:
        return frozenset(l.strip().lower() for l in IANA_TLD_PATH.read_text(encoding="utf-8").splitlines()
                         if l.strip() and not l.startswith("#"))
    except OSError:
        return frozenset()


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


def _host_of(v: str) -> str:
    m = re.match(r"^(?:https?://)?([^/\s:?#]+)", str(v).strip(), flags=re.IGNORECASE)
    return (m.group(1) if m else str(v)).lower().rstrip(".")


def _context_sources(context: Any) -> set:
    """Collector identities the RECORD itself asserts (set by pipeline code, not by the IOC text)."""
    if not isinstance(context, dict):
        return set()
    toks: set = set()
    for k in ("source", "feed_source", "source_name", "collector"):
        if context.get(k):
            toks.add(str(context[k]).strip().lower())
    for k in ("sources", "source_list"):
        v = context.get(k)
        if isinstance(v, (list, tuple)):
            toks.update(str(x).strip().lower() for x in v if x)
    for k in ("source_url", "nvd_url", "reference_url"):
        if context.get(k):
            toks.add(_host_of(context[k]))
    return {t for t in toks if t}


def ioc_provenance(ioc: Any, context: Any = None) -> Dict[str, Any]:
    """Provenance of one IOC: {state, claimed, corroborated, malicious_assertion}."""
    out = {"state": UNVERIFIED, "claimed": [], "corroborated": False, "malicious_assertion": False}
    if not isinstance(ioc, dict):
        return out
    if ioc.get("generated"):
        out["state"] = GENERATED
        return out
    claimed = []
    for k in _SOURCE_KEYS:
        v = ioc.get(k)
        if v:
            claimed.append(str(v).strip().lower())
            if k in ("source_url", "reference"):
                claimed.append(_host_of(v))
    out["claimed"] = sorted(set(claimed))
    ctx = _context_sources(context)
    out["corroborated"] = bool(claimed) and any(
        c == t or (len(c) > 3 and (c in t or t in c)) for c in claimed for t in ctx if len(t) > 3 or c == t)
    verdict = str(ioc.get("verdict") or "").strip().lower()
    out["malicious_assertion"] = (ioc.get("malicious") is True or ioc.get("observed_in_wild") is True
                                  or verdict in _MALICIOUS_VERDICTS)
    if not claimed:
        out["state"] = UNVERIFIED
    elif not out["corroborated"]:
        out["state"] = "SOURCE_CLAIMED"
    elif ioc.get("observed_in_wild") is True:
        out["state"] = OBSERVED
    else:
        out["state"] = SOURCE_REPORTED
    return out


def ioc_evidence_state(ioc: Any, context: Any = None) -> str:
    """Provenance state of one IOC (see module notes).  Never OBSERVED without marker + corroborated source."""
    return ioc_provenance(ioc, context)["state"]


def is_validated_actionable(ioc: Any, context: Any = None) -> bool:
    """Corroborated provenance AND an explicit maliciousness assertion -- syntax alone never qualifies."""
    p = ioc_provenance(ioc, context)
    return p["state"] in (SOURCE_REPORTED, OBSERVED) and p["corroborated"] and p["malicious_assertion"]


def _classify_observable(value: str) -> Tuple[Dict[str, Any], bool]:
    """(verdict, domain_preserved).  classify_ioc is the authority; the ONLY override is for domain-shaped
    strings it rejected as 'software_component' because of a bare lowercase two-label shape."""
    verdict = _ite.classify_ioc(value)
    if verdict["category"] == "operational_ioc":
        return verdict, False
    if verdict.get("non_ioc_class") == "software_component" and _ite.DOMAIN_RE.match(value):
        host = value.lower().rstrip(".")
        tld = host.rsplit(".", 1)[-1]
        if _ite.ADVISORY_URL_RE.search(host):
            # bare advisory / intelligence-source host (cisa.gov, nvd.nist.gov ...): a reference, never an observable
            return dict(verdict, non_ioc_class="contextual_reference",
                        rejection_reason="advisory/intelligence source host -- a reference, not threat infrastructure"), False
        if (tld in _iana_tlds() and host not in _ite.KNOWN_PRODUCT_DOMAINS
                and not any(host == d or host.endswith("." + d) for d in _PLATFORM_DOMAINS)):
            v2 = dict(verdict, category="operational_ioc", non_ioc_class=None, rejection_reason=None,
                      ioc_type="FQDN" if host.count(".") >= 2 else "DOMAIN")
            return v2, True
    if verdict.get("non_ioc_class") == "software_component" and any(
            value.lower().rstrip(".") == d or value.lower().rstrip(".").endswith("." + d) for d in _PLATFORM_DOMAINS):
        verdict = dict(verdict, non_ioc_class="platform_infrastructure",
                       rejection_reason="platform-owned domain is not threat infrastructure")
    return verdict, False


def qualify_iocs(raw: Any, context: Any = None) -> Dict[str, Any]:
    """Split a raw IOC collection into observables and the validated-actionable subset.

    `context` is the owning record (used ONLY to corroborate claimed sources).

    Returns:
      actionable       list -- (name kept for compatibility) the qualified OBSERVABLES, original shape
                        preserved; the sole input to every displayed/exported observable count
      observables      alias of `actionable`
      validated        list -- subset that is validated actionable (corroborated + malicious assertion)
      generated        list -- AI-derived candidates (never counted)
      rejected         list -- [{value, reason_class, reason}] audit trail
      duplicates       int
      count            int  -- len(observables)           (ioc_count / len(iocs) invariant)
      validated_count  int  -- len(validated)
      by_state         dict -- evidence-state breakdown of the observables
    """
    items: List[Any] = list(raw) if isinstance(raw, (list, tuple)) else []
    observables: List[Any] = []
    validated: List[Any] = []
    generated: List[Any] = []
    rejected: List[Dict[str, str]] = []
    seen: set = set()
    duplicates = 0

    for ioc in items:
        value = _refang(_ioc_value(ioc))
        verdict, domain_preserved = _classify_observable(value)
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
        prov = ioc_provenance(ioc, context)
        if isinstance(ioc, dict):
            out = dict(ioc)
            out["value"] = value
            out["ioc_type"] = verdict["ioc_type"]
            out["evidence_state"] = prov["state"]
            if domain_preserved:
                out["ambiguous_domain"] = True        # could be a vendor/product host; syntax only
        else:
            out = value
        if prov["state"] == GENERATED:
            generated.append(out)
            continue
        observables.append(out)
        if is_validated_actionable(ioc, context):
            validated.append(out)

    by_state: Dict[str, int] = {}
    for o in observables:
        st = o.get("evidence_state") if isinstance(o, dict) else UNVERIFIED
        by_state[st] = by_state.get(st, 0) + 1
    return {
        "actionable": observables,
        "observables": observables,
        "validated": validated,
        "generated": generated,
        "rejected": rejected,
        "duplicates": duplicates,
        "count": len(observables),
        "validated_count": len(validated),
        "by_state": by_state,
    }


def ioc_count_phrase(observables: int, validated: int) -> str:
    """The ONE wording for IOC counts on any customer-visible surface."""
    return f"{observables} IOC observable(s); {validated} validated as malicious"


# =============================================================================
# 2. ATT&CK authority (release-pinned; fail-closed)
# =============================================================================
# Authority = data/attck/enterprise-attack.json (condensed sync) AND
# data/attck/attack_release_pin.json (written by scripts/attack_release_pin.py after
# verifying the sync is identical to an official MITRE release). If either is missing,
# unreadable, or the snapshot's content hash no longer matches the pin, NOTHING validates:
# every ID/name is suppressed (DATASET_UNAVAILABLE) rather than published unverified.
#
# No broad coercion: only ids listed in the pin's `approved_legacy_aliases` are ever
# rewritten (T1190.001 -> T1190). Unknown sub-techniques are NOT mapped to their parent;
# retired (revoked) ids are suppressed and reported with MITRE's replacement ids.

ATTACK_PIN_PATH = _REPO / "data" / "attck" / "attack_release_pin.json"
_TECH_RE = re.compile(r"^T\d{4}(?:\.\d{3})?$")
_ID_LIKE_RE = re.compile(r"^T\d{3,5}(?:\.\d+)?$", re.IGNORECASE)


@lru_cache(maxsize=1)
def _attack_state() -> Optional[Dict[str, Any]]:
    """Loaded + integrity-checked authority, or None (fail closed)."""
    try:
        snap = json.loads(ATTACK_DATASET_PATH.read_text(encoding="utf-8"))
        pin = json.loads(ATTACK_PIN_PATH.read_text(encoding="utf-8"))
        if not pin.get("snapshot_verified_equal_to_official") or not pin.get("release"):
            return None
        if pin.get("snapshot_content_hash") != snap.get("content_hash"):
            return None                      # snapshot drifted from the verified release
        idx = {t["attck_id"]: t for t in snap.get("techniques", []) if t.get("attck_id")}
        if not idx or len(idx) != pin.get("current_technique_count"):
            return None
        names: Dict[str, List[str]] = {}
        for tid, t in idx.items():
            names.setdefault(str(t.get("name", "")).strip().lower(), []).append(tid)
        return {"snap": snap, "pin": pin, "idx": idx, "names": names,
                "retired": pin.get("retired_techniques") or {},
                "aliases": pin.get("approved_legacy_aliases") or {}}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _attack_index() -> Optional[Dict[str, Dict[str, Any]]]:
    st = _attack_state()
    return st["idx"] if st else None


@lru_cache(maxsize=1)
def attack_dataset_pin() -> Dict[str, Any]:
    """Identity of the dataset every technique is validated against."""
    st = _attack_state()
    if not st:
        return {"available": False, "attack_release": None}
    p, s = st["pin"], st["snap"]
    return {
        "available": True,
        "attack_release": p["release"],
        "release_major": p.get("release_major"),
        "release_modified": p.get("release_modified"),
        "official_file_sha256": p.get("official_file_sha256"),
        "source": p.get("official_source"),
        "synced_at": s.get("synced_at"),
        "content_hash": s.get("content_hash"),
        "technique_count": len(st["idx"]),
        "retired_count": len(st["retired"]),
    }


def navigator_attack_version() -> str:
    """ATT&CK major version for Navigator layer `versions.attack`: the PINNED release's major,
    or "unpinned" when the release cannot be verified (never a guessed number)."""
    pin = attack_dataset_pin()
    return str(pin.get("release_major")) if pin.get("available") else "unpinned"


def validate_technique(tid: Any) -> Dict[str, Any]:
    """Validate one ATT&CK technique ID.

    status: VALID | APPROVED_LEGACY_ALIAS | RETIRED | UNKNOWN_TECHNIQUE | MALFORMED |
            DATASET_UNAVAILABLE   (callers must not claim 'validated' on the last)
    Only VALID and APPROVED_LEGACY_ALIAS are publishable (the latter as `maps_to`).
    """
    t = str(tid or "").strip().upper()
    res: Dict[str, Any] = {"input": str(tid), "id": t, "status": "MALFORMED", "name": None,
                           "tactics": [], "maps_to": None, "revoked_by": [], "suggested_parent": None}
    if not _TECH_RE.match(t):
        return res
    st = _attack_state()
    if st is None:
        res["status"] = "DATASET_UNAVAILABLE"
        return res
    if t in st["idx"]:
        res.update(status="VALID", name=st["idx"][t].get("name"),
                   tactics=list(st["idx"][t].get("tactics") or []))
        return res
    if t in st["aliases"]:
        target = st["aliases"][t].get("maps_to")
        if target in st["idx"]:
            res.update(status="APPROVED_LEGACY_ALIAS", maps_to=target, name=st["idx"][target].get("name"))
            return res
    if t in st["retired"]:
        res.update(status="RETIRED", name=st["retired"][t].get("name"),
                   revoked_by=list(st["retired"][t].get("revoked_by") or []))
        return res
    res["status"] = "UNKNOWN_TECHNIQUE"
    parent = t.split(".")[0]
    if "." in t and parent in st["idx"]:
        res["suggested_parent"] = parent      # a hint for reviewers only -- never applied
    return res


def technique_name(tid: Any) -> Optional[str]:
    """Official name of a current technique, else None (never a made-up label)."""
    r = validate_technique(tid)
    return r["name"] if r["status"] in ("VALID", "APPROVED_LEGACY_ALIAS") else None


def canonical_technique_id(tid: Any) -> Optional[str]:
    """The ID that may be published: itself if currently valid, the approved target of an
    explicitly approved legacy alias, else None (suppress -- retired/unknown/malformed)."""
    r = validate_technique(tid)
    if r["status"] == "VALID":
        return r["id"]
    if r["status"] == "APPROVED_LEGACY_ALIAS":
        return r["maps_to"]
    return None


def technique_id_of(entry: Any) -> str:
    """Extract an ID from the several shapes found in feed records."""
    if isinstance(entry, dict):
        return str(entry.get("technique_id") or entry.get("id") or entry.get("attck_id") or "")
    return str(entry or "")


def resolve_technique_name(name: Any) -> Dict[str, Any]:
    """Verify a technique NAME against the pinned release.  Accepts an exact current
    technique name, or 'Parent: Sub' where the pair resolves to a real sub-technique.
    Anything else (retired/legacy names, free text) is UNVERIFIED_NAME."""
    n = re.sub(r"\s+", " ", str(name or "")).strip()
    res: Dict[str, Any] = {"input": str(name), "status": "UNVERIFIED_NAME", "ids": []}
    st = _attack_state()
    if st is None:
        res["status"] = "DATASET_UNAVAILABLE"
        return res
    if not n or len(n) > 120:
        return res
    ids = st["names"].get(n.lower())
    if ids:
        res.update(status="VERIFIED_NAME", ids=sorted(ids))
        return res
    if ": " in n:
        parent_n, sub_n = n.split(": ", 1)
        pids = set(st["names"].get(parent_n.strip().lower(), []))
        hit = sorted(i for i in st["names"].get(sub_n.strip().lower(), []) if i.split(".")[0] in pids and "." in i)
        if hit:
            res.update(status="VERIFIED_NAME", ids=hit)
    return res


def filter_valid_techniques(entries: Iterable[Any]) -> Tuple[List[Any], List[Dict[str, Any]]]:
    """Return (publishable entries, rejected audit rows).  Order-preserving.

    * ID-shaped values: published only if VALID, or rewritten via an approved legacy alias.
      Unknown sub-techniques, retired ids and malformed ids are rejected (never coerced).
    * Names: published only if they resolve to an official current technique
      (exact name or 'Parent: Sub'); everything else is rejected as UNVERIFIED_NAME.
    * Dataset unavailable: everything is rejected (fail closed).
    """
    out: List[Any] = []
    rejected: List[Dict[str, Any]] = []
    seen: set = set()
    for e in entries or []:
        raw = technique_id_of(e)
        if not _ID_LIKE_RE.match(raw.strip()):
            r = resolve_technique_name(raw)
            if r["status"] != "VERIFIED_NAME":
                rejected.append({"input": raw[:120], "id": "", "status": r["status"]})
                continue
            key = ("name", raw.strip().lower())
            if key in seen:
                continue
            seen.add(key)
            out.append(e)
            continue
        canon = canonical_technique_id(raw)
        if canon is None:
            rejected.append(validate_technique(raw))
            continue
        if ("id", canon) in seen:
            continue
        seen.add(("id", canon))
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


def severity_basis(item: Dict[str, Any], cvss: Any, kev: bool) -> Dict[str, Any]:
    """What may be displayed as this record's *severity*, kept separate from exploitation
    evidence (KEV) and from APEX's own heuristic.  (P0 #721 review: KEV is not a severity.)

    Fields
      display        CVSS qualitative band of the reported score; "UNRATED" for a vulnerability with
                     no usable CVSS; for non-vulnerability records (no CVSS exists) APEX's own label.
      rated          True only when `display` comes from a CVSS score.
      kev            CISA KEV listed -- exploitation / prioritization evidence, never a rating.
      prioritized    rated OR kev OR non-vulnerability: the record has a basis for an action priority.
      authoritative  `display` is a concrete label (compat alias for display != "UNRATED").
      composite      the pipeline's proprietary heuristic label, disclosed but never presented as a
                     vendor/CVSS severity; `conflict` when it disagrees with the CVSS band.
      severity_source cvss_vector_verified | cvss_reported | none | apex_heuristic
    A CVSS score of 0/blank/garbage is missing, never a rating.  Production data carries no CVSS
    vector, so scores are labelled "as reported by source; vector unavailable to verify".
    """
    sev = str(item.get("severity") or "UNKNOWN").upper()
    out: Dict[str, Any] = {"composite": sev, "conflict": False, "kev": bool(kev), "rated": False,
                           "prioritized": False, "authoritative": True, "note": "", "display": sev,
                           "basis": "", "severity_source": "none"}
    if not is_vulnerability_record(item):
        out.update(prioritized=True, severity_source="apex_heuristic",
                   basis="non-vulnerability record",
                   note="APEX composite label (CVSS does not apply to this record type)")
        return out
    try:
        score = float(cvss) if cvss not in (None, "") else None
    except (TypeError, ValueError):
        score = None
    band = _ste.cvss_rating(score) if score is not None else None
    if band:
        verified = _ste.verified_cvss(dict(item, cvss_score=score)) is not None
        src = "vector-verified" if verified else "score as reported by source; vector unavailable to verify"
        basis = f"CVSS {score:g} ({src})" + ("; CISA KEV listed" if kev else "")
        conflict = band != sev
        out.update(display=band, rated=True, prioritized=True, basis=basis, conflict=conflict,
                   severity_source="cvss_vector_verified" if verified else "cvss_reported",
                   note=(f"{basis}; the APEX composite label {sev} disagrees and is superseded") if conflict else "")
        return out
    out.update(display="UNRATED", authoritative=False)
    if kev:
        out.update(prioritized=True,
                   basis="CISA KEV listed (exploitation evidence); no CVSS score available",
                   note=f"CISA KEV-listed (exploitation evidence, not a severity rating); no CVSS score available; "
                        f"APEX composite label {sev} is a proprietary heuristic, not a vendor severity")
    else:
        out.update(basis="no authoritative CVSS or KEV listing available",
                   note=f"no authoritative CVSS or KEV listing available; APEX composite heuristic: {sev} (not a rating)")
    return out


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
# 5. TLP publication policy  (DEPRECATED wrappers -- authority: scripts/tlp_policy.py)
# =============================================================================
# Replacement: tlp_policy.publication_decision(item).  These wrappers are kept for importers and are
# now FAIL-CLOSED: a missing/invalid/legacy/restricted label is a conflict (previously None -> CLEAR and
# TLP:WHITE was treated as public).  Remove after the next layer once no importer remains.

import tlp_policy as _tlp  # noqa: E402


def normalize_tlp(value: Any) -> str:
    p = _tlp.parse_label(value)
    return p["label"] or ("TLP:UNLABELLED" if p["status"] == _tlp.MISSING else "TLP:INVALID")


def tlp_public_conflict(value: Any) -> bool:
    """True unless the label alone permits anonymous publication (explicit TLP:CLEAR)."""
    return not _tlp.publication_decision({"tlp": value}, {"legacy_white_treated_as_clear": False,
                                                          "first_party_public_sources": []})["allowed"]
