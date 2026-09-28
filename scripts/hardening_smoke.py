"""Isolated engine smoke evidence. This is not production certification.

Every invocation gets an empty working directory: tracked reports can never
make a failed run appear successful, and synthetic tenants never reach data/.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def quality():
    from agent.dossier_quality_engine import DossierQualityEngine
    result = DossierQualityEngine().process_advisory({
        "id": "ci-smoke-only", "title": "Synthetic quality fixture",
        "description": "Synthetic advisory for engine execution checks only.",
        "iocs": {}, "mitre_attack": [],
    })
    if result.grade not in {"A", "B", "C", "D", "F"}:
        raise ValueError("Invalid quality grade")
    return {"grade": result.grade, "iocs_suppressed": result.ioc_suppression.suppressed_count}


def tenant():
    from agent.enterprise_tenant_isolation_engine import EnterpriseTenantIsolationEngine
    engine = EnterpriseTenantIsolationEngine()
    engine.register_tenant("ci-free", "free@test.invalid", "free")
    engine.register_tenant("ci-ent", "enterprise@test.invalid", "enterprise")
    cases = [("ci-free", "read:preview", True), ("ci-free", "read:stix", False),
             ("ci-ent", "read:stix", True), ("missing", "read:feed", False)]
    for tid, permission, expected in cases:
        if engine.gate_request(tid, permission, "/ci-smoke", "127.0.0.1").allowed != expected:
            raise ValueError(f"Tenant permission decision mismatch: {tid}/{permission}")
    engine.generate_report()
    return read_object(Path("data/tenant/tenant_isolation_report.json"))


def monetization():
    from agent.enterprise_monetization_analytics_engine import EnterpriseMonetizationAnalyticsEngine
    engine = EnterpriseMonetizationAnalyticsEngine(output_dir="data/monetization/ci_validation")
    engine.run_full_pipeline({"ci-free": "free", "ci-pro": "pro"}, {}, {})
    return read_object(Path("data/monetization/ci_validation/monetization_report.json"))


def read_object(path):
    def reject_constant(value):
        raise ValueError(f"Non-finite JSON number: {value}")
    value = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    if not isinstance(value, dict) or not value:
        raise ValueError(f"Expected nonempty JSON object: {path}")
    return value


def run(output, enabled, runners=None):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError("Smoke evidence must be outside the repository")
    # Refuse to overwrite or mix with evidence from a previous invocation.
    output.mkdir(parents=True, exist_ok=False)
    runners = runners if runners is not None else {
        "quality": quality, "tenant": tenant, "monetization": monetization,
    }
    manifest = {"schema_version": 1, "evidence_type": "synthetic_engine_smoke",
                "production_certified": False, "source_sha": os.environ.get("GITHUB_SHA"),
                "generated_at": datetime.now(timezone.utc).isoformat(), "phases": {}}
    previous = Path.cwd()
    try:
        with tempfile.TemporaryDirectory(prefix="cdb-engine-smoke-") as work:
            os.chdir(work)
            for name, runner in runners.items():
                if not enabled.get(name, False):
                    manifest["phases"][name] = {"status": "skipped"}
                    continue
                try:
                    result = runner()
                    if not isinstance(result, dict) or not result:
                        raise ValueError("Phase returned no evidence")
                    path = output / f"{name}.json"
                    path.write_text(json.dumps({"synthetic": True, "result": result},
                                              indent=2, allow_nan=False), encoding="utf-8")
                    read_object(path)
                    manifest["phases"][name] = {"status": "passed", "artifact": path.name}
                except Exception as exc:
                    # The report retains failure type only; no secrets or arbitrary
                    # exception contents are copied into downloadable evidence.
                    manifest["phases"][name] = {"status": "failed", "error_type": type(exc).__name__}
    finally:
        os.chdir(previous)
    states = [p["status"] for p in manifest["phases"].values()]
    manifest["status"] = "failed" if "failed" in states or "passed" not in states else "passed"
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0 if manifest["status"] == "passed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    for phase in ("quality", "tenant", "monetization"):
        parser.add_argument(f"--{phase}", choices=("true", "false"), default="true")
    args = parser.parse_args()
    return run(args.output, {p: getattr(args, p) == "true" for p in ("quality", "tenant", "monetization")})


if __name__ == "__main__":
    sys.exit(main())
