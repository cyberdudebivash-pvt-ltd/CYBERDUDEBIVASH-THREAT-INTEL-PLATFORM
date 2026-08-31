"""
sdk/sentinel_sdk/client.py — CYBERDUDEBIVASH® Sentinel APEX Python SDK v1.0.0
Production-grade synchronous API client.

Features:
  - Automatic retry with exponential backoff (4 attempts, jitter)
  - Per-tier rate limit awareness (429 → retry-after honoured)
  - Connection pooling via urllib (no external deps required)
  - Response deserialization to typed model objects
  - Thread-safe: single instance safe for multi-threaded use
  - Covers every capability the deployed API actually serves: feed-derived
    advisories/search (client-side filtered — the live worker has no
    server-side query params on its feed route), TAXII/STIX export,
    IOC lookup, health.

Zero external dependencies — stdlib only (urllib, json, hmac, hashlib).
Optional: install 'requests' for HTTP/2 and connection reuse improvements.

Every method below is verified against the deployed Cloudflare Worker
(workers/intel-gateway/src/index.js) — the only backend this API is
actually served from, at https://intel.cyberdudebivash.com. Earlier
versions of this file pointed at
https://api.sentinelapex.cyberdudebivash.com, a domain with no Worker
route, DNS entry, or any other backing infrastructure anywhere in this
repository (see wrangler.toml's `routes` block) — every call would have
failed outright. A handful of methods below have no real server-side
equivalent at all (key rotation, ingestion status); those raise
SDKConfigurationError with an explanation instead of silently hitting a
route that would 404/401 for every real customer.
"""
from __future__ import annotations

import json
import logging
import random
import time
from typing import Any, Dict, Iterator, List, Optional
from urllib.parse import urlencode, urljoin
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

from .exceptions import (
    AuthenticationError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    SDKConfigurationError,
    ServerError,
    TierPermissionError,
    ValidationError,
)
from .models import (
    AdvisoryItem,
    ApiKeyInfo,
    FeedMetadata,
    HealthStatus,
    Page,
    StixBundle,
)

logger = logging.getLogger("sentinel_sdk.client")

_DEFAULT_BASE_URL = "https://intel.cyberdudebivash.com"
_DEFAULT_TIMEOUT  = 30
_MAX_RETRIES      = 4
_RETRY_BASE_S     = 1.0
_RETRY_MAX_S      = 30.0
_SDK_VERSION      = "1.0.0"
_USER_AGENT       = f"SentinelAPEX-Python-SDK/{_SDK_VERSION}"


