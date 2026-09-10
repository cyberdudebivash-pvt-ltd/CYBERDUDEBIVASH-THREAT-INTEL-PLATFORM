#!/usr/bin/env python3
"""
tests/test_pipeline_staleness_thresholds.py

P0 regression guard (2026-09-10): scripts/check_pipeline_staleness.py's
MONITORED_WORKFLOWS entries for sentinel-blogger.yml and status-monitor.yml
had alert thresholds tighter than -- in status-monitor's case, less than
half of -- the actual cron cadence of the workflow they monitor. That
guarantees the alert fires on a healthy platform: status-monitor.yml runs
3x/day (nominal 8h gaps) against a 3h threshold, so it read "STALE" for
5+ of every 8 hours, every day, regardless of whether anything was
actually wrong. sentinel-blogger.yml shared the same cron with a 8h
threshold -- zero margin for the scheduling jitter GitHub's own docs
warn cron workflows are subject to under load (confirmed empirically:
observed real gaps of 6h21m-9h31m against a nominal 8h).

This test parses each monitored workflow's OWN `.github/workflows/*.yml`
cron schedule (the same file check_pipeline_staleness.py names in
MONITORED_WORKFLOWS -- read directly, not duplicated by hand) and fails
if any configured max_age_hours provides less than a 1.3x safety margin
over that workflow's real maximum possible gap between scheduled fires.
This is deliberately mechanical rather than a fixed pin on today's values:
running it is what found that Automated Backup's existing 26h/24h margin
was equally undersized, alongside the two thresholds the original alert
named, and it also catches the same mistake being reintroduced later for
any of these rows, or made fresh for any row added in the future.
"""
import pathlib
import re
import sys
import unittest

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import check_pipeline_staleness as cps  # noqa: E402

# How much headroom a threshold must have over the real max scheduled gap.
# 1.3x tolerates real observed GitHub Actions scheduling jitter (see module
# docstring) without being so loose it stops catching genuine outages.
SAFETY_FACTOR = 1.3

# A "daily, fires at these UTC hours" cron: minute and hour fixed/listed,
# day-of-month/month/weekday all wildcards. Deliberately narrow: this is
# the only shape every workflow in MONITORED_WORKFLOWS actually uses for
# its recurring cadence (some also carry an additional monthly-only cron,
# e.g. sentinel-blogger's '0 0 1 * *' -- skipped here since an extra rarer
# firing can only shorten real-world gaps, never lengthen the recurring
# day-to-day one staleness detection cares about, so ignoring it is
# conservative, not a blind spot).
_DAILY_CRON_RE = re.compile(r"^(\d{1,2})\s+([\d,]+)\s+\*\s+\*\s+\*$")


def _daily_fire_hours(cron_expr: str) -> "set[int] | None":
    m = _DAILY_CRON_RE.match(cron_expr.strip())
    if not m:
        return None
    return {int(h) for h in m.group(2).split(",")}


def max_gap_hours_for_workflow(workflow_file: str) -> float:
    """The largest possible gap (hours) between this workflow's own
    scheduled fires, unioning every 'daily' cron entry it declares."""
    path = WORKFLOWS_DIR / workflow_file
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    on_block = doc.get(True, doc.get("on"))  # PyYAML parses bare `on:` as bool True
    schedules = (on_block or {}).get("schedule") or []

    hours: set[int] = set()
    for entry in schedules:
        found = _daily_fire_hours(entry.get("cron", ""))
        if found:
            hours |= found

    assert hours, (
        f"{workflow_file}: no recognisable daily 'M H,H,H * * *' cron schedule "
        f"found (schedules seen: {schedules}) -- this test's cron parser needs "
        f"extending before it can validate this workflow's threshold"
    )

    ordered = sorted(hours)
    gaps = [
        (ordered[i + 1] - ordered[i]) if i + 1 < len(ordered)
        else (24 - ordered[-1] + ordered[0])
        for i in range(len(ordered))
    ]
    return float(max(gaps))


class TestPipelineStalenessThresholds(unittest.TestCase):
    def test_threshold_has_real_safety_margin(self):
        for wf in cps.MONITORED_WORKFLOWS:
            if wf["max_age_hours"] == 0:
                continue  # deliberately exempt (push-triggered, not scheduled)

            max_gap = max_gap_hours_for_workflow(wf["file"])
            required = max_gap * SAFETY_FACTOR
            self.assertGreaterEqual(
                wf["max_age_hours"], required,
                f"{wf['name']} ({wf['file']}): max_age_hours={wf['max_age_hours']}h "
                f"gives less than the required {SAFETY_FACTOR}x margin over its own "
                f"real max scheduled gap ({max_gap}h, needs >= {required}h) -- this "
                f"threshold will false-alarm on a healthy pipeline, exactly the "
                f"2026-09-10 status-monitor/sentinel-blogger incident this test "
                f"guards against.",
            )

    def test_incident_values_fixed(self):
        """Pins this specific incident's three corrected values (found by
        running the general mechanical check above, not hand-picked), in
        addition to that general check."""
        by_file = {wf["file"]: wf for wf in cps.MONITORED_WORKFLOWS}
        self.assertEqual(by_file["status-monitor.yml"]["max_age_hours"], 16)
        self.assertEqual(by_file["sentinel-blogger.yml"]["max_age_hours"], 16)
        self.assertEqual(by_file["automated-backup.yml"]["max_age_hours"], 32)

    def test_cron_parser_reproduces_the_known_8h_cadence(self):
        """Sanity check on the parser itself, independent of the thresholds
        it is about to judge: both incident workflows share the exact cron
        this test's own analysis is built on."""
        self.assertEqual(max_gap_hours_for_workflow("status-monitor.yml"), 8.0)
        self.assertEqual(max_gap_hours_for_workflow("sentinel-blogger.yml"), 8.0)


if __name__ == "__main__":
    unittest.main()
