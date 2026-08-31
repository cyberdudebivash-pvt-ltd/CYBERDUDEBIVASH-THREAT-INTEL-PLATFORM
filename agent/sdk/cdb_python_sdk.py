#!/usr/bin/env python3
"""
cdb_python_sdk.py - CYBERDUDEBIVASH(R) SENTINEL APEX v24.0
Official Python SDK for the CDB Threat Intelligence Platform API.

Non-Breaking Addition: Standalone SDK module.
Does NOT modify any existing platform modules.

Install:
    pip install requests

Usage:
    from agent.sdk.cdb_python_sdk import CDBClient

    # Free tier
    client = CDBClient()
    threats = client.get_threats()

    # PRO tier
    client = CDBClient(api_key="cdb-pro-your-key")
    iocs = client.get_iocs(limit=100)

    # Enterprise tier
    client = CDBClient(api_key="cdb-ent-your-key")
    actors = client.get_actors()
    stix = client.get_stix_bundle("bundle--abc123")

Author: CyberDudeBivash Pvt. Ltd.
Platform: https://intel.cyberdudebivash.com

Every route this client calls is verified against the deployed Cloudflare
Worker (workers/intel-gateway/src/index.js) — the only backend this API is
actually served from (see wrangler.toml's `routes` block, which registers
only intel.cyberdudebivash.com; api.cyberdudebivash.com has no Worker
route, DNS entry, or any other backing infrastructure in this repository).
Methods with no real deployed equivalent (per-item exploit forecasting,
batch forecasting, supply-chain intel, risk trend) raise
agent.sdk.exceptions.FeatureNotDeployedError instead of calling a route
that would 404 for every real customer.
"""

import json
import time
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from agent.sdk.exceptions import FeatureNotDeployedError

try:
    import requests
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

logger = logging.getLogger("CDB-SDK")

# ----------------------------------------------
# SDK Constants
# ----------------------------------------------
SDK_VERSION       = "1.0.0"
DEFAULT_BASE_URL  = "https://intel.cyberdudebivash.com"
DEFAULT_TIMEOUT   = 30
DEFAULT_MAX_RETRY = 3
DEFAULT_RETRY_BACKOFF = 2  # seconds


class CDBAPIError(Exception):
    """Raised when the CDB API returns an error response."""
    def __init__(self, status_code: int, message: str, detail: Any = None):
        self.status_code = status_code
        self.message     = message
        self.detail      = detail
        super().__init__(f"CDB API Error [{status_code}]: {message}")


class CDBAuthError(CDBAPIError):
    """Raised on authentication / tier access errors."""
    pass


class CDBRateLimitError(CDBAPIError):
    """Raised when rate limit is exceeded."""
    pass


