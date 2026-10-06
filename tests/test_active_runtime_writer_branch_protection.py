import pathlib
import re

import yaml


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = {
    "status-monitor.yml": REPO_ROOT / ".github" / "workflows" / "status-monitor.yml",
    "weekly-analyst-briefing.yml": REPO_ROOT
    / ".github"
    / "workflows"
    / "weekly-analyst-briefing.yml",
}
PAGES_ACTION = (
    "JamesIves/github-pages-deploy-action@"
    "fa24774553152dd7873cd16ebd8d959b010c5445"
)


def _load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _run_bodies(doc):
    for job in (doc.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            run = step.get("run")
            if run:
                yield run


def _steps(doc):
    for job in (doc.get("jobs") or {}).values():
        yield from job.get("steps") or []


def test_active_runtime_writers_never_push_protected_main():
    for name, path in WORKFLOWS.items():
        body = "\n".join(_run_bodies(_load(path)))
        assert not re.search(
            r"git\s+push\s+origin\s+(?:main|HEAD(?::main)?)\b", body
        ), name
        assert not re.search(r"git\s+push\s+[^\n]*\bmain\b", body), name


def test_active_runtime_writers_use_commit_pinned_pages_publication():
    for name, path in WORKFLOWS.items():
        doc = _load(path)
        deploy_steps = [
            step for step in _steps(doc)
            if str(step.get("uses", "")).startswith(
                "JamesIves/github-pages-deploy-action@"
            )
        ]
        assert len(deploy_steps) == 1, name
        deploy = deploy_steps[0]
        assert deploy["uses"] == PAGES_ACTION, name
        with_args = deploy.get("with") or {}
        assert with_args.get("branch") == "gh-pages", name
        assert with_args.get("clean") is False, name
        assert with_args.get("single-commit") is False, name


def test_weekly_analyst_has_real_resource_scoped_concurrency():
    doc = _load(WORKFLOWS["weekly-analyst-briefing.yml"])
    concurrency = doc.get("concurrency") or {}
    assert concurrency.get("group") == "sentinel-data-writer-weekly-analyst"
    assert concurrency.get("cancel-in-progress") is False


def test_publication_staging_preserves_customer_paths():
    status = WORKFLOWS["status-monitor.yml"].read_text(encoding="utf-8")
    analyst = WORKFLOWS["weekly-analyst-briefing.yml"].read_text(encoding="utf-8")
    assert ".publish/data/status" in status
    assert "test -s data/status/status.json" in status
    assert ".publish/data/weekly_briefings" in analyst
    assert "find data/weekly_briefings -type f -size +0c" in analyst
