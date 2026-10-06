"""
tests/test_canonical_timestamp.py — CyberDudeBivash SENTINEL APEX
Unit tests for scripts/canonical_timestamp.py, the single timestamp
normalization engine adopted by scripts/true_intel_ingestor.py and
scripts/source_fabric_health.py after the NVD CVE incident (a missing
format pattern silently discarded every timestamp for weeks). Covers the
full Section-5 test matrix: format variants, precision preservation,
timezone normalization, failure modes, and cursor-safe comparison.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from canonical_timestamp import parse_timestamp, parse_ts, is_cursor_advance  # noqa: E402


class TestFormatMatrix:
    """The exact test matrix from the task's Section 5."""

    def test_iso_with_z(self):
        r = parse_timestamp("2026-08-06T22:16:40Z")
        assert r.parse_status == "SUCCESS"
        assert r.normalized == datetime(2026, 8, 6, 22, 16, 40, tzinfo=timezone.utc)
        assert r.source_timezone == "UTC"

    def test_iso_fractional_no_z(self):
        """The exact NVD CVE API v2 format that caused the production incident."""
        r = parse_timestamp("2026-08-06T22:16:40.020")
        assert r.parse_status == "SUCCESS"
        assert r.normalized.microsecond == 20000
        assert r.source_timezone == "NAIVE_ASSUMED_UTC"

    def test_iso_fractional_with_z(self):
        r = parse_timestamp("2026-08-06T22:16:40.020Z")
        assert r.parse_status == "SUCCESS"
        assert r.normalized.microsecond == 20000
        assert r.source_timezone == "UTC"

    def test_iso_with_positive_offset(self):
        r = parse_timestamp("2026-08-06T22:16:40+05:30")
        assert r.parse_status == "SUCCESS"
        # Normalized to UTC: 22:16:40 IST == 16:46:40 UTC
        assert r.normalized == datetime(2026, 8, 6, 16, 46, 40, tzinfo=timezone.utc)
        assert "05:30" in r.source_timezone

    def test_iso_fractional_with_offset(self):
        r = parse_timestamp("2026-08-06T22:16:40.020+05:30")
        assert r.parse_status == "SUCCESS"
        assert r.normalized.microsecond == 20000
        assert r.normalized.hour == 16 and r.normalized.minute == 46

    def test_date_only(self):
        """CISA KEV's dateAdded field format."""
        r = parse_timestamp("2026-08-06")
        assert r.parse_status == "SUCCESS"
        assert r.normalized == datetime(2026, 8, 6, 0, 0, 0, tzinfo=timezone.utc)

    def test_invalid_string(self):
        r = parse_timestamp("invalid")
        assert r.parse_status == "FAILED"
        assert r.normalized is None
        assert r.parse_error is not None

    def test_empty_string(self):
        r = parse_timestamp("")
        assert r.parse_status == "FAILED"
        assert r.parse_error == "empty_string"

    def test_null(self):
        r = parse_timestamp(None)
        assert r.parse_status == "FAILED"
        assert r.parse_error == "null"

    def test_unexpected_format(self):
        r = parse_timestamp("not-a-timestamp-at-all")
        assert r.parse_status == "FAILED"
        assert r.normalized is None


class TestAdditionalRealWorldFormats:
    """Formats found in the repo-wide audit that weren't in the literal
    Section-5 list but are real inputs from live sources."""

    def test_rss_rfc822(self):
        r = parse_timestamp("Sat, 08 Aug 2026 12:00:00 GMT")
        assert r.parse_status == "SUCCESS"
        assert r.normalized == datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)

    def test_rss_rfc822_with_offset(self):
        r = parse_timestamp("Sat, 08 Aug 2026 12:00:00 +0000")
        assert r.parse_status == "SUCCESS"
        assert r.normalized == datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)

    def test_feedparser_struct_time_tuple(self):
        # feedparser's time.struct_time is index-compatible with a 9-tuple:
        # (year, month, day, hour, minute, second, weekday, yday, isdst)
        r = parse_timestamp((2026, 8, 6, 22, 16, 40, 3, 218, 0))
        assert r.parse_status == "SUCCESS"
        assert r.normalized == datetime(2026, 8, 6, 22, 16, 40, tzinfo=timezone.utc)

    def test_short_tuple_fails_safely(self):
        r = parse_timestamp((2026, 8))
        assert r.parse_status == "FAILED"
        assert r.parse_error == "struct_time_too_short"

    def test_non_string_non_tuple_type(self):
        r = parse_timestamp(12345)
        assert r.parse_status == "FAILED"
        assert "unsupported_type" in r.parse_error

    def test_whitespace_only(self):
        r = parse_timestamp("   ")
        assert r.parse_status == "FAILED"


