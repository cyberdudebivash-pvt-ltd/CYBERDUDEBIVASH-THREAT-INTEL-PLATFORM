import pathlib
import re

import yaml


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "weekly-threat-brief.yml"


def _load_workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _run_bodies(doc):
    for job in (doc.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            run = step.get("run")
            if run:
                yield run


def test_weekly_threat_brief_never_pushes_protected_main():
    doc = _load_workflow()
    body = "\n".join(_run_bodies(doc))
    assert not re.search(r"git\s+push\s+origin\s+(?:main|HEAD(?::main)?)\b", body)
    assert not re.search(r"git\s+push\s+[^\n]*\bmain\b", body)


def test_weekly_threat_brief_keeps_shared_writer_concurrency():
    doc = _load_workflow()
    concurrency = doc.get("concurrency") or {}
    assert concurrency.get("group") == "sentinel-data-writer"
    assert concurrency.get("cancel-in-progress") is False


def test_weekly_threat_brief_pages_action_is_commit_pinned():
    doc = _load_workflow()
    steps = (doc["jobs"]["generate-brief"].get("steps") or [])
    deploy = next(step for step in steps if step.get("name") == "STEP 7 — Deploy brief to GitHub Pages")
    uses = deploy.get("uses", "")
    assert uses.startswith("JamesIves/github-pages-deploy-action@")
    ref = uses.split("@", 1)[1]
    assert re.fullmatch(r"[0-9a-f]{40}", ref)
