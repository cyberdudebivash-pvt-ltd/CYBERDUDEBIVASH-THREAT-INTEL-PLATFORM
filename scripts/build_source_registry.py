#!/usr/bin/env python3
"""
scripts/build_source_registry.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- Global Intelligence Source Fabric
Canonical Source Registry Generator (P40.0)

WHAT THIS IS
  The single canonical, machine-readable representation of every
  intelligence source this platform integrates, has code for but has not
  activated, requires credentials/licensing for, or has evaluated and
  deferred. This is the "Source Registry" required by the Global
  Intelligence Source Fabric mission: every source is structured
  configuration/data, never logic scattered across the app.

WHY A GENERATOR SCRIPT INSTEAD OF A HAND-WRITTEN JSON FILE
  data/registry/source_registry.json (the checked-in output of this
  script) is the single source of truth that every consumer reads
  (scripts/source_registry.py, scripts/true_intel_ingestor.py,
  scripts/source_fabric_health.py, workers/intel-gateway P40 handlers via
  R2). This script is a maintainability/onboarding tool, not a runtime
  dependency of any of them -- it exists so that onboarding a new source
  (Section 38 of the mission spec) is "add one entry below and re-run",
  not "hand-edit a multi-thousand-line JSON file and risk a typo breaking
  every consumer's parser". Re-run this script only when adding/updating a
  source definition; nothing at request-serving time imports it.

HONESTY CONTRACT (mission Section 40 -- NO FAKE INTEGRATIONS)
  implementation_status is the governance field. It is ONLY ever one of:
    ACTIVE                -- real adapter code, actually scheduled/live today
    IMPLEMENTED            -- real adapter code exists, not currently scheduled
    REQUIRES_CREDENTIALS   -- would work today if a free/paid API key were supplied
    REQUIRES_LICENSE       -- requires a commercial contract/registration/MOU
    PLANNED                 -- no code yet; deferred with a documented reason
    DISABLED                -- was active, deliberately turned off
  Sources with no live code never get reliability_score/quality_score/
  default_confidence above 0, never get a fabricated health_status of
  HEALTHY, and never get non-zero records_* counters. See _status_defaults().

Run: python3 scripts/build_source_registry.py
Output: data/registry/source_registry.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "registry" / "source_registry.json"

REGISTRY_SCHEMA_VERSION = "1.0.0"

IMPLEMENTATION_STATUSES = {
    "ACTIVE", "IMPLEMENTED", "REQUIRES_CREDENTIALS",
    "REQUIRES_LICENSE", "PLANNED", "DISABLED",
}
INTEGRATION_MODES = {"EVENT_STREAM", "ENRICHMENT", "REFERENCE_SYNC", "NOT_INTEGRATED"}
AUTHORITY_LEVELS = {
    "GOVERNMENT_AUTHORITATIVE", "VENDOR_AUTHORITATIVE", "COMMERCIAL_VENDOR",
    "RESEARCH_PUBLICATION", "AGGREGATOR", "COMMUNITY",
}
INTELLIGENCE_DOMAINS = {
    "vulnerability", "exploit", "malware", "ioc", "threat_actor", "campaign",
    "ttp", "infrastructure", "passive_dns", "certificate", "phishing",
    "botnet_c2", "ransomware", "attack_surface", "internet_measurement",
    "dark_web", "security_research", "government_cert", "sector_specific",
    "geopolitical_cyber", "osint_news", "vendor_advisory",
}

# Baseline reliability/quality/confidence by authority level -- ONLY applied
# to sources with a real operating track record (ACTIVE/IMPLEMENTED).
# These are starting points for the Source Quality Engine (mission Section
# 13), not final scores -- p40_production_certification.py and the live
# health aggregator (scripts/source_fabric_health.py) are expected to
# recompute reliability_score from actual error_rate/freshness over time.
_AUTHORITY_BASELINE = {
    "GOVERNMENT_AUTHORITATIVE": (95, 90, 90),
    "VENDOR_AUTHORITATIVE":     (88, 85, 85),
    "COMMERCIAL_VENDOR":        (82, 80, 78),
    "RESEARCH_PUBLICATION":     (75, 72, 65),
    "AGGREGATOR":               (70, 68, 60),
    "COMMUNITY":                (60, 58, 50),
}


def _status_defaults(implementation_status: str) -> Dict[str, Any]:
    """Operational-field defaults keyed ONLY by implementation_status.
    This is the enforcement point for the no-fake-integrations contract."""
    if implementation_status == "ACTIVE":
        return dict(enabled=True, health_status="HEALTHY")
    if implementation_status == "IMPLEMENTED":
        return dict(enabled=False, health_status="NOT_RUNNING")
    if implementation_status == "REQUIRES_CREDENTIALS":
        return dict(enabled=False, health_status="AWAITING_CREDENTIALS")
    if implementation_status == "REQUIRES_LICENSE":
        return dict(enabled=False, health_status="AWAITING_LICENSE")
    if implementation_status == "DISABLED":
        return dict(enabled=False, health_status="DISABLED")
    return dict(enabled=False, health_status="NOT_APPLICABLE")  # PLANNED


def mk(
    source_id: str, canonical_name: str, provider: str, description: str,
    intelligence_domains: List[str], source_type: str, authority_level: str,
    access_type: str, implementation_status: str, wave: int,
    *,
    geographic_scope: str = "GLOBAL",
    sector_scope: Optional[List[str]] = None,
    protocol: str = "REST_JSON",
    endpoint: Optional[str] = None,
    authentication_type: str = "NONE",
    credential_reference: Optional[str] = None,
    polling_interval: str = "on-demand",
    rate_limit: Optional[str] = None,
    pagination_strategy: str = "NONE",
    incremental_cursor_strategy: str = "FULL_RESCAN_ONLY",
    response_format: str = "JSON",
    schema_version: str = "N/A",
    licensing_class: str = "PUBLIC_DOMAIN",
    redistribution_allowed: bool = True,
    commercial_use_allowed: Optional[bool] = None,
    attribution_required: bool = False,
    retention_policy: str = "INDEFINITE",
    freshness_expectation: str = "DAILY",
    priority: int = 3,
    criticality: str = "MEDIUM",
    documentation_url: Optional[str] = None,
    terms_url: Optional[str] = None,
    integration_mode: str = "NOT_INTEGRATED",
    connector_ref: Optional[str] = None,
    notes: Optional[str] = None,
    pipeline_feed_source_key: Optional[str] = None,
) -> Dict[str, Any]:
    assert implementation_status in IMPLEMENTATION_STATUSES, source_id
    assert integration_mode in INTEGRATION_MODES, source_id
    assert authority_level in AUTHORITY_LEVELS, source_id
    for d in intelligence_domains:
        assert d in INTELLIGENCE_DOMAINS, f"{source_id}: unknown domain {d!r}"

    defaults = _status_defaults(implementation_status)
    has_track_record = implementation_status in ("ACTIVE", "IMPLEMENTED")
    rel, qual, conf = _AUTHORITY_BASELINE[authority_level] if has_track_record else (0, 0, 0)

    # Licensing governance (mission Section 23): "do not assume publicly
    # accessible data is commercially redistributable." FREE_NONCOMMERCIAL
    # and INTERNAL_USE_ONLY licensing classes default commercial_use_allowed
    # to False unless a source's actual published terms are checked and it
    # is explicitly passed True at the call site -- secure default, not an
    # optimistic one (mission Section 21: "secure defaults -- permissive
    # behavior requires explicit enablement").
    if commercial_use_allowed is None:
        commercial_use_allowed = licensing_class not in ("FREE_NONCOMMERCIAL", "INTERNAL_USE_ONLY")

    return {
        "source_id": source_id,
        "canonical_name": canonical_name,
        "provider": provider,
        "description": description,
        "intelligence_domains": intelligence_domains,
        "source_type": source_type,
        "authority_level": authority_level,
        "geographic_scope": geographic_scope,
        "sector_scope": sector_scope or ["ALL"],
        "access_type": access_type,
        "protocol": protocol,
        "endpoint": endpoint,
        "authentication_type": authentication_type,
        "credential_reference": credential_reference,
        "polling_interval": polling_interval,
        "rate_limit": rate_limit,
        "pagination_strategy": pagination_strategy,
        "incremental_cursor_strategy": incremental_cursor_strategy,
        "response_format": response_format,
        "schema_version": schema_version,
        "parser_version": "v1" if has_track_record else None,
        "licensing_class": licensing_class,
        "redistribution_allowed": redistribution_allowed,
        "commercial_use_allowed": commercial_use_allowed,
        "attribution_required": attribution_required,
        "retention_policy": retention_policy,
        "freshness_expectation": freshness_expectation,
        "reliability_score": rel,
        "quality_score": qual,
        "default_confidence": conf,
        "enabled": defaults["enabled"],
        "priority": priority,
        "criticality": criticality,
        "health_status": defaults["health_status"],
        "last_success": None,
        "last_failure": None,
        "last_event": None,
        "records_received": 0,
        "records_accepted": 0,
        "records_rejected": 0,
        "records_deduplicated": 0,
        "error_rate": None,
        "latency": None,
        "documentation_url": documentation_url,
        "terms_url": terms_url,
        "implementation_status": implementation_status,
        "wave": wave,
        "integration_mode": integration_mode,
        "connector_ref": connector_ref,
        "notes": notes,
        # Bridges this registry's canonical source_id to the literal
        # feed_source string scripts/true_intel_ingestor.py writes onto
        # manifest items (its internal SOURCE_KEY constants predate this
        # registry and are NOT renamed to match it -- renaming them would
        # silently break data/cache/feed_state.json's already-persisted
        # per-source cursors in production). Only meaningful for
        # EVENT_STREAM sources; defaults to source_id when the two happen
        # to already agree. Consumed by scripts/source_fabric_health.py.
        "pipeline_feed_source_key": pipeline_feed_source_key or source_id,
    }


# =============================================================================
# WAVE 1 -- CORE (mission Section 39). No-credential sources verified
# reachable by live curl during reconnaissance for this change; KEV/NVD/
# GHSA/ransomware.live/URLhaus/RSS already run in production via
# scripts/true_intel_ingestor.py (multi-source-intel.yml, cron
# '45 1,5,9,13,17,21 * * *').
# =============================================================================

_WAVE1: List[Dict[str, Any]] = [
    mk("cisa_kev", "CISA Known Exploited Vulnerabilities Catalog", "CISA (US)",
       "Authoritative US-government catalogue of vulnerabilities confirmed under active "
       "exploitation, with mandated remediation deadlines for US federal agencies.",
       ["vulnerability", "government_cert"], "GOVERNMENT_AUTHORITATIVE", "GOVERNMENT_AUTHORITATIVE",
       "PUBLIC_FREE", "ACTIVE", 1,
       protocol="REST_JSON",
       endpoint="https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
       polling_interval="30m", rate_limit="none published; single bulk JSON fetch",
       pagination_strategy="NONE", incremental_cursor_strategy="PUBLISHED_TIMESTAMP",
       licensing_class="PUBLIC_DOMAIN", freshness_expectation="HOURLY", priority=1,
       criticality="CRITICAL",
       documentation_url="https://www.cisa.gov/known-exploited-vulnerabilities-catalog",
       terms_url="https://www.cisa.gov/website-notices",
       integration_mode="EVENT_STREAM",
       connector_ref="scripts/true_intel_ingestor.py:ingest_cisa_kev"),

    mk("nvd_cve", "NIST National Vulnerability Database (CVE API v2.0)", "NIST (US)",
       "Authoritative US-government CVE repository with CVSS v2/v3, CWE, and CPE affected-"
       "product data.",
       ["vulnerability"], "GOVERNMENT_AUTHORITATIVE", "GOVERNMENT_AUTHORITATIVE",
       "PUBLIC_FREE", "ACTIVE", 1,
       protocol="REST_JSON", endpoint="https://services.nvd.nist.gov/rest/json/cves/2.0",
       authentication_type="API_KEY", credential_reference="NVD_API_KEY",
       polling_interval="1h (48h lookback window)",
       rate_limit="5 req/30s unauthenticated, 50 req/30s with API key",
       pagination_strategy="OFFSET", incremental_cursor_strategy="PUBLISHED_TIMESTAMP",
       licensing_class="PUBLIC_DOMAIN", freshness_expectation="HOURLY", priority=1,
       criticality="CRITICAL", documentation_url="https://nvd.nist.gov/developers/vulnerabilities",
       terms_url="https://nvd.nist.gov/general/faq",
       integration_mode="EVENT_STREAM",
       connector_ref="scripts/true_intel_ingestor.py:ingest_nvd_cves",
       notes="Also has an independent BaseSource-pattern adapter at "
             "core/ingestion/sources/nvd_source.py (IMPLEMENTED, not currently orchestrated "
             "-- see core_ingestion_engine registry note)."),

    mk("first_epss", "FIRST.org Exploit Prediction Scoring System", "FIRST.org",
       "Daily-updated probabilistic score (0-1) estimating likelihood of real-world "
       "exploitation in the next 30 days, for every published CVE. Integrated as a batch "
       "ENRICHMENT pass over CVE IDs already collected from KEV/NVD/GHSA/RSS in the same "
       "run, not as a standalone item stream -- FIRST publishes a score for the entire "
       "~280k-CVE corpus daily, so treating it as a firehose of 'new items' would flood the "
       "manifest with non-events.",
       ["vulnerability"], "RESEARCH_PUBLICATION", "RESEARCH_PUBLICATION",
       "PUBLIC_FREE", "ACTIVE", 1,
       protocol="REST_JSON", endpoint="https://api.first.org/data/v1/epss",
       polling_interval="per-run, batched by CVE ID (100/request)", rate_limit="unpublished; batched conservatively",
       pagination_strategy="OFFSET", incremental_cursor_strategy="FULL_RESCAN_ONLY",
       licensing_class="OPEN_ATTRIBUTION", attribution_required=True,
       freshness_expectation="DAILY", priority=2, criticality="HIGH",
       documentation_url="https://www.first.org/epss/api", terms_url="https://www.first.org/epss/",
       integration_mode="ENRICHMENT",
       connector_ref="scripts/true_intel_ingestor.py:enrich_with_epss"),

    mk("github_advisory_database", "GitHub Security Advisory Database", "GitHub (Microsoft)",
       "Reviewed open-source vulnerability advisories (GHSA) spanning npm, PyPI, Maven, "
       "NuGet, RubyGems, Go, Rust, Composer, etc., cross-referenced to CVE where applicable.",
       ["vulnerability", "vendor_advisory"], "VENDOR_AUTHORITATIVE", "VENDOR_AUTHORITATIVE",
       "PUBLIC_FREE", "ACTIVE", 1,
       protocol="REST_JSON",
       endpoint="https://api.github.com/advisories",
       authentication_type="API_KEY", credential_reference="GITHUB_TOKEN_INTEL",
       polling_interval="per scheduled run", rate_limit="60 req/h unauthenticated, 5000 req/h authenticated",
       pagination_strategy="PAGE_TOKEN", incremental_cursor_strategy="PUBLISHED_TIMESTAMP",
       licensing_class="OPEN_ATTRIBUTION", attribution_required=True,
       freshness_expectation="HOURLY", priority=1, criticality="HIGH",
       documentation_url="https://docs.github.com/en/rest/security-advisories",
       terms_url="https://docs.github.com/en/site-policy/github-terms/github-terms-of-service",
       integration_mode="EVENT_STREAM",
       connector_ref="scripts/true_intel_ingestor.py:ingest_github_advisories",
       pipeline_feed_source_key="github_advisory"),

    mk("mitre_attack", "MITRE ATT&CK Enterprise Matrix (STIX 2.1 bundle)", "MITRE",
       "Canonical adversary tactics/techniques/sub-techniques/mitigations/software/groups "
       "knowledge base, published as a native STIX 2.1 bundle. Ingested as REFERENCE_SYNC "
       "(taxonomy data refreshed on change, not treated as daily 'new items') feeding "
       "Section 16 ATT&CK correlation across the platform. Original STIX object IDs are "
       "preserved verbatim -- never replaced with synthetic IDs.",
       ["ttp", "threat_actor", "security_research"], "VENDOR_AUTHORITATIVE", "VENDOR_AUTHORITATIVE",
       "PUBLIC_FREE", "ACTIVE", 1,
       protocol="STIX_TAXII_2_1",
       endpoint="https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json",
       polling_interval="24h (content-hash gated -- only re-synced on change)",
       rate_limit="GitHub raw content CDN; no documented limit",
       pagination_strategy="BULK_SNAPSHOT", incremental_cursor_strategy="CONTENT_HASH",
       response_format="STIX2.1", schema_version="STIX 2.1",
       licensing_class="OPEN_ATTRIBUTION", attribution_required=True,
       freshness_expectation="WEEKLY", priority=2, criticality="HIGH",
       documentation_url="https://attack.mitre.org", terms_url="https://attack.mitre.org/resources/terms-of-use/",
       integration_mode="REFERENCE_SYNC",
       connector_ref="scripts/true_intel_ingestor.py:sync_mitre_attack"),

    mk("abuse_ch_urlhaus", "abuse.ch URLhaus", "abuse.ch",
       "Community feed of URLs actively distributing malware. VERIFIED REGRESSION during "
       "this change: abuse.ch now mandates an Auth-Key on this endpoint (live curl returned "
       "HTTP 401 unauthenticated on 2026-08-08, confirming the endpoint this platform has "
       "called unauthenticated since v142.0 has been silently returning zero items). Fixed "
       "to send the key when ABUSECH_AUTH_KEY is set and to report AWAITING_CREDENTIALS "
       "explicitly instead of a silent empty result when it is not.",
       ["ioc", "malware", "botnet_c2"], "COMMUNITY", "COMMUNITY",
       "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 1,
       protocol="REST_JSON", endpoint="https://urlhaus-api.abuse.ch/v1/urls/recent/",
       authentication_type="API_KEY", credential_reference="ABUSECH_AUTH_KEY",
       polling_interval="per scheduled run (capped 30/run)", rate_limit="abuse.ch fair-use policy",
       pagination_strategy="NONE", incremental_cursor_strategy="PUBLISHED_TIMESTAMP",
       licensing_class="FREE_NONCOMMERCIAL", attribution_required=True,
       freshness_expectation="HOURLY", priority=2, criticality="HIGH",
       documentation_url="https://urlhaus-api.abuse.ch/", terms_url="https://abuse.ch/about/#tos",
       integration_mode="EVENT_STREAM",
       connector_ref="scripts/true_intel_ingestor.py:ingest_urlhaus",
       pipeline_feed_source_key="urlhaus",
       notes="Auth-Key not present in this environment; code path is ready and activates "
             "automatically once ABUSECH_AUTH_KEY is provisioned as a GitHub Actions secret."),

    mk("abuse_ch_threatfox", "abuse.ch ThreatFox", "abuse.ch",
       "Community IOC feed (IPs, domains, URLs, hashes) tagged to malware families, with "
       "confidence levels contributed by the analyst community.",
       ["ioc", "malware", "botnet_c2"], "COMMUNITY", "COMMUNITY",
       "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 1,
       protocol="REST_JSON", endpoint="https://threatfox-api.abuse.ch/api/v1/",
       authentication_type="API_KEY", credential_reference="ABUSECH_AUTH_KEY",
       polling_interval="1h", pagination_strategy="NONE",
       incremental_cursor_strategy="PUBLISHED_TIMESTAMP",
       licensing_class="FREE_NONCOMMERCIAL", attribution_required=True,
       freshness_expectation="HOURLY", priority=3, criticality="MEDIUM",
       documentation_url="https://threatfox.abuse.ch/api/", terms_url="https://abuse.ch/about/#tos",
       notes="Verified via live curl 2026-08-08: HTTP 401 without Auth-Key (abuse.ch "
             "platform-wide policy). Same ABUSECH_AUTH_KEY as URLhaus/MalwareBazaar would "
             "activate this."),

    mk("abuse_ch_malwarebazaar", "abuse.ch MalwareBazaar", "abuse.ch",
       "Community malware sample-sharing platform: SHA256/MD5/SHA1, signature family, "
       "YARA hits, and vendor detections for recently submitted samples.",
       ["malware"], "COMMUNITY", "COMMUNITY",
       "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 1,
       protocol="REST_JSON", endpoint="https://mb-api.abuse.ch/api/v1/",
       authentication_type="API_KEY", credential_reference="ABUSECH_AUTH_KEY",
       polling_interval="15m", pagination_strategy="NONE",
       incremental_cursor_strategy="CATALOG_VERSION",
       licensing_class="FREE_NONCOMMERCIAL", attribution_required=True,
       freshness_expectation="HOURLY", priority=3, criticality="MEDIUM",
       documentation_url="https://bazaar.abuse.ch/api/", terms_url="https://abuse.ch/about/#tos",
       integration_mode="NOT_INTEGRATED",
       connector_ref="core/ingestion/sources/malwarebazaar_source.py",
       notes="Real BaseSource-pattern adapter code exists (core/ingestion) but that engine "
             "is mounted, never started (see core_ingestion_engine registry note), AND "
             "verified via live curl 2026-08-08: HTTP 401 without Auth-Key. Two independent "
             "reasons this cannot claim ACTIVE today."),

    mk("abuseipdb", "AbuseIPDB", "AbuseIPDB",
       "Crowdsourced IP abuse-report database with confidence scoring across 25 abuse "
       "categories (brute-force, port scan, web attack, spam, etc.).",
       ["ioc", "infrastructure"], "COMMUNITY", "COMMUNITY",
       "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 1,
       protocol="REST_JSON", endpoint="https://api.abuseipdb.com/api/v2/blacklist",
       authentication_type="API_KEY", credential_reference="ABUSEIPDB_API_KEY",
       polling_interval="1h", pagination_strategy="NONE",
       incremental_cursor_strategy="FULL_RESCAN_ONLY",
       licensing_class="FREE_NONCOMMERCIAL", attribution_required=True,
       freshness_expectation="HOURLY", priority=3, criticality="MEDIUM",
       documentation_url="https://docs.abuseipdb.com/", terms_url="https://www.abuseipdb.com/legal/terms-of-use",
       integration_mode="NOT_INTEGRATED",
       connector_ref="core/ingestion/sources/abuseipdb_source.py",
       notes="Real BaseSource-pattern adapter code exists; verified via live curl "
             "2026-08-08: HTTP 401 without a key. core/ingestion orchestrator is dormant "
             "(see core_ingestion_engine note)."),

    mk("openphish", "OpenPhish Community Feed", "OpenPhish",
       "Free plaintext feed of actively-verified phishing URLs, updated continuously.",
       ["phishing"], "COMMUNITY", "COMMUNITY",
       "PUBLIC_FREE", "ACTIVE", 1,
       protocol="REST_JSON", endpoint="https://openphish.com/feed.txt",
       polling_interval="per scheduled run (capped 50/run)",
       rate_limit="unpublished; polled at pipeline cadence only",
       pagination_strategy="NONE", incremental_cursor_strategy="CONTENT_HASH",
       response_format="PLAINTEXT",
       licensing_class="FREE_NONCOMMERCIAL", attribution_required=True,
       freshness_expectation="HOURLY", priority=2, criticality="HIGH",
       documentation_url="https://openphish.com/phish_feed.html", terms_url="https://openphish.com/",
       integration_mode="EVENT_STREAM",
       connector_ref="scripts/true_intel_ingestor.py:ingest_openphish"),

    mk("phishtank", "PhishTank", "Cisco Talos",
       "Community-verified phishing URL database with voting-based confirmation.",
       ["phishing"], "COMMUNITY", "COMMUNITY",
       "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 1,
       protocol="REST_JSON", endpoint="https://data.phishtank.com/data/online-valid.json",
       authentication_type="API_KEY", credential_reference="PHISHTANK_API_KEY",
       polling_interval="1h", pagination_strategy="NONE",
       incremental_cursor_strategy="PUBLISHED_TIMESTAMP",
       licensing_class="FREE_NONCOMMERCIAL", attribution_required=True,
       freshness_expectation="HOURLY", priority=3, criticality="MEDIUM",
       documentation_url="https://phishtank.org/api_info.php", terms_url="https://phishtank.org/terms.php",
       notes="Registration-gated application key required since 2023 policy change."),

    mk("alienvault_otx", "AlienVault Open Threat Exchange", "LevelBlue (AT&T Cybersecurity)",
       "Community threat-sharing platform: pulses (curated IOC bundles) with actor/campaign "
       "tagging contributed by 100k+ analysts.",
       ["ioc", "threat_actor", "campaign"], "COMMUNITY", "COMMUNITY",
       "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 1,
       protocol="REST_JSON", endpoint="https://otx.alienvault.com/api/v1/pulses/subscribed",
       authentication_type="API_KEY", credential_reference="OTX_API_KEY",
       polling_interval="1h", pagination_strategy="PAGE_TOKEN",
       incremental_cursor_strategy="PUBLISHED_TIMESTAMP",
       licensing_class="FREE_NONCOMMERCIAL", attribution_required=True,
       freshness_expectation="HOURLY", priority=2, criticality="HIGH",
       documentation_url="https://otx.alienvault.com/api", terms_url="https://www.alienvault.com/terms-of-use",
       notes="Free API key required (no anonymous access tier)."),

    mk("greynoise_community", "GreyNoise Community API", "GreyNoise",
       "Internet-wide scan/mass-exploitation noise classification -- distinguishes targeted "
       "attacks from opportunistic internet background noise.",
       ["ioc", "internet_measurement", "attack_surface"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 1,
       protocol="REST_JSON", endpoint="https://api.greynoise.io/v3/community/{ip}",
       authentication_type="API_KEY", credential_reference="GREYNOISE_API_KEY",
       polling_interval="on-demand (per-IOC lookup, not a bulk feed)",
       pagination_strategy="NONE", incremental_cursor_strategy="FULL_RESCAN_ONLY",
       licensing_class="COMMERCIAL_LICENSED", freshness_expectation="REALTIME",
       priority=3, criticality="MEDIUM",
       documentation_url="https://docs.greynoise.io/", terms_url="https://www.greynoise.io/terms",
       notes="Community tier is lookup-by-IP, not a bulk 'recent' feed -- best modeled as an "
             "ENRICHMENT source once activated, not an event stream."),

    mk("ransomware_live", "ransomware.live", "ransomware.live (independent research)",
       "Tracks ransomware group leak-site postings (named victims) scraped from public Tor "
       "leak sites and mirrored via a public API.",
       ["ransomware", "threat_actor"], "AGGREGATOR", "AGGREGATOR",
       "PUBLIC_FREE", "ACTIVE", 1,
       protocol="REST_JSON", endpoint="https://api.ransomware.live/v2/recentvictims",
       polling_interval="per scheduled run (capped 50/run)",
       pagination_strategy="NONE", incremental_cursor_strategy="PUBLISHED_TIMESTAMP",
       licensing_class="FREE_NONCOMMERCIAL", attribution_required=True,
       freshness_expectation="HOURLY", priority=2, criticality="HIGH",
       documentation_url="https://www.ransomware.live/legal-notes", terms_url="https://www.ransomware.live/legal-notes",
       integration_mode="EVENT_STREAM",
       connector_ref="scripts/true_intel_ingestor.py:ingest_ransomware_live"),

    mk("cisa_cybersecurity_advisories", "CISA Cybersecurity Advisories", "CISA (US)",
       "ICS-CERT and general cybersecurity advisories published by CISA, delivered via RSS.",
       ["vulnerability", "government_cert", "vendor_advisory"], "GOVERNMENT_AUTHORITATIVE",
       "GOVERNMENT_AUTHORITATIVE", "PUBLIC_FREE", "ACTIVE", 1,
       protocol="RSS", endpoint="https://www.cisa.gov/cybersecurity-advisories/all.xml",
       polling_interval="per scheduled run", pagination_strategy="NONE",
       incremental_cursor_strategy="PUBLISHED_TIMESTAMP", response_format="RSS_XML",
       licensing_class="PUBLIC_DOMAIN", freshness_expectation="HOURLY", priority=2,
       criticality="HIGH", documentation_url="https://www.cisa.gov/news-events/cybersecurity-advisories",
       integration_mode="EVENT_STREAM",
       connector_ref="scripts/true_intel_ingestor.py:ingest_rss_feeds (agent/config.py:RSS_FEEDS)",
       pipeline_feed_source_key="rss:cisa.gov"),

    mk("rss_osint_aggregate", "OSINT / Vendor Research RSS Aggregate", "Multiple (see agent/config.py)",
       "~30 curated RSS feeds spanning breaking-news OSINT (The Hacker News, Krebs on "
       "Security, The Record, CyberScoop, Security Affairs), vulnerability research "
       "(CVEfeed, Vulners, ZDI), and vendor threat-research blogs (SentinelOne, Unit 42, "
       "Securelist, CrowdStrike, Mandiant). Individual feed URLs, including a maintained "
       "dead-feed exclusion list from prior audits, live in agent/config.py:RSS_FEEDS -- "
       "listed here as one registry entry (the taxonomy in mission Section 5 does not ask "
       "for each individual blog as a separately governed 'source').",
       ["osint_news", "security_research", "vendor_advisory"], "AGGREGATOR", "AGGREGATOR",
       "PUBLIC_FREE", "ACTIVE", 1,
       protocol="RSS", endpoint=None, polling_interval="per scheduled run (10 items/feed cap)",
       pagination_strategy="NONE", incremental_cursor_strategy="PUBLISHED_TIMESTAMP",
       response_format="RSS_XML", licensing_class="FREE_NONCOMMERCIAL", attribution_required=True,
       freshness_expectation="HOURLY", priority=3, criticality="MEDIUM",
       integration_mode="EVENT_STREAM",
       connector_ref="scripts/true_intel_ingestor.py:ingest_rss_feeds",
       pipeline_feed_source_key="rss:*",
       notes="unit42.paloaltonetworks.com, securelist.com, sentinelone.com, "
             "crowdstrike.com, mandiant.com research blogs are already covered here -- "
             "not separately listed as Wave 2 vendor-research entries below. "
             "pipeline_feed_source_key='rss:*' is the catch-all bucket for any RSS feed "
             "item not matched by a more specific rss:<substring> entry (see "
             "scripts/source_fabric_health.py for the matching order)."),

    mk("shadowserver", "Shadowserver Foundation", "The Shadowserver Foundation",
       "Non-profit providing free daily victim-notification and internet-exposure reports "
       "to national CERTs and vetted network owners (vulnerable/compromised/misconfigured "
       "host telemetry).",
       ["infrastructure", "attack_surface", "internet_measurement", "botnet_c2"],
       "COMMUNITY", "COMMUNITY", "COMMERCIAL_LICENSED", "REQUIRES_LICENSE", 1,
       protocol="REST_JSON", authentication_type="MTLS", credential_reference="SHADOWSERVER_API_CERT",
       licensing_class="INTERNAL_USE_ONLY", redistribution_allowed=False,
       freshness_expectation="DAILY", priority=3, criticality="MEDIUM",
       documentation_url="https://www.shadowserver.org/what-we-do/network-reporting/api-documentation/",
       terms_url="https://www.shadowserver.org/what-we-do/network-reporting/",
       notes="Requires vetted registration (organization + IP ranges under management) -- "
             "not a self-serve API key."),

    mk("virustotal", "VirusTotal", "Google (Chronicle)",
       "Multi-engine file/URL/domain/IP reputation aggregator with 70+ AV engine "
       "detections, sandboxing, and relationship graphing.",
       ["malware", "ioc"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 1,
       protocol="REST_JSON", endpoint="https://www.virustotal.com/api/v3/",
       authentication_type="API_KEY", credential_reference="VIRUSTOTAL_API_KEY",
       polling_interval="on-demand (per-IOC lookup)", pagination_strategy="CURSOR",
       licensing_class="COMMERCIAL_LICENSED", freshness_expectation="REALTIME",
       priority=2, criticality="HIGH", documentation_url="https://docs.virustotal.com/reference/overview",
       terms_url="https://support.virustotal.com/hc/en-us/articles/115002145529-Terms-of-Service",
       notes="Public API free tier is rate-limited lookup, not a bulk feed -- best modeled "
             "as ENRICHMENT once activated."),

    mk("cert_in", "CERT-In (Indian Computer Emergency Response Team)", "CERT-In / MeitY (India)",
       "India's national CERT: vulnerability notes, advisories, and incident guidance.",
       ["government_cert", "sector_specific", "geopolitical_cyber"],
       "GOVERNMENT_AUTHORITATIVE", "GOVERNMENT_AUTHORITATIVE", "PUBLIC_FREE", "PLANNED", 1,
       geographic_scope="IN", licensing_class="PUBLIC_DOMAIN", priority=2, criticality="HIGH",
       documentation_url="https://www.cert-in.org.in/",
       notes="No stable machine-readable feed (RSS/API) publicly confirmed reachable as of "
             "this change -- CERT-In publishes advisories as HTML/PDF bulletins. Deferred "
             "pending a confirmed structured endpoint rather than building a fragile HTML "
             "scraper."),

    mk("osv_dev", "OSV.dev (Open Source Vulnerabilities)", "Open Source Security Foundation (OpenSSF)",
       "Aggregates ecosystem-specific vulnerability databases (PyPI, npm, Go, crates.io, "
       "Maven, RubyGems, etc.) into one schema, cross-linked to GHSA/CVE.",
       ["vulnerability"], "AGGREGATOR", "AGGREGATOR", "PUBLIC_FREE", "PLANNED", 1,
       protocol="REST_JSON", endpoint="https://api.osv.dev/v1/query",
       documentation_url="https://google.github.io/osv.dev/api/", terms_url="https://osv.dev/",
       licensing_class="PUBLIC_DOMAIN", priority=3, criticality="MEDIUM",
       notes="Verified reachable (live curl 2026-08-08). No endpoint exists for 'everything "
             "published since cursor X across all ecosystems' -- the query API needs a "
             "package/commit context, and the alternative (per-ecosystem all.zip bulk "
             "export, confirmed ~11MB for the Go ecosystem alone, larger for npm/PyPI) needs "
             "dedicated storage/compute budget this change does not allocate. Tracked for "
             "Wave 2 as a scoped per-ecosystem bulk-sync job, not built here to avoid a "
             "fragile or partial implementation."),

    mk("core_ingestion_engine", "core/ingestion BaseSource Adapter Engine (internal)", "CyberDudeBivash (internal)",
       "Pre-existing, well-formed Python adapter framework (BaseSource contract: fetch/"
       "health/rate-limit/retry/structured-errors) mounted into the Railway FastAPI app at "
       "api/main.py:294-296 (ingestion_router), with 4 source adapters already coded: NVD, "
       "CISA KEV, MalwareBazaar, AbuseIPDB. VERIFIED DURING RECONNAISSANCE: get_engine() is "
       "instantiated but .start() is never called anywhere in the live path -- the "
       "scheduler/worker threads that would actually run these adapters never start. This "
       "registry entry documents that finding; it is not itself a data source.",
       ["vulnerability", "malware", "ioc"], "AGGREGATOR", "AGGREGATOR", "PUBLIC_FREE",
       "IMPLEMENTED", 1, priority=4, criticality="LOW",
       integration_mode="NOT_INTEGRATED",
       connector_ref="core/ingestion/ingestion_engine.py:get_engine",
       notes="Activating engine.start() would run a background thread pool inside the "
             "shared Railway web dyno and would independently re-fetch NVD/KEV -- sources "
             "already live via scripts/true_intel_ingestor.py through a different code "
             "path. That is a real architectural change (new always-on background "
             "workload in a request-serving process, and a second live producer for data "
             "the platform already gets elsewhere) requiring its own blast-radius sign-off "
             "under the Architecture Preservation Rule -- intentionally NOT done in this "
             "change. Recommended as a Wave 2 follow-up with its own plan."),
]


# =============================================================================
# WAVE 2 -- ENTERPRISE VENDOR PSIRTs, EXPLOIT/MALWARE RESEARCH, THREAT-ACTOR
# RESEARCH VENDORS. Structured, but no live code -- deferred per mission
# Section 39 wave discipline ("do NOT activate hundreds of sources
# simultaneously").
# =============================================================================

def _vendor_psirt(source_id, canonical_name, provider, product_scope, docs_url, geo="GLOBAL"):
    return mk(
        source_id, canonical_name, provider,
        f"Vendor Product Security Incident Response Team advisories for {product_scope}.",
        ["vulnerability", "vendor_advisory"], "VENDOR_AUTHORITATIVE", "VENDOR_AUTHORITATIVE",
        "PUBLIC_FREE", "PLANNED", 2, geographic_scope=geo,
        licensing_class="PUBLIC_DOMAIN", freshness_expectation="DAILY",
        priority=3, criticality="MEDIUM", documentation_url=docs_url,
        notes="Wave 2 vendor PSIRT -- endpoint/feed format to be confirmed against the "
              "vendor's current published advisory API before implementation begins.",
    )

_WAVE2_PSIRT: List[Dict[str, Any]] = [
    _vendor_psirt("microsoft_msrc", "Microsoft Security Response Center", "Microsoft",
                  "Windows, Azure, Microsoft 365, and the Patch Tuesday cycle",
                  "https://msrc.microsoft.com/update-guide"),
    _vendor_psirt("apple_security", "Apple Security Releases", "Apple",
                  "macOS, iOS, iPadOS, watchOS, tvOS, Safari",
                  "https://support.apple.com/en-us/HT201222"),
    _vendor_psirt("google_security_advisories", "Google / Android Security Advisories", "Google",
                  "Android, Chrome, ChromeOS, Google Cloud",
                  "https://source.android.com/docs/security/bulletin"),
    _vendor_psirt("cisco_psirt", "Cisco PSIRT Advisories", "Cisco",
                  "IOS/IOS-XE/NX-OS, ASA, network infrastructure",
                  "https://sec.cloudapps.cisco.com/security/center/publicationListing.x"),
    _vendor_psirt("fortinet_psirt", "Fortinet PSIRT Advisories", "Fortinet",
                  "FortiOS, FortiGate, and the Fortinet product suite",
                  "https://www.fortiguard.com/psirt"),
    _vendor_psirt("paloalto_psirt", "Palo Alto Networks Security Advisories", "Palo Alto Networks",
                  "PAN-OS, GlobalProtect, Prisma", "https://security.paloaltonetworks.com/"),
    _vendor_psirt("broadcom_vmware_advisories", "Broadcom/VMware Security Advisories", "Broadcom",
                  "vSphere, ESXi, NSX, VMware product suite",
                  "https://support.broadcom.com/security-advisory"),
    _vendor_psirt("redhat_security", "Red Hat Security Advisories (RHSA)", "Red Hat (IBM)",
                  "RHEL and the Red Hat product portfolio", "https://access.redhat.com/security/"),
    _vendor_psirt("ubuntu_security", "Ubuntu Security Notices (USN)", "Canonical",
                  "Ubuntu LTS/interim releases", "https://ubuntu.com/security/notices"),
    _vendor_psirt("debian_security", "Debian Security Advisories (DSA)", "Debian Project",
                  "Debian stable/oldstable", "https://www.debian.org/security/"),
    _vendor_psirt("suse_security", "SUSE Security Advisories", "SUSE",
                  "SLES, openSUSE", "https://www.suse.com/security/cve/"),
    _vendor_psirt("oracle_csa", "Oracle Critical Patch Update", "Oracle",
                  "Database, Java, Fusion Middleware, E-Business Suite",
                  "https://www.oracle.com/security-alerts/"),
    _vendor_psirt("adobe_psirt", "Adobe Product Security Bulletins", "Adobe",
                  "Acrobat/Reader, Creative Cloud, Experience Manager",
                  "https://helpx.adobe.com/security.html"),
    _vendor_psirt("sap_security", "SAP Security Patch Day", "SAP",
                  "SAP ERP/S4HANA/NetWeaver product suite", "https://support.sap.com/en/my-support/knowledge-base/security-notes-news.html"),
    _vendor_psirt("atlassian_security", "Atlassian Security Advisories", "Atlassian",
                  "Jira, Confluence, Bitbucket, Bamboo", "https://confluence.atlassian.com/security"),
    mk("cert_cc", "CERT Coordination Center (CERT/CC)", "Carnegie Mellon SEI",
       "Vulnerability coordination and disclosure notes from the original CERT.",
       ["vulnerability", "government_cert"], "RESEARCH_PUBLICATION", "RESEARCH_PUBLICATION",
       "PUBLIC_FREE", "PLANNED", 2, licensing_class="PUBLIC_DOMAIN", priority=3,
       criticality="MEDIUM", documentation_url="https://www.kb.cert.org/vulnotes/"),
    mk("cert_eu", "CERT-EU", "CERT-EU (European Union)",
       "EU institutions' CERT: advisories and threat landscape reports.",
       ["government_cert", "geopolitical_cyber"], "GOVERNMENT_AUTHORITATIVE",
       "GOVERNMENT_AUTHORITATIVE", "PUBLIC_FREE", "PLANNED", 2, geographic_scope="EU",
       licensing_class="PUBLIC_DOMAIN", priority=3, criticality="MEDIUM",
       documentation_url="https://cert.europa.eu/publications/security-advisories",
       notes="Prior RSS attempt (agent/config.py history) logged 0 entries consistently; "
             "needs a confirmed working feed before implementation."),
    mk("jvn", "Japan Vulnerability Notes (JVN)", "JPCERT/CC + IPA",
       "Japan's coordinated vulnerability disclosure database.",
       ["vulnerability", "government_cert"], "GOVERNMENT_AUTHORITATIVE",
       "GOVERNMENT_AUTHORITATIVE", "PUBLIC_FREE", "PLANNED", 2, geographic_scope="JP",
       licensing_class="PUBLIC_DOMAIN", priority=4, criticality="LOW",
       documentation_url="https://jvn.jp/en/"),
]

_WAVE2_EXPLOIT_MALWARE: List[Dict[str, Any]] = [
    mk("exploit_db", "Exploit-DB", "Offensive Security",
       "Archive of public exploits and vulnerable software, with Exploit Database IDs.",
       ["exploit"], "COMMUNITY", "COMMUNITY", "PUBLIC_FREE", "PLANNED", 2,
       licensing_class="PUBLIC_DOMAIN", priority=3, criticality="MEDIUM",
       documentation_url="https://www.exploit-db.com/",
       notes="PoC existence tracked distinctly from verified/weaponized exploitation per "
             "mission Section 5's exploit-maturity requirement -- Exploit-DB entries would "
             "be ingested as 'poc_published' evidence, never conflated with confirmed "
             "in-the-wild exploitation (that distinction stays owned by CISA KEV)."),
    mk("packetstorm", "Packet Storm Security", "Packet Storm",
       "Exploit, advisory, and security-tool archive.",
       ["exploit", "security_research"], "COMMUNITY", "COMMUNITY", "PUBLIC_FREE", "PLANNED", 2,
       priority=4, criticality="LOW", documentation_url="https://packetstormsecurity.com/",
       notes="Prior fetch attempts (agent/config.py history) logged CI-runner IP blocks."),
    mk("nuclei_templates", "ProjectDiscovery Nuclei Templates", "ProjectDiscovery",
       "Community-maintained YAML vulnerability-detection templates, version-controlled on "
       "GitHub -- template additions are a strong signal of new detectable exploitation.",
       ["exploit", "vulnerability"], "COMMUNITY", "COMMUNITY", "PUBLIC_FREE", "PLANNED", 2,
       protocol="REST_JSON", endpoint="https://api.github.com/repos/projectdiscovery/nuclei-templates/commits",
       licensing_class="OPEN_ATTRIBUTION", attribution_required=True, priority=3,
       criticality="MEDIUM", documentation_url="https://github.com/projectdiscovery/nuclei-templates"),
    mk("metasploit_framework", "Metasploit Framework Modules", "Rapid7",
       "Weaponized-exploit module repository -- module presence is strong exploit-maturity "
       "evidence.",
       ["exploit"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR", "PUBLIC_FREE", "PLANNED", 2,
       licensing_class="OPEN_ATTRIBUTION", attribution_required=True, priority=3,
       criticality="MEDIUM", documentation_url="https://github.com/rapid7/metasploit-framework"),
    mk("rapid7_research", "Rapid7 Research (AttackerKB / Labs)", "Rapid7",
       "Vulnerability exploitability analysis and attacker-perspective research.",
       ["vulnerability", "exploit", "security_research"], "COMMERCIAL_VENDOR",
       "COMMERCIAL_VENDOR", "PUBLIC_FREE", "PLANNED", 2, priority=4, criticality="LOW",
       documentation_url="https://www.rapid7.com/research/"),
    mk("malware_traffic_analysis", "Malware-Traffic-Analysis.net", "Brad Duncan (independent research)",
       "Packet-capture-level malware traffic analysis with IOC writeups.",
       ["malware", "ioc"], "RESEARCH_PUBLICATION", "RESEARCH_PUBLICATION", "PUBLIC_FREE",
       "PLANNED", 2, priority=4, criticality="LOW",
       documentation_url="https://www.malware-traffic-analysis.net/"),
    mk("anyrun", "ANY.RUN Interactive Sandbox", "ANY.RUN",
       "Interactive malware detonation sandbox with public sample submissions and IOC "
       "extraction.",
       ["malware", "ioc"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR", "FREE_REGISTRATION",
       "REQUIRES_CREDENTIALS", 2, authentication_type="API_KEY",
       credential_reference="ANYRUN_API_KEY", licensing_class="COMMERCIAL_LICENSED",
       priority=4, criticality="LOW", documentation_url="https://any.run/api-documentation/"),
    mk("hybrid_analysis", "Hybrid Analysis", "CrowdStrike",
       "Free-tier malware sandbox analysis and IOC/report export.",
       ["malware", "ioc"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR", "FREE_REGISTRATION",
       "REQUIRES_CREDENTIALS", 2, authentication_type="API_KEY",
       credential_reference="HYBRID_ANALYSIS_API_KEY", licensing_class="COMMERCIAL_LICENSED",
       priority=4, criticality="LOW", documentation_url="https://www.hybrid-analysis.com/docs/api/v2"),
    mk("cape_sandbox", "CAPE Sandbox (public instances)", "CAPESandbox community",
       "Open-source malware configuration/behavior extraction sandbox.",
       ["malware"], "COMMUNITY", "COMMUNITY", "PUBLIC_FREE", "PLANNED", 2,
       priority=5, criticality="LOW", documentation_url="https://capesandbox.com/"),
    mk("malpedia", "Malpedia", "Fraunhofer FKIE",
       "Curated malware-family reference corpus with YARA rules, mapped to actor "
       "attribution.",
       ["malware", "threat_actor"], "RESEARCH_PUBLICATION", "RESEARCH_PUBLICATION",
       "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 2, authentication_type="API_KEY",
       credential_reference="MALPEDIA_API_KEY", licensing_class="FREE_NONCOMMERCIAL",
       attribution_required=True, priority=3, criticality="MEDIUM",
       documentation_url="https://malpedia.caad.fkie.fraunhofer.de/usage/api"),
    mk("vx_underground", "VX-Underground", "vx-underground",
       "Large-scale malware sample and research-paper archive.",
       ["malware", "security_research"], "COMMUNITY", "COMMUNITY", "PUBLIC_FREE", "PLANNED",
       2, priority=5, criticality="LOW", documentation_url="https://vx-underground.org/"),
]

_WAVE2_ACTOR_RESEARCH: List[Dict[str, Any]] = [
    mk("mandiant", "Mandiant Threat Intelligence", "Google (Mandiant)",
       "Nation-state and criminal actor attribution research, APT tracking.",
       ["threat_actor", "campaign", "security_research"], "COMMERCIAL_VENDOR",
       "COMMERCIAL_VENDOR", "COMMERCIAL_LICENSED", "REQUIRES_LICENSE", 2,
       licensing_class="COMMERCIAL_LICENSED", redistribution_allowed=False, priority=2,
       criticality="HIGH", documentation_url="https://www.mandiant.com/advantage/threat-intelligence"),
    mk("crowdstrike_intel", "CrowdStrike Falcon Intelligence", "CrowdStrike",
       "Adversary-tracked (named) threat-actor intelligence with TTP and campaign mapping.",
       ["threat_actor", "campaign", "ttp"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "COMMERCIAL_LICENSED", "REQUIRES_LICENSE", 2, licensing_class="COMMERCIAL_LICENSED",
       redistribution_allowed=False, priority=2, criticality="HIGH",
       documentation_url="https://www.crowdstrike.com/platform/threat-intelligence/"),
    mk("microsoft_threat_intelligence", "Microsoft Threat Intelligence", "Microsoft",
       "Nation-state actor tracking (Microsoft naming taxonomy) and campaign research.",
       ["threat_actor", "campaign"], "VENDOR_AUTHORITATIVE", "VENDOR_AUTHORITATIVE",
       "PUBLIC_FREE", "PLANNED", 2, priority=3, criticality="MEDIUM",
       documentation_url="https://www.microsoft.com/en-us/security/blog/threat-intelligence/"),
    mk("google_threat_intelligence", "Google Threat Intelligence Group (GTIG)", "Google",
       "Combined Mandiant + Google TAG nation-state and cybercrime research.",
       ["threat_actor", "campaign"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "COMMERCIAL_LICENSED", "REQUIRES_LICENSE", 2, licensing_class="COMMERCIAL_LICENSED",
       redistribution_allowed=False, priority=3, criticality="MEDIUM",
       documentation_url="https://cloud.google.com/security/gti"),
    mk("secureworks_ctu", "Secureworks Counter Threat Unit", "Secureworks (Sophos)",
       "Threat-actor and campaign research (GOLD-prefixed actor taxonomy).",
       ["threat_actor", "campaign"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "COMMERCIAL_LICENSED", "REQUIRES_LICENSE", 2, licensing_class="COMMERCIAL_LICENSED",
       redistribution_allowed=False, priority=4, criticality="LOW",
       documentation_url="https://www.secureworks.com/research"),
    mk("sophos_x_ops", "Sophos X-Ops", "Sophos",
       "Ransomware and endpoint-threat research.",
       ["threat_actor", "ransomware"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "PUBLIC_FREE", "PLANNED", 2, priority=4, criticality="LOW",
       documentation_url="https://news.sophos.com/en-us/category/threat-research/"),
    mk("trendmicro_research", "Trend Micro Research", "Trend Micro",
       "APT and criminal campaign research.",
       ["threat_actor", "campaign"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "PUBLIC_FREE", "PLANNED", 2, priority=4, criticality="LOW",
       documentation_url="https://www.trendmicro.com/en_us/research.html"),
    mk("proofpoint_research", "Proofpoint Threat Research", "Proofpoint",
       "Email-borne threat and BEC/phishing campaign research.",
       ["threat_actor", "phishing", "campaign"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "PUBLIC_FREE", "PLANNED", 2, priority=4, criticality="LOW",
       documentation_url="https://www.proofpoint.com/us/blog/threat-insight"),
    mk("ibm_xforce", "IBM X-Force Exchange", "IBM",
       "Threat-actor and vulnerability intelligence sharing platform.",
       ["threat_actor", "vulnerability", "ioc"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 2, authentication_type="API_KEY",
       credential_reference="XFORCE_API_KEY", licensing_class="FREE_NONCOMMERCIAL",
       priority=4, criticality="LOW", documentation_url="https://api.xforce.ibmcloud.com/doc/"),
    mk("checkpoint_research", "Check Point Research", "Check Point",
       "Threat-actor, malware, and campaign research.",
       ["threat_actor", "malware", "campaign"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "PUBLIC_FREE", "PLANNED", 2, priority=4, criticality="LOW",
       documentation_url="https://research.checkpoint.com/"),
]


# =============================================================================
# WAVE 3 -- INFRASTRUCTURE / INTERNET EXPOSURE / PASSIVE DNS
# =============================================================================

_WAVE3: List[Dict[str, Any]] = [
    mk("censys", "Censys", "Censys",
       "Internet-wide host/certificate/service scan data.",
       ["infrastructure", "attack_surface", "internet_measurement", "certificate"],
       "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR", "FREE_REGISTRATION", "REQUIRES_CREDENTIALS",
       3, authentication_type="API_KEY", credential_reference="CENSYS_API_ID",
       licensing_class="COMMERCIAL_LICENSED", priority=3, criticality="MEDIUM",
       documentation_url="https://search.censys.io/api"),
    mk("shodan", "Shodan", "Shodan",
       "Internet-wide device/service scan data and vulnerability tagging.",
       ["infrastructure", "attack_surface", "internet_measurement"], "COMMERCIAL_VENDOR",
       "COMMERCIAL_VENDOR", "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 3,
       authentication_type="API_KEY", credential_reference="SHODAN_API_KEY",
       licensing_class="COMMERCIAL_LICENSED", priority=3, criticality="MEDIUM",
       documentation_url="https://developer.shodan.io/api",
       notes="Verified via live curl 2026-08-08: HTTP 401 without a key, as expected."),
    mk("securitytrails", "SecurityTrails", "SecurityTrails (Recorded Future)",
       "Historical + current DNS/WHOIS/passive-DNS data.",
       ["infrastructure", "passive_dns"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 3, authentication_type="API_KEY",
       credential_reference="SECURITYTRAILS_API_KEY", licensing_class="COMMERCIAL_LICENSED",
       priority=4, criticality="LOW", documentation_url="https://docs.securitytrails.com/"),
    mk("domaintools", "DomainTools Iris", "DomainTools",
       "WHOIS history, domain risk scoring, infrastructure pivoting.",
       ["infrastructure", "passive_dns"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "COMMERCIAL_LICENSED", "REQUIRES_LICENSE", 3, licensing_class="COMMERCIAL_LICENSED",
       redistribution_allowed=False, priority=4, criticality="LOW",
       documentation_url="https://www.domaintools.com/resources/api-documentation/"),
    mk("farsight_dnsdb", "Farsight DNSDB", "DomainTools (Farsight)",
       "Passive DNS historical resolution database.",
       ["passive_dns", "infrastructure"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "COMMERCIAL_LICENSED", "REQUIRES_LICENSE", 3, licensing_class="COMMERCIAL_LICENSED",
       redistribution_allowed=False, priority=4, criticality="LOW",
       documentation_url="https://docs.dnsdb.info/dnsdb-apiv2/"),
    mk("circl_passive_dns", "CIRCL Passive DNS", "CIRCL (Luxembourg)",
       "Passive DNS replication service for CERT/vetted-community members.",
       ["passive_dns", "infrastructure"], "GOVERNMENT_AUTHORITATIVE",
       "GOVERNMENT_AUTHORITATIVE", "FREE_REGISTRATION", "REQUIRES_LICENSE", 3,
       geographic_scope="EU", licensing_class="INTERNAL_USE_ONLY", redistribution_allowed=False,
       priority=4, criticality="LOW", documentation_url="https://www.circl.lu/services/passive-dns/"),
    mk("riskiq_passivetotal", "RiskIQ PassiveTotal", "Microsoft (RiskIQ)",
       "Passive DNS, WHOIS, SSL cert, and infrastructure pivot platform.",
       ["passive_dns", "infrastructure", "certificate"], "COMMERCIAL_VENDOR",
       "COMMERCIAL_VENDOR", "COMMERCIAL_LICENSED", "REQUIRES_LICENSE", 3,
       licensing_class="COMMERCIAL_LICENSED", redistribution_allowed=False, priority=4,
       criticality="LOW", documentation_url="https://community.riskiq.com/"),
    mk("whoisxmlapi", "WhoisXML API", "WhoisXML API Inc.",
       "WHOIS, reverse WHOIS, and DNS history lookup API.",
       ["infrastructure", "passive_dns"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 3, authentication_type="API_KEY",
       credential_reference="WHOISXMLAPI_KEY", licensing_class="COMMERCIAL_LICENSED",
       priority=5, criticality="LOW", documentation_url="https://whois.whoisxmlapi.com/documentation"),
    mk("dnslytics", "DNSlytics", "DNSlytics",
       "Reverse IP/analytics-ID/adsense-ID infrastructure pivoting.",
       ["infrastructure"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR", "FREE_REGISTRATION",
       "REQUIRES_CREDENTIALS", 3, authentication_type="API_KEY",
       credential_reference="DNSLYTICS_API_KEY", licensing_class="COMMERCIAL_LICENSED",
       priority=5, criticality="LOW", documentation_url="https://dnslytics.com/api"),
    mk("urlscan_io", "urlscan.io", "urlscan.io",
       "Automated website/URL scanning with screenshot, DOM, and infrastructure capture.",
       ["infrastructure", "phishing", "attack_surface"], "COMMUNITY", "COMMUNITY",
       "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 3, authentication_type="API_KEY",
       credential_reference="URLSCAN_API_KEY", licensing_class="FREE_NONCOMMERCIAL",
       priority=3, criticality="MEDIUM", documentation_url="https://urlscan.io/docs/api/"),
    mk("zoomeye", "ZoomEye", "Knownsec",
       "Internet-wide device/service search engine (China-based).",
       ["infrastructure", "attack_surface"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 3, authentication_type="API_KEY",
       credential_reference="ZOOMEYE_API_KEY", licensing_class="COMMERCIAL_LICENSED",
       priority=5, criticality="LOW", documentation_url="https://www.zoomeye.org/doc"),
    mk("fofa", "FOFA", "Baimaohui / FOFA",
       "Internet-wide asset search engine (China-based).",
       ["infrastructure", "attack_surface"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 3, authentication_type="API_KEY",
       credential_reference="FOFA_API_KEY", licensing_class="COMMERCIAL_LICENSED",
       priority=5, criticality="LOW", documentation_url="https://fofa.info/api"),
    mk("binaryedge", "BinaryEdge", "BinaryEdge",
       "Internet-wide scan data and risk scoring.",
       ["infrastructure", "attack_surface"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 3, authentication_type="API_KEY",
       credential_reference="BINARYEDGE_API_KEY", licensing_class="COMMERCIAL_LICENSED",
       priority=5, criticality="LOW", documentation_url="https://docs.binaryedge.io/"),
    mk("netlas", "Netlas.io", "Netlas",
       "Internet-wide asset/service search engine.",
       ["infrastructure", "attack_surface"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 3, authentication_type="API_KEY",
       credential_reference="NETLAS_API_KEY", licensing_class="COMMERCIAL_LICENSED",
       priority=5, criticality="LOW", documentation_url="https://netlas.io/api"),
    mk("leakix", "LeakIX", "LeakIX",
       "Exposed-service and leak/misconfiguration search engine.",
       ["infrastructure", "attack_surface"], "COMMUNITY", "COMMUNITY", "FREE_REGISTRATION",
       "REQUIRES_CREDENTIALS", 3, authentication_type="API_KEY",
       credential_reference="LEAKIX_API_KEY", licensing_class="FREE_NONCOMMERCIAL",
       priority=5, criticality="LOW", documentation_url="https://leakix.net/api-documentation"),
    mk("criminalip", "Criminal IP", "AI Spera",
       "Internet-wide asset search and IP risk scoring.",
       ["infrastructure", "attack_surface", "ioc"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 3, authentication_type="API_KEY",
       credential_reference="CRIMINALIP_API_KEY", licensing_class="COMMERCIAL_LICENSED",
       priority=5, criticality="LOW", documentation_url="https://www.criminalip.io/developer/api"),
    mk("onyphe", "ONYPHE", "ONYPHE SAS",
       "Cyber-defense search engine (internet-wide scan + passive DNS).",
       ["infrastructure", "attack_surface", "passive_dns"], "COMMERCIAL_VENDOR",
       "COMMERCIAL_VENDOR", "FREE_REGISTRATION", "REQUIRES_CREDENTIALS", 3,
       authentication_type="API_KEY", credential_reference="ONYPHE_API_KEY",
       licensing_class="COMMERCIAL_LICENSED", priority=5, criticality="LOW",
       documentation_url="https://www.onyphe.io/documentation/api"),
    mk("rapid7_sonar", "Rapid7 Project Sonar", "Rapid7",
       "Internet-wide scan research datasets (bulk export, not a live API).",
       ["internet_measurement", "attack_surface"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
       "PUBLIC_FREE", "PLANNED", 3, priority=5, criticality="LOW",
       documentation_url="https://www.rapid7.com/research/project-sonar/",
       notes="Bulk research-dataset distribution model, not a pollable API -- needs its "
             "own scoped bulk-ingestion design, not the incremental-poll pattern used "
             "elsewhere in this registry."),
    mk("team_cymru", "Team Cymru", "Team Cymru",
       "Internet reputation, IP-to-ASN, and bogon reference data; full threat feeds require "
       "a vetted community membership.",
       ["infrastructure", "ioc"], "COMMUNITY", "COMMUNITY", "COMMERCIAL_LICENSED",
       "REQUIRES_LICENSE", 3, licensing_class="INTERNAL_USE_ONLY", redistribution_allowed=False,
       priority=4, criticality="LOW", documentation_url="https://www.team-cymru.com/community-services"),
    mk("circl_cve_search", "CIRCL CVE Search", "CIRCL (Luxembourg)",
       "Legacy CVE aggregation/search API mirroring NVD content.",
       ["vulnerability"], "AGGREGATOR", "AGGREGATOR", "PUBLIC_FREE", "PLANNED", 3,
       geographic_scope="EU", licensing_class="PUBLIC_DOMAIN", priority=5, criticality="LOW",
       documentation_url="https://cve.circl.lu/api/",
       notes="Verified reachable (live curl 2026-08-08, HTTP 200) but its CVE coverage "
             "substantially overlaps the already-ACTIVE nvd_cve source with no independent "
             "authority -- building a live puller here would be a duplicate engine per "
             "Principle 3 (Single Source of Truth) with no signal gain. Deferred unless a "
             "CIRCL-specific enrichment (e.g. their vulnerability-lookup.circl.lu "
             "successor service) is identified as adding real value."),
    mk("ripe_ncc", "RIPE NCC / RIS", "RIPE NCC",
       "European IP allocation registry and BGP routing information service.",
       ["infrastructure"], "GOVERNMENT_AUTHORITATIVE", "GOVERNMENT_AUTHORITATIVE",
       "PUBLIC_FREE", "PLANNED", 3, geographic_scope="EU", licensing_class="PUBLIC_DOMAIN",
       priority=5, criticality="LOW", documentation_url="https://stat.ripe.net/docs/02.data-api/"),
    mk("bgp_intelligence", "BGP Routing Intelligence (BGPView/RouteViews)", "Multiple (RIR-adjacent)",
       "BGP route/ASN/prefix-hijack monitoring data.",
       ["infrastructure", "internet_measurement"], "AGGREGATOR", "AGGREGATOR", "PUBLIC_FREE",
       "PLANNED", 3, licensing_class="PUBLIC_DOMAIN", priority=5, criticality="LOW",
       documentation_url="https://bgpview.docs.apiary.io/"),
]


# =============================================================================
# WAVE 4 -- COMMERCIAL / DARK WEB / UNDERGROUND (licensed only -- mission
# Section 5 is explicit: "DO NOT scrape unauthorized sources... treat these
# as licensed intelligence integrations").
# =============================================================================

def _licensed_dark_web(source_id, canonical_name, provider, focus):
    return mk(
        source_id, canonical_name, provider,
        f"Licensed commercial dark-web/underground intelligence provider. {focus}",
        ["dark_web", "threat_actor"], "COMMERCIAL_VENDOR", "COMMERCIAL_VENDOR",
        "COMMERCIAL_LICENSED", "REQUIRES_LICENSE", 4,
        licensing_class="COMMERCIAL_LICENSED", redistribution_allowed=False,
        commercial_use_allowed=True, priority=4, criticality="LOW",
        notes="Requires a signed commercial contract. Access architecture (tenant-scoped "
              "credential, contractual redistribution terms) is designed for in Section 22/23 "
              "of the Source Registry documentation; no connector is built without an "
              "executed contract to test and validate against, per mission Section 40.",
    )

_WAVE4: List[Dict[str, Any]] = [
    _licensed_dark_web("recorded_future", "Recorded Future", "Recorded Future",
                       "Broad-spectrum CTI with dark-web collection, risk scoring, and "
                       "the Intelligence Graph."),
    _licensed_dark_web("flashpoint", "Flashpoint", "Flashpoint",
                       "Illicit-communities intelligence (forums, marketplaces, ransomware "
                       "leak sites)."),
    _licensed_dark_web("intel471", "Intel 471", "Intel 471",
                       "Cybercrime-focused underground forum and malware intelligence."),
    _licensed_dark_web("kela", "KELA Cyber Intelligence Center", "KELA",
                       "Darknet threat intelligence and exposure monitoring."),
    _licensed_dark_web("socradar", "SOCRadar", "SOCRadar",
                       "External attack-surface + dark-web + brand-protection intelligence."),
    _licensed_dark_web("cyble", "Cyble", "Cyble",
                       "Dark-web monitoring, vulnerability intelligence, and brand protection."),
    _licensed_dark_web("group_ib", "Group-IB Threat Intelligence", "Group-IB",
                       "Threat-actor attribution and underground marketplace monitoring."),
    _licensed_dark_web("searchlight_cyber", "Searchlight Cyber", "Searchlight Cyber",
                       "Dark-web investigation and monitoring platform."),
    _licensed_dark_web("darkowl", "DarkOwl Vision", "DarkOwl",
                       "Darknet document/data-leak search and monitoring."),
    _licensed_dark_web("flare", "Flare", "Flare Systems",
                       "Digital-footprint and dark-web exposure monitoring."),
    _licensed_dark_web("constella_intelligence", "Constella Intelligence", "Constella Intelligence",
                       "Identity-breach and digital-risk intelligence."),
]


# =============================================================================
# WAVE 5 -- SECTOR / GOVERNMENT (national CERTs, sector-specific)
# =============================================================================

def _gov_cert(source_id, canonical_name, provider, geo, notes=None):
    return mk(
        source_id, canonical_name, provider,
        f"National CERT/government cyber authority advisories for {geo}.",
        ["government_cert", "geopolitical_cyber"], "GOVERNMENT_AUTHORITATIVE",
        "GOVERNMENT_AUTHORITATIVE", "PUBLIC_FREE", "PLANNED", 5, geographic_scope=geo,
        licensing_class="PUBLIC_DOMAIN", priority=4, criticality="MEDIUM",
        notes=notes or "Wave 5 -- structured/machine-readable feed to be confirmed before "
                       "implementation begins.",
    )

_WAVE5: List[Dict[str, Any]] = [
    mk("fbi_ic3", "FBI Internet Crime Complaint Center (IC3)", "FBI (US)",
       "Public service announcements on cybercrime trends and threat campaigns.",
       ["government_cert", "ransomware"], "GOVERNMENT_AUTHORITATIVE",
       "GOVERNMENT_AUTHORITATIVE", "PUBLIC_FREE", "PLANNED", 5, geographic_scope="US",
       priority=4, criticality="MEDIUM", documentation_url="https://www.ic3.gov/",
       notes="Prior year-specific RSS URL (ic3.gov/Media/Y2024/PSA/rss) went dead and was "
             "removed from agent/config.py -- needs a durable non-year-specific endpoint."),
    _gov_cert("nsa_cybersecurity_advisories", "NSA Cybersecurity Advisories", "NSA (US)", "US"),
    _gov_cert("ncsc_uk", "UK National Cyber Security Centre", "NCSC UK", "UK",
              notes="Prior RSS attempts (agent/config.py history) logged 0 entries "
                    "consistently -- needs a confirmed working feed."),
    _gov_cert("acsc_australia", "Australian Cyber Security Centre", "ACSC", "AU"),
    _gov_cert("enisa", "ENISA (EU Agency for Cybersecurity)", "ENISA", "EU",
              notes="Prior RSS attempts logged 0 entries consistently -- needs a confirmed "
                    "working feed."),
    _gov_cert("jpcert_cc", "JPCERT/CC", "JPCERT/CC", "JP"),
    _gov_cert("singcert", "Singapore CERT (SingCERT)", "CSA Singapore", "SG"),
    _gov_cert("nciipc_india", "National Critical Information Infrastructure Protection Centre",
              "NCIIPC (India)", "IN"),
    _gov_cert("kisa_korea", "Korea Internet & Security Agency (KISA)", "KISA", "KR"),
    mk("no_more_ransom", "No More Ransom", "Europol + industry partners",
       "Free ransomware decryption tools and victim-guidance resource.",
       ["ransomware"], "GOVERNMENT_AUTHORITATIVE", "GOVERNMENT_AUTHORITATIVE", "PUBLIC_FREE",
       "PLANNED", 5, geographic_scope="EU", priority=4, criticality="LOW",
       documentation_url="https://www.nomoreransom.org/"),
    mk("ransomwatch", "Ransomwatch", "Ransomwatch (independent research)",
       "Community-maintained ransomware leak-site tracker (GitHub-based).",
       ["ransomware", "threat_actor"], "COMMUNITY", "COMMUNITY", "PUBLIC_FREE", "PLANNED", 5,
       licensing_class="OPEN_ATTRIBUTION", attribution_required=True, priority=4,
       criticality="LOW", documentation_url="https://github.com/joshhighet/ransomwatch",
       notes="Overlaps ransomware_live (already ACTIVE) -- would be evaluated as a "
             "corroborating second source for cross-source confidence per Section 14, not "
             "a replacement."),
]


ALL_SOURCES: List[Dict[str, Any]] = (
    _WAVE1 + _WAVE2_PSIRT + _WAVE2_EXPLOIT_MALWARE + _WAVE2_ACTOR_RESEARCH
    + _WAVE3 + _WAVE4 + _WAVE5
)


def validate(entries: List[Dict[str, Any]]) -> None:
    seen = set()
    for e in entries:
        sid = e["source_id"]
        if sid in seen:
            raise ValueError(f"Duplicate source_id: {sid}")
        seen.add(sid)
        for required in ("canonical_name", "provider", "description", "intelligence_domains"):
            if not e.get(required):
                raise ValueError(f"{sid}: missing required field {required}")
        if e["implementation_status"] not in IMPLEMENTATION_STATUSES:
            raise ValueError(f"{sid}: invalid implementation_status {e['implementation_status']!r}")
        if e["implementation_status"] not in ("ACTIVE", "IMPLEMENTED") and e["health_status"] == "HEALTHY":
            raise ValueError(f"{sid}: non-live source cannot claim HEALTHY (no-fake-integrations violation)")
        if e["implementation_status"] not in ("ACTIVE", "IMPLEMENTED") and e["reliability_score"] > 0:
            raise ValueError(f"{sid}: non-live source cannot have a nonzero reliability_score")


def main() -> int:
    validate(ALL_SOURCES)

    status_breakdown: Dict[str, int] = {}
    wave_breakdown: Dict[str, int] = {}
    domain_breakdown: Dict[str, int] = {}
    for e in ALL_SOURCES:
        status_breakdown[e["implementation_status"]] = status_breakdown.get(e["implementation_status"], 0) + 1
        wave_breakdown[str(e["wave"])] = wave_breakdown.get(str(e["wave"]), 0) + 1
        for d in e["intelligence_domains"]:
            domain_breakdown[d] = domain_breakdown.get(d, 0) + 1

    registry = {
        "registry_version": REGISTRY_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "scripts/build_source_registry.py",
        "part_of": "CYBERDUDEBIVASH SENTINEL APEX -- Global Intelligence Source Fabric (P40.0)",
        "total_sources": len(ALL_SOURCES),
        "status_breakdown": status_breakdown,
        "wave_breakdown": wave_breakdown,
        "domain_breakdown": domain_breakdown,
        "field_schema_doc": "docs/SOURCE_REGISTRY.md",
        "sources": ALL_SOURCES,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[source-registry] wrote {len(ALL_SOURCES)} sources -> {OUT_PATH}")
    print(f"[source-registry] status breakdown: {status_breakdown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