class TestPrecisionPreservation:
    def test_microsecond_precision_round_trips(self):
        r = parse_timestamp("2026-08-06T22:16:40.123456Z")
        assert r.normalized.microsecond == 123456

    def test_three_digit_millisecond_precision(self):
        r = parse_timestamp("2026-08-06T22:16:40.020")
        assert r.normalized.microsecond == 20000


class TestParseTsBackwardCompatibleWrapper:
    """parse_ts() must match every existing _parse_ts(ts) -> Optional[datetime]
    call site's contract exactly: bare datetime or None, no exceptions."""

    def test_returns_bare_datetime_on_success(self):
        result = parse_ts("2026-08-06T22:16:40Z")
        assert isinstance(result, datetime)
        assert result.tzinfo is not None

    def test_returns_none_on_failure(self):
        assert parse_ts("garbage") is None
        assert parse_ts(None) is None
        assert parse_ts("") is None

    def test_never_raises(self):
        for bad_input in [None, "", "   ", 12345, [], (1, 2), {"a": 1}, "\x00\x01"]:
            parse_ts(bad_input)  # must not raise


class TestCursorSafety:
    """Section 5: cursor advancement, cursor persistence, timezone
    normalization for comparisons."""

    def test_cursor_advances_on_newer_timestamp(self):
        last = parse_ts("2026-08-06T00:00:00Z")
        new = parse_ts("2026-08-07T00:00:00Z")
        assert is_cursor_advance(new, last) is True

    def test_cursor_does_not_advance_on_older_timestamp(self):
        last = parse_ts("2026-08-07T00:00:00Z")
        new = parse_ts("2026-08-06T00:00:00Z")
        assert is_cursor_advance(new, last) is False

    def test_cursor_does_not_advance_on_equal_timestamp(self):
        last = parse_ts("2026-08-06T00:00:00Z")
        new = parse_ts("2026-08-06T00:00:00Z")
        assert is_cursor_advance(new, last) is False

    def test_no_prior_cursor_always_advances(self):
        new = parse_ts("2026-08-06T00:00:00Z")
        assert is_cursor_advance(new, None) is True

    def test_no_new_timestamp_never_advances(self):
        last = parse_ts("2026-08-06T00:00:00Z")
        assert is_cursor_advance(None, last) is False

    def test_cross_timezone_comparison_is_correct(self):
        """A source emitting +05:30 timestamps must compare correctly
        against a cursor recorded from a UTC/Z source -- exactly the
        cross-source consistency this engine exists to guarantee."""
        last_utc = parse_ts("2026-08-06T20:00:00Z")           # 20:00 UTC
        new_ist = parse_ts("2026-08-07T00:00:00+05:30")        # == 18:30 UTC -- OLDER
        assert is_cursor_advance(new_ist, last_utc) is False

        new_ist_later = parse_ts("2026-08-07T02:00:00+05:30")  # == 20:30 UTC -- NEWER
        assert is_cursor_advance(new_ist_later, last_utc) is True

    def test_duplicate_timestamp_detection_via_equality(self):
        """Same instant, different representations, must compare equal --
        the basis for duplicate detection across sources with different
        native timestamp formats."""
        a = parse_ts("2026-08-06T22:16:40Z")
        b = parse_ts("2026-08-06T22:16:40+00:00")
        assert a == b
