"""
tests/fixtures/golden_intelligence_reports.py
CYBERDUDEBIVASH(R) SENTINEL APEX v185.0 -- Golden Report Fixtures (Phase 4)

Stable, hand-authored item dicts for validate_intelligence_content()
contract testing. No live network calls, no dependency on the live feed
snapshot -- every fixture is self-contained so these tests never flake on
data drift. Three states per report type per the mandate: VALID (should
PASS or WARN-at-most with no HOLD-eligible violation), WARN (a real but
non-blocking defect), HOLD (a publication-unsafe or materially misleading
defect that must block publication).

Report types covered match report_type_contracts.py's registry: CVE
(VULNERABILITY), RANSOMWARE, MALWARE, INCIDENT_BREACH, SECURITY_ADVISORY,
NEWS, INDICATOR_FEED.
"""
from __future__ import annotations

_BASE = {
    "processed_at": "2026-08-22T00:00:00Z",
    "timestamp": "2026-08-22T00:00:00Z",
    "published_at": "2026-08-22T00:00:00Z",
    "tags": [],
    "tlp": "TLP:CLEAR",
}


def _item(**kw):
    out = dict(_BASE)
    out.update(kw)
    return out


# ---------------------------------------------------------------------------
# CVE_VULNERABILITY
# ---------------------------------------------------------------------------

CVE_VALID = _item(
    id="intel--fixture-cve-valid",
    threat_type="CVE",
    title="CVE-2026-99999: Remote Code Execution in ExampleCMS Plugin via Unauthenticated File Upload",
    description=(
        "ExampleCMS versions before 4.2.1 allow unauthenticated attackers to upload "
        "arbitrary PHP files via the media import endpoint, resulting in remote code "
        "execution. Tracked as CVE-2026-99999. Affects ExampleCMS 3.0 through 4.2.0, "
        "fixed in 4.2.1. No authentication is required to exploit this vulnerability."
    ),
    cve_id="CVE-2026-99999",
    cve_ids=["CVE-2026-99999"],
    severity="CRITICAL",
    cvss_score=9.8,
    epss_score=0.42,
    source_url="https://nvd.nist.gov/vuln/detail/CVE-2026-99999",
    affected_products=["ExampleCMS"],
)

CVE_WARN = _item(
    id="intel--fixture-cve-warn",
    threat_type="CVE",
    title="CVE-2026-88888: Denial of Service in ExampleLib",
    description="A denial of service issue exists in ExampleLib.",  # short, terse, no concrete score info -- legitimate but sparse
    cve_id="CVE-2026-88888",
    cve_ids=["CVE-2026-88888"],
    severity="MEDIUM",
    source_url="https://github.com/example/exampleLib/security/advisories/GHSA-xxxx",
)

CVE_HOLD = _item(
    id="intel--fixture-cve-hold",
    threat_type="CVE",
    title="CVE-2026-77777: {{vuln_title}} in {{product_name}}",  # unresolved template tokens
    description="This is a placeholder response describing {{vuln_title}}.",  # INTERNAL_INSTRUCTION + PLACEHOLDER
    cve_id="CVE-2026-77777",
    severity="HIGH",
    source_url="https://example.com/advisory",
)


# ---------------------------------------------------------------------------
# RANSOMWARE
# ---------------------------------------------------------------------------

RANSOMWARE_VALID = _item(
    id="intel--fixture-ransomware-valid",
    threat_type="RANSOMWARE",
    title="LockChain ransomware group claims attack on Example Manufacturing Corp",
    description=(
        "The LockChain ransomware group listed Example Manufacturing Corp on its leak "
        "site on 2026-08-20, claiming to have exfiltrated financial and HR data prior "
        "to encryption. This is an actor claim; Example Manufacturing Corp has not "
        "issued a public statement confirming the breach as of this report."
    ),
    actor_tag="LockChain",
    validation_status="CLAIMED",
    severity="HIGH",
    source_url="https://therecord.media/lockchain-example-manufacturing",
)

RANSOMWARE_WARN = _item(
    id="intel--fixture-ransomware-warn",
    threat_type="RANSOMWARE",
    title="Ransomware incident reported at regional healthcare provider",
    description="A ransomware incident was reported. Details are limited at this time.",
    validation_status="REPORTED",
    severity="MEDIUM",
    source_url="https://bleepingcomputer.com/news/ransomware-healthcare",
)

