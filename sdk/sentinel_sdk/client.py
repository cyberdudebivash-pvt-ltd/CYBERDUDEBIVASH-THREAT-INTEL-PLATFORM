"""
sdk/sentinel_sdk/client.py — CYBERDUDEBIVASH® Sentinel APEX Python SDK v135.0
Production-grade synchronous API client.

Features:
  - Automatic retry with exponential backoff (4 attempts, jitter)
  - Per-tier rate limit awareness (429 → retry-after honoured)
  - Connection pooling via urllib (no external deps required)
  - Response deserialization to typed model objects
  - Thread-safe: single instance safe for multi-threaded use
  - Full coverage of the live intel.cyberdudebivash.com API: feed, search,
    IOC lookup, STIX/TAXII export, health, API key self-service

Zero external dependencies — stdlib only (urllib, json, hmac, hashlib).
Optional: install 'requests' for HTTP/2 and connection reuse improvements.

v135.0: this client previously targeted api.sentinelapex.cyberdudebivash.com,
a domain with no configured route anywhere in the platform's deployment (no
DNS, no wrangler.toml route, not referenced by any other file in the repo) --
every call would have failed for a real user. Every method below was
re-verified against the actual live router
(workers/intel-gateway/src/index.js) and, where a method's path had no real
backing route (get_advisory-by-id, search pagination, STIX filtering,
ingestion status/trigger), rewritten to match what the API genuinely
supports rather than what was previously assumed.
"""
from __future__ import annotations

import json
import logging
import random
import time
from typing import Any, Dict, Iterator, Optional
from urllib.parse import urlencode
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

# The only domain with real configured routes for this platform
# (workers/intel-gateway/wrangler.toml `routes`). Do not point this at any
# other subdomain without first confirming a real route exists there.
_DEFAULT_BASE_URL = "https://intel.cyberdudebivash.com"
# Customer self-service (API key validate/rotate) is served by a separate
# Worker (workers/revenue-engine), reachable via its own custom domain
# (workers/revenue-engine/wrangler.toml `routes`) rather than a path prefix
# on the main domain.
_DEFAULT_BILLING_BASE_URL = "https://revenue.intel.cyberdudebivash.com"
_DEFAULT_TIMEOUT  = 30
_MAX_RETRIES      = 4
_RETRY_BASE_S     = 1.0
_RETRY_MAX_S      = 30.0
_SDK_VERSION      = "135.0.0"
_USER_AGENT       = f"SentinelAPEX-Python-SDK/{_SDK_VERSION}"


