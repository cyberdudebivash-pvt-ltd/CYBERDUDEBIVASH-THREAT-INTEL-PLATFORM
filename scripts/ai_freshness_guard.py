#!/usr/bin/env python3
"""
===============================================================================
CYBERDUDEBIVASH(R) SENTINEL APEX
scripts/ai_freshness_guard.py -- AI ARTIFACT FRESHNESS GUARD (SSOT)
===============================================================================
INCIDENT THIS MODULE EXISTS TO PREVENT
--------------------------------------
Forensic audit (2026-09-09) of the APEX AI plane found that the public,
premium-gated "AI Cyber Brain" endpoint api/v1/intel/ai_summary.json was
republishing AI artifacts produced by pipelines that had not run in months,
under a freshly-stamped `generated_at`:

    data/ai_predictions/anomalies.json          2026-05-04   (128 days old)
    data/ai_predictions/forecasts.json          2026-05-04   (128 days old)
    data/ai_predictions/predictions_summary.json 2026-05-04  (128 days old)
    data/ai_predictions/apex_forecast_latest.json 2026-04-04 (158 days old)
    data/ai/anomaly_radar.json                  2026-05-05   (127 days old)

scripts/ai_brain_publisher.py checked only `is not None` (file presence) and
never file age, so a dead upstream producer was indistinguishable from a
healthy one. The regression suite had the same blind spot: T13 validated the
anomaly radar's *schema* and passed on a 127-day-old artifact.

Presence is not freshness. This module is the single place in the platform
that decides how old an AI artifact is and what that means -- Engineering
Constitution Principle 3 (Single Source of Truth) and Principle 7
(Observable Everything).

DESIGN CONTRACT
---------------
  * ZERO external dependencies (stdlib only) -- runs in every CI job.
  * DETERMINISTIC -- same artifact + same `now` produces the same verdict.
  * NON-RAISING -- assess() never throws; an unreadable artifact is reported
    as UNREADABLE, never as fresh. Fail closed, never fail open.
  * READ-ONLY -- this module never mutates or deletes an artifact. Callers
    decide what to do with a verdict.
  * ADDITIVE -- introduces no change to any existing artifact schema.

FRESHNESS STATES (ordered worst -> best by `severity_rank`)
-----------------------------------------------------------
  MISSING     -- artifact does not exist on disk
  UNREADABLE  -- artifact exists but is not parseable JSON
  UNDATED     -- artifact parsed but carries no recognisable timestamp
  EXPIRED     -- age > expire_hours; MUST NOT be published as current intel
  STALE       -- age > stale_hours; publishable but MUST be labelled degraded
  FRESH       -- age <= stale_hours; publishable as current intelligence

TIMESTAMP DISCOVERY
-------------------
Artifacts across this platform use several timestamp key spellings
(`generated_at`, `forecast_timestamp`, `last_updated`, ...). assess() checks
TIMESTAMP_KEYS in order at the JSON root. A list-rooted artifact is checked
via its first element. If no key matches, the verdict is UNDATED -- the
filesystem mtime is deliberately NOT used as a fallback, because a git
checkout rewrites mtime to checkout time and would make every stale artifact
look seconds old in CI. That is the exact failure mode this module prevents.

(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved. CONFIDENTIAL.
===============================================================================
"""
# NOTE: deliberately no `from __future__ import annotations` here.
# It makes every annotation a string, and @dataclass then resolves those via
# sys.modules[cls.__module__] -- which is None when a caller loads this file
# through importlib.util.spec_from_file_location() without registering it in
# sys.modules first, raising AttributeError at import time. Several tools in
# this repository (scripts/regression_tests.py among them) load modules that
# way, so real annotation objects are used instead: this module then imports
# correctly under every import mechanism. All annotations below are runtime-
# evaluable on the platform's Python 3.11/3.12 baseline.
import json
import pathlib
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

__all__ = [
    "FreshnessState",
    "FreshnessVerdict",
    "assess",
    "assess_many",
    "summarize",
    "DEFAULT_STALE_HOURS",
    "DEFAULT_EXPIRE_HOURS",
    "TIMESTAMP_KEYS",
]


# -----------------------------------------------------------------------------
# Thresholds
# -----------------------------------------------------------------------------
# Rationale: the AI prediction producers are scheduled at 6h cadence
# (.github/workflows/ai-predictions.yml) and the AI brain publisher runs on
# every sentinel-blogger run. 48h therefore tolerates a full day of CI outage
# before an artifact is called STALE. 168h (7 days) is the point past which an
# artifact describes a threat window that no longer resembles the present one,
# so it must not be presented to a customer as current intelligence.
DEFAULT_STALE_HOURS: float = 48.0
DEFAULT_EXPIRE_HOURS: float = 168.0

# Checked in order at the JSON root.
TIMESTAMP_KEYS: tuple = (
    "generated_at",
    "forecast_timestamp",
    "last_updated",
    "updated_at",
    "created_at",
    "timestamp",
    "as_of",
)