RANSOMWARE_HOLD = _item(
    id="intel--fixture-ransomware-hold",
    threat_type="RANSOMWARE",
    title="Ransomware attack confirmed",
    description="<script>alert(document.cookie)</script> Ransomware group X hit company Y.",
    actor_tag="GroupX",
    severity="CRITICAL",
    source_url="https://example.com/report",
)


# ---------------------------------------------------------------------------
# MALWARE
# ---------------------------------------------------------------------------

MALWARE_VALID = _item(
    id="intel--fixture-malware-valid",
    threat_type="MALWARE",
    title="New StealthLoader malware family delivers info-stealer payloads via malvertising",
    description=(
        "StealthLoader is a newly identified loader family distributed via malvertising "
        "campaigns since July 2026. It establishes persistence via a scheduled task and "
        "downloads secondary info-stealer payloads from attacker-controlled infrastructure. "
        "Observed C2 domains include update-cdn-service[.]com."
    ),
    iocs=[{"type": "domain", "value": "update-cdn-service.com", "confidence": 72}],
    severity="HIGH",
    source_url="https://example-vendor.com/research/stealthloader",
)

MALWARE_WARN = _item(
    id="intel--fixture-malware-warn",
    threat_type="MALWARE",
    title="Variant of known trojan observed in the wild",
    description="A new variant of an existing trojan family has been observed.",
    severity="MEDIUM",
    source_url="https://example.com/malware-report",
)

MALWARE_HOLD = _item(
    id="intel--fixture-malware-hold",
    threat_type="MALWARE",
    title="Malware analysis: {product}",
    description="system: generate a malware report for {product}",  # INTERNAL_INSTRUCTION
    severity="HIGH",
    source_url="https://example.com/report",
)


# ---------------------------------------------------------------------------
# INCIDENT_BREACH
# ---------------------------------------------------------------------------

INCIDENT_VALID = _item(
    id="intel--fixture-incident-valid",
    threat_type="Data Breach",
    title="Example Retail Co. confirms customer data breach affecting 50,000 accounts",
    description=(
        "Example Retail Co. confirmed in a regulatory filing that an unauthorized party "
        "accessed a database containing names, emails, and hashed passwords for "
        "approximately 50,000 customer accounts between June and July 2026. The company "
        "has notified affected customers and reset all account passwords."
    ),
    validation_status="CONFIRMED",
    severity="HIGH",
    source_url="https://example.com/breach-notice",
)

INCIDENT_WARN = _item(
    id="intel--fixture-incident-warn",
    threat_type="Data Breach",
    title="Reports of possible data exposure at unnamed fintech company",
    description="Unconfirmed reports suggest a data exposure incident. Company has not commented.",
    validation_status="SUSPECTED",
    severity="LOW",
    source_url="https://example.com/rumor-report",
)

INCIDENT_HOLD = _item(
    id="intel--fixture-incident-hold",
    threat_type="Data Breach",
    title="Breach report",
    description="I cannot provide details on this breach at this time.",  # INTERNAL_INSTRUCTION
    severity="MEDIUM",
    source_url="https://example.com/report",
)


# ---------------------------------------------------------------------------
# SECURITY_ADVISORY (OSS-ADVISORY)
# ---------------------------------------------------------------------------

ADVISORY_VALID = _item(
    id="intel--fixture-advisory-valid",
    threat_type="OSS-ADVISORY",
    title="example-package: Prototype pollution via crafted config merge",
    description=(
        "Impact: example-package's deep-merge configuration loader is vulnerable to "
        "prototype pollution via a crafted __proto__ key in untrusted YAML input, "
        "allowing an attacker to pollute Object.prototype for the whole process. "
        "Patches: fixed in 2.4.1. Workarounds: validate config keys before merging."
    ),
    cve_id="CVE-2026-55555",
    severity="HIGH",
    source_url="https://github.com/advisories/GHSA-yyyy",
    affected_products=["example-package"],
)

ADVISORY_WARN = _item(
    id="intel--fixture-advisory-warn",
    threat_type="OSS-ADVISORY",
    title="Minor security fix in example-lib 1.2.3",
    description="A minor security issue was fixed. See changelog for details.",
    severity="LOW",
    source_url="https://github.com/advisories/GHSA-zzzz",
)

