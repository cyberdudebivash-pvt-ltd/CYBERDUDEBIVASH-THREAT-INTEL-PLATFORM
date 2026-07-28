#!/usr/bin/env python3
"""
scripts/detect_repository_drift.py
CYBERDUDEBIVASH(R) SENTINEL APEX - Repository Drift Detector

Scans the repository for production-shaped components (Worker directories,
deploy-shaped GitHub Actions workflows, Cloudflare bindings, deployment-asset
files) and reports anything not already accounted for in
production_manifest.yaml or COMPONENT_REGISTRY.json.

This script REPORTS ONLY. It never modifies repository content, and it never
assigns a classification (production / legacy / experimental / etc.) to
anything it finds -- that judgment is left to a human, in a future batch,
with evidence. A finding here means "not yet documented," not "wrong."

Exit code is always 0 -- this is an informational report, not a pass/fail
gate (see scripts/validate_canonical_docs.py for the enforcing check).

Usage:
  python3 scripts/detect_repository_drift.py [--repo-root PATH]
"""
import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("FATAL: PyYAML is required. Run: pip install pyyaml")
    sys.exit(2)

DEPLOY_ASSET_GLOBS = ["Dockerfile*", "docker-compose*.yml", "railway.json", "Procfile"]
BINDING_LINE = re.compile(r'^\s*binding\s*=\s*"([^"]+)"', re.MULTILINE)


def load_manifest(root):
    with open(root / "production_manifest.yaml") as f:
        return yaml.safe_load(f)


def load_registry(root):
    with open(root / "COMPONENT_REGISTRY.json") as f:
        return json.load(f)


def registry_paths(registry):
    paths = set()
    for c in registry.get("components", []):
        for raw in str(c["path"]).split(","):
            p = raw.strip()
            if p and not p.startswith("("):
                paths.add(p)
    return paths


def find_undocumented_workers(root, manifest, findings):
    documented = {w["path"].rstrip("/") for w in manifest.get("production_workers", [])}
    workers_dir = root / "workers"
    if not workers_dir.is_dir():
        return
    for d in sorted(workers_dir.iterdir()):
        if d.is_dir():
            rel = f"workers/{d.name}"
            if rel not in documented:
                findings.append(f"Worker directory not in production_manifest.yaml's production_workers: {rel}")


def find_undocumented_deploy_workflows(root, manifest, findings):
    documented = {p["workflow"] for p in manifest.get("production_deployment_pipeline", [])}
    wf_dir = root / ".github" / "workflows"
    if not wf_dir.is_dir():
        return
    for f in sorted(wf_dir.glob("*.yml")):
        try:
            text = f.read_text(errors="replace")
        except Exception:
            continue
        if "wrangler deploy" in text:
            rel = f".github/workflows/{f.name}"
            if rel not in documented:
                findings.append(f"Workflow runs 'wrangler deploy' but is not in production_manifest.yaml's production_deployment_pipeline: {rel}")


def find_undocumented_bindings(root, manifest, findings):
    documented_kv = {ns["name"] for ns in manifest.get("production_storage", {}).get("kv_namespaces", [])}
    # production_manifest.yaml records D1/R2 by their resource name (e.g. "sentinel-apex-data",
    # "sentinel-crm"), not their wrangler.toml binding string (e.g. "INTEL_R2", "CRM_DB") -- these
    # known aliases bridge that gap rather than requiring the manifest schema to change.
    known_r2_bindings = {"INTEL_R2", "REPORTS_R2"}
    known_d1_bindings = {"CRM_DB"}

    for w in manifest.get("production_workers", []):
        wrangler = root / w["path"] / "wrangler.toml"
        if not wrangler.exists():
            continue
        text = wrangler.read_text(errors="replace")
        bindings = set(BINDING_LINE.findall(text))
        for b in bindings:
            if b in documented_kv or b in known_r2_bindings or b in known_d1_bindings:
                continue
            findings.append(f"Binding '{b}' in {w['path']}wrangler.toml not recognized against production_manifest.yaml's documented storage")


def _is_covered(rel, documented):
    # Exact match, or nested inside a documented directory path (which always
    # ends in "/" in this registry's convention).
    if rel in documented:
        return True
    return any(p.endswith("/") and rel.startswith(p) for p in documented)


def find_undocumented_deploy_assets(root, registry, findings):
    documented = registry_paths(registry)
    for pattern in DEPLOY_ASSET_GLOBS:
        for f in sorted(root.glob(pattern)):
            rel = f.name
            if not _is_covered(rel, documented):
                findings.append(f"Deployment-shaped file at repo root not referenced in COMPONENT_REGISTRY.json: {rel}")
        # Also check one level down, since some assets (e.g. deploy/docker-compose.yml) are nested.
        for f in sorted(root.glob(f"*/{pattern}")):
            rel = f"{f.parent.name}/{f.name}"
            if not _is_covered(rel, documented):
                findings.append(f"Deployment-shaped file not referenced in COMPONENT_REGISTRY.json: {rel}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Path to the repository root (default: current directory)")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()

    findings = []
    try:
        manifest = load_manifest(root)
    except Exception as e:
        print(f"FATAL: could not load production_manifest.yaml: {e}")
        sys.exit(2)
    try:
        registry = load_registry(root)
    except Exception as e:
        print(f"FATAL: could not load COMPONENT_REGISTRY.json: {e}")
        sys.exit(2)

    find_undocumented_workers(root, manifest, findings)
    find_undocumented_deploy_workflows(root, manifest, findings)
    find_undocumented_bindings(root, manifest, findings)
    find_undocumented_deploy_assets(root, registry, findings)

    print("=== Repository Drift Detection Report ===")
    print("(Findings are informational only. Nothing here is auto-classified.)")
    print()
    if not findings:
        print("No drift detected against the documented production surface.")
    else:
        print(f"{len(findings)} item(s) found, not yet reflected in canonical documentation:")
        for f in findings:
            print(f"  - {f}")
    sys.exit(0)  # always 0 -- see module docstring


if __name__ == "__main__":
    main()
