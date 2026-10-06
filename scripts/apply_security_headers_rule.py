#!/usr/bin/env python3
"""
scripts/apply_security_headers_rule.py
CYBERDUDEBIVASH(R) SENTINEL APEX -- apply the static-site security headers rule
==================================================================================
The static site (GitHub Pages behind Cloudflare) serves every page, checkout
included, with HSTS only: no X-Frame-Options / CSP frame-ancestors, no
X-Content-Type-Options, Referrer-Policy or Permissions-Policy (verified live
2026-09-28). cloudflare/security_headers_transform_rule.json is the fix; this
script applies it through the Cloudflare Rulesets API without disturbing any
other rule, and verifies the result on the live site.

Modes (argv[1]):
  plan    read the zone's http_response_headers_transform entrypoint and print
          the rule list that apply would write. Changes nothing.
  apply   back up the current entrypoint to --backup, upsert ONLY our rule
          (matched by RULE_KEY description prefix; replaced in place, else
          appended), preserve every other rule and its order, PUT, then verify.
  verify  check live response headers only (no token needed).

Env: CF_API_TOKEN (Zone:Read + Zone Transform Rules:Edit) for plan/apply.
Exit codes: 0 ok, 1 verification/API failure, 2 usage error.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RULE_FILE = REPO / "cloudflare" / "security_headers_transform_rule.json"
API = "https://api.cloudflare.com/client/v4"
PHASE = "http_response_headers_transform"
ZONE_NAME = "cyberdudebivash.com"
HOST = "https://intel.cyberdudebivash.com"
RULE_KEY = "Security headers on static pages"

# Fields Cloudflare accepts for a rule in a ruleset PUT; read-only fields
# (version, last_updated, ...) returned by GET are dropped.
RULE_FIELDS = ("id", "ref", "expression", "action", "action_parameters", "description", "enabled", "logging")

# Static pages (checkout and key pages first) must carry the rule's headers.
STATIC_PAGES = ("/", "/upgrade.html", "/get-api-key.html", "/pricing.html", "/api-key-manager.html")
# Worker-served paths must keep their own headers, untouched by the rule.
WORKER_PATHS = {"/api/watchdog/health": "DENY", "/reports/": "DENY"}


def load_rule() -> dict:
    return json.loads(RULE_FILE.read_text(encoding="utf-8"))["ruleset"]["rules"][0]


def clean_rule(rule: dict) -> dict:
    return {k: rule[k] for k in RULE_FIELDS if k in rule}


def merge_rules(existing: list[dict], ours: dict) -> list[dict]:
    """Upsert `ours` into `existing` by RULE_KEY description prefix.

    Every other rule is kept, in order, unchanged (minus read-only fields).
    An existing rule of ours is replaced in place and keeps its id, so the
    update is a modification, not a delete-and-create. More than one existing
    rule of ours is ambiguous and refused rather than guessed at.
    """
    ours = clean_rule(ours)
    mine = [i for i, r in enumerate(existing) if str(r.get("description", "")).startswith(RULE_KEY)]
    if len(mine) > 1:
        raise ValueError(f"{len(mine)} existing rules start with {RULE_KEY!r}; resolve by hand")
    merged = [clean_rule(r) for r in existing]
    if mine:
        i = mine[0]
        if "id" in merged[i]:
            ours = {"id": merged[i]["id"], **ours}
        merged[i] = ours
    else:
        merged.append(ours)
    return merged


def expected_headers(rule: dict) -> dict[str, str]:
    return {k.lower(): v["value"] for k, v in rule["action_parameters"]["headers"].items()}


def _api(method: str, path: str, token: str, body: dict | None = None):
    req = urllib.request.Request(
        API + path, method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read() or b"{}")
        except ValueError:
            payload = {}
        return e.code, payload


def _zone_id(token: str) -> str:
    status, body = _api("GET", f"/zones?name={ZONE_NAME}", token)
    if status != 200 or not body.get("result"):
        raise RuntimeError(f"zone lookup failed ({status}): {body.get('errors')}")
    return body["result"][0]["id"]


def _entrypoint(token: str, zone: str) -> list[dict]:
    status, body = _api("GET", f"/zones/{zone}/rulesets/phases/{PHASE}/entrypoint", token)
    if status == 404:
        return []  # no response-header rules on the zone yet
    if status != 200:
        raise RuntimeError(f"reading {PHASE} entrypoint failed ({status}): {body.get('errors')}")
    return body["result"].get("rules", [])


def _headers(url: str) -> tuple[int, dict[str, str]]:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "cdb-security-headers-verify/1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}


def verify(rule: dict, attempts: int = 6, wait: float = 10.0) -> bool:
    want = expected_headers(rule)
    for attempt in range(1, attempts + 1):
        problems = []
        for path in STATIC_PAGES:
            status, got = _headers(HOST + path)
            for name, value in want.items():
                if got.get(name) != value:
                    problems.append(f"{path}: {name} = {got.get(name)!r}, want {value!r}")
        for path, xfo in WORKER_PATHS.items():
            _, got = _headers(HOST + path)
            if got.get("x-frame-options") != xfo:
                problems.append(f"{path}: Worker header x-frame-options = {got.get('x-frame-options')!r}, want {xfo!r} (rule must not touch it)")
        if not problems:
            print(f"verify: PASS ({len(STATIC_PAGES)} static pages carry the headers; Worker paths untouched)")
            return True
        print(f"verify attempt {attempt}/{attempts}: {len(problems)} problem(s)")
        for p in problems:
            print("  -", p)
        if attempt < attempts:
            time.sleep(wait)
    return False


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ("plan", "apply", "verify"):
        print(__doc__)
        return 2
    mode = argv[1]
    rule = load_rule()
    if mode == "verify":
        return 0 if verify(rule, attempts=1) else 1

    token = os.environ.get("CF_API_TOKEN", "")
    if not token:
        print("CF_API_TOKEN is not set")
        return 2
    zone = _zone_id(token)
    existing = _entrypoint(token, zone)
    merged = merge_rules(existing, rule)
    others = [r.get("description", r.get("id", "?")) for r in existing if not str(r.get("description", "")).startswith(RULE_KEY)]
    print(f"zone {ZONE_NAME}: {len(existing)} existing {PHASE} rule(s); {len(others)} unrelated rule(s) preserved: {others}")
    print(json.dumps(merged, indent=2))
    if mode == "plan":
        return 0

    backup = Path(argv[argv.index("--backup") + 1]) if "--backup" in argv else Path("security-headers-entrypoint-backup.json")
    backup.write_text(json.dumps({"zone": ZONE_NAME, "phase": PHASE, "rules": existing}, indent=2), encoding="utf-8")
    print(f"backup of the current entrypoint written to {backup}")
    status, body = _api("PUT", f"/zones/{zone}/rulesets/phases/{PHASE}/entrypoint", token, {"rules": merged})
    if status != 200:
        print(f"PUT failed ({status}): {body.get('errors')}")
        return 1
    print("rule applied")
    return 0 if verify(rule) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
