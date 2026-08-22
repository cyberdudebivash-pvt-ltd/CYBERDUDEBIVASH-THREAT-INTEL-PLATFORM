#!/usr/bin/env python3
"""
scripts/report_type_contracts.py
CYBERDUDEBIVASH(R) SENTINEL APEX v185.0 -- Report-Type Contract Registry
=========================================================================
Phase 4. A registry (not a mega-template): each report type defines what
fields are REQUIRED, CONDITIONAL (required only when a signal implies they
should exist), OPTIONAL, or genuinely NOT_APPLICABLE. This is what makes
validate_intelligence_content() (intelligence_content_contract.py)
report-type-aware instead of applying one rubric to every item -- the
same category error root-caused in P21 (Phase 4 Checkpoint A): a
PHISHING-URL indicator alert and a CVE deep-dive are not the same kind of
document and must not be held to the same bar.

Only report types actually represented in this platform's data are
mapped from real threat_type values (see REPORT_TYPE_MAP below, derived
from the observed distribution across api/feed.json and
data/stix/feed_manifest.json: CVE, THREAT-INTEL, PHISHING-URL,
OSS-ADVISORY, RANSOMWARE, Vulnerability, Threat Intel, KEV). Contracts for
MALWARE / INCIDENT_BREACH / THREAT_ACTOR / CAMPAIGN are still defined
per the mandate (sections 10/13/14) since the taxonomy should not be
blind to content the platform may carry in the future, but no current
threat_type maps to them yet -- documented here rather than silently
omitted.

(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved. CONFIDENTIAL.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

# ---------------------------------------------------------------------------
# Canonical report-type identifiers
# ---------------------------------------------------------------------------
CVE_VULNERABILITY = "CVE_VULNERABILITY"
RANSOMWARE        = "RANSOMWARE"
MALWARE           = "MALWARE"
INCIDENT_BREACH   = "INCIDENT_BREACH"
SECURITY_ADVISORY = "SECURITY_ADVISORY"
NEWS              = "NEWS"
INDICATOR_FEED    = "INDICATOR_FEED"   # platform addition: raw phishing/malware-URL alerts --
                                         # not one of the mandate's named categories, but a real,
                                         # high-volume content class (PHISHING-URL = 148/500 of the
                                         # live feed) that is not equivalent to a written NEWS item
                                         # or a CVE report either. Documented per mandate section 10's
                                         # "if taxonomy requires slight adjustment, document it."
THREAT_ACTOR       = "THREAT_ACTOR"
CAMPAIGN           = "CAMPAIGN"
UNKNOWN            = "UNKNOWN"          # fallback: unmapped threat_type -- treated as NEWS-strictness
                                         # (least demanding) rather than silently failing every field.

REQUIRED       = "REQUIRED"
CONDITIONAL    = "CONDITIONAL"
OPTIONAL       = "OPTIONAL"
NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass
class FieldRequirement:
    field: str
    level: str
    note: str = ""


@dataclass
class ReportContract:
    report_type: str
    description: str
    fields: List[FieldRequirement] = field(default_factory=list)

    def requirement_for(self, field_name: str) -> str:
        for fr in self.fields:
            if fr.field == field_name:
                return fr.level
        return OPTIONAL

    def required_fields(self) -> List[str]:
        return [fr.field for fr in self.fields if fr.level == REQUIRED]

    def conditional_fields(self) -> List[FieldRequirement]:
        return [fr for fr in self.fields if fr.level == CONDITIONAL]


# ---------------------------------------------------------------------------
# threat_type (raw, observed) -> canonical report_type
# ---------------------------------------------------------------------------
REPORT_TYPE_MAP: Dict[str, str] = {
    "cve":                    CVE_VULNERABILITY,
    "vulnerability":          CVE_VULNERABILITY,
    "kev":                    CVE_VULNERABILITY,
    "remote code execution":  CVE_VULNERABILITY,
    "web application attack": CVE_VULNERABILITY,
    "ransomware":             RANSOMWARE,
    "malware":                MALWARE,
    "malware-url":            INDICATOR_FEED,
    "malicious url":          INDICATOR_FEED,
    "phishing-url":           INDICATOR_FEED,
    "phishing":                INDICATOR_FEED,
    "data breach":            INCIDENT_BREACH,
    "breach":                 INCIDENT_BREACH,
    "incident":               INCIDENT_BREACH,
    "oss-advisory":           SECURITY_ADVISORY,
    "security advisory":      SECURITY_ADVISORY,
    "threat-intel":           NEWS,
    "threat intel":           NEWS,
    "threat intelligence":    NEWS,
    "threat actor":           THREAT_ACTOR,
    "campaign":                CAMPAIGN,
}


def classify_report_type(item: Dict) -> str:
    """Map an item's threat_type (or best-available signal) to a canonical
    report_type. Falls back to UNKNOWN -> validated at NEWS-level strictness
    (least demanding) rather than penalizing unclassified content."""
    tt = str(item.get("threat_type") or "").strip().lower()
    if tt in REPORT_TYPE_MAP:
        return REPORT_TYPE_MAP[tt]
    if item.get("cve_id") or item.get("cve_ids") or item.get("cves"):
        return CVE_VULNERABILITY
    return UNKNOWN


# ---------------------------------------------------------------------------
# Contracts (mandate sections 11-16 + 10's threat_actor/campaign)
# ---------------------------------------------------------------------------

CONTRACTS: Dict[str, ReportContract] = {

    CVE_VULNERABILITY: ReportContract(
        report_type=CVE_VULNERABILITY,
        description="CVE / vulnerability advisory -- mandate section 11.",
        fields=[
            FieldRequirement("title",              REQUIRED),
            FieldRequirement("description",         REQUIRED),
            FieldRequirement("cve_id",              CONDITIONAL, "required when threat_type=CVE/KEV; a Vulnerability item without an assigned CVE (0-day, vendor advisory) is legitimate"),
            FieldRequirement("severity",            REQUIRED),
            FieldRequirement("source_url",          REQUIRED),
            FieldRequirement("cvss_score",           CONDITIONAL, "required once a CVE ID is assigned and scored upstream (NVD); pre-scoring items legitimately lack it"),
            FieldRequirement("epss_score",           OPTIONAL, "not all sources publish EPSS"),
            FieldRequirement("kev_present",          OPTIONAL),
            FieldRequirement("affected_products",    CONDITIONAL, "required when the source names a specific product/vendor"),
            FieldRequirement("exploit_maturity",     OPTIONAL),
            FieldRequirement("attck_technique_ids",  CONDITIONAL, "required only when the description names a concrete exploitation mechanism -- see attck_eligible()"),
            FieldRequirement("detection_rules_total", CONDITIONAL, "required only when is_detection_eligible(item)"),
            FieldRequirement("iocs",                 NOT_APPLICABLE, "most CVE advisories describe a vulnerability, not an active campaign with observable indicators -- absence is not a defect"),
            FieldRequirement("confidence",           OPTIONAL),
        ],
    ),

    RANSOMWARE: ReportContract(
        report_type=RANSOMWARE,
        description="Ransomware activity report -- mandate section 12. Requires semantic separation between actor claim and independent confirmation.",
        fields=[
            FieldRequirement("title",              REQUIRED),
            FieldRequirement("description",         REQUIRED),
            FieldRequirement("actor_tag",           CONDITIONAL, "required when the actor/group is named in source text"),
            FieldRequirement("validation_status",    REQUIRED, "must distinguish claim vs confirmation -- see report-type mismatch check"),
            FieldRequirement("severity",            REQUIRED),
            FieldRequirement("source_url",          REQUIRED),
            FieldRequirement("iocs",                 CONDITIONAL, "required when source publishes indicators (leak site, ransom note, infrastructure) -- absent is legitimate when only a victim-listing is available"),
            FieldRequirement("attck_technique_ids",  CONDITIONAL, "required when the description names concrete TTPs"),
            FieldRequirement("mitigation",           OPTIONAL),
            FieldRequirement("confidence",           OPTIONAL),
        ],
    ),

    MALWARE: ReportContract(
        report_type=MALWARE,
        description="Malware family/campaign report -- mandate section 13.",
        fields=[
            FieldRequirement("title",              REQUIRED),
            FieldRequirement("description",         REQUIRED),
            FieldRequirement("severity",            REQUIRED),
            FieldRequirement("source_url",          REQUIRED),
            FieldRequirement("iocs",                 CONDITIONAL, "required when the source publishes hashes/C2/network indicators"),
            FieldRequirement("attck_technique_ids",  CONDITIONAL, "required when delivery/execution/persistence/C2 behavior is described"),
            FieldRequirement("sigma_rule",           OPTIONAL),
            FieldRequirement("confidence",           OPTIONAL),
        ],
    ),

    INCIDENT_BREACH: ReportContract(
        report_type=INCIDENT_BREACH,
        description="Incident / data breach report -- mandate section 14. Status must distinguish CONFIRMED/REPORTED/CLAIMED/SUSPECTED/UNKNOWN.",
        fields=[
            FieldRequirement("title",              REQUIRED),
            FieldRequirement("description",         REQUIRED),
            FieldRequirement("validation_status",    REQUIRED, "must carry a confirmation-state signal, not just severity"),
            FieldRequirement("severity",            REQUIRED),
            FieldRequirement("source_url",          REQUIRED),
            FieldRequirement("actor_tag",           OPTIONAL, "attribution often unresolved for breaches"),
            FieldRequirement("iocs",                 OPTIONAL),
            FieldRequirement("confidence",           OPTIONAL),
        ],
    ),

    SECURITY_ADVISORY: ReportContract(
        report_type=SECURITY_ADVISORY,
        description="Vendor / OSS security advisory (e.g. GitHub Security Advisories) -- mandate section 15, action-optimized.",
        fields=[
            FieldRequirement("title",              REQUIRED),
            FieldRequirement("description",         REQUIRED),
            FieldRequirement("severity",            REQUIRED),
            FieldRequirement("source_url",          REQUIRED),
            FieldRequirement("cve_id",              CONDITIONAL, "required when the advisory itself assigns a CVE"),
            FieldRequirement("affected_products",    CONDITIONAL, "required when the advisory names a package/product"),
            FieldRequirement("iocs",                 NOT_APPLICABLE, "advisories describe a fixable defect, not observable attacker infrastructure"),
            FieldRequirement("confidence",           OPTIONAL),
        ],
    ),

    NEWS: ReportContract(
        report_type=NEWS,
        description="Cybersecurity / technology news -- mandate section 16. NOT automatically intelligence: 0 IOC, 0 ATT&CK, 0 detection is a valid, correct state, not a defect.",
        fields=[
            FieldRequirement("title",              REQUIRED),
            FieldRequirement("description",         REQUIRED),
            FieldRequirement("source_url",          REQUIRED),
            FieldRequirement("severity",            OPTIONAL, "many news items have no operational severity"),
            FieldRequirement("iocs",                 NOT_APPLICABLE),
            FieldRequirement("attck_technique_ids",  NOT_APPLICABLE),
            FieldRequirement("detection_rules_total", NOT_APPLICABLE),
            FieldRequirement("cvss_score",           NOT_APPLICABLE),
            FieldRequirement("epss_score",           NOT_APPLICABLE),
            FieldRequirement("confidence",           OPTIONAL),
        ],
    ),

    INDICATOR_FEED: ReportContract(
        report_type=INDICATOR_FEED,
        description="Raw indicator pass-through (e.g. OpenPhish phishing URL, URLhaus malware URL) -- single-fact, machine-generated. Not a narrative report; judged on indicator correctness, not prose depth.",
        fields=[
            FieldRequirement("title",              REQUIRED),
            FieldRequirement("description",         REQUIRED, "may legitimately be a single sentence"),
            FieldRequirement("source_url",          REQUIRED),
            FieldRequirement("iocs",                 REQUIRED, "the indicator itself is the entire point of this report type"),
            FieldRequirement("severity",            OPTIONAL),
            FieldRequirement("attck_technique_ids",  NOT_APPLICABLE, "a single flagged URL rarely supports a specific technique beyond the generic phishing/delivery vector already implied by report type"),
            FieldRequirement("detection_rules_total", NOT_APPLICABLE),
            FieldRequirement("cvss_score",           NOT_APPLICABLE),
            FieldRequirement("confidence",           OPTIONAL),
        ],
    ),

    THREAT_ACTOR: ReportContract(
        report_type=THREAT_ACTOR,
        description="Threat actor profile -- mandate section 10. Not yet observed as a distinct threat_type in current platform data; defined for forward compatibility.",
        fields=[
            FieldRequirement("title",              REQUIRED),
            FieldRequirement("description",         REQUIRED),
            FieldRequirement("actor_tag",           REQUIRED),
            FieldRequirement("source_url",          REQUIRED),
            FieldRequirement("attck_technique_ids",  CONDITIONAL, "required when known TTPs are attributed to the actor"),
            FieldRequirement("confidence",           OPTIONAL),
        ],
    ),

    CAMPAIGN: ReportContract(
        report_type=CAMPAIGN,
        description="Multi-incident campaign report -- mandate section 10. Not yet observed as a distinct threat_type in current platform data; defined for forward compatibility.",
        fields=[
            FieldRequirement("title",              REQUIRED),
            FieldRequirement("description",         REQUIRED),
            FieldRequirement("source_url",          REQUIRED),
            FieldRequirement("iocs",                 CONDITIONAL, "required when the campaign report publishes shared infrastructure"),
            FieldRequirement("attck_technique_ids",  CONDITIONAL),
            FieldRequirement("confidence",           OPTIONAL),
        ],
    ),

    UNKNOWN: ReportContract(
        report_type=UNKNOWN,
        description="Unclassified threat_type -- validated at NEWS-level strictness (least demanding) rather than penalized for missing fields it may not need.",
        fields=[
            FieldRequirement("title",              REQUIRED),
            FieldRequirement("description",         REQUIRED),
            FieldRequirement("source_url",          REQUIRED),
        ],
    ),
}


def get_contract(report_type: str) -> ReportContract:
    return CONTRACTS.get(report_type, CONTRACTS[UNKNOWN])


def contract_for_item(item: Dict) -> ReportContract:
    return get_contract(classify_report_type(item))