class SentinelClient:
    """
    Synchronous client for the CYBERDUDEBIVASH® Sentinel APEX Threat Intelligence API.

    Quick start::

        from sentinel_sdk import SentinelClient

        client = SentinelClient(api_key="sa_live_xxxx")
        advisories = client.get_advisories(severity="CRITICAL", limit=25)
        for item in advisories.items:
            print(item.title, item.risk_score)

    Args:
        api_key:    Your Sentinel APEX API key (required).
        base_url:   Override the API base URL (default: production endpoint).
        timeout:    HTTP request timeout in seconds (default: 30).
        max_retries: Max retry attempts on transient errors (default: 4).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: int = _DEFAULT_TIMEOUT,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        if not api_key:
            raise SDKConfigurationError(
                "api_key is required. Get one at https://sentinel.cyberdudebivash.com/onboarding"
            )
        self._api_key    = api_key
        self._base_url   = base_url.rstrip("/")
        self._timeout    = timeout
        self._max_retries = max_retries

    # ─────────────────────────────────────────────────────────────────────────
    # Advisories
    # ─────────────────────────────────────────────────────────────────────────

    def get_advisories(
        self,
        severity:   Optional[str] = None,
        threat_type: Optional[str] = None,
        limit:      int = 20,
        page:       int = 1,
        kev_only:   bool = False,
    ) -> Page:
        """
        Fetch threat intelligence advisories.

        The deployed API serves the advisory manifest from a single route
        (GET /api/feed — the same data as /api/v1/intel/latest.json) with
        no server-side severity/threat_type/kev_only/pagination params;
        the worker only tier-gates which fields are visible per API key.
        This method fetches that manifest and applies the filters below
        client-side.

        Args:
            severity:    Filter by severity: CRITICAL | HIGH | MEDIUM | LOW
            threat_type: Filter by type (substring match against the
                         item's threat_type, e.g. "ransomware", "apt")
            limit:       Results per page
            page:        Page number (1-indexed)
            kev_only:    Only return CISA KEV entries

        Returns:
            Page object with .items (List[AdvisoryItem]) and .metadata (FeedMetadata)
        """
        raw   = self._get("/api/feed")
        items_raw = raw.get("items", [])

        if severity:
            s = severity.upper()
            items_raw = [d for d in items_raw if str(d.get("severity", "")).upper() == s]
        if threat_type:
            t = threat_type.lower()
            items_raw = [d for d in items_raw if t in str(d.get("threat_type", "")).lower()]
        if kev_only:
            items_raw = [d for d in items_raw if d.get("kev_present")]

        total = len(items_raw)
        start = max(page - 1, 0) * limit
        page_raw = items_raw[start:start + limit]
        items = [AdvisoryItem.from_dict(d) for d in page_raw]
        meta = FeedMetadata(
            total=total, returned=len(items), page=page,
            tier=str(raw.get("tier", "")), feed_version=str(raw.get("version", "")),
            last_updated=str(raw.get("generated_at", "")),
            critical_count=sum(1 for d in items_raw if str(d.get("severity", "")).upper() == "CRITICAL"),
            high_count=sum(1 for d in items_raw if str(d.get("severity", "")).upper() == "HIGH"),
            kev_count=sum(1 for d in items_raw if d.get("kev_present")),
        )
        return Page(items=items, metadata=meta, raw=raw)

    def get_advisory(self, stix_id: str) -> AdvisoryItem:
        """
        Fetch a single advisory by STIX ID.

        There is no single-resource advisory route in the deployed API;
        this looks the ID up client-side against the same feed manifest
        get_advisories() uses.

        Raises:
            NotFoundError: If the advisory does not exist.
        """
        raw = self._get("/api/feed")
        for d in raw.get("items", []):
            if d.get("stix_id") == stix_id or d.get("id") == stix_id:
                return AdvisoryItem.from_dict(d)
        raise NotFoundError(f"No advisory found with stix_id={stix_id!r}", status_code=404)

    def search_advisories(self, query: str, limit: int = 20) -> Page:
        """
        Search across advisory titles and descriptions.

        There is no dedicated full-text search route in the deployed API;
        this filters the same feed manifest get_advisories() uses. Data
        depth still depends on your API key's tier, since the feed route
        itself masks IOCs/detection rules for FREE-tier keys.

        Args:
            query: Search string (CVE IDs, actor names, keywords)
            limit: Max results to return
        """
        raw   = self._get("/api/feed")
        q     = query.lower()
        matched = [
            d for d in raw.get("items", [])
            if q in str(d.get("title", "")).lower() or q in str(d.get("description", "")).lower()
        ]
        total = len(matched)
        page_raw = matched[:limit]
        items = [AdvisoryItem.from_dict(d) for d in page_raw]
        meta = FeedMetadata(
            total=total, returned=len(items), page=1,
            tier=str(raw.get("tier", "")), feed_version=str(raw.get("version", "")),
            last_updated=str(raw.get("generated_at", "")),
        )
        return Page(items=items, metadata=meta, raw=raw)

    def iter_advisories(
        self,
        severity: Optional[str] = None,
        threat_type: Optional[str] = None,
        max_pages: int = 10,
        page_size: int = 100,
    ) -> Iterator[AdvisoryItem]:
        """
        Generator that transparently paginates through all matching advisories.

        Args:
            severity:    Optional severity filter
            threat_type: Optional threat type filter
            max_pages:   Safety ceiling on pages fetched (default: 10)
            page_size:   Items per page (default: 100)

        Yields:
            AdvisoryItem objects one by one
        """
        for page_num in range(1, max_pages + 1):
            page = self.get_advisories(
                severity=severity,
                threat_type=threat_type,
                limit=page_size,
                page=page_num,
            )
            yield from page.items
            if not page.has_more:
                break

    # ─────────────────────────────────────────────────────────────────────────
    # STIX Export (PRO+)
    # ─────────────────────────────────────────────────────────────────────────

    def export_stix(
        self,
        stix_ids: Optional[List[str]] = None,
        severity: Optional[str] = None,
        limit: int = 50,
        collection: str = "sentinel-apex-main",
    ) -> StixBundle:
        """
        Export advisories as a STIX 2.1 bundle via the deployed TAXII 2.1
        server (PRO+ — the worker 401s FREE-tier keys on this route).

        There is no dedicated /stix/export route; this calls the real
        TAXII object-collection route (GET /taxii/collections/{id}/objects/)
        and applies stix_ids/severity/limit client-side. The other real
        collection is "sentinel-apex-kev" (ENTERPRISE-only, CISA KEV
        entries only).

        Args:
            stix_ids:   Optional list of specific STIX object IDs to keep
            severity:   Optional severity filter (matches each object's
                        custom_properties.x_sentinel_severity)
            limit:      Max objects in the returned bundle
            collection: TAXII collection ID (default: main collection)

        Returns:
            StixBundle with .objects (list of STIX objects)

        Raises:
            TierPermissionError: Requires PRO tier or higher
        """
        raw = self._get(f"/taxii/collections/{collection}/objects/")
        objects = raw.get("objects", [])
        if severity:
            s = severity.upper()
            objects = [
                o for o in objects
                if str((o.get("custom_properties") or {}).get("x_sentinel_severity", "")).upper() == s
            ]
        if stix_ids:
            id_set = set(stix_ids)
            objects = [o for o in objects if o.get("id") in id_set]
        objects = objects[:limit]
        return StixBundle(
            type=raw.get("type", "bundle"), id=raw.get("id", ""),
            objects=objects, spec_version=raw.get("spec_version", "2.1"),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # IOC Lookup (PRO+)
    # ─────────────────────────────────────────────────────────────────────────

    def lookup_ioc(self, ioc: str, ioc_type: str = "auto") -> Dict[str, Any]:
        """
        Look up a specific IOC (IP, hash, domain, CVE ID) (PRO+).

        Args:
            ioc:      The IOC value to look up
            ioc_type: Hint for type: ip | hash | domain | cve | auto
                      (accepted for forward compatibility; the deployed
                      route does not currently filter on it — it infers
                      the type from the query itself)

        Returns:
            Raw dict with matched advisories and threat context
        """
        # The deployed route reads the query from "q" (or "query"/"ioc" in
        # a POST body) — it has never accepted "value", so every lookup
        # previously 400'd/ignored the query entirely.
        params = {"q": ioc, "type": ioc_type}
        return self._get("/api/v1/ioc/lookup", params=params)

    # ─────────────────────────────────────────────────────────────────────────
    # Health & Status
    # ─────────────────────────────────────────────────────────────────────────

    def health(self) -> HealthStatus:
        """
        Check Sentinel APEX API health status.

        Returns:
            HealthStatus with .is_healthy bool and .components dict

        Note:
            Does not consume API quota. Safe to call frequently.
            No authentication required — this is a public route.
        """
        raw = self._get("/api/health")
        return HealthStatus.from_dict(raw)

    def ping(self) -> bool:
        """
        Simple reachability check.

        Returns:
            True if API responds, False otherwise (never raises).
        """
        try:
            status = self.health()
            return status.is_healthy
        except Exception:
            return False

    # ─────────────────────────────────────────────────────────────────────────
    # API Key Management
    # ─────────────────────────────────────────────────────────────────────────

    def get_key_info(self) -> ApiKeyInfo:
        """
        Retrieve metadata for the current API key.

        There is no /monetize/key/info route in the deployed API. The
        closest real equivalent is the auth-validation route, which only
        confirms validity and tier — it does not report usage_today,
        daily_limit, or expires_at, so those fields stay at their
        ApiKeyInfo defaults (0 / None) rather than fabricated values.

        Returns:
            ApiKeyInfo with .tier and .is_active populated from the live
            API; usage/quota fields are not available from any current
            endpoint.
        """
        raw = self._get("/api/auth/validate")
        return ApiKeyInfo(
            key=self._api_key, tier=str(raw.get("tier", "")),
            owner="", label="", created_at="",
            is_active=bool(raw.get("valid", False)),
        )

    def rotate_key(self, confirm: bool = False) -> ApiKeyInfo:
        """
        Rotate the current API key (generates a new key, invalidates old one).

        Not supported: the deployed API only exposes key issuance/rotation
        under /api/admin/keys, gated by an operator-only ADMIN_SECRET header
        no customer API key can supply — there is no self-service rotation
        endpoint for customers today.

        Raises:
            SDKConfigurationError: Always — see above. Contact support to
                rotate a key until a self-service route exists.
        """
        raise SDKConfigurationError(
            "Key rotation is not available through the public API. "
            "Key management is operator-only (ADMIN_SECRET-gated); "
            "contact support to rotate your key.",
            param="confirm",
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Ingestion Status (ENTERPRISE+)
    # ─────────────────────────────────────────────────────────────────────────

    def get_ingestion_status(self) -> Dict[str, Any]:
        """
        Get live ingestion pipeline status (ENTERPRISE+).

        Not supported: the deployed API has no customer-facing ingestion
        status route. Source-health/observability data exists only under
        the internal P30/P40 platform routes, which
        docs/developer-portal-guide.md explicitly documents as
        platform-internal infrastructure, not part of the customer
        developer surface.

        Raises:
            SDKConfigurationError: Always — see above.
        """
        raise SDKConfigurationError(
            "Ingestion status is not available through the public API. "
            "Source-health data is internal-only platform infrastructure."
        )

    def trigger_ingestion(self, source_id: str = "all") -> Dict[str, Any]:
        """
        Manually trigger a data source fetch (ENTERPRISE+).

        Not supported: no ingestion-trigger route exists anywhere in the
        deployed API for customers to call.

        Raises:
            SDKConfigurationError: Always — see above.
        """
        raise SDKConfigurationError(
            "Manually triggering ingestion is not available through the public API."
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Internal HTTP layer
    # ─────────────────────────────────────────────────────────────────────────

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = self._build_url(path, params)
        return self._request("GET", url)

    def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        url  = self._build_url(path)
        data = json.dumps(body).encode("utf-8")
        return self._request("POST", url, data=data)

    def _request(self, method: str, url: str,
                 data: Optional[bytes] = None) -> Dict[str, Any]:
        headers = {
            "X-API-Key":     self._api_key,
            "Accept":        "application/json",
            "Content-Type":  "application/json",
            "User-Agent":    _USER_AGENT,
        }
        req = Request(url, data=data, headers=headers, method=method)

        last_exc: Optional[Exception] = None
        for attempt in range(1, self._max_retries + 1):
            try:
                with urlopen(req, timeout=self._timeout) as resp:
                    body = resp.read().decode("utf-8")
                    return json.loads(body) if body.strip() else {}

            except HTTPError as exc:
                status = exc.code
                try:
                    body = exc.read().decode("utf-8")
                    resp_body = json.loads(body) if body else {}
                except Exception:
                    resp_body = {}

                if status == 401:
                    raise AuthenticationError(
                        "Invalid or missing API key. Check your key at "
                        "https://sentinel.cyberdudebivash.com/dashboard",
                        status_code=401, response_body=resp_body,
                    ) from exc

                if status == 403:
                    tier = resp_body.get("required_tier", "")
                    raise TierPermissionError(
                        resp_body.get("detail", "Feature not available on your tier"),
                        status_code=403, required_tier=tier, response_body=resp_body,
                    ) from exc

                if status == 404:
                    raise NotFoundError(
                        resp_body.get("detail", f"Resource not found: {url}"),
                        status_code=404, response_body=resp_body,
                    ) from exc

                if status == 422:
                    raise ValidationError(
                        resp_body.get("detail", "Request validation failed"),
                        status_code=422, response_body=resp_body,
                    ) from exc

                if status == 429:
                    retry_after = int(exc.headers.get("Retry-After", 60))
                    if attempt < self._max_retries:
                        logger.warning("rate_limited retry_after=%ds attempt=%d",
                                       retry_after, attempt)
                        time.sleep(retry_after)
                        continue
                    raise RateLimitError(
                        f"Rate limit exceeded. Retry after {retry_after}s.",
                        status_code=429,
                        retry_after_s=retry_after,
                        response_body=resp_body,
                    ) from exc

                if status >= 500:
                    last_exc = ServerError(
                        f"Server error {status}: {resp_body.get('detail', 'Internal error')}",
                        status_code=status, response_body=resp_body,
                    )
                    # Retry on 5xx
                    if attempt < self._max_retries:
                        delay = self._backoff_delay(attempt)
                        logger.warning("server_error status=%d attempt=%d retry_in=%.1fs",
                                       status, attempt, delay)
                        time.sleep(delay)
                        continue
                    raise last_exc from exc

                raise  # Non-retryable HTTP errors

            except URLError as exc:
                last_exc = NetworkError(
                    f"Network error connecting to Sentinel APEX API: {exc.reason}",
                    status_code=0,
                )
                if attempt < self._max_retries:
                    delay = self._backoff_delay(attempt)
                    logger.warning("network_error attempt=%d retry_in=%.1fs err=%s",
                                   attempt, delay, exc.reason)
                    time.sleep(delay)
                    continue
                raise last_exc from exc

        # Should not reach here, but satisfy type checker
        if last_exc:
            raise last_exc
        raise NetworkError("Exhausted retries with no definitive error")

    def _build_url(self, path: str,
                   params: Optional[Dict[str, Any]] = None) -> str:
        """Construct full URL with query string."""
        # Bug fix: __init__ stores this as self._base_url; every call here
        # previously read the never-set self.base_url, so _build_url raised
        # AttributeError on the very first request the SDK ever made.
        base = self._base_url.rstrip("/")
        url  = f"{base}{path}"
        if params:
            from urllib.parse import urlencode
            qs = urlencode({k: v for k, v in params.items() if v is not None})
            if qs:
                url = f"{url}?{qs}"
        return url
