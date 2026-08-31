# OpenCTI Connector -- CYBERDUDEBIVASH(R) SENTINEL APEX

Pulls threat intelligence into OpenCTI via its built-in TAXII 2.1 connector,
pointed at this platform's real, live `/taxii/` server
(`workers/intel-gateway/src/index.js`'s `handleTAXII`, extended by
`taxii.js`'s collection registry and pagination) -- not a fabricated,
OpenCTI-specific endpoint.

## Prerequisites

- A running OpenCTI instance (this connector attaches to your existing
  `docker-compose.yml` stack -- it is not a standalone deployment).
- A Sentinel APEX API key. `/taxii/` requires PRO or ENTERPRISE at minimum;
  the `sentinel-apex-kev` and `apt-attribution` collections additionally
  require ENTERPRISE. Get a key at
  https://intel.cyberdudebivash.com/pricing.html

## Setup

1. Copy `docker-compose.yml`'s `connector-sentinel-apex-taxii` service block
   into your existing OpenCTI `docker-compose.yml`, alongside your other
   `opencti/connector-*` services.
2. `cp .env.sample .env` and fill in `OPENCTI_URL`, `OPENCTI_TOKEN`, and
   `SENTINEL_APEX_API_KEY`. Never commit the filled-in `.env`.
3. `docker compose up -d connector-sentinel-apex-taxii`
4. In the OpenCTI UI, confirm the connector under Data > Connectors --
   it should show as `CyberDudeBivash Sentinel APEX`, status `RUNNING`,
   after its first poll.

## Available collections

| Collection id | Contents | Minimum tier |
|---|---|---|
| `sentinel-apex-main` | CVEs, IOCs, APT activity, ransomware, dark-web findings | PRO |
| `c2-indicators` | Indicators tied to active malicious infrastructure | PRO |
| `active-ransomware` | Items classified Ransomware or attributed to a tracked ransomware operator | PRO |
| `sentinel-apex-kev` | CISA KEV-confirmed exploited vulnerabilities | ENTERPRISE |
| `apt-attribution` | Items classified APT or attributed to a tracked nation-state actor | ENTERPRISE |

Set `SENTINEL_APEX_TAXII_COLLECTIONS` in `.env` to a comma-separated subset
of the ids above. Default is the three PRO-accessible collections.

## Authentication note

`TAXII2_USERNAME` is set to a placeholder and ignored server-side --
`/taxii/`'s Basic-auth handling only reads the password half of the
`Authorization: Basic` header as the API key (this platform's keys are
single opaque tokens, not username+password pairs). Only
`SENTINEL_APEX_API_KEY` (mapped to `TAXII2_PASSWORD`) needs to be real.

## Troubleshooting

- **Connector shows an auth error / 401**: no key was resolved at all --
  double check `TAXII2_PASSWORD` is actually set from `SENTINEL_APEX_API_KEY`
  in your `.env`.
- **403 on a specific collection**: your key's tier doesn't clear that
  collection's minimum tier (see table above) -- either drop it from
  `TAXII2_COLLECTIONS` or upgrade.
- **Full API reference**: https://intel.cyberdudebivash.com/api-docs.html
