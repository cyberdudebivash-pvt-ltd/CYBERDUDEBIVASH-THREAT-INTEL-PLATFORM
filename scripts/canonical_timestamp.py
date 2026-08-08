#!/usr/bin/env python3
"""
scripts/canonical_timestamp.py
CYBERDUDEBIVASH(R) SENTINEL APEX — Canonical Timestamp Normalization Engine

MOTIVATION (evidence, not speculation): the NVD CVE incident (fixed in
scripts/true_intel_ingestor.py) traced back to one parser's format list
missing NVD's fractional-seconds-no-Z variant. A full repo audit for this
task found 90+ independent timestamp-parsing implementations across 73
files, each with its own format list and its own failure behavior --
silently returning None, or 0.0, or -1, or 9999.0, or an epoch sentinel, or
`datetime.now()`, or raising uncaught, depending on the file. That
inconsistency is exactly what let the NVD bug hide for weeks.

SCOPE DECISION: this module is adopted by the two parsers that sit
directly in the P40 Global Intelligence Source Fabric's ingestion/health
path -- scripts/true_intel_ingestor.py and scripts/source_fabric_health.py
(see their _parse_ts functions, now thin wrappers around parse_ts() below).
The other ~70+ call sites found in the audit span unrelated subsystems
(license/JWT expiry, SLA engines, billing, AI prediction models, backup
snapshots, etc.) with their own owners, tests, and failure-handling
conventions already tuned to their use case (e.g. some intentionally
default to "very stale" sentinels rather than None). Migrating all of them
in one pass would touch 70+ files with no single defect driving each
change -- a blast radius and architectural-event scale that needs its own
scoped, sign-off change, not a rider on this task. Left as a documented,
explicit gap; see the P40 hardening report for the full inventory.

CONTRACT (Section 3/4 of the task):
  RAW_TIMESTAMP        -- the original string exactly as received
  NORMALIZED_TIMESTAMP -- tz-aware UTC datetime, or None if parsing failed
  PARSE_STATUS         -- "SUCCESS" or "FAILED" -- ALWAYS explicit, never
                           just a bare None a caller has to guess the
                           meaning of
  PARSE_ERROR          -- machine-readable reason when PARSE_STATUS is
                           FAILED (None on success)
  SOURCE_TIMEZONE       -- the offset/zone actually present in the raw
                           string ("UTC", "+05:30", "NAIVE_ASSUMED_UTC"),
                           or None on failure

Formats accepted (union of every format string found across the repo-wide
audit, plus fromisoformat's broader native ISO-8601 support as the primary
path):
  ISO-8601 with Z, with/without fractional seconds (any precision),
  with explicit UTC offset, without any offset (assumed UTC), date-only
  (CISA KEV's `dateAdded`), RFC-822/RFC-7231 (RSS `pubDate` / HTTP
  `Last-Modified`), plus a handful of vendor date-only variants
  (%Y/%m/%d, %m/%d/%Y, %d-%m-%Y, %Y%m%d, %B %d %Y, %b %d %Y) found in the
  audit's per-file parsers.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Sequence, Union

# Fixed-format fallbacks tried after fromisoformat -- covers everything
# fromisoformat can't parse natively (RFC-822/7231 weekday-prefixed dates,
# date-only in non-ISO order, month-name dates).
_STRPTIME_FORMATS: Sequence[str] = (
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%Y%m%d",
    "%B %d %Y",
    "%b %d %Y",
    "%a, %d %b %Y %H:%M:%S %z",       # RFC-822-ish RSS pubDate
    "%a, %d %b %Y %H:%M:%S GMT",      # RFC-7231 (HTTP Last-Modified)
)


@dataclass(frozen=True)
class TimestampResult:
    raw: Optional[str]
    normalized: Optional[datetime]
    parse_status: str          # "SUCCESS" | "FAILED"
    parse_error: Optional[str]
    source_timezone: Optional[str]


def parse_timestamp(raw: Optional[Union[str, Sequence[int]]]) -> TimestampResult:
    """
    Canonical timestamp parser. Never raises. Always returns an explicit
    parse_status -- a malformed timestamp is reported as FAILED, not
    silently coerced into None with no way for the caller to tell "no
    data" apart from "bad data" (Section 4's #5/#6 requirement).
    """
    # feedparser sometimes hands back a struct_time-like 9-tuple instead of
    # a string -- check this before the string-type guard below.
    if isinstance(raw, (list, tuple)):
        if len(raw) >= 6:
            try:
                dt = datetime(*raw[:6], tzinfo=timezone.utc)
                return TimestampResult(raw=str(raw), normalized=dt, parse_status="SUCCESS",
                                        parse_error=None, source_timezone="UTC")
            except Exception as e:
                return TimestampResult(raw=str(raw), normalized=None, parse_status="FAILED",
                                        parse_error=f"invalid_struct_time:{e}", source_timezone=None)
        return TimestampResult(raw=str(raw), normalized=None, parse_status="FAILED",
                                parse_error="struct_time_too_short", source_timezone=None)

    if raw is None:
        return TimestampResult(raw=None, normalized=None, parse_status="FAILED",
                                parse_error="null", source_timezone=None)

    if not isinstance(raw, str):
        return TimestampResult(raw=str(raw), normalized=None, parse_status="FAILED",
                                parse_error=f"unsupported_type:{type(raw).__name__}", source_timezone=None)

    s = raw.strip()
    if not s:
        return TimestampResult(raw=raw, normalized=None, parse_status="FAILED",
                                parse_error="empty_string", source_timezone=None)

    # Primary path: fromisoformat handles the widest range of real-world
    # ISO-8601 variants in one call (fractional seconds of any precision,
    # explicit offsets) -- explicit Z -> +00:00 substitution since
    # fromisoformat only accepts a bare "Z" from Python 3.11+, and this
    # module must stay correct on whatever CPython this repo's CI runs.
    try:
        iso_candidate = s[:-1] + "+00:00" if s.endswith("Z") else s
        dt = datetime.fromisoformat(iso_candidate)
        if dt.tzinfo is None:
            source_tz = "NAIVE_ASSUMED_UTC"
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            source_tz = "UTC" if s.endswith("Z") else str(dt.tzinfo)
        return TimestampResult(raw=raw, normalized=dt.astimezone(timezone.utc),
                                parse_status="SUCCESS", parse_error=None, source_timezone=source_tz)
    except ValueError:
        pass

    # Fixed-format fallbacks.
    for fmt in _STRPTIME_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
        except ValueError:
            continue
        if dt.tzinfo is None:
            source_tz = "UTC" if ("Z" in fmt or "GMT" in fmt) else "NAIVE_ASSUMED_UTC"
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            source_tz = str(dt.tzinfo)
        return TimestampResult(raw=raw, normalized=dt.astimezone(timezone.utc),
                                parse_status="SUCCESS", parse_error=None, source_timezone=source_tz)

    return TimestampResult(raw=raw, normalized=None, parse_status="FAILED",
                            parse_error="no_matching_format", source_timezone=None)


def parse_ts(raw: Optional[Union[str, Sequence[int]]]) -> Optional[datetime]:
    """
    Backward-compatible thin wrapper matching the `_parse_ts(ts) ->
    Optional[datetime]` signature already used throughout this codebase.
    Returns the normalized datetime, or None on failure. Callers that need
    to distinguish "no data" from "malformed data we couldn't parse"
    should call parse_timestamp() directly instead.
    """
    return parse_timestamp(raw).normalized


def is_cursor_advance(new_ts: Optional[datetime], last_ts: Optional[datetime]) -> bool:
    """
    Cursor-safe comparison: True if new_ts is strictly newer than last_ts.
    Both arguments must already be tz-aware (as returned by parse_ts /
    parse_timestamp.normalized) -- comparing a naive and an aware datetime
    raises TypeError in Python, which is exactly the class of bug this
    module exists to prevent, so this function does not attempt to
    silently paper over mismatched awareness.
    """
    if new_ts is None:
        return False
    if last_ts is None:
        return True
    return new_ts > last_ts
