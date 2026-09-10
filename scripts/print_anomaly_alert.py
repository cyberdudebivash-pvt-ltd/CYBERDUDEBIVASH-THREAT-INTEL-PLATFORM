#!/usr/bin/env python3
# =============================================================================
# CYBERDUDEBIVASH(R) SENTINEL APEX
# scripts/print_anomaly_alert.py
# Extracted from storage-governance.yml (RULE 5 compliance)
# Reads anomaly report and triggers alert if anomalies detected.
#
# FIX (P0, 2026-09-10, operational-readiness audit): this script has always
# only ever print()'d to the job log -- no urllib/requests import, no
# network call anywhere -- despite storage-governance.yml's "Anomaly alert
# if detected" step injecting real TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID
# secrets into its environment. That's worse than an honest gap: the
# secrets being present creates false confidence a real alert fires when
# it structurally could not. Wired to the same send_telegram() this
# codebase already built and proven (scripts/pipeline_alert.py, used by
# enterprise-governance.yml/enterprise-rollback-governance.yml/
# self-healing.yml) -- reused unchanged, not re-implemented. Silent
# print-only behavior is preserved exactly when the secrets are absent
# (e.g. local/dry runs), matching this codebase's established
# skip-gracefully-if-unconfigured convention.
# =============================================================================
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from pipeline_alert import send_telegram  # noqa: E402

ar_path = pathlib.Path("data/telemetry/anomaly_report.json")
if not ar_path.exists():
    print("[ANOMALY] No anomaly report found -- platform nominal")
    sys.exit(0)

try:
    ar = json.loads(ar_path.read_text(encoding="utf-8"))
except Exception as e:
    print(f"[ANOMALY] Could not parse anomaly report: {e}")
    sys.exit(0)

total = ar.get("total_anomalies", 0)
if total > 0:
    print(f"[ANOMALY] {total} anomalies detected -- alerting ops")
    lines = [f"<b>SENTINEL APEX storage anomaly alert</b> -- {total} detected"]
    for a in ar.get("anomalies", []):
        severity = a.get("severity", "UNKNOWN")
        line = f"  [{severity}] {a.get('type', '')} {a.get('endpoint', '')}"
        print(line)
        lines.append(f"[{severity}] {a.get('type', '')} {a.get('endpoint', '')}")

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if token and chat_id:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        run_id = os.environ.get("GITHUB_RUN_ID", "")
        if repo and run_id:
            lines.append(f"https://github.com/{repo}/actions/runs/{run_id}")
        ok = send_telegram(token, chat_id, "\n".join(lines))
        print(f"[ANOMALY] Telegram alert {'sent' if ok else 'FAILED to send'}")
    else:
        print("[ANOMALY] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set -- alert logged here only")
else:
    print("[ANOMALY] No anomalies -- platform nominal")
