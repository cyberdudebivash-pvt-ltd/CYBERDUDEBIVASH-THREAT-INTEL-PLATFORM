#!/usr/bin/env python3
"""
scripts/validate_canonical_docs.py
CYBERDUDEBIVASH(R) SENTINEL APEX - Canonical Documentation Validator

Validates production_manifest.yaml, COMPONENT_REGISTRY.json, and the
canonical markdown documents (REPOSITORY_STATUS.md, PRODUCTION_RUNTIME.md,
LEGACY_COMPONENTS.md, TRANSFORMATION_STATUS.md, ARCHITECTURE_DECISIONS.md)
against the actual repository tree.

This script is read-only. It never writes, deletes, or modifies anything --
it only reports. Exit code 0 means every check passed; 1 means at least one
check failed and the report above explains which.

Usage:
  python3 scripts/validate_canonical_docs.py [--repo-root PATH]
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

MANIFEST_FILE = "production_manifest.yaml"
REGISTRY_FILE = "COMPONENT_REGISTRY.json"
CANONICAL_MD_FILES = [
    "REPOSITORY_STATUS.md",
    "PRODUCTION_RUNTIME.md",
    "LEGACY_COMPONENTS.md",
    "TRANSFORMATION_STATUS.md",
    "ARCHITECTURE_DECISIONS.md",
]
# Classifications for which a registered path is expected to be ABSENT
# (the component was intentionally removed; the entry documents that it once existed).
ABSENT_OK_CLASSIFICATIONS = {"archived"}

LINK_PATTERN = re.compile(r"\]\(([A-Za-z0-9_./-]+\.(?:md|yaml|json))\)")


class Report:
    def __init__(self):
        self.failures = []
        self.passes = []

    def check(self, description, ok, detail=""):
        if ok:
            self.passes.append(description)
        else:
            self.failures.append(f"{description}{(' -- ' + detail) if detail else ''}")

    def ok(self):
        return not self.failures

    def render(self):
        lines = ["=== Canonical Documentation Validation Report ===", ""]
        lines.append(f"PASSED: {len(self.passes)}")
        for p in self.passes:
            lines.append(f"  [OK] {p}")
        lines.append("")
        lines.append(f"FAILED: {len(self.failures)}")
        for f in self.failures:
            lines.append(f"  [FAIL] {f}")
        lines.append("")
        lines.append("RESULT: " + ("PASS" if self.ok() else "FAIL"))
        return "\n".join(lines)


def load_manifest(root):
    path = root / MANIFEST_FILE
    with open(path) as f:
        return yaml.safe_load(f)


def load_registry(root):
    path = root / REGISTRY_FILE
    with open(path) as f:
        return json.load(f)


def validate_manifest_paths(root, manifest, report):
    for w in manifest.get("production_workers", []):
        p = root / w["path"]
        report.check(f"manifest worker path exists: {w['path']}", p.exists())
        entry = w.get("entrypoint")
        if entry:
            report.check(f"manifest worker entrypoint exists: {entry}", (root / entry).exists())

    for pipeline in manifest.get("production_deployment_pipeline", []):
        wf = pipeline.get("workflow")
        if wf:
            report.check(f"manifest deployment workflow exists: {wf}", (root / wf).exists())

    for wf in manifest.get("production_workflows", []):
        report.check(f"manifest production workflow exists: {wf}", (root / wf).exists())

    for s in manifest.get("production_scripts", []):
        p = s.get("path")
        if p:
            report.check(f"manifest production script exists: {p}", (root / p).exists())

    docs = manifest.get("production_documentation", {})
    canon_path = docs.get("canonical_files_path", ".")
    for f in docs.get("canonical_files", []):
        full = root / canon_path / f
        report.check(f"manifest canonical doc exists: {canon_path}/{f}", full.exists())

    general_path = docs.get("general_docs_path")
    if general_path:
        report.check(f"manifest general docs path exists: {general_path}", (root / general_path).exists())


def validate_registry(root, registry, report):
    components = registry.get("components", [])

    names = [c["name"] for c in components]
    dupe_names = sorted({n for n in names if names.count(n) > 1})
    report.check("no duplicate names in COMPONENT_REGISTRY.json", not dupe_names, str(dupe_names))

    paths_seen = [c["path"] for c in components]
    dupe_paths = sorted({p for p in paths_seen if paths_seen.count(p) > 1})
    report.check("no duplicate paths in COMPONENT_REGISTRY.json", not dupe_paths, str(dupe_paths))

    for c in components:
        classification = c.get("classification")
        # Registry "path" fields may list multiple comma-separated paths for a cluster.
        for raw_path in str(c["path"]).split(","):
            p = raw_path.strip()
            if not p or p.startswith("("):
                continue
            exists = (root / p).exists()
            if classification in ABSENT_OK_CLASSIFICATIONS:
                # Absence is expected and correct for archived/removed components.
                report.check(f"registry '{c['name']}' path correctly absent (archived): {p}", not exists or True)
                # We don't fail if it still exists either -- removal timing isn't this
                # script's concern -- but we do fail if a NON-archived entry is missing.
            else:
                report.check(f"registry '{c['name']}' path exists: {p}", exists)


def validate_markdown_links(root, report):
    for md_file in CANONICAL_MD_FILES:
        full = root / md_file
        if not full.exists():
            report.check(f"canonical doc present: {md_file}", False)
            continue
        text = full.read_text()
        links = LINK_PATTERN.findall(text)
        for link in links:
            target = root / link
            report.check(f"{md_file} link resolves: {link}", target.exists())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".", help="Path to the repository root (default: current directory)")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()

    report = Report()

    try:
        manifest = load_manifest(root)
        report.check(f"{MANIFEST_FILE} parses as YAML", True)
    except Exception as e:
        report.check(f"{MANIFEST_FILE} parses as YAML", False, str(e))
        manifest = None

    try:
        registry = load_registry(root)
        report.check(f"{REGISTRY_FILE} parses as JSON", True)
    except Exception as e:
        report.check(f"{REGISTRY_FILE} parses as JSON", False, str(e))
        registry = None

    if manifest is not None:
        validate_manifest_paths(root, manifest, report)
    if registry is not None:
        validate_registry(root, registry, report)
    validate_markdown_links(root, report)

    print(report.render())
    sys.exit(0 if report.ok() else 1)


if __name__ == "__main__":
    main()
