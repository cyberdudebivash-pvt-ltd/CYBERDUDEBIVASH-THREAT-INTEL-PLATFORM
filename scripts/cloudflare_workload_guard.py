#!/usr/bin/env python3
"""Read-only guard against unreviewed Cloudflare workload configuration drift."""
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "config/cloudflare_worker_workload_baseline.json"
# Source/runtime release metadata is allowed to evolve. Resource configuration
# and schedules are pinned separately; vars have existing activation gates.
METADATA = {"name", "main", "compatibility_date", "compatibility_flags", "vars", "env", "migrations"}

def signature(config):
    result = {"default": {k: v for k, v in config.items() if k not in METADATA}}
    result["environments"] = {
        name: {k: v for k, v in values.items() if k not in METADATA}
        for name, values in config.get("env", {}).items()
    }
    return result

def configuration_paths(root):
    return sorted(p.relative_to(root).as_posix()
                  for p in (root / "workers").rglob("wrangler.*")
                  if p.suffix in {".toml", ".json", ".jsonc"}
                  and "node_modules" not in p.parts)

def check(root=ROOT):
    root = Path(root)
    baseline = json.loads((root / BASELINE).read_text())
    if baseline.get("schema_version") != 1:
        raise ValueError("Unsupported workload baseline schema")
    expected = baseline["workers"]
    actual = configuration_paths(root)
    errors = []
    if set(actual) != set(expected):
        errors.append("Worker inventory changed; review new/removed configurations and account headroom")
    for name in actual:
        if name not in expected:
            continue
        if not name.endswith(".toml"):
            errors.append(f"{name}: unsupported config format; explicit review required")
            continue
        config = tomllib.loads((root / name).read_text())
        if signature(config) != expected[name]:
            errors.append(f"{name}: resource/schedule configuration changed; usage review required")
    return errors

def main():
    try:
        errors = check()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"FAIL: workload baseline unavailable or invalid: {error}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASS: Worker inventory and resource/schedule configuration match the reviewed baseline")
    print("This static check does not certify live account usage or remaining plan headroom.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

