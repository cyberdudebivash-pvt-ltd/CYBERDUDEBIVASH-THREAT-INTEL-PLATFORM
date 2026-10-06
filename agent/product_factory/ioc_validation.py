#!/usr/bin/env python3
"""
ioc_validation.py - CYBERDUDEBIVASH(R) SENTINEL APEX
COMMERCIAL IOC VALIDATION AND FALSE-POSITIVE SUPPRESSION ENGINE
Founder & CEO - CyberDudeBivash Pvt. Ltd.

WHY THIS MODULE EXISTS  --  VERIFIED CUSTOMER-HARM DEFECT
---------------------------------------------------------
The IOC blocklist shipped to paying customers is documented for import as an
external block list into Palo Alto PAN-OS, FortiGate, Pi-hole and pfSense --
i.e. it is an ENFORCEMENT artefact. An audit of the staged blocklist built from
api/feed.baseline.json found it dominated by indicators that are not malicious:

  179  cvefeed.io                  <- CVE reference database (harvested from
                                      the reference URL of every advisory)
   10  www.zerodayinitiative.com   <- vulnerability research vendor
    4  metacpan.org                <- Perl module archive
    3  gitweb.gentoo.org           <- distribution source browser
    6  miniorange.com              <- SSO vendor whose product had a CVE
   11  plancontroller.getimmediateplans   <- Java symbols from advisory prose,
    9  configprovider.getcontextprops        parsed as if they were domains
    8  messagescontroller.java
    7  llama.cpp / ggml-rpc.cpp
    3  env.production / env.backup

A customer who imported that list into a firewall EDL would have blocked their
own vulnerability-research workflow and a set of legitimate vendors, caused by
a product they paid for. For an enforcement artefact a false positive is a
customer outage, which is strictly more damaging than a missed detection.

WHAT THIS ENGINE DOES
---------------------
  1. Structural validation  -- rejects strings that are not indicators at all
     (source-code symbols, file paths, version strings) via strict per-type
     grammar plus registrable-TLD validation.
  2. Benign-infrastructure suppression -- rejects security-research, CVE
     database, vendor, code-hosting, CDN and major-platform hosts that are
     harvested as advisory *references*, not as attacker infrastructure.
  3. Non-routable suppression -- rejects RFC1918 / loopback / link-local /
     documentation / reserved address space.
  4. Enforcement tiering -- splits survivors into ENFORCEMENT (safe to block
     inline) and MONITORING (hunt / alert only), so a customer never points a
     blocking policy at an indicator that was never validated for blocking.

Every rejection is returned with a machine-readable reason so the decision is
auditable rather than a silent drop.
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlsplit

ENGINE_VERSION = "1.0.0"

# ── Registrable TLDs ─────────────────────────────────────────────────────────
# Any two-letter alphabetic suffix is treated as a ccTLD (a safe superset of the
# ~250 assigned codes). Longer suffixes must appear in the gTLD set below. This
# single check is what rejects `messagescontroller.java`, `llama.cpp`,
# `env.production` and `selectquerybuilder.distincton` -- none of which are
# registrable namespaces -- without needing a source-code heuristic.
_GTLDS: Set[str] = {
    # Legacy / infrastructure
    "com", "net", "org", "edu", "gov", "mil", "int", "arpa", "info", "biz",
    "name", "pro", "aero", "coop", "museum", "jobs", "mobi", "tel", "travel",
    "asia", "cat", "post", "xxx", "adult", "porn",
    # Widely used generics
    "app", "dev", "page", "cloud", "site", "online", "store", "shop", "tech",
    "space", "website", "host", "press", "blog", "wiki", "news", "media",
    "email", "network", "systems", "solutions", "services", "digital",
    "agency", "company", "group", "team", "world", "life", "live", "today",
    "center", "works", "tools", "software", "computer", "technology",
    "security", "expert", "consulting", "capital", "finance", "financial",
    "bank", "insurance", "legal", "law", "health", "care", "clinic", "doctor",
    "education", "academy", "school", "college", "university", "institute",
    "training", "courses", "study", "science", "engineering", "design",
    "studio", "gallery", "photo", "photos", "photography", "video", "audio",
    "music", "film", "movie", "games", "game", "play", "sport", "sports",
    "fitness", "travel", "tours", "vacations", "hotel", "hotels", "restaurant",
    "cafe", "bar", "pizza", "food", "kitchen", "recipes", "coffee", "beer",
    "wine", "shopping", "market", "sale", "deals", "discount", "cheap",
    "auction", "bid", "money", "cash", "credit", "loans", "investments",
    "exchange", "trade", "trading", "business", "enterprises", "industries",
    "management", "marketing", "promo", "guru", "ninja", "rocks", "cool",
    "best", "plus", "one", "global", "international", "network",
    # Abuse-heavy namespaces (must NOT be dropped -- these carry real IOCs)
    "xyz", "top", "club", "icu", "cyou", "click", "link", "buzz", "quest",
    "rest", "monster", "sbs", "cfd", "bond", "autos", "beauty", "hair",
    "skin", "makeup", "mom", "lol", "pics", "fun", "zip", "mov", "cam",
    "webcam", "download", "stream", "party", "review", "science", "date",
    "faith", "accountant", "racing", "loan", "men", "win", "trade", "gdn",
    "work", "support", "help", "guru", "info", "vip", "wang", "ltd", "cn",
    "kim", "art", "shopping", "fit", "run", "gold", "pink", "red", "blue",
    "black", "green", "wtf", "fyi", "biz", "pw", "su", "surf", "boats",
    "yachts", "motorcycles", "homes", "villas", "casa", "house", "estate",
    "properties", "rentals", "realty", "land", "farm", "garden", "flowers",
    "gift", "gifts", "toys", "baby", "kids", "family", "singles", "dating",
    "wedding", "church", "faith", "bible", "islam", "charity", "ngo", "ong",
}


@dataclass
class ValidationResult:
    """Outcome of validating a single candidate indicator."""

    value: str
    ioc_type: str
    accepted: bool
    tier: str = "rejected"          # "enforcement" | "monitoring" | "rejected"
    reason: str = ""
    confidence: Optional[float] = None
    normalized: str = ""


@dataclass
class ValidationReport:
    """Aggregate outcome for a batch, suitable for a certification artefact."""

    engine_version: str = ENGINE_VERSION
    total_candidates: int = 0
    accepted: int = 0
    rejected: int = 0
    enforcement: int = 0
    monitoring: int = 0
    rejection_reasons: Dict[str, int] = field(default_factory=dict)
    accepted_by_type: Dict[str, int] = field(default_factory=dict)
    suppressed_hosts: Dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> Dict:
        return {
            "engine": "CDB IOC Validation Engine",
            "engine_version": self.engine_version,
            "total_candidates": self.total_candidates,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "enforcement_tier": self.enforcement,
            "monitoring_tier": self.monitoring,
            "acceptance_rate_pct": (
                round(100.0 * self.accepted / self.total_candidates, 2)
                if self.total_candidates else 0.0
            ),
            "rejection_reasons": dict(sorted(
                self.rejection_reasons.items(), key=lambda kv: -kv[1])),
            "accepted_by_type": dict(sorted(self.accepted_by_type.items())),
            "top_suppressed_hosts": dict(sorted(
                self.suppressed_hosts.items(), key=lambda kv: -kv[1])[:40]),
        }


# ── Benign infrastructure ────────────────────────────────────────────────────
# Registrable domains that appear in advisory *references* rather than as
# attacker infrastructure. Matching is suffix-based, so a subdomain of any entry
# is suppressed too. Blocking any of these would break a customer's own
# security-research and patching workflow.
BENIGN_SUFFIXES: Tuple[str, ...] = (
    # CVE / vulnerability databases and trackers
    "cvefeed.io", "nvd.nist.gov", "cve.org", "cve.mitre.org", "mitre.org",
    "first.org", "cisa.gov", "us-cert.gov", "kb.cert.org", "cert.org",
    "exploit-db.com", "vulndb.cyberriskanalytics.com", "vuldb.com",
    "packetstormsecurity.com", "seclists.org", "openwall.com", "securityfocus.com",
    "zerodayinitiative.com", "talosintelligence.com", "zerodium.com",
    "attackerkb.com", "rapid7.com", "tenable.com", "qualys.com", "nist.gov",
    "securityaffairs.com", "bleepingcomputer.com", "thehackernews.com",
    "krebsonsecurity.com", "darkreading.com", "securityweek.com", "helpnetsecurity.com",
    "infosecurity-magazine.com", "theregister.com", "scmagazine.com",
    # Code hosting / package registries / distro infrastructure
    "github.com", "gist.github.com",
    "gitlab.com", "bitbucket.org", "sourceforge.net", "savannah.gnu.org",
    "gnu.org", "kernel.org", "gentoo.org", "debian.org", "ubuntu.com",
    "redhat.com", "access.redhat.com", "suse.com", "opensuse.org",
    "archlinux.org", "fedoraproject.org", "almalinux.org", "rockylinux.org",
    "apache.org", "eclipse.org", "mozilla.org", "python.org", "pypi.org",
    "npmjs.com", "nuget.org", "rubygems.org", "metacpan.org", "cpan.org",
    "maven.org", "mvnrepository.com", "packagist.org", "crates.io", "pkg.go.dev",
    "golang.org", "go.dev", "docker.com", "hub.docker.com", "quay.io",
    "readthedocs.io", "readthedocs.org", "stackoverflow.com", "stackexchange.com",
    # Major platforms / CDNs / cloud (never appropriate for a blanket block)
    "google.com", "googleapis.com", "gstatic.com", "youtube.com", "goo.gl",
    "microsoft.com", "msrc.microsoft.com", "windows.com", "office.com",
    "azure.com", "live.com", "outlook.com",
    "apple.com", "icloud.com", "amazon.com", "aws.amazon.com",
    "cloudflare.com", "cloudflare.net", "akamai.com", "akamaized.net",
    "fastly.net", "jsdelivr.net", "unpkg.com", "cdnjs.com", "bootstrapcdn.com",
    "facebook.com", "meta.com", "twitter.com", "x.com", "linkedin.com",
    "reddit.com", "wikipedia.org", "wikimedia.org", "archive.org",
    "adobe.com", "oracle.com", "ibm.com", "cisco.com", "vmware.com",
    "broadcom.com", "hp.com", "hpe.com", "dell.com", "intel.com", "nvidia.com",
    "atlassian.com", "jetbrains.com", "wordpress.org", "wordpress.com",
    "wpscan.com", "patchstack.com", "miniorange.com", "roblox.com",
    "slack.com", "zoom.us", "salesforce.com", "sap.com", "servicenow.com",
    "splunk.com", "elastic.co", "crowdstrike.com", "paloaltonetworks.com",
    "fortinet.com", "sonicwall.com", "sophos.com", "trendmicro.com",
    "kaspersky.com", "eset.com", "mcafee.com", "symantec.com", "avast.com",
    "virustotal.com", "any.run", "hybrid-analysis.com", "joesandbox.com",
    "abuse.ch", "urlhaus.abuse.ch", "malwarebazaar.abuse.ch", "alienvault.com",
    "otx.alienvault.com", "shodan.io", "censys.io", "greynoise.io",
    "doi.org", "arxiv.org", "ieee.org", "acm.org",
    # Own platform -- never ship our own infrastructure as an indicator
    "cyberdudebivash.com", "cyberdudebivash.in", "gumroad.com",
)

# Hostnames that are structurally valid but carry no enforcement value.
BENIGN_EXACT: Set[str] = {
    "localhost", "example.com", "example.org", "example.net",
    "test.com", "invalid", "local", "victim.site", "attacker.com",
    "evil.com", "malicious.com", "domain.com", "yourdomain.com",
    "your-domain.com", "site.com", "website.com", "target.com",
}

# ── User-content hosting namespaces ──────────────────────────────────────────
# Suffixes where every subdomain is registered by an arbitrary third party.
# Attackers host phishing and payload infrastructure on these constantly, so a
# subdomain here is a legitimate indicator and MUST NOT be suppressed. Only the
# apex itself is suppressed -- blocking `pages.dev` or `github.io` outright at a
# firewall would take out a large amount of legitimate traffic, but blocking
# `docs-trezor-app.pages.dev` is exactly the intended enforcement action.
USER_CONTENT_SUFFIXES: Tuple[str, ...] = (
    "github.io", "githubusercontent.com", "gitlab.io", "pages.dev",
    "workers.dev", "r2.dev", "web.app", "firebaseapp.com", "netlify.app",
    "vercel.app", "herokuapp.com", "onrender.com", "glitch.me", "repl.co",
    "replit.dev", "blogspot.com", "wordpress.com", "weebly.com", "wixsite.com",
    "squarespace.com", "webflow.io", "azurewebsites.net", "cloudapp.azure.com",
    "cloudfront.net", "amazonaws.com", "windows.net", "sharepoint.com",
    "googleusercontent.com", "appspot.com", "translate.goog", "000webhostapp.com",
    "sites.google.com", "docs.google.com", "drive.google.com", "forms.gle",
    "notion.site", "surge.sh", "neocities.org", "ngrok.io", "ngrok-free.app",
    "trycloudflare.com", "duckdns.org", "no-ip.org", "dynu.net", "hopto.org",
)


_RE_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_RE_MD5 = re.compile(r"^[a-f0-9]{32}$", re.IGNORECASE)
_RE_SHA1 = re.compile(r"^[a-f0-9]{40}$", re.IGNORECASE)
_RE_SHA256 = re.compile(r"^[a-f0-9]{64}$", re.IGNORECASE)
_RE_SHA512 = re.compile(r"^[a-f0-9]{128}$", re.IGNORECASE)
_RE_CVE = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)
_RE_DOMAIN = re.compile(
    r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(?:\.(?!-)[a-z0-9-]{1,63}(?<!-))+$",
    re.IGNORECASE,
)
_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)

# Indicator types that are safe to enforce inline once validated. Hashes and
# network indicators are blockable; behavioural and vulnerability references are
# analytic context and must never drive an inline block.
ENFORCEABLE_TYPES: Set[str] = {"ipv4", "ipv6", "domain", "url", "md5", "sha1", "sha256", "sha512"}
MONITORING_ONLY_TYPES: Set[str] = {"behavioral", "email", "registry", "filepath", "mutex", "useragent"}

# An indicator below this confidence is delivered for hunting but is never
# placed in the enforcement blocklist.
ENFORCEMENT_CONFIDENCE_FLOOR = 60.0


def registrable_tld(host: str) -> Optional[str]:
    """Return the lower-cased TLD if the host ends in a registrable namespace."""
    if "." not in host:
        return None
    tld = host.rsplit(".", 1)[-1].lower()
    if not tld.isalpha():
        return None
    if len(tld) == 2:          # ccTLD superset
        return tld
    return tld if tld in _GTLDS else None


def is_user_content_namespace(host: str) -> bool:
    """True when `host` is the apex of a namespace whose subdomains are
    third-party controlled (so subdomains stay eligible as indicators)."""
    host = host.lower().strip().rstrip(".")
    return any(host == suffix for suffix in USER_CONTENT_SUFFIXES)


def is_benign_host(host: str) -> bool:
    """True when the host belongs to reference/vendor/platform infrastructure."""
    host = host.lower().strip().rstrip(".")
    if host in BENIGN_EXACT:
        return True
    # A subdomain under a user-content namespace is attacker-controlled far more
    # often than not, so only the apex is treated as benign.
    if is_user_content_namespace(host):
        return True
    if any(host.endswith("." + suffix) for suffix in USER_CONTENT_SUFFIXES):
        return False
    for suffix in BENIGN_SUFFIXES:
        if host == suffix or host.endswith("." + suffix):
            return True
    return False


def _non_routable_ip(value: str) -> Optional[str]:
    """Return a rejection reason when the address must never be blocked."""
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return "malformed_ip"
    # Order matters: ipaddress marks loopback, link-local and the documentation
    # ranges as private too, so the specific reason must be tested first or every
    # rejection reads "non_routable_private" and the audit trail loses precision.
    if addr.is_loopback:
        return "non_routable_loopback"
    if addr.is_link_local:
        return "non_routable_link_local"
    if addr.is_multicast:
        return "non_routable_multicast"
    # RFC 5737 / RFC 3849 documentation ranges
    for net in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "2001:db8::/32"):
        try:
            if addr in ipaddress.ip_network(net):
                return "documentation_range"
        except ValueError:
            continue
    if addr.is_private:
        return "non_routable_private"
    if addr.is_reserved or addr.is_unspecified:
        return "non_routable_reserved"
    return None


def infer_type(value: str) -> str:
    """Derive an indicator type from the value when the feed says 'indicator'."""
    v = value.strip()
    if _RE_CVE.match(v):
        return "cve"
    if _RE_IPV4.match(v):
        return "ipv4"
    if ":" in v and not v.lower().startswith(("http://", "https://")):
        try:
            ipaddress.IPv6Address(v)
            return "ipv6"
        except ValueError:
            pass
    if _RE_SHA512.match(v):
        return "sha512"
    if _RE_SHA256.match(v):
        return "sha256"
    if _RE_SHA1.match(v):
        return "sha1"
    if _RE_MD5.match(v):
        return "md5"
    if v.lower().startswith(("http://", "https://")):
        return "url"
    if _RE_EMAIL.match(v):
        return "email"
    if _RE_DOMAIN.match(v):
        return "domain"
    return "unknown"


def validate(value: str, ioc_type: str = "indicator",
             confidence: Optional[float] = None) -> ValidationResult:
    """Validate one candidate indicator and assign its delivery tier."""
    raw = (value or "").strip()
    if not raw:
        return ValidationResult(raw, ioc_type, False, reason="empty_value")
    if len(raw) > 2048:
        return ValidationResult(raw, ioc_type, False, reason="oversized_value")

    t = (ioc_type or "indicator").strip().lower()
    if t in ("indicator", "", "unknown"):
        t = infer_type(raw)

    norm = raw

    # -- Vulnerability identifiers are analytic context, never blockable -------
    if t == "cve" or _RE_CVE.match(raw):
        return ValidationResult(raw, "cve", False, reason="cve_not_an_indicator")

    # -- Hashes ---------------------------------------------------------------
    if t in ("md5", "sha1", "sha256", "sha512"):
        pattern = {"md5": _RE_MD5, "sha1": _RE_SHA1,
                   "sha256": _RE_SHA256, "sha512": _RE_SHA512}[t]
        if not pattern.match(raw):
            return ValidationResult(raw, t, False, reason="malformed_hash")
        norm = raw.lower()
        # An all-zero or all-same-nibble digest is a placeholder, not a sample.
        if len(set(norm)) <= 1:
            return ValidationResult(raw, t, False, reason="placeholder_hash")

    # -- IP addresses ---------------------------------------------------------
    elif t in ("ipv4", "ipv6"):
        why = _non_routable_ip(raw)
        if why:
            return ValidationResult(raw, t, False, reason=why)

    # -- Domains --------------------------------------------------------------
    elif t == "domain":
        host = raw.lower().rstrip(".")
        if not _RE_DOMAIN.match(host):
            return ValidationResult(raw, t, False, reason="malformed_domain")
        if registrable_tld(host) is None:
            # This is the check that removes source-code symbols and file names
            # ('llama.cpp', 'messagescontroller.java', 'env.production').
            return ValidationResult(raw, t, False, reason="non_registrable_tld")
        if is_benign_host(host):
            return ValidationResult(raw, t, False, reason="benign_infrastructure")
        norm = host

    # -- URLs -----------------------------------------------------------------
    elif t == "url":
        try:
            parts = urlsplit(raw)
        except ValueError:
            return ValidationResult(raw, t, False, reason="malformed_url")
        host = (parts.hostname or "").lower().rstrip(".")
        if not host:
            return ValidationResult(raw, t, False, reason="malformed_url")
        if _RE_IPV4.match(host):
            why = _non_routable_ip(host)
            if why:
                return ValidationResult(raw, t, False, reason=why)
        else:
            if not _RE_DOMAIN.match(host) or registrable_tld(host) is None:
                return ValidationResult(raw, t, False, reason="non_registrable_tld")
            if is_benign_host(host):
                return ValidationResult(raw, t, False, reason="benign_infrastructure")
        norm = raw

    # -- Email ----------------------------------------------------------------
    elif t == "email":
        if not _RE_EMAIL.match(raw):
            return ValidationResult(raw, t, False, reason="malformed_email")
        if is_benign_host(raw.rsplit("@", 1)[-1].lower()):
            return ValidationResult(raw, t, False, reason="benign_infrastructure")
        norm = raw.lower()

    elif t in MONITORING_ONLY_TYPES:
        pass  # structurally free-form; delivered as hunting context only

    else:
        return ValidationResult(raw, t, False, reason="unclassifiable_value")

    # -- Tiering --------------------------------------------------------------
    conf = confidence if isinstance(confidence, (int, float)) else None
    if t not in ENFORCEABLE_TYPES:
        tier = "monitoring"
    elif conf is not None and conf < ENFORCEMENT_CONFIDENCE_FLOOR:
        tier = "monitoring"
    else:
        tier = "enforcement"

    return ValidationResult(
        value=raw, ioc_type=t, accepted=True, tier=tier,
        reason="validated", confidence=conf, normalized=norm,
    )


def validate_batch(candidates: Iterable[Dict]) -> Tuple[List[ValidationResult], ValidationReport]:
    """Validate and deduplicate a batch of candidate indicators.

    ``candidates`` items are dicts with at least ``value``; ``type`` and
    ``confidence`` are used when present. Deduplication is on the normalized
    value, keeping the highest-confidence occurrence.
    """
    report = ValidationReport()
    best: Dict[str, ValidationResult] = {}

    for cand in candidates:
        if isinstance(cand, str):
            cand = {"value": cand}
        if not isinstance(cand, dict):
            continue
        report.total_candidates += 1
        res = validate(
            str(cand.get("value") or ""),
            str(cand.get("type") or "indicator"),
            cand.get("confidence"),
        )
        if not res.accepted:
            report.rejected += 1
            report.rejection_reasons[res.reason] = report.rejection_reasons.get(res.reason, 0) + 1
            if res.reason == "benign_infrastructure":
                host = res.value.lower()
                if host.startswith(("http://", "https://")):
                    host = (urlsplit(res.value).hostname or host).lower()
                report.suppressed_hosts[host] = report.suppressed_hosts.get(host, 0) + 1
            continue

        key = f"{res.ioc_type}:{res.normalized}"
        prior = best.get(key)
        if prior is None or (res.confidence or 0) > (prior.confidence or 0):
            best[key] = res

    accepted = sorted(best.values(), key=lambda r: (r.ioc_type, r.normalized))
    for res in accepted:
        report.accepted += 1
        report.accepted_by_type[res.ioc_type] = report.accepted_by_type.get(res.ioc_type, 0) + 1
        if res.tier == "enforcement":
            report.enforcement += 1
        else:
            report.monitoring += 1

    return accepted, report


__all__ = [
    "BENIGN_EXACT",
    "BENIGN_SUFFIXES",
    "USER_CONTENT_SUFFIXES",
    "ENFORCEABLE_TYPES",
    "ENFORCEMENT_CONFIDENCE_FLOOR",
    "ENGINE_VERSION",
    "ValidationReport",
    "ValidationResult",
    "infer_type",
    "is_benign_host",
    "is_user_content_namespace",
    "registrable_tld",
    "validate",
    "validate_batch",
]
