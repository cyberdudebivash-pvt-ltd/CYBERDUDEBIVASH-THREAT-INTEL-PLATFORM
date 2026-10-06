# SENTINEL APEX — SIEM / TAXII Integration Guide

**Version:** v1.0.0
**Status:** Production
**Base URL:** `https://intel.cyberdudebivash.com`

---

## What this is

SENTINEL APEX runs a real, live **TAXII 2.1** server. A SIEM that speaks
TAXII — Microsoft Sentinel and Splunk both do — can poll it directly for
structured threat data (STIX 2.1 indicators, malware, attack-pattern, tool,
and threat-actor objects) without any custom parsing.

This guide covers the TAXII feed only. A native Splunk app, a Sentinel Data
Connector package, and SOAR playbook actions are not built yet — see
[developer-portal-guide.md](developer-portal-guide.md) for what's still
"Coming Soon." Everything below is live today.

---

## Authentication and tier

TAXII discovery (`GET /taxii/` and `GET /taxii`) is public — no key needed,
per the TAXII 2.1 spec. Everything past discovery (collections and their
objects) requires a **PRO or ENTERPRISE** API key, sent the same way as
every other endpoint:

```
Authorization: Bearer sa_YOUR_API_KEY_HERE
```

See [api-auth-guide.md](api-auth-guide.md) for how to get a key. The CISA
KEV collection specifically requires **ENTERPRISE**; PRO callers see it
listed with `can_read: false`.

---

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/taxii/` | none | Server discovery document |
| GET | `/taxii/collections/` | PRO/ENTERPRISE | List available collections |
| GET | `/taxii/collections/{id}/objects/` | PRO/ENTERPRISE (ENTERPRISE for KEV) | STIX 2.1 objects in a collection |

Collection IDs:

| ID | Contents | Minimum tier |
|---|---|---|
| `sentinel-apex-main` | CVEs, IOCs, APT activity, ransomware alerts, dark web findings | PRO |
| `sentinel-apex-kev` | CISA Known Exploited Vulnerabilities (confirmed) | ENTERPRISE |

Responses are `Content-Type: application/taxii+json;version=2.1` for
discovery/collections and `application/stix+json;version=2.1` for the
objects feed.

### Quick verification

```bash
# 1. Discovery -- no auth
curl -s https://intel.cyberdudebivash.com/taxii/ | python3 -m json.tool

# 2. Collections -- requires a key
curl -s -H "Authorization: Bearer sa_YOUR_KEY" \
  https://intel.cyberdudebivash.com/taxii/collections/ | python3 -m json.tool

# 3. Objects
curl -s -H "Authorization: Bearer sa_YOUR_KEY" \
  https://intel.cyberdudebivash.com/taxii/collections/sentinel-apex-main/objects/ \
  | python3 -m json.tool
```

A 401 here follows the same troubleshooting steps as every other endpoint —
see [api-auth-guide.md's 401 section](api-auth-guide.md#401-unauthorized--troubleshooting).

---

## Microsoft Sentinel

Sentinel has a native **Threat Intelligence – TAXII** data connector
(Content hub → "Threat Intelligence - TAXII", or the older
`ThreatIntelligenceTaxii` connector).

1. In the Sentinel workspace, open **Content hub**, install/enable **Threat
   Intelligence - TAXII**.
2. Add a new TAXII server with:
   - **API Root**: `https://intel.cyberdudebivash.com/taxii/`
   - **Collection ID**: `sentinel-apex-main` (add a second connector instance
     for `sentinel-apex-kev` if your tier is ENTERPRISE)
   - **Username**: leave blank (this feed doesn't use TAXII Basic Auth)
   - **Password / API key field**: paste your `sa_...` key — the connector
     sends whatever's in this field as the request's bearer/API credential
   - **Polling frequency**: hourly is a reasonable start; the feed itself
     updates on the platform's normal sync cadence (see
     [SLA.md](SLA.md) for tier-specific feed latency)
3. Save, then check **Threat Intelligence** → **Indicators** in Sentinel a
   few minutes after the first poll to confirm objects are landing.

If the connector's credential field doesn't accept a raw bearer token,
use its "custom header" option (where available) to send
`Authorization: Bearer sa_YOUR_KEY` explicitly — the server only checks
the header, not which UI field it came from.

---

## Splunk

Splunk doesn't ship TAXII support in core; use the
[TAXII Connector for Splunk](https://splunkbase.splunk.com/) app (or
`splunk-taxii-connector` community app) or the equivalent Splunk SOAR TAXII
Poller if you're on Splunk SOAR / Phantom.

1. Install the TAXII connector app on a search head or heavy forwarder.
2. Configure a new TAXII 2.1 server input:
   - **Discovery URL**: `https://intel.cyberdudebivash.com/taxii/`
   - **Collection**: `sentinel-apex-main` (and `sentinel-apex-kev` for
     ENTERPRISE)
   - **Auth type**: HTTP header / bearer token
   - **Header value**: `Authorization: Bearer sa_YOUR_KEY`
3. Set the polling interval and target index, then save.
4. Verify with `index=<your_index> sourcetype=stix*` after the first poll.

If your specific TAXII app only supports HTTP Basic Auth, put the key as
the password with the username left empty — some connectors translate that
into an `Authorization: Bearer <password>` header; check the app's own docs
for its exact auth-mapping behavior before relying on this.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `401` on `/taxii/collections/` but `/taxii/` works | Missing/invalid key, or FREE tier | Confirm the connector is actually sending `Authorization: Bearer sa_...` (not just configured with the key in some other field), and confirm your tier is PRO or ENTERPRISE |
| `sentinel-apex-kev` shows `can_read: false` | Tier is PRO, not ENTERPRISE | KEV requires ENTERPRISE; contact `bivashnayak.ai007@gmail.com` per [api-auth-guide.md](api-auth-guide.md) |
| Objects feed returns fewer than expected | Inline fallback bundle caps at 200 objects when a pre-built R2 bundle isn't yet available for that collection | Retry after the next platform sync cycle, or reduce polling interval expectations to match [SLA.md](SLA.md) |
| Connector reports a schema/parse error | Confirm your TAXII app expects TAXII **2.1** (not 2.0 — the response shapes differ) | Upgrade the connector/app to a 2.1-compatible version |

---

## Changelog

- **v1.0.0** (2026-08-20): Initial SIEM/TAXII integration guide — fills the
  documented-but-unguided ENTERPRISE "SIEM integration" feature referenced
  in [api-auth-guide.md](api-auth-guide.md).