class CDBClient:
    """
    Official Python client for the CYBERDUDEBIVASH SENTINEL APEX API.

    Tier Access:
        FREE       - No API key required. 60 req/min. Latest 10 threats.
        PRO        - API key (cdb-pro-xxx). 300 req/min. Full IOC + detection feed.
        ENTERPRISE - API key (cdb-ent-xxx). 1000 req/min. Full intelligence + STIX + actors.

    Get API Key: https://tools.cyberdudebivash.com/
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRY,
        auto_retry: bool = True,
        verbose: bool = False,
    ):
        if not _REQUESTS_AVAILABLE:
            raise ImportError(
                "requests library required. Run: pip install requests"
            )

        self.api_key     = api_key
        self.base_url    = base_url.rstrip("/")
        self.timeout     = timeout
        self.max_retries = max_retries
        self.auto_retry  = auto_retry
        self._jwt_token  = None
        self._jwt_expiry = 0

        if verbose:
            logging.basicConfig(level=logging.DEBUG)

        logger.debug(f"CDB SDK v{SDK_VERSION} initialized. Base URL: {self.base_url}")

    # ------------------------------------------
    # Internal HTTP layer
    # ------------------------------------------

    def _headers(self) -> Dict[str, str]:
        """Build request headers with auth."""
        headers = {
            "User-Agent":       f"CDB-Python-SDK/{SDK_VERSION}",
            "Accept":           "application/json",
            "X-SDK-Version":    SDK_VERSION,
        }
        if self.api_key:
            # Bug fix: the deployed worker reads "X-API-Key" (or an
            # Authorization: Bearer JWT, or a ?api_key= query param) --
            # it has never recognized "X-CDB-API-Key". Every unauthenticated
            # request previously fell through to anonymous/FREE-tier
            # handling regardless of the caller's real tier.
            headers["X-API-Key"] = self.api_key
        if self._jwt_token and time.time() < self._jwt_expiry:
            headers["Authorization"] = f"Bearer {self._jwt_token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        json_body: Optional[Dict] = None,
    ) -> Any:
        """Execute HTTP request with retry logic."""
        url = f"{self.base_url}{path}"
        last_error = None

        for attempt in range(self.max_retries):
            try:
                response = requests.request(
                    method,
                    url,
                    headers=self._headers(),
                    params=params,
                    json=json_body,
                    timeout=self.timeout,
                )

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    if self.auto_retry and attempt < self.max_retries - 1:
                        logger.warning(f"Rate limited. Retrying in {retry_after}s...")
                        time.sleep(retry_after)
                        continue
                    raise CDBRateLimitError(
                        429, "Rate limit exceeded", response.json()
                    )

                if response.status_code == 401:
                    raise CDBAuthError(401, "Unauthorized. Check your API key.", response.json())

                if response.status_code == 403:
                    detail = response.json()
                    raise CDBAuthError(
                        403,
                        f"Insufficient tier. {detail.get('message', '')} "
                        f"Upgrade: {detail.get('upgrade_url', 'https://tools.cyberdudebivash.com/')}",
                        detail,
                    )

                if response.status_code == 404:
                    raise CDBAPIError(404, "Resource not found.", response.json())

                if response.status_code >= 500:
                    if self.auto_retry and attempt < self.max_retries - 1:
                        wait = DEFAULT_RETRY_BACKOFF ** attempt
                        logger.warning(f"Server error {response.status_code}. Retrying in {wait}s...")
                        time.sleep(wait)
                        continue
                    raise CDBAPIError(response.status_code, "Server error", response.text)

                response.raise_for_status()
                return response.json()

            except (requests.ConnectionError, requests.Timeout) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait = DEFAULT_RETRY_BACKOFF ** attempt
                    logger.warning(f"Connection error: {e}. Retrying in {wait}s...")
                    time.sleep(wait)

        raise CDBAPIError(0, f"Max retries exceeded: {last_error}")

    # ------------------------------------------
    # Authentication
    # ------------------------------------------

    def authenticate(self) -> Dict:
        """
        Exchange API key for a JWT token via the real login route.
        Automatically used for subsequent requests.

        Returns:
            dict: {token, token_type, tier, sub, expires_in, expires_at, issued_at}
        """
        result = self._request("POST", "/api/auth/login", json_body={"api_key": self.api_key})
        self._jwt_token  = result.get("token")
        self._jwt_expiry = time.time() + result.get("expires_in", 86400) - 60
        logger.info(f"Authenticated. Tier: {result.get('tier')}. Token valid {result.get('expires_in')}s.")
        return result

    # ------------------------------------------
    # Free Tier Endpoints
    # ------------------------------------------

    def health(self) -> Dict:
        """Platform health check (FREE). Returns operational status."""
        return self._request("GET", "/api/health")

    def stats(self) -> Dict:
        """Platform statistics (FREE). Returns advisory counts, KEV stats, avg EPSS."""
        return self._request("GET", "/api/v1/stats")

    def get_threats(self) -> Dict:
        """
        Threat advisory feed manifest - FREE tier.

        The deployed API serves one feed route for every tier; the worker
        masks IOCs/detection rules/actor attribution for FREE-tier keys
        server-side (there is no separate "latest 10" route).
        """
        return self._request("GET", "/api/feed")

    def get_feed(self) -> Dict:
        """Public threat feed manifest (FREE). Same route as get_threats()."""
        return self._request("GET", "/api/feed")

    def get_threat(self, threat_id: str) -> Dict:
        """
        Single threat summary by ID (FREE).

        There is no single-resource route in the deployed API; this looks
        the ID up client-side against the feed manifest get_threats() uses.

        Args:
            threat_id: stix_id (or legacy id) from the manifest.

        Raises:
            CDBAPIError: 404 if no matching item is found.
        """
        data = self.get_feed()
        for item in data.get("items", []):
            if item.get("stix_id") == threat_id or item.get("id") == threat_id:
                return item
        raise CDBAPIError(404, f"No threat found with id={threat_id!r}")

    # ------------------------------------------
    # PRO Tier Endpoints
    # ------------------------------------------

    def get_full_threats(self, limit: int = 50) -> Dict:
        """
        Full threat list with extended metadata (PRO tier).
        Includes: severity, TLP, MITRE, actor, CVSS/EPSS.

        There is no separate /pro/threats route -- the deployed API serves
        richer fields on the same feed route once the API key resolves to
        PRO/ENTERPRISE server-side. This applies `limit` client-side.

        Args:
            limit: Max threats to return.

        Requires: PRO API key
        """
        data = self.get_feed()
        items = (data.get("items") or [])[:limit]
        return {**data, "items": items}

    def get_iocs(self, limit: int = 50) -> Dict:
        """
        IOC export feed - IPs, domains, hashes, URLs, CVEs (PRO tier).
        Ready for SIEM ingestion.

        There is no dedicated bulk-IOC-export route; this aggregates the
        `iocs_by_type` field already present on each feed item into a flat
        list, client-side.

        Args:
            limit: Max IOCs to return.

        Requires: PRO API key
        """
        data = self.get_feed()
        iocs: List[Dict[str, Any]] = []
        for item in data.get("items", []):
            by_type = item.get("iocs_by_type") or {}
            for ioc_type, values in by_type.items():
                for value in values:
                    iocs.append({
                        "type": ioc_type, "value": value,
                        "source_stix_id": item.get("stix_id") or item.get("id"),
                        "severity": item.get("severity"),
                    })
                    if len(iocs) >= limit:
                        return {"data": iocs, "count": len(iocs)}
        return {"data": iocs, "count": len(iocs)}

    def get_detections(self) -> Dict:
        """
        Detection rules feed - Sigma, YARA, KQL, SPL, Suricata (PRO tier).
        Ready for direct SIEM/EDR import.

        Requires: PRO API key
        """
        return self._request("GET", "/api/v1/premium/detections/")

    # ------------------------------------------
    # Enterprise Tier Endpoints
    # ------------------------------------------

    def get_enterprise_threats(self, limit: int = 100, include_archived: bool = False) -> Dict:
        """
        Full threat intelligence with complete IOC details (ENTERPRISE tier).

        There is no separate /enterprise/threats route -- same feed route
        as get_full_threats(), which the worker serves at full depth once
        the key resolves to ENTERPRISE server-side. `include_archived` has
        no effect: the deployed feed has no archived-item concept to filter.

        Args:
            limit: Max threats to return.
            include_archived: Accepted for signature compatibility; ignored
                (no real archived-item filter exists).

        Requires: ENTERPRISE API key
        """
        return self.get_full_threats(limit=limit)

    def get_stix_bundle(self, bundle_id: str) -> Dict:
        """
        Full STIX 2.1 bundle by ID (ENTERPRISE tier).

        There is no /enterprise/stix/{id} route; this pulls the real TAXII
        2.1 bundle (GET /taxii/collections/{id}/objects/) and, if bundle_id
        matches the bundle's own `id` (e.g. 'bundle--...'), returns it
        whole. If it instead matches one object's `id` within the bundle,
        returns a single-object bundle containing just that object.

        Args:
            bundle_id: STIX bundle ID, or a single object ID within it.

        Requires: ENTERPRISE API key
        """
        bundle = self._request("GET", "/taxii/collections/sentinel-apex-main/objects/")
        if bundle.get("id") == bundle_id:
            return bundle
        for obj in bundle.get("objects", []):
            if obj.get("id") == bundle_id:
                return {**bundle, "objects": [obj]}
        raise CDBAPIError(404, f"No STIX bundle or object found with id={bundle_id!r}")

    def get_actors(self) -> Dict:
        """
        Actor/APT intelligence (ENTERPRISE tier).

        There is no dedicated actor registry route; this is the closest
        real analog -- APT-tagged intelligence from the feed.

        Requires: ENTERPRISE API key
        """
        return self._request("GET", "/api/v1/intel/apt")

    def get_campaigns(self) -> Dict:
        """
        Active threat campaign tracking with IOC clusters (ENTERPRISE tier).

        Requires: ENTERPRISE API key
        """
        return self._request("GET", "/api/v1/intel/campaigns")

    def get_exploit_forecast(self, threat_id: str) -> Dict:
        """
        Exploit probability forecast for a threat (ENTERPRISE tier).

        Not available: no per-item exploit-forecasting route exists
        anywhere in the deployed API.

        Raises:
            FeatureNotDeployedError: Always -- see above.
        """
        raise FeatureNotDeployedError(
            "Per-item exploit forecasting has no deployed backend route.",
            feature="exploit_forecast",
        )

    def get_batch_forecast(self, threat_ids: List[str]) -> Dict:
        """
        Batch exploit probability forecasting (ENTERPRISE tier).

        Not available: no batch-forecasting route exists anywhere in the
        deployed API.

        Raises:
            FeatureNotDeployedError: Always -- see above.
        """
        raise FeatureNotDeployedError(
            "Batch exploit forecasting has no deployed backend route.",
            feature="batch_forecast",
        )

    def get_metrics(self) -> Dict:
        """
        Platform telemetry metrics (ENTERPRISE tier).

        There is no per-key /enterprise/metrics route; this returns the
        real platform-wide stats route instead (same data every caller
        sees, not scoped to your account).

        Requires: ENTERPRISE API key
        """
        return self._request("GET", "/api/platform/stats")

    def search_threats(
        self,
        query: str = "",
        severity: Optional[str] = None,
        actor: Optional[str] = None,
        cve: Optional[str] = None,
        mitre: Optional[str] = None,
        tlp: Optional[str] = None,
    ) -> Dict:
        """
        Full-text + filtered threat search (ENTERPRISE tier).

        There is no dedicated search route; this filters the feed
        manifest client-side.

        Args:
            query:    Free-text search query (matches title/description).
            severity: Filter by severity (CRITICAL/HIGH/MEDIUM/LOW).
            actor:    Filter by threat actor tag.
            cve:      Filter by CVE ID (matched against each item's IOCs).
            mitre:    Filter by MITRE technique ID.
            tlp:      Filter by TLP classification.

        Requires: ENTERPRISE API key
        """
        data  = self.get_feed()
        items = data.get("items", [])

        q = (query or "").lower()
        if q:
            items = [i for i in items if q in str(i.get("title", "")).lower()
                     or q in str(i.get("description", "")).lower()]
        if severity:
            s = severity.upper()
            items = [i for i in items if str(i.get("severity", "")).upper() == s]
        if actor:
            a = actor.lower()
            items = [i for i in items if a in str(i.get("actor_tag", "")).lower()]
        if cve:
            c = cve.upper()
            items = [i for i in items if c in [str(x).upper() for x in i.get("iocs", [])]]
        if mitre:
            m = mitre.upper()
            items = [i for i in items if m in [str(t.get("id", "")).upper()
                     for t in i.get("mitre_tactics", []) if isinstance(t, dict)]]
        if tlp:
            t = tlp.upper()
            items = [i for i in items if t in str(i.get("tlp_label", "")).upper()]

        return {"data": items, "total": len(items)}

    def get_supply_chain_intel(self) -> Dict:
        """
        Supply chain attack intelligence feed (ENTERPRISE tier).

        Not available: no supply-chain-specific route exists anywhere in
        the deployed API.

        Raises:
            FeatureNotDeployedError: Always -- see above.
        """
        raise FeatureNotDeployedError(
            "Supply-chain intelligence has no deployed backend route.",
            feature="supply_chain_intel",
        )

    def get_epss_enrichment(self, cve_ids: List[str]) -> Dict:
        """
        Bulk EPSS score enrichment for CVE IDs (ENTERPRISE tier).

        Uses the real EPSS route (GET /api/v1/intel/epss), which returns a
        top_cves list drawn from the feed; this filters it down to the
        requested CVE IDs client-side. Only CVEs already present in that
        list can be enriched -- there is no arbitrary-CVE EPSS lookup.

        Args:
            cve_ids: List of CVE IDs (e.g., ['CVE-2024-1234', 'CVE-2024-5678']).

        Requires: ENTERPRISE API key
        """
        raw = self._request("GET", "/api/v1/intel/epss")
        wanted = {c.upper() for c in cve_ids}
        matched = [c for c in raw.get("top_cves", []) if str(c.get("cve_id", "")).upper() in wanted]
        return {**raw, "top_cves": matched}

    def get_risk_trend(self, window_hours: int = 168) -> Dict:
        """
        Risk trend analytics over a rolling window (ENTERPRISE tier).

        Not available: no risk-trend route exists anywhere in the deployed
        API.

        Raises:
            FeatureNotDeployedError: Always -- see above.
        """
        raise FeatureNotDeployedError(
            "Risk trend analytics has no deployed backend route.",
            feature="risk_trend",
        )

    # ------------------------------------------
    # TAXII 2.1
    # ------------------------------------------

    def get_taxii_collections(self) -> Dict:
        """TAXII 2.1 collection listing (FREE)."""
        return self._request("GET", "/taxii/collections/")

    def get_taxii_objects(self, collection_id: str, limit: int = 20) -> Dict:
        """
        TAXII 2.1 object fetch (ENTERPRISE tier for the KEV collection).

        The deployed route has no `limit` query param; it's applied
        client-side against the returned bundle's objects.

        Args:
            collection_id: TAXII collection ID (e.g. "sentinel-apex-main"
                           or the ENTERPRISE-only "sentinel-apex-kev").
            limit:         Max objects to return.

        Requires: ENTERPRISE API key for the KEV collection.
        """
        bundle = self._request("GET", f"/taxii/collections/{collection_id}/objects/")
        objects = (bundle.get("objects") or [])[:limit]
        return {**bundle, "objects": objects}

    # ------------------------------------------
    # Convenience / Helper Methods
    # ------------------------------------------

    def get_critical_threats(self, limit: int = 20) -> List[Dict]:
        """
        Shortcut: Get CRITICAL severity threats only (ENTERPRISE tier).

        Args:
            limit: Max threats to return.
        """
        result = self.search_threats(severity="CRITICAL")
        data   = result.get("data", result.get("threats", []))
        return data[:limit]

    def get_iocs_by_type(self, ioc_type: str, limit: int = 100) -> List[Dict]:
        """
        Shortcut: Get IOCs filtered by type (PRO tier).

        Args:
            ioc_type: IOC type (ipv4, domain, url, sha256, sha1, md5, email, cve, registry).
            limit:    Max IOCs to return.
        """
        result = self.get_iocs(limit=limit)
        iocs   = result.get("data", result.get("iocs", []))
        return [i for i in iocs if i.get("type", "").lower() == ioc_type.lower()]

    def export_iocs_to_json(self, filepath: str, limit: int = 200) -> str:
        """
        Export IOC feed to a JSON file (PRO tier).

        Args:
            filepath: Output file path.
            limit:    Max IOCs to export.

        Returns:
            filepath of written file.
        """
        ioc_data = self.get_iocs(limit=limit)
        with open(filepath, "w") as f:
            json.dump(ioc_data, f, indent=2)
        logger.info(f"IOC feed exported to {filepath}")
        return filepath

    def export_stix_bundle(self, bundle_id: str, filepath: str) -> str:
        """
        Export a STIX 2.1 bundle to a JSON file (ENTERPRISE tier).

        Args:
            bundle_id: STIX bundle ID.
            filepath:  Output file path.

        Returns:
            filepath of written file.
        """
        bundle = self.get_stix_bundle(bundle_id)
        with open(filepath, "w") as f:
            json.dump(bundle, f, indent=2)
        logger.info(f"STIX bundle exported to {filepath}")
        return filepath

    def get_platform_summary(self) -> Dict:
        """
        Shortcut: Combine health + stats into a single platform summary (FREE).
        """
        health = self.health()
        stats  = self.stats()
        return {
            "timestamp":     datetime.now(timezone.utc).isoformat(),
            "sdk_version":   SDK_VERSION,
            "health":        health,
            "stats":         stats,
            "platform":      "CYBERDUDEBIVASH SENTINEL APEX",
            "documentation": "https://intel.cyberdudebivash.com/api-docs.html",
        }

    def __repr__(self) -> str:
        tier = "FREE"
        if self.api_key:
            tier = "PRO" if self.api_key.startswith("cdb-pro-") else "ENTERPRISE"
        return f"<CDBClient tier={tier} base_url={self.base_url} sdk_version={SDK_VERSION}>"


# ------------------------------------------------------------------
# Quick-start CLI demo (python -m agent.sdk.cdb_python_sdk)
# ------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    api_key = sys.argv[1] if len(sys.argv) > 1 else None

    print(f"""
+==========================================================+
|  CyberDudeBivash Python SDK v{SDK_VERSION}                       |
|  Platform: https://intel.cyberdudebivash.com             |
|  API Docs: https://intel.cyberdudebivash.com/api-docs.html |
+==========================================================+
    """)

    client = CDBClient(api_key=api_key, verbose=True)
    print(f"Client: {client}\n")

    print("-> Fetching platform health...")
    try:
        h = client.health()
        print(f"   Status: {h.get('status', 'N/A')}")
    except Exception as e:
        print(f"   Error: {e}")

    print("\n-> Fetching public stats...")
    try:
        s = client.stats()
        print(f"   Data: {json.dumps(s, indent=4)}")
    except Exception as e:
        print(f"   Error: {e}")

    print("\n-> Fetching latest threats (FREE tier)...")
    try:
        t = client.get_threats()
        print(f"   Returned {len(t.get('data', t.get('threats', [])))} threats")
    except Exception as e:
        print(f"   Error: {e}")

    print("\n? SDK demo complete. Get your API key: https://tools.cyberdudebivash.com/")