class FreshnessState:
    """Freshness state constants and their ordering."""

    MISSING = "MISSING"
    UNREADABLE = "UNREADABLE"
    UNDATED = "UNDATED"
    EXPIRED = "EXPIRED"
    STALE = "STALE"
    FRESH = "FRESH"

    # Higher rank == worse. Used to derive the worst state across a set.
    RANK: Dict[str, int] = {
        FRESH: 0,
        STALE: 1,
        EXPIRED: 2,
        UNDATED: 3,
        UNREADABLE: 4,
        MISSING: 5,
    }

    #: States whose artifact must never be republished as current intelligence.
    NOT_PUBLISHABLE = frozenset({MISSING, UNREADABLE, UNDATED, EXPIRED})


@dataclass(frozen=True)
class FreshnessVerdict:
    """The result of assessing one AI artifact. Immutable and JSON-safe."""

    label: str                      # caller-supplied identity, e.g. "anomalies"
    path: str                       # repo-relative path as given
    state: str                      # one of FreshnessState.*
    exists: bool
    age_hours: Optional[float]      # None when no timestamp was resolvable
    age_days: Optional[float]
    generated_at: Optional[str]     # the timestamp actually found, verbatim
    timestamp_key: Optional[str]    # which key it came from
    stale_hours: float
    expire_hours: float
    reason: str                     # human-readable explanation

    @property
    def is_fresh(self) -> bool:
        return self.state == FreshnessState.FRESH

    @property
    def is_publishable(self) -> bool:
        """True when this artifact may be published as current intelligence.

        STALE is publishable but the caller MUST label the output degraded.
        """
        return self.state not in FreshnessState.NOT_PUBLISHABLE

    @property
    def severity_rank(self) -> int:
        return FreshnessState.RANK.get(self.state, 5)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["is_fresh"] = self.is_fresh
        d["is_publishable"] = self.is_publishable
        return d


# -----------------------------------------------------------------------------
# Timestamp parsing
# -----------------------------------------------------------------------------

