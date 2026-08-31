# Sentinel APEX Python SDK

Official Python client for the [CYBERDUDEBIVASH® Sentinel APEX](https://intel.cyberdudebivash.com) Threat Intelligence API — real-time CVE, KEV, and IOC intelligence with zero external dependencies.

```bash
pip install sentinel-apex-sdk
```

## Quickstart — IOC lookup in 3 lines

```python
from sentinel_sdk import SentinelClient
client = SentinelClient(api_key="YOUR_API_KEY")
result = client.lookup_ioc("1.2.3.4")
```

Don't have a key yet? [**Get a free API key →**](https://intel.cyberdudebivash.com/pricing.html?ref=pypi_readme) (no credit card required for the FREE tier).

## Full example

```python
from sentinel_sdk import SentinelClient

client = SentinelClient(api_key="YOUR_API_KEY")

# Pull the latest CRITICAL advisories
page = client.get_advisories(severity="CRITICAL", limit=10)
for advisory in page.items:
    print(f"{advisory.severity} — {advisory.title} (risk={advisory.risk_score})")

# Search across titles and descriptions
results = client.search_advisories("log4shell")

# Auto-paginate through everything matching a filter
for item in client.iter_advisories(severity="HIGH"):
    process(item)

# Look up a specific IOC (IP, hash, domain, or CVE)
match = client.lookup_ioc("CVE-2026-1234")

# Export a STIX 2.1 bundle for SIEM/SOAR ingestion (PRO+)
bundle = client.export_stix(severity="CRITICAL")
print(f"{bundle.object_count} STIX objects")

# Health check — no API key or quota consumed
assert client.ping()
```

## What's actually implemented

Every method below calls a real, live route on the deployed API — this SDK
does not paper over gaps with fabricated data:

| Method | What it does |
|---|---|
| `get_advisories(severity=, threat_type=, limit=, page=, kev_only=)` | Fetch the threat feed, filtered client-side |
| `get_advisory(stix_id)` | Look up a single advisory by ID |
| `search_advisories(query, limit=)` | Free-text search across titles/descriptions |
| `iter_advisories(...)` | Auto-paginating generator over `get_advisories` |
| `export_stix(stix_ids=, severity=, limit=, collection=)` | STIX 2.1 bundle via the real TAXII 2.1 server (PRO+) |
| `lookup_ioc(ioc, ioc_type="auto")` | Look up an IP, hash, domain, or CVE (PRO+) |
| `health()` / `ping()` | Platform health check — no API key required |
| `get_key_info()` | Your key's tier and validity |

`rotate_key()`, `get_ingestion_status()`, and `trigger_ingestion()` raise
`SDKConfigurationError` with an explanation — those aren't available
through the public API yet, and this SDK won't silently pretend they work.

## Tiers

| Tier | Price | What you get |
|---|---|---|
| **FREE** | $0 | Rate-limited public feed access, IOC lookup, health checks |
| **PRO** | $49/mo | Full feed depth, STIX/TAXII export, higher rate limits |
| **ENTERPRISE** | Custom | Highest limits, priority support |

[**See full pricing →**](https://intel.cyberdudebivash.com/pricing.html?ref=pypi_readme)

## Error handling

```python
from sentinel_sdk import (
    SentinelClient,
    AuthenticationError,
    RateLimitError,
    TierPermissionError,
    NotFoundError,
)

client = SentinelClient(api_key="YOUR_API_KEY")

try:
    bundle = client.export_stix(severity="CRITICAL")
except TierPermissionError as e:
    print(f"Upgrade to {e.required_tier} to use STIX export: https://intel.cyberdudebivash.com/pricing.html")
except RateLimitError as e:
    print(f"Rate limited — retry in {e.retry_after_s}s")
except AuthenticationError:
    print("Invalid or expired API key")
```

## Troubleshooting

**`AuthenticationError: Invalid or missing API key`**
Check your key at your [dashboard](https://intel.cyberdudebivash.com/pricing.html). Keys are passed as `api_key=` to `SentinelClient()`, never as an environment variable read implicitly by the SDK — pass it explicitly.

**`RateLimitError` on every other call**
You're on the FREE tier's shared rate limit. `RateLimitError.retry_after_s` tells you exactly how long to back off; for sustained higher throughput, [upgrade to PRO](https://intel.cyberdudebivash.com/pricing.html?ref=pypi_ratelimit) (5,000 requests/day vs. FREE's 50).

**`TierPermissionError` on `export_stix()` or `lookup_ioc()`**
Both require PRO or higher. The exception carries `required_tier` so you can build a precise upgrade prompt.

**Connection/timeout errors**
The client retries transient network errors and 5xx responses automatically (`max_retries=4` by default, exponential backoff). A `NetworkError` after that means the retries were exhausted — check your network or [status page](https://intel.cyberdudebivash.com/).

## Requirements

- Python ≥ 3.9
- Zero required dependencies (stdlib `urllib` only)
- Optional: `pip install sentinel-apex-sdk[requests]` for HTTP/2 and connection pooling

## License

Distributed under CyberDudeBivash Pvt. Ltd.'s commercial license — see
[`LICENSE.txt`](https://github.com/cyberdudebivash/sentinel-apex-sdk/blob/main/LICENSE.txt)
in the source repository for full terms.
