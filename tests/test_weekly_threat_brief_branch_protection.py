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



def test_weekly_threat_brief_publishes_api_json_through_budgeted_r2_path():
    doc = _load_workflow()
    steps = doc["jobs"]["generate-brief"].get("steps") or []
    r2_step = next(
        step for step in steps
        if step.get("name") == "STEP 7 — Publish Weekly Brief API JSON to canonical R2"
    )
    assert r2_step.get("run") == "python3 scripts/r2_upload.py --weekly-brief-only"
    env = r2_step.get("env") or {}
    assert "CF_ACCOUNT_ID" in env
    assert "AWS_ACCESS_KEY_ID" in env
    assert "AWS_SECRET_ACCESS_KEY" in env


def test_weekly_threat_brief_has_hard_live_api_release_verification():
    doc = _load_workflow()
    steps = doc["jobs"]["generate-brief"].get("steps") or []
    verify = next(
        step for step in steps
        if step.get("name") == "STEP 9 — Verify live Weekly Brief API"
    )
    assert verify.get("run") == "python3 scripts/verify_weekly_brief_live.py"
    assert verify.get("continue-on-error") is not True


def test_weekly_brief_r2_publisher_is_single_key_budgeted_and_fail_closed():
    source = (REPO_ROOT / "scripts" / "r2_upload.py").read_text(encoding="utf-8")
    assert 'WEEKLY_BRIEF_FILES: list[tuple[str, str]]' in source
    assert (
        '("api/v1/intel/weekly_brief.json", "api/v1/intel/weekly_brief.json")'
        in source
    )
    assert 'label="r2_upload_weekly_brief"' in source
    assert "enforce_budget(plan, budgets, is_report_plan=False)" in source
    assert 'elif "--weekly-brief-only" in sys.argv:' in source
    assert "main_weekly_brief_only()" in source

    build_plan = source.split("def build_upload_plan()", 1)[1].split(
        "def main()", 1
    )[0]
    assert "WEEKLY_BRIEF_FILES" not in build_plan
