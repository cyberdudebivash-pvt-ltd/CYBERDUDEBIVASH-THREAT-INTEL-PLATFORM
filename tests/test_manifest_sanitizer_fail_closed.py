"""Exercise publication with missing/broken sanitizer dependencies in isolation."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("dependency", ["missing", "broken", "healthy"])
def test_publication_requires_working_sanitizer(tmp_path, dependency):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for name in ("generate_api_manifests.py", "severity_epss_truth.py"):
        shutil.copyfile(ROOT / "scripts" / name, scripts / name)
    sanitizer = scripts / "public_api_sanitizer.py"
    if dependency == "healthy":
        shutil.copyfile(ROOT / "scripts" / sanitizer.name, sanitizer)
    elif dependency == "broken":
        sanitizer.write_text("raise ImportError('dependency unavailable')\n")
    api = tmp_path / "api"
    api.mkdir()
    (api / "feed.json").write_text(json.dumps([{
        "id": "test-advisory", "title": "Evidence fixture", "severity": "HIGH",
        "timestamp": "2026-10-06T00:00:00Z", "report_url": "https://example.com/private",
    }]))
    out = api / "v1" / "intel"
    out.mkdir(parents=True)
    existing = out / "latest.json"
    existing.write_text('{"last_known_good":true}')
    result = subprocess.run([sys.executable, str(scripts / "generate_api_manifests.py")],
                            cwd=tmp_path, capture_output=True, text=True)
    if dependency != "healthy":
        assert result.returncode == 1
        assert "publication refused" in result.stderr
        assert existing.read_text() == '{"last_known_good":true}'
        assert list(out.iterdir()) == [existing]
        assert not (tmp_path / "reports").exists()
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        payload = json.loads(existing.read_text())
        assert payload["count"] == 1
        assert "report_url" not in payload["items"][0]
        assert (out / "latest_pro.json").exists()
