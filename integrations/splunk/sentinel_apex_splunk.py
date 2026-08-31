#!/usr/bin/env python3
"""CYBERDUDEBIVASH(R) SENTINEL APEX -- Splunk Threat Intelligence Connector.

Pulls from the REAL, live, Enterprise-gated GET /api/siem/splunk endpoint
(workers/intel-gateway/src/enterprise-endpoints.js, handleSiemSplunk) --
not a re-derivation of feed data, the exact NDJSON that endpoint already
builds for Splunk HEC ingestion. Requires a Sentinel APEX ENTERPRISE (or
MSSP) API key; PRO/FREE keys receive a 403 from the API itself.

Two usage modes:

1. Splunk Modular Input (recommended for Splunk ES real-time ingestion).
   Drop this file into $SPLUNK_HOME/etc/apps/sentinel_apex/bin/, add an
   inputs.conf stanza:

       [sentinel_apex_splunk://main]
       python.version = python3
       api_key = cdb_ent_...
       interval = 300
       index = threat_intel

   Splunk invokes this script with no arguments and an XML config document
   on stdin per the Splunk modular input protocol; it streams <event> XML
   to stdout, which Splunk indexes directly. No CSV/KV store step needed
   for this path.

2. Standalone KV Store lookup export (for Splunk Enterprise Security's
   Threat Intelligence framework, which consumes indicator data via a CSV
   KV store lookup rather than a live stream):

       python3 sentinel_apex_splunk.py --export-csv threat_intel.csv \\
           --api-key cdb_ent_...

   threat_intel.csv uses ES's generic Threat Intelligence add-on schema
   (threat_key, type, weight, description, source, first_seen) -- see
   https://docs.splunk.com/Documentation/ES for the KV store's expected
   fields. One row per IOC value found in each event's `iocs` field --
   NOT one row per event, since ES threat intel lookups match on
   individual indicator values, not whole reports.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

API_BASE = "https://intel.cyberdudebivash.com"
SIEM_SPLUNK_PATH = "/api/siem/splunk"


def fetch_ndjson_events(api_key: str, limit: int = 500, base_url: str = API_BASE) -> list[dict]:
    """Calls the real /api/siem/splunk endpoint and parses its NDJSON body.

    Raises RuntimeError with a clear, actionable message on a 403 (wrong
    tier) or any other non-200 response -- never silently returns an empty
    list, which would look like "no threats today" instead of "this key
    can't reach this endpoint."
    """
    url = f"{base_url}{SIEM_SPLUNK_PATH}?limit={int(limit)}"
    req = urllib.request.Request(url, headers={"X-API-Key": api_key, "Accept": "application/x-ndjson"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        if e.code == 403:
            raise RuntimeError(
                "403 Forbidden: /api/siem/splunk requires a SENTINEL APEX ENTERPRISE "
                "(or MSSP) API key. Upgrade at https://intel.cyberdudebivash.com/pricing.html"
            ) from None
        raise RuntimeError(f"HTTP {e.code} from {url}: {detail[:500]}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach {url}: {e.reason}") from None

    events = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a malformed line must not abort the whole ingest
    return events


def events_to_kv_rows(events: list[dict]) -> list[dict]:
    """Expands each event's `iocs` list into one Splunk ES KV-store-ready row per indicator."""
    rows = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for ev in events:
        e = ev.get("event", {})
        weight = e.get("apex_enterprise_score") or e.get("risk_score") or 0
        base = {
            "type": (e.get("severity") or "unknown").lower(),
            "weight": weight,
            "description": (e.get("title") or "")[:512],
            "source": "sentinel-apex",
            "first_seen": now_iso,
            "sentinel_id": e.get("id", ""),
            "sentinel_actor": e.get("actor") or "",
            "sentinel_cve_ids": ";".join(e.get("cve_ids") or []),
        }
        iocs = e.get("iocs") or []
        if not iocs:
            # No extracted indicator -- still worth a row keyed on the CVE
            # (or the report id as a last resort) so CVE-only advisories
            # aren't silently dropped from the lookup.
            key = (e.get("cve_ids") or [None])[0] or e.get("id") or ""
            if key:
                rows.append({"threat_key": key, **base})
            continue
        for ioc in iocs:
            if ioc:
                rows.append({"threat_key": ioc, **base})
    return rows


CSV_FIELDS = [
    "threat_key", "type", "weight", "description", "source",
    "first_seen", "sentinel_id", "sentinel_actor", "sentinel_cve_ids",
]


def write_kv_csv(rows: list[dict], out_path: str) -> None:
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


# -- Splunk Modular Input protocol --------------------------------------------

def _read_stdin_config() -> dict:
    """Minimal modular-input stdin XML parser: extracts <param name="...">value</param>."""
    import re

    raw = sys.stdin.read()
    config = {}
    for m in re.finditer(r'<param name="([^"]+)">([^<]*)</param>', raw):
        config[m.group(1)] = m.group(2)
    return config


def _xml_escape(s: str) -> str:
    return (
        str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def run_modular_input() -> None:
    config = _read_stdin_config()
    api_key = config.get("api_key", "")
    index = config.get("index", "threat_intel")
    if not api_key:
        print("Sentinel APEX modular input: missing api_key stanza parameter", file=sys.stderr)
        sys.exit(1)

    try:
        events = fetch_ndjson_events(api_key)
    except RuntimeError as e:
        print(f"Sentinel APEX modular input: {e}", file=sys.stderr)
        sys.exit(1)

    print("<stream>")
    for ev in events:
        ts = ev.get("time", int(datetime.now(timezone.utc).timestamp()))
        raw = _xml_escape(json.dumps(ev.get("event", {})))
        print(
            f'<event><time>{ts}</time><index>{_xml_escape(index)}</index>'
            f'<sourcetype>sentinel:apex:threat_intel</sourcetype>'
            f'<source>sentinel-apex</source><data>{raw}</data></event>'
        )
    print("</stream>")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--export-csv", metavar="PATH", help="Write a Splunk ES KV-store threat_intel.csv lookup instead of running as a modular input")
    parser.add_argument("--api-key", help="Sentinel APEX ENTERPRISE/MSSP API key (required with --export-csv)")
    parser.add_argument("--limit", type=int, default=500, help="Max events to pull (server caps at 500)")
    parser.add_argument("--base-url", default=API_BASE, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.export_csv:
        if not args.api_key:
            parser.error("--export-csv requires --api-key")
        events = fetch_ndjson_events(args.api_key, args.limit, args.base_url)
        rows = events_to_kv_rows(events)
        write_kv_csv(rows, args.export_csv)
        print(f"Wrote {len(rows)} KV lookup rows from {len(events)} events -> {args.export_csv}")
        return

    # No --export-csv: assume we were invoked as a Splunk modular input
    # (Splunk always calls with no args and an XML config on stdin).
    run_modular_input()


if __name__ == "__main__":
    main()