def _parse_iso(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or None.

    Tolerates the three shapes this platform actually emits:
      2026-05-04T17:52:19.789981+00:00   (datetime.isoformat)
      2026-08-26T09:55:08Z               (trailing Z)
      2026-08-26T09:55:08                (naive -- assumed UTC)
    """
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None
    # A naive timestamp is assumed UTC: every producer in this platform
    # writes UTC, and assuming UTC can only ever over-estimate age by the
    # local offset, which fails safe (older, not newer).
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_timestamp(payload: Any) -> tuple:
    """Return (datetime, key) for the first recognised timestamp, else (None, None)."""
    root = payload
    if isinstance(root, list):
        root = root[0] if root else None
    if not isinstance(root, dict):
        return (None, None)
    for key in TIMESTAMP_KEYS:
        if key in root:
            dt = _parse_iso(root[key])
            if dt is not None:
                return (dt, key)
    return (None, None)


# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------

def assess(
    path: Any,
    label: str = "",
    stale_hours: float = DEFAULT_STALE_HOURS,
    expire_hours: float = DEFAULT_EXPIRE_HOURS,
    now: Optional[datetime] = None,
) -> FreshnessVerdict:
    """Assess one AI artifact's freshness. Never raises.

    Args:
        path:         path to a JSON artifact (str or pathlib.Path).
        label:        short identity for reporting; defaults to the filename.
        stale_hours:  age beyond which the artifact is STALE.
        expire_hours: age beyond which the artifact is EXPIRED.
        now:          injected clock for deterministic tests; defaults to
                      the current UTC time.

    Returns:
        A FreshnessVerdict. Any error condition yields a non-publishable
        state -- this function never reports an artifact fresh on a
        failure path.
    """
    p = pathlib.Path(path)
    label = label or p.name
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    def _verdict(state, age_h, gen, key, reason):
        return FreshnessVerdict(
            label=label,
            path=str(path),
            state=state,
            exists=state != FreshnessState.MISSING,
            age_hours=(round(age_h, 2) if age_h is not None else None),
            age_days=(round(age_h / 24.0, 2) if age_h is not None else None),
            generated_at=gen,
            timestamp_key=key,
            stale_hours=float(stale_hours),
            expire_hours=float(expire_hours),
            reason=reason,
        )

    try:
        if not p.exists():
            return _verdict(FreshnessState.MISSING, None, None, None,
                            "artifact does not exist on disk")
        with open(p, encoding="utf-8", errors="replace") as fh:
            payload = json.load(fh)
    except Exception as exc:  # noqa: BLE001 -- fail closed on any read error
        return _verdict(FreshnessState.UNREADABLE, None, None, None,
                        f"artifact is not readable JSON: {type(exc).__name__}")

    dt, key = _extract_timestamp(payload)
    if dt is None:
        return _verdict(
            FreshnessState.UNDATED, None, None, None,
            "no recognisable timestamp key at JSON root "
            f"(checked: {', '.join(TIMESTAMP_KEYS)})",
        )

    gen_iso = dt.isoformat()
    age_h = (now - dt).total_seconds() / 3600.0

    # A timestamp in the future is a producer clock defect, not freshness.
    # Clamp to 0 so it is never reported as negative age, and treat a
    # materially future timestamp (>1h) as UNDATED -- untrustworthy.
    if age_h < -1.0:
        return _verdict(FreshnessState.UNDATED, 0.0, gen_iso, key,
                        "timestamp is in the future -- producer clock is unreliable")
    age_h = max(0.0, age_h)

    if age_h > expire_hours:
        return _verdict(FreshnessState.EXPIRED, age_h, gen_iso, key,
                        f"{age_h / 24.0:.1f} days old -- exceeds "
                        f"{expire_hours / 24.0:.1f}-day expiry; not current intelligence")
    if age_h > stale_hours:
        return _verdict(FreshnessState.STALE, age_h, gen_iso, key,
                        f"{age_h:.1f}h old -- exceeds {stale_hours:.0f}h "
                        "freshness window; publish only as degraded")
    return _verdict(FreshnessState.FRESH, age_h, gen_iso, key,
                    f"{age_h:.1f}h old -- within {stale_hours:.0f}h freshness window")


def assess_many(
    specs: Iterable,
    stale_hours: float = DEFAULT_STALE_HOURS,
    expire_hours: float = DEFAULT_EXPIRE_HOURS,
    now: Optional[datetime] = None,
) -> List[FreshnessVerdict]:
    """Assess several artifacts.

    Args:
        specs: an iterable of (label, path) pairs, or of bare paths.

    Returns:
        A list of verdicts in the order the specs were given.
    """
    out: List[FreshnessVerdict] = []
    for spec in specs:
        if isinstance(spec, (tuple, list)) and len(spec) == 2:
            label, path = spec[0], spec[1]
        else:
            label, path = "", spec
        out.append(assess(path, label=label, stale_hours=stale_hours,
                          expire_hours=expire_hours, now=now))
    return out


def summarize(verdicts: Iterable) -> Dict[str, Any]:
    """Reduce verdicts to a JSON-safe observability block.

    The returned `overall_state` is the WORST state present, so a single
    expired input can never be masked by fresh siblings.
    """
    vs = list(verdicts)
    if not vs:
        return {
            "overall_state": FreshnessState.MISSING,
            "degraded": True,
            "fresh_count": 0,
            "total_count": 0,
            "expired": [],
            "stale": [],
            "artifacts": {},
        }

    worst = max(vs, key=lambda v: v.severity_rank)
    return {
        "overall_state": worst.state,
        "degraded": worst.state != FreshnessState.FRESH,
        "fresh_count": sum(1 for v in vs if v.is_fresh),
        "total_count": len(vs),
        "expired": sorted(v.label for v in vs if v.state == FreshnessState.EXPIRED),
        "stale": sorted(v.label for v in vs if v.state == FreshnessState.STALE),
        "unavailable": sorted(
            v.label for v in vs
            if v.state in (FreshnessState.MISSING, FreshnessState.UNREADABLE,
                           FreshnessState.UNDATED)
        ),
        "max_age_days": max((v.age_days for v in vs if v.age_days is not None),
                            default=None),
        "artifacts": {v.label: v.to_dict() for v in vs},
    }


# -----------------------------------------------------------------------------
# CLI -- operator diagnostic for the live AI plane
# -----------------------------------------------------------------------------

def _default_targets(repo_root: pathlib.Path) -> List[tuple]:
    """The AI plane artifacts the Cyber Brain actually consumes."""
    return [
        ("anomalies", repo_root / "data" / "ai_predictions" / "anomalies.json"),
        ("forecasts", repo_root / "data" / "ai_predictions" / "forecasts.json"),
        ("apex_forecast", repo_root / "data" / "ai_predictions" / "apex_forecast_latest.json"),
        ("anomaly_radar", repo_root / "data" / "ai" / "anomaly_radar.json"),
        ("ai_summary", repo_root / "api" / "v1" / "intel" / "ai_summary.json"),
    ]


def main() -> int:
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    verdicts = assess_many(_default_targets(repo_root))
    summary = summarize(verdicts)

    print("=" * 74)
    print("SENTINEL APEX -- AI PLANE FRESHNESS")
    print("=" * 74)
    for v in verdicts:
        age = f"{v.age_days:>7.1f}d" if v.age_days is not None else "      -"
        print(f"  {v.state:<10} {age}  {v.label:<16} {v.reason}")
    print("-" * 74)
    print(f"  overall={summary['overall_state']} "
          f"fresh={summary['fresh_count']}/{summary['total_count']} "
          f"degraded={summary['degraded']}")
    print("=" * 74)

    # Exit 0 always: this CLI is a diagnostic, not a gate. The gate lives in
    # scripts/regression_tests.py so it runs with every other production gate.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
