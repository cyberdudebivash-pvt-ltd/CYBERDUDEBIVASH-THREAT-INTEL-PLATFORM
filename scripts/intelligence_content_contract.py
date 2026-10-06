#!/usr/bin/env python3
"""
scripts/intelligence_content_contract.py
CYBERDUDEBIVASH(R) SENTINEL APEX v185.0 -- Canonical Intelligence Content
Contract Engine (Phase 4)
=========================================================================
validate_intelligence_content(item, report_type=None, publication_context=None)
    -> ValidationResult

The mandate's deferred Phase 3 item, built now. Deliberately NOT a
duplicate of anti_hallucination_engine.py's HallucinationEngine: this
module COMPOSES it (calls .audit(), reuses its Violation dataclass and
several of its regexes) and adds report-type-aware checks that engine has
no concept of (it audits an item in isolation; this module additionally
asks "is this item's report_type-implied content actually present, and
does the report_type itself match the evidence").

Reuse map (Principle 3 -- Single Source of Truth):
  - IOC validity / pseudo-IOC-as-reference   -> anti_hallucination_engine.HallucinationEngine._check_iocs
  - source-URL-as-IOC (own article as IOC)    -> p38_shared_validators.is_pseudo_ioc (Phase 3)
  - ATT&CK mapping with no evidence           -> anti_hallucination_engine.HallucinationEngine._check_attack_mapping
  - fabricated/static risk scores             -> anti_hallucination_engine.HallucinationEngine._check_risk_score
  - unsupported attribution / confidence       -> anti_hallucination_engine.HallucinationEngine._check_actor / _check_confidence
  - exact duplicate content                   -> anti_hallucination_engine.HallucinationEngine._check_duplicate
  - known platform template/boilerplate text  -> anti_hallucination_engine.TEMPLATE_EXEC_RE
  - Markdown syntax leakage                   -> normalize_text.strip_markdown_artifacts (Phase 3)
  - report-type classification                -> report_type_contracts.classify_report_type (this phase)

New checks this module adds (not covered by the above):
  PLACEHOLDER            -- unresolved template TOKENS ({{x}}, {field}, [TODO]),
                            NOT the English word "placeholder" (see Phase 3's
                            documented false positive on django-cms's legitimate
                            "placeholder" content-region terminology -- the
                            lesson that motivates this narrower, token-shaped
                            signal instead of banning a common word).
  TEMPLATE_LEAK           -- known platform boilerplate phrases, generalized to
                            title/description (existing engine only checked
                            executive_summary/summary).
  BROKEN_MARKDOWN         -- description differs from strip_markdown_artifacts(description),
                            i.e. Markdown syntax leaked through (Phase 3's own
                            fix should already prevent this at ingestion; this
                            is the after-the-fact detection half of that fix).
  INTERNAL_INSTRUCTION    -- LLM/prompt artifact leakage ("as an AI", "I cannot",
                            "system:", "assistant:").
  UNSAFE_HTML             -- <script>/<iframe>/event-handler/javascript: --
                            content is rendered as plain text per Phase 3's
                            security note, but detecting it here catches the
                            defect at its source rather than relying solely on
                            the renderer never treating it as markup.
  GENERIC_FILLER          -- WARN only, statistical (not phrase-banning, per the
                            mandate's explicit instruction): description is both
                            below the report-type's implied richness AND
                            anchored to zero concrete technical entities (no
                            CVE ID, no IOC, no numeric score, no named product).
  DUPLICATE_CONTENT       -- delegated to HallucinationEngine._check_duplicate.
  TRUNCATED_CONTENT       -- description ends at a known ingestion truncation
                            boundary (300/1000 chars -- see true_intel_ingestor.py
                            / multi_source_collector.py) without closing
                            punctuation.
  MALFORMED_REFERENCE     -- dangling Markdown link syntax, or JS-serialization
                            leakage ("[object Object]", "undefined", "NaN")
                            from a broken template substitution.
  UNSUPPORTED_ASSERTION   -- delegated to HallucinationEngine's risk/confidence/
                            attribution checks (composition, not duplication).
  INVALID_IOC_CONTEXT     -- delegated to HallucinationEngine._check_iocs PLUS
                            p38_shared_validators.is_pseudo_ioc.
  INVALID_ATTACK_MAPPING  -- delegated to HallucinationEngine._check_attack_mapping.
  MISSING_CRITICAL_SECTION -- report_type_contracts: any REQUIRED field absent.
  REPORT_TYPE_MISMATCH    -- report_type's own evidence requirement contradicts
                            the item's actual content (e.g. classified
                            CVE_VULNERABILITY with zero CVE-shaped signal
                            anywhere in id/cve_id/cve_ids/title/description).

(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved. CONFIDENTIAL.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from anti_hallucination_engine import HallucinationEngine, Violation, TEMPLATE_EXEC_RE  # noqa: E402
from normalize_text import strip_markdown_artifacts  # noqa: E402
from p38_shared_validators import is_pseudo_ioc  # noqa: E402
from report_type_contracts import (  # noqa: E402
    classify_report_type,
    get_contract,
    REQUIRED,
    NOT_APPLICABLE,
    CVE_VULNERABILITY,
    RANSOMWARE,
)

ENGINE_VERSION = "185.0"

# ---------------------------------------------------------------------------
# New-check patterns
# ---------------------------------------------------------------------------

# Unresolved template TOKENS -- structurally distinct from prose (mustache/
# format-string/angle-bracket shapes), not a banned English word. See module
# docstring: this is the direct fix for Phase 3's "placeholder" false positive.
_PLACEHOLDER_TOKEN_RE = re.compile(
    r"\{\{[^}]{0,80}\}\}"                 # {{token}}
    # {token} unresolved format string -- (?<!/) excludes REST API route
    # patterns quoted in vulnerability descriptions (e.g. "GET /api/
    # transaction/{id}", "POST /api/v1/command/{db}"), which are legitimate
    # technical content describing the vulnerable endpoint, not a failed
    # template substitution. Evidence: intel--2cce4ec78244e150 ({id}),
    # intel--dd7689f9e120279d1ec845f7 ({other_user_id}),
    # intel--271fb0274ed59cea ({db}), intel--fb3a8ddaaebb2a3d ({plugin}) --
    # all four were REST route syntax, zero were real template leaks.
    r"|(?<!/)\{[a-zA-Z_][a-zA-Z0-9_]{0,40}\}"
    r"|<%[^%]{0,80}%>"                     # <% token %>
    r"|\[(?:TODO|FIXME|INSERT[ _][A-Z_]+|PLACEHOLDER|TBD)\]"  # [TODO] etc, bracketed+uppercase only
)

_INTERNAL_INSTRUCTION_RE = re.compile(
    r"\bas an ai\b|\bas a language model\b|\bi cannot\b|\bi'm sorry\b|\bi am sorry\b"
    r"|^\s*(system|user|assistant)\s*:|\byou are a\b.{0,20}\bassistant\b"
    r"|\bthis is a placeholder response\b",
    re.IGNORECASE,
)

_UNSAFE_HTML_RE = re.compile(
    r"<\s*script\b|<\s*iframe\b|<\s*object\b|<\s*embed\b"
    r"|on\w+\s*=\s*['\"]"
    # javascript: URI scheme -- (?!\s) excludes CVE-description prose like
    # "the JavaScript: GC component" (Firefox's own component-naming
    # convention, always followed by a space + capitalized word), which a
    # bare `javascript\s*:` match flagged as a false positive (evidence:
    # intel--c676baa09b244ce6, intel--129eb23016e72a2a,
    # intel--a27366c223e9977a). Real payloads (javascript:alert(1),
    # javascript:void(0)) are never followed by whitespace.
    r"|javascript\s*:(?!\s)",
    re.IGNORECASE,
)

_MALFORMED_REF_RE = re.compile(
    r"\[object Object\]|\bundefined\b.{0,10}\bundefined\b|\bNaN\b.{0,10}\bNaN\b"
    r"|\[[^\]\n]{1,80}\]\(\s*\)"     # [text]() -- empty URL
)

# Ingestion truncation boundaries observed in true_intel_ingestor.py /
# multi_source_collector.py (Phase 3): title[:300]/[:200], description[:1000].
_TRUNCATION_BOUNDARIES = {300, 200, 1000}
_SENTENCE_END_RE = re.compile(r"[.!?…\"')\]]\s*$")

_CVE_ID_RE = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)
_RANSOMWARE_KEYWORDS = ("ransomware", "ransom note", "encrypt", "leak site", "double extortion", "data leak")


# ---------------------------------------------------------------------------
# ValidationResult
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    item_id: str
    report_type: str
    valid: bool
    severity: str                 # PASS | WARN | HOLD
    hold_publication: bool
    violations: List[Violation] = dc_field(default_factory=list)
    quality_dimensions: Dict[str, Any] = dc_field(default_factory=dict)
    applicability: Dict[str, str] = dc_field(default_factory=dict)
    evidence: Dict[str, Any] = dc_field(default_factory=dict)
    engine_version: str = ENGINE_VERSION

    def to_dict(self) -> Dict:
        return {
            "item_id": self.item_id,
            "report_type": self.report_type,
            "valid": self.valid,
            "severity": self.severity,
            "hold_publication": self.hold_publication,
            "violations": [v.__dict__ for v in self.violations],
            "quality_dimensions": self.quality_dimensions,
            "applicability": self.applicability,
            "evidence": self.evidence,
            "engine_version": self.engine_version,
        }


# HOLD-eligible violation codes: publication-unsafe or materially misleading
# (mandate section 9). Everything else that reaches HARD_FAIL severity in the
# underlying checks is surfaced as WARN here, not HOLD -- e.g. INVALID_CONFIDENCE
# (missing rationale) is a real defect worth flagging but does not make the
# item unsafe or misleading to publish.
_HOLD_CODES = {
    "PLACEHOLDER", "TEMPLATE_LEAK", "INTERNAL_INSTRUCTION", "UNSAFE_HTML",
    "INVALID_IOC_CONTEXT", "INVALID_IOC", "PSEUDO_IOC",
    "MALFORMED_REFERENCE", "REPORT_URL_IS_SOURCE_URL",
    "MISSING_CRITICAL_SECTION",
}


def _text_fields(item: Dict) -> Dict[str, str]:
    return {
        "title": str(item.get("title") or ""),
        "description": str(item.get("description") or ""),
    }


def _has_concrete_entity(item: Dict, text: str) -> bool:
    """True if the item is anchored to at least one concrete, checkable fact
    -- used only to keep GENERIC_FILLER from flagging legitimately terse but
    factual content (e.g. a short but specific advisory sentence)."""
    if item.get("cve_id") or item.get("cve_ids") or item.get("cves"):
        return True
    if _CVE_ID_RE.search(text):
        return True
    if item.get("iocs"):
        return True
    if item.get("cvss_score") or item.get("epss_score"):
        return True
    if item.get("affected_products"):
        return True
    return False


def _check_placeholder(text_fields: Dict[str, str]) -> List[Violation]:
    out = []
    for fname, text in text_fields.items():
        m = _PLACEHOLDER_TOKEN_RE.search(text)
        if m:
            out.append(Violation(
                code="PLACEHOLDER", severity="HARD_FAIL", field=fname,
                evidence=m.group(0)[:60],
                explanation="Unresolved template token found in published content "
                            "(e.g. {{var}}, {field}, [TODO]) -- a template substitution "
                            "failed upstream. This is a token-shape match, not a banned "
                            "word, so it will not flag legitimate prose that happens to "
                            "contain words like 'placeholder' in their normal sense.",
            ))
    return out


def _check_template_leak(text_fields: Dict[str, str]) -> List[Violation]:
    out = []
    for fname, text in text_fields.items():
        if not text:
            continue
        m = TEMPLATE_EXEC_RE.search(text)
        if m:
            out.append(Violation(
                code="TEMPLATE_LEAK", severity="HARD_FAIL", field=fname,
                evidence=m.group(0)[:60],
                explanation="Known platform boilerplate/template phrase leaked into "
                            "published content (reused from anti_hallucination_engine.py's "
                            "TEMPLATE_EXEC_PHRASES list).",
            ))
    return out


def _check_broken_markdown(item: Dict) -> List[Violation]:
    out = []
    for fname in ("title", "description"):
        raw = str(item.get(fname) or "")
        if not raw:
            continue
        cleaned = strip_markdown_artifacts(raw)
        if cleaned != raw:
            out.append(Violation(
                code="BROKEN_MARKDOWN", severity="WARN", field=fname,
                evidence=raw[:80],
                explanation="Markdown syntax present in a field the platform stores and "
                            "renders as plain text (strip_markdown_artifacts would change "
                            "this value). Should have been caught at ingestion by the "
                            "Phase 3 fix -- WARN here catches any producer that bypasses it.",
            ))
    return out


def _check_internal_instruction(text_fields: Dict[str, str]) -> List[Violation]:
    out = []
    for fname, text in text_fields.items():
        m = _INTERNAL_INSTRUCTION_RE.search(text)
        if m:
            out.append(Violation(
                code="INTERNAL_INSTRUCTION", severity="HARD_FAIL", field=fname,
                evidence=m.group(0)[:60],
                explanation="LLM/prompt artifact leaked into published content "
                            "(e.g. 'as an AI', 'I cannot', a role-prefixed line like "
                            "'system:'). Indicates a generation pipeline failure, not "
                            "real intelligence content.",
            ))
    return out


def _check_unsafe_html(text_fields: Dict[str, str]) -> List[Violation]:
    out = []
    for fname, text in text_fields.items():
        m = _UNSAFE_HTML_RE.search(text)
        if m:
            out.append(Violation(
                code="UNSAFE_HTML", severity="HARD_FAIL", field=fname,
                evidence=m.group(0)[:40],
                explanation="Executable HTML/script content found in a field ingested "
                            "from an untrusted external source. Must never be rendered as "
                            "markup (XSS/HTML-injection surface) -- flagged here so the "
                            "defect is caught at the content layer, not only relied on the "
                            "renderer to never treat it as markup.",
            ))
    return out


def _check_malformed_reference(text_fields: Dict[str, str]) -> List[Violation]:
    out = []
    for fname, text in text_fields.items():
        m = _MALFORMED_REF_RE.search(text)
        if m:
            out.append(Violation(
                code="MALFORMED_REFERENCE", severity="HARD_FAIL", field=fname,
                evidence=m.group(0)[:60],
                explanation="Malformed reference/citation or JS-serialization leakage "
                            "(e.g. '[object Object]', an empty Markdown link '[text]()') "
                            "-- symptomatic of a broken template substitution upstream.",
            ))
    return out


def _check_truncated_content(item: Dict) -> List[Violation]:
    out = []
    for fname, maxlen in (("title", 300), ("title", 200), ("description", 1000)):
        text = str(item.get(fname) or "")
        if len(text) == maxlen and not _SENTENCE_END_RE.search(text):
            out.append(Violation(
                code="TRUNCATED_CONTENT", severity="WARN", field=fname,
                evidence=f"len={len(text)}, ends: ...{text[-30:]!r}",
                explanation=f"Field is exactly {maxlen} characters (a known ingestion "
                            "truncation boundary) and does not end with closing "
                            "punctuation -- likely cut mid-sentence at the source, not "
                            "a coincidentally round length.",
            ))
            break  # one truncation finding per field is enough
    return out


def _check_generic_filler(item: Dict, contract, text_fields: Dict[str, str]) -> List[Violation]:
    """WARN only. Statistical, not phrase-banning (mandate section 6/8's
    explicit instruction): flags content that is BOTH below the report
    type's implied richness AND anchored to zero concrete technical facts.
    A short-but-factual INDICATOR_FEED sentence never trips this; a long
    but fact-free paragraph can."""
    out = []
    desc = text_fields["description"]
    if not desc:
        return out
    word_count = len(desc.split())
    min_words = 8 if contract.report_type == "INDICATOR_FEED" else 15
    if word_count < min_words:
        return out  # too short to judge fairly either way; MISSING_CRITICAL_SECTION covers true absence
    if not _has_concrete_entity(item, desc) and word_count < 40:
        out.append(Violation(
            code="GENERIC_FILLER", severity="WARN", field="description",
            evidence=f"{word_count} words, no CVE/IOC/CVSS/product anchor",
            explanation="Description is short and not anchored to any concrete, "
                        "checkable fact (CVE ID, IOC, CVSS/EPSS score, named product). "
                        "May be legitimate high-level commentary -- WARN, not HOLD.",
        ))
    return out


def _check_missing_critical_sections(item: Dict, contract) -> List[Violation]:
    out = []
    for f in contract.required_fields():
        val = item.get(f)
        if val is None or val == "" or val == [] or val == {}:
            severity = "HARD_FAIL" if f in ("title", "description", "source_url") else "WARN"
            out.append(Violation(
                code="MISSING_CRITICAL_SECTION", severity=severity, field=f,
                evidence="absent",
                explanation=f"'{f}' is REQUIRED for report_type={contract.report_type} "
                            "per the report-type contract registry, and is missing/empty "
                            "on this item.",
            ))
    return out


def _check_report_type_mismatch(item: Dict, report_type: str, text_fields: Dict[str, str]) -> List[Violation]:
    out = []
    blob = (text_fields["title"] + " " + text_fields["description"]).lower()
    if report_type == CVE_VULNERABILITY:
        has_cve = bool(item.get("cve_id") or item.get("cve_ids") or item.get("cves") or _CVE_ID_RE.search(blob))
        if not has_cve:
            out.append(Violation(
                code="REPORT_TYPE_MISMATCH", severity="WARN", field="threat_type",
                evidence=str(item.get("threat_type")),
                explanation="Classified as CVE_VULNERABILITY but no CVE ID appears in "
                            "cve_id/cve_ids/cves or anywhere in title/description.",
            ))
    elif report_type == RANSOMWARE:
        if not any(kw in blob for kw in _RANSOMWARE_KEYWORDS):
            out.append(Violation(
                code="REPORT_TYPE_MISMATCH", severity="WARN", field="threat_type",
                evidence=str(item.get("threat_type")),
                explanation="Classified as RANSOMWARE but no ransomware-related keyword "
                            "(ransomware/ransom note/encrypt/leak site/extortion) appears "
                            "in title/description.",
            ))
    return out


def _check_ioc_context(item: Dict, ahe_result_violations: List[Violation]) -> List[Violation]:
    """Adds Phase 3's is_pseudo_ioc (own-source_url-as-IOC) on top of
    anti_hallucination_engine's REFERENCE_URL_PATTERNS/CVE_RE-based check,
    which does not catch the own-source_url case for domains outside its
    fixed reference-domain list."""
    out = []
    for ioc in (item.get("iocs") or []):
        if not isinstance(ioc, dict):
            continue
        val = str(ioc.get("value") or "")
        if is_pseudo_ioc(val, item):
            out.append(Violation(
                code="INVALID_IOC_CONTEXT", severity="HARD_FAIL", field="iocs",
                evidence=val[:80],
                explanation="IOC value is this item's own source_url (the article "
                            "reporting on the threat, not the threat itself) -- "
                            "reused from p38_shared_validators.is_pseudo_ioc (Phase 3).",
            ))
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_intelligence_content(
    item: Dict,
    report_type: Optional[str] = None,
    publication_context: Optional[Dict] = None,
) -> ValidationResult:
    """Canonical content-quality contract for one intelligence item.
    Composes anti_hallucination_engine.HallucinationEngine (existing,
    proven checks) with new report-type-aware and syntax/leakage checks
    (see module docstring's reuse map). Never fabricates: every violation
    traces to a concrete field and pattern match, not a heuristic guess."""
    item_id = str(item.get("id") or item.get("stix_id") or "UNKNOWN")
    rtype = report_type or classify_report_type(item)
    contract = get_contract(rtype)
    text_fields = _text_fields(item)

    violations: List[Violation] = []

    # 1. Composed: existing HallucinationEngine (INVALID_IOC_CONTEXT/PSEUDO_IOC,
    #    INVALID_ATTACK_MAPPING, UNSUPPORTED_ASSERTION-class, DUPLICATE_CONTENT,
    #    TEMPLATE_LEAK-adjacent via EMPTY_EXECUTIVE).
    engine = publication_context.get("_hallucination_engine") if publication_context else None
    if engine is None:
        engine = HallucinationEngine()
    ahe_result = engine.audit(item)
    violations.extend(ahe_result.violations)
    violations.extend(ahe_result.warnings)

    # 2. Composed: Phase 3 pseudo-IOC (own-source-url-as-IOC), broader than AHE's.
    violations.extend(_check_ioc_context(item, violations))

    # 3. New checks.
    violations.extend(_check_placeholder(text_fields))
    violations.extend(_check_template_leak(text_fields))
    violations.extend(_check_broken_markdown(item))
    violations.extend(_check_internal_instruction(text_fields))
    violations.extend(_check_unsafe_html(text_fields))
    violations.extend(_check_malformed_reference(text_fields))
    violations.extend(_check_truncated_content(item))
    violations.extend(_check_generic_filler(item, contract, text_fields))

    # 4. Report-type-aware checks.
    violations.extend(_check_missing_critical_sections(item, contract))
    violations.extend(_check_report_type_mismatch(item, rtype, text_fields))

    # T09-style: report_url masquerading as the external source (mandate
    # section 9's explicit HOLD example) -- reuses the Phase 2 invariant.
    report_url = item.get("report_url") or ""
    source_url = item.get("source_url") or ""
    if report_url and source_url and report_url == source_url:
        violations.append(Violation(
            code="REPORT_URL_IS_SOURCE_URL", severity="HARD_FAIL", field="report_url",
            evidence=report_url[:80],
            explanation="report_url is identical to source_url -- the internal report "
                        "link points at the external article instead of this platform's "
                        "own report page (Phase 2's T09 invariant).",
        ))

    hard_fails = [v for v in violations if v.severity == "HARD_FAIL"]
    warns = [v for v in violations if v.severity != "HARD_FAIL"]
    hold_codes_present = {v.code for v in hard_fails} & _HOLD_CODES

    if hold_codes_present:
        severity = "HOLD"
        hold_publication = True
        valid = False
    elif hard_fails or warns:
        severity = "WARN"
        hold_publication = False
        valid = True
    else:
        severity = "PASS"
        hold_publication = False
        valid = True

    applicability = {f.field: f.level for f in contract.fields}

    quality_dimensions = {
        "hard_fail_count": len(hard_fails),
        "warn_count": len(warns),
        "not_applicable_fields": [f for f, lvl in applicability.items() if lvl == NOT_APPLICABLE],
        "required_fields_present": sum(
            1 for f in contract.required_fields()
            if item.get(f) not in (None, "", [], {})
        ),
        "required_fields_total": len(contract.required_fields()),
    }

    evidence = {
        "classified_report_type": rtype,
        "contract_description": contract.description,
    }

    return ValidationResult(
        item_id=item_id,
        report_type=rtype,
        valid=valid,
        severity=severity,
        hold_publication=hold_publication,
        violations=violations,
        quality_dimensions=quality_dimensions,
        applicability=applicability,
        evidence=evidence,
    )


def validate_batch(items: List[Dict]) -> Dict[str, Any]:
    """Batch entry point. Shares one HallucinationEngine instance across the
    batch so its run-level duplicate-detection (DUPLICATE_ENTRY) works
    across the whole batch, matching its own intended usage pattern."""
    engine = HallucinationEngine()
    ctx = {"_hallucination_engine": engine}
    results = [validate_intelligence_content(item, publication_context=ctx) for item in items]
    by_severity = {"PASS": 0, "WARN": 0, "HOLD": 0}
    by_report_type: Dict[str, Dict[str, int]] = {}
    violation_code_counts: Dict[str, int] = {}
    for r in results:
        by_severity[r.severity] += 1
        rt = by_report_type.setdefault(r.report_type, {"PASS": 0, "WARN": 0, "HOLD": 0})
        rt[r.severity] += 1
        for v in r.violations:
            violation_code_counts[v.code] = violation_code_counts.get(v.code, 0) + 1
    return {
        "total_items": len(items),
        "by_severity": by_severity,
        "by_report_type": by_report_type,
        "violation_code_counts": violation_code_counts,
        "results": results,
    }