class SentinelClient:
    """
    Synchronous client for the CYBERDUDEBIVASH® Sentinel APEX Threat Intelligence API.

    Quick start::

        from sentinel_sdk import SentinelClient

        client = SentinelClient(api_key="cdb_pro_xxxx")
        advisories = client.get_advisories(severity="CRITICAL", limit=25)
        for item in advisories.items:
            print(item.title, item.risk_score)

    Args:
        api_key:     Your Sentinel APEX API key (required).
        base_url:    Override the main API base URL (default: production endpoint).
        billing_base_url: Override the customer-portal/billing base URL used by
                     get_key_info()/rotate_key() (default: production endpoint).
        timeout:     HTTP request timeout in seconds (default: 30).
        max_retries: Max retry attempts on transient errors (default: 4).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = _DEFAULT_BASE_URL,
        billing_base_url: str = _DEFAULT_BILLING_BASE_URL,
        timeout: int = _DEFAULT_TIMEOUT,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        if not api_key:
            raise SDKConfigurationError(
                "api_key is required. Get one at https://intel.cyberdudebivash.com/get-api-key.html"
            )
        self._api_key         = api_key
        self._base_url        = base_url.rstrip("/")
        self._billing_base_url = billing_base_url.rstrip("/")
        self._timeout         = timeout
        self._max_retries     = max_retries

    # ─────────────────────────────────────────────────────────────────────────
    # Advisories / Feed
    # ─────────────────────────────────────────────────────────────────────────
    #
    # GET /api/feed returns the full current feed with no server-side
    # filtering or pagination (confirmed against index.js's /api/feed
    # handler) -- so severity/threat_type/kev_only/limit/page are applied
    # client-side here. This means get_advisories() fetches the whole feed
    # on every call; there is no cheaper server-side query available today.

    def get_advisories(
        self,
        severity:   Optional[str] = None,
        threat_type: Optional[str] = None,
        limit:      int = 20,
        page:       int = 1,
        kev_only:   bool = False,
    ) -> Page:
        """
        Fetch threat intelligence advisories (filtered/paginated client-side).

        Args:
            severity:    Filter by severity: CRITICAL | HIGH | MEDIUM | LOW
            threat_type: Filter by type (matched against the item's threat_type)
            limit:       Results per page (client-side slice)
            page:        Page number (1-indexed, client-side slice)
            kev_only:    Only return CISA KEV entries

        Returns:
            Page object with .items (List[AdvisoryItem]) and .metadata (FeedMetadata)
        """
        raw = self._get("/api/feed")
        items = raw.get("items", []) if isinstance(raw, dict) else (raw or [])

        if severity:
            severity = severity.upper()
            items = [i for i in items if str(i.get("severity", "")).upper() == severity]
        if threat_type:
            items = [i for i in items if threat_type.lower() in str(i.get("threat_type", "")).lower()]
        if kev_only:
            items = [i for i in items if _is_kev(i)]

        total = len(items)
        start = max(page - 1, 0) * limit
        page_items = items[start:start + limit]

        meta = FeedMetadata(
            total=total, returned=len(page_items), page=page,
            tier=raw.get("tier", "") if isinstance(raw, dict) else "",
            feed_version=raw.get("feed_version", "") if isinstance(raw, dict) else "",
            last_updated=raw.get("generated_at", "") if isinstance(raw, dict) else "",
            critical_count=sum(1 for i in items if str(i.get("severity", "")).upper() == "CRITICAL"),
            high_count=sum(1 for i in items if str(i.get("severity", "")).upper() == "HIGH"),
            kev_count=sum(1 for i in items if _is_kev(i)),
        )
        return _PageWithMeta(
            items=[AdvisoryItem.from_dict(d) for d in page_items], metadata=meta, raw=raw,
            offset=start, limit=limit,
        )

    def get_advisory(self, stix_id: str) -> AdvisoryItem:
        """
        Fetch a single advisory by its STIX ID (or plain id) from the live feed.

        Raises:
            NotFoundError: If no advisory in the current feed matches.
        """
        raw = self._get("/api/feed")
        items = raw.get("items", []) if isinstance(raw, dict) else (raw or [])
        for d in items:
            if d.get("stix_id") == stix_id or d.get("id") == stix_id:
                return AdvisoryItem.from_dict(d)
        raise NotFoundError(f"No advisory found with id={stix_id!r} in the current feed")

    def iter_advisories(
        self,
        severity: Optional[str] = None,
        threat_type: Optional[str] = None,
        max_pages: int = 10,
        page_size: int = 100,
    ) -> Iterator[AdvisoryItem]:
        """
        Generator that transparently paginates through all matching advisories.

        Note: since /api/feed has no server-side pagination, this fetches the
        full feed once per page (cheap -- the underlying HTTP client does not
        cache) and slices client-side; prefer get_advisories() directly if
        you only need one page.
        """
        for page_num in range(1, max_pages + 1):
            page = self.get_advisories(
                severity=severity, threat_type=threat_type,
                limit=page_size, page=page_num,
            )
            yield from page.items
            if not page.has_more:
                break

    # ─────────────────────────────────────────────────────────────────────────
    # Search (PRO+)
    # ─────────────────────────────────────────────────────────────────────────

    def search_advisories(self, query: str, limit: int = 20) -> Page:
        """
        Full-text search across advisory titles, IOCs, and TTPs (PRO+).

        Args:
            query: Search string (CVE IDs, actor names, keywords)
            limit: Max results to return

        Raises:
            TierPermissionError: If on FREE tier (search requires PRO+)
        """
        raw = self._get("/api/search", params={"q": query, "limit": limit})
        items = [AdvisoryItem.from_dict(d) for d in raw.get("data", raw.get("results", []))]
        meta  = FeedMetadata(
            total=raw.get("total", len(items)), returned=len(items), page=1,
            tier=raw.get("tier", ""), feed_version="", last_updated="",
        )
        return _PageWithMeta(items=items, metadata=meta, raw=raw, offset=0, limit=limit)

    # ─────────────────────────────────────────────────────────────────────────
    # STIX / TAXII Export (PRO+; KEV collection is ENTERPRISE+)
    # ─────────────────────────────────────────────────────────────────────────

    def export_stix(self, kev_only: bool = False, limit: int = 50) -> StixBundle:
        """
        Export the live TAXII 2.1 collection as a STIX bundle.

        Args:
            kev_only: Export the CISA-KEV-only collection (ENTERPRISE+)
                      instead of the main collection (PRO+).
            limit:    Max objects to keep (applied client-side; the server
                      does not currently support a limit query param).

        Returns:
            StixBundle with .objects (list of STIX objects)

        Raises:
            TierPermissionError: Requires PRO tier or higher (ENTERPRISE+ for kev_only)
        """
        collection = "sentinel-apex-kev" if kev_only else "sentinel-apex-main"
        raw = self._get(f"/taxii/collections/{collection}/objects/")
        bundle = StixBundle.from_dict(raw)
        if limit and len(bundle.objects) > limit:
            bundle = StixBundle(type=bundle.type, id=bundle.id,
                                 objects=bundle.objects[:limit], spec_version=bundle.spec_version)
        return bundle

    # ─────────────────────────────────────────────────────────────────────────
    # IOC Lookup
    # ─────────────────────────────────────────────────────────────────────────

    def lookup_ioc(self, ioc: str, ioc_type: str = "auto") -> Dict[str, Any]:
        """
        Look up a specific IOC (IP, hash, domain, CVE ID, or keyword) against
        the live feed.

        Args:
            ioc:      The IOC value to look up
            ioc_type: Hint for type: ip | hash | domain | cve | auto.
                      Not currently used server-side (the live endpoint does a
                      keyword match, not typed indicator matching) -- kept in
                      the signature so this doesn't need another breaking
                      change once typed lookup ships.

        Returns:
            Raw dict: {found, query, results: [...]}
        """
        return self._get("/api/v1/ioc/lookup", params={"q": ioc})

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
    # API Key Management (self-service; served by the billing base URL)
    # ─────────────────────────────────────────────────────────────────────────

    def get_key_info(self) -> ApiKeyInfo:
        """
        Retrieve metadata for the current API key.

        Returns:
            ApiKeyInfo with tier, usage_today, daily_limit, etc.
        """
        raw = self._get("/api/apikeys/validate", base_url=self._billing_base_url)
        return ApiKeyInfo.from_dict(raw)

    def rotate_key(self, confirm: bool = False) -> ApiKeyInfo:
        """
        Rotate the current API key (generates a new key, invalidates old one).

        Args:
            confirm: Must be True to perform the rotation (safety guard)

        Raises:
            SDKConfigurationError: If confirm=False
        """
        if not confirm:
            raise SDKConfigurationError(
                "Set confirm=True to confirm key rotation. "
                "This will invalidate your current key immediately."
            )
        raw = self._post("/api/apikeys/self-rotate", body={}, base_url=self._billing_base_url)
        new_key = raw.get("new_key", raw.get("key", ""))
        if new_key:
            self._api_key = new_key
            logger.info("API key rotated successfully — client updated with new key")
        return ApiKeyInfo.from_dict(raw)

    # ─────────────────────────────────────────────────────────────────────────
    # Internal HTTP layer
    # ─────────────────────────────────────────────────────────────────────────

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None,
              base_url: Optional[str] = None) -> Dict[str, Any]:
        url = self._build_url(path, params, base_url)
        return self._request("GET", url)

    def _post(self, path: str, body: Dict[str, Any],
               base_url: Optional[str] = None) -> Dict[str, Any]:
        url  = self._build_url(path, None, base_url)
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
                        "Invalid or missing API key. Get one at "
                        "https://intel.cyberdudebivash.com/get-api-key.html",
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

    def _backoff_delay(self, attempt: int) -> float:
        delay = min(_RETRY_BASE_S * (2 ** (attempt - 1)), _RETRY_MAX_S)
        return delay * (0.5 + random.random())

    def _build_url(self, path: str, params: Optional[Dict[str, Any]] = None,
                    base_url: Optional[str] = None) -> str:
        """Construct full URL with query string."""
        base = (base_url or self._base_url).rstrip("/")
        url  = f"{base}{path}"
        if params:
            qs = urlencode({k: v for k, v in params.items() if v is not None})
            if qs:
                url = f"{url}?{qs}"
        return url


def _is_kev(item: Dict[str, Any]) -> bool:
    """
    kev_feed_marker.py writes the canonical boolean field `kev_present`.
    Some exported feed snapshots instead (or additionally) carry a legacy
    string field `kev` ("YES"/"NO"). Check both so this doesn't silently
    under-count depending on which snapshot the caller's feed came from.
    """
    if item.get("kev_present"):
        return True
    return str(item.get("kev", "")).strip().upper() in ("YES", "TRUE", "1")


class _PageWithMeta(Page):
    """Page subclass that also exposes .metadata, matching this SDK's
    documented interface (Page itself only tracks offset/limit/total).
    offset/limit are passed explicitly rather than derived from
    FeedMetadata, which has no limit field of its own."""

    def __init__(self, items, metadata: FeedMetadata, offset: int, limit: int,
                 raw: Optional[Dict[str, Any]] = None):
        super().__init__(
            items=items,
            total_available=metadata.total,
            offset=offset,
            limit=limit,
            tier=metadata.tier,
            generated=metadata.last_updated,
        )
        self.metadata = metadata
        self.raw = raw or {}