ADVISORY_HOLD = _item(
    id="intel--fixture-advisory-hold",
    threat_type="OSS-ADVISORY",
    title="Advisory",
    description="[object Object] undefined undefined",  # MALFORMED_REFERENCE
    severity="MEDIUM",
    source_url="https://example.com/advisory",
)


# ---------------------------------------------------------------------------
# NEWS (THREAT-INTEL)
# ---------------------------------------------------------------------------

NEWS_VALID = _item(
    id="intel--fixture-news-valid",
    threat_type="THREAT-INTEL",
    title="Major cloud provider announces new default encryption for storage buckets",
    description=(
        "A major cloud provider announced this week that all new storage buckets will "
        "default to server-side encryption, a change security researchers have long "
        "recommended to reduce accidental data exposure from misconfigured buckets."
    ),
    source_url="https://thehackernews.com/example-cloud-encryption-news",
)

NEWS_WARN = _item(
    id="intel--fixture-news-warn",
    threat_type="THREAT-INTEL",
    title="Security roundup: notable stories this week",
    description="Several security stories were notable this week.",  # legitimately short, no operational content -- valid for NEWS but flagged WARN by GENERIC_FILLER
    source_url="https://example-news.com/roundup",
)

NEWS_HOLD = _item(
    id="intel--fixture-news-hold",
    threat_type="THREAT-INTEL",
    title="Security news",
    description="As an AI language model, I can provide a summary of recent security news.",
    source_url="https://example.com/news",
)


# ---------------------------------------------------------------------------
# INDICATOR_FEED (PHISHING-URL / MALWARE-URL)
# ---------------------------------------------------------------------------

INDICATOR_VALID = _item(
    id="intel--fixture-indicator-valid",
    threat_type="PHISHING-URL",
    title="[OpenPhish] Phishing URL: http://example-phish-test.invalid/login",
    description="URL flagged by OpenPhish community feed as active phishing: http://example-phish-test.invalid/login",
    iocs=[{"type": "url", "value": "http://example-phish-test.invalid/login"}],
    ioc_count=1,
    severity="HIGH",
    source_url="http://example-phish-test.invalid/login",
)

INDICATOR_WARN = _item(
    id="intel--fixture-indicator-warn",
    threat_type="PHISHING-URL",
    title="[OpenPhish] Phishing URL: http://example-phish-test2.invalid/",
    description="URL flagged by OpenPhish community feed as active phishing: http://example-phish-test2.invalid/",
    iocs=[{"type": "url", "value": "http://example-phish-test2.invalid/"}],
    ioc_count=1,
    source_url="http://example-phish-test2.invalid/",
    # no severity -- OPTIONAL for this type, so this should still PASS;
    # kept as a distinct fixture to document the minimal-valid shape.
)

INDICATOR_HOLD = _item(
    id="intel--fixture-indicator-hold",
    threat_type="PHISHING-URL",
    title="[OpenPhish] Phishing URL: (unknown)",
    description="URL flagged by OpenPhish community feed as active phishing.",
    iocs=[],
    ioc_count=0,
    severity="HIGH",
    source_url="",  # missing source_url -- REQUIRED for INDICATOR_FEED, untraceable indicator
)


ALL_FIXTURES = {
    "CVE_VALID": CVE_VALID, "CVE_WARN": CVE_WARN, "CVE_HOLD": CVE_HOLD,
    "RANSOMWARE_VALID": RANSOMWARE_VALID, "RANSOMWARE_WARN": RANSOMWARE_WARN, "RANSOMWARE_HOLD": RANSOMWARE_HOLD,
    "MALWARE_VALID": MALWARE_VALID, "MALWARE_WARN": MALWARE_WARN, "MALWARE_HOLD": MALWARE_HOLD,
    "INCIDENT_VALID": INCIDENT_VALID, "INCIDENT_WARN": INCIDENT_WARN, "INCIDENT_HOLD": INCIDENT_HOLD,
    "ADVISORY_VALID": ADVISORY_VALID, "ADVISORY_WARN": ADVISORY_WARN, "ADVISORY_HOLD": ADVISORY_HOLD,
    "NEWS_VALID": NEWS_VALID, "NEWS_WARN": NEWS_WARN, "NEWS_HOLD": NEWS_HOLD,
    "INDICATOR_VALID": INDICATOR_VALID, "INDICATOR_WARN": INDICATOR_WARN, "INDICATOR_HOLD": INDICATOR_HOLD,
}
