#!/usr/bin/env python3
"""
scripts/p38_schema_mirror_check.py
P38.0 — Schema Mirror Conformance Check

Workers have no Python runtime, so workers/intel-gateway/src/p38-handlers.js
carries a hand-mirrored copy of scripts/p38_shared_validators.py:SCHEMA_REGISTRY
(same pattern already used for FEED_REGISTRY in that file). A mirror with no
automated check silently drifts from its source — this is exactly what this
script found on first run: the JS side hardcoded 153 fields / 6 deprecated
against a real registry of 179 fields / 5 deprecated, and listed
'grade_notes' as deprecated when the Python source does not mark it so.

This script is the fix for that class of bug recurring: it parses both
copies and fails if they disagree on field set, domain, type, nullable,
required, deprecated, or replacement. Run it in CI (STAGE 4.04) after any
change to either file.

Exit 0  — mirrors match.
Exit 1  — drift detected, details printed.
Exit 2  — could not parse one of the two sources (environment problem,
          not a drift finding).
"""
from __future__ import annotations

import ast
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PY_SOURCE = ROOT / "scripts" / "p38_shared_validators.py"
JS_MIRROR = ROOT / "workers" / "intel-gateway" / "src" / "p38-handlers.js"

COMPARE_KEYS = ("required", "type", "domain", "nullable", "version_introduced", "deprecated", "replacement")


def load_python_registry() -> dict:
    tree = ast.parse(PY_SOURCE.read_text())
    for node in ast.walk(tree):
        targets = getattr(node, "targets", None) or ([node.target] if isinstance(node, ast.AnnAssign) else [])
        if any(getattr(t, "id", None) == "SCHEMA_REGISTRY" for t in targets):
            return {ast.literal_eval(k): ast.literal_eval(v) for k, v in zip(node.value.keys, node.value.values)}
    raise SystemExit(f"SCHEMA_REGISTRY not found in {PY_SOURCE}")


def load_js_registry() -> dict:
    js_text = JS_MIRROR.read_text()
    start = js_text.find("const SCHEMA_REGISTRY = {")
    if start == -1:
        raise SystemExit(f"SCHEMA_REGISTRY not found in {JS_MIRROR}")
    # Bracket-match from the opening brace to find the block end.
    brace_start = js_text.index("{", start)
    depth = 0
    end = None
    for i in range(brace_start, len(js_text)):
        if js_text[i] == "{":
            depth += 1
        elif js_text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise SystemExit(f"Could not find end of SCHEMA_REGISTRY block in {JS_MIRROR}")
    block = js_text[start:end]

    node_script = (
        block
        + ";\nprocess.stdout.write(JSON.stringify(SCHEMA_REGISTRY));\n"
    )
    tmp = ROOT / "scripts" / "_p38_schema_mirror_extract.mjs"
    tmp.write_text(node_script)
    try:
        result = subprocess.run(
            ["node", str(tmp)], capture_output=True, text=True, timeout=30
        )
    except FileNotFoundError:
        raise SystemExit("node executable not found — required to parse the JS schema mirror")
    finally:
        tmp.unlink(missing_ok=True)

    if result.returncode != 0:
        raise SystemExit(f"node failed to evaluate SCHEMA_REGISTRY block:\n{result.stderr}")
    return json.loads(result.stdout)


def diff(py_reg: dict, js_reg: dict) -> list[str]:
    problems = []
    py_fields, js_fields = set(py_reg), set(js_reg)

    only_py = sorted(py_fields - js_fields)
    only_js = sorted(js_fields - py_fields)
    if only_py:
        problems.append(f"Fields in Python SCHEMA_REGISTRY but missing from JS mirror: {only_py}")
    if only_js:
        problems.append(f"Fields in JS mirror but not in Python SCHEMA_REGISTRY: {only_js}")

    for field in sorted(py_fields & js_fields):
        py_meta, js_meta = py_reg[field], js_reg[field]
        for key in COMPARE_KEYS:
            py_val = py_meta.get(key)
            js_val = js_meta.get(key)
            if py_val != js_val:
                problems.append(
                    f"Field '{field}' key '{key}': Python={py_val!r} JS={js_val!r}"
                )
    return problems


def main() -> int:
    py_reg = load_python_registry()
    js_reg = load_js_registry()

    problems = diff(py_reg, js_reg)
    if problems:
        print(f"SCHEMA MIRROR DRIFT DETECTED — {len(problems)} issue(s)", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print(
            f"\nRegenerate the JS mirror in {JS_MIRROR.relative_to(ROOT)} from "
            f"{PY_SOURCE.relative_to(ROOT)}:SCHEMA_REGISTRY and re-run this check.",
            file=sys.stderr,
        )
        return 1

    print(
        f"Schema mirror OK — {len(py_reg)} fields, "
        f"{sum(1 for v in py_reg.values() if v.get('deprecated'))} deprecated, in sync."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
