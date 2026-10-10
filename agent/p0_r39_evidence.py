"""P0 R39 — provenance from observed RSS bytes, never from invented defaults.

The digest is a fingerprint of the *captured RSS entry fields*, not a
publisher-signed checksum or a cryptographic attestation of article truth.
Retrieval time must be supplied by the caller at the actual fetch boundary.
Unknown source trust and publication time intentionally remain absent.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit

_TRUST_FILE = Path(__file__).resolve().parents[1] / "data/quality/source_trust_scores.json"


def _host(url: str) -> str:
    if not isinstance(url, str):
        return ""
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ("https", "http"):
            return ""
        return (parsed.hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _utc_stamp(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            d = parsedate_to_datetime(value)
        except (ValueError, TypeError, IndexError):
            return ""
    if not d.tzinfo:
        return ""  # Do not assume ambiguous time zone.
    d = d.astimezone(timezone.utc)
    if d.year < 2000:
        return ""
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _verified_trust(host: str, registry: Path) -> float | None:
    if not host or not registry.is_file():
        return None
    try:
        source = json.loads(registry.read_text(encoding="utf-8"))
        observed = source.get("trust_scores", {}).get(host)
        if not isinstance(observed, dict):
            return None
        raw = observed.get("trust_score")
        score = float(raw)
        if not math.isfinite(score) or score <= 0 or score > 1:
            return None
        return round(score * 10, 2)
    except (OSError, ValueError, TypeError):
        return None


def capture_rss_evidence(entry: dict, feed_url: str, retrieved_at: str,
                         registry: Path = _TRUST_FILE) -> dict:
    """Preserve only fields observed in an actual RSS/Atom collection."""
    if not isinstance(entry, dict):
        return {}
    host = _host(feed_url)
    article_url = entry.get("link", "")
    if not host or not _host(article_url):
        return {}
    when = _utc_stamp(retrieved_at)
    if not when:
        return {}
    raw_title = entry.get("title", "") or ""
    raw_summary = entry.get("summary", "") or ""
    raw_content = entry.get("content", "") or ""
    if not any(isinstance(v, str) and v.strip() for v in (raw_title, raw_summary, raw_content)):
        return {}
    original = {"title": raw_title, "summary": raw_summary, "content": raw_content, "link": article_url}
    digest = hashlib.sha256(json.dumps(original, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    result = {
        "source_name": host,
        "source_domain": host,
        "source_url": article_url,
        "retrieval_timestamp": when,
        "content_hash": digest,
        "content_hash_scope": "rss_entry_fields_sha256",
        "evidence_count": 1,
        "evidence_basis": ["captured_rss_entry"],
    }
    pub = _utc_stamp(entry.get("published", "") or entry.get("published_at", ""))
    if pub:
        try:
            if datetime.fromisoformat(pub.replace("Z", "+00:00")) <= datetime.fromisoformat(when.replace("Z", "+00:00")) + timedelta(minutes=5):
                result["publication_timestamp"] = pub
        except ValueError:
            pass
    trust = _verified_trust(host, registry)
    if trust is not None:
        result["trust_score"] = trust
    return result


def append_fetched_article_evidence(provenance: dict, fetched: dict | None) -> dict:
    """Second distinct retrieved artifact, never a fabricated second source."""
    updated = dict(provenance or {})
    if not isinstance(fetched, dict) or fetched.get("fetch_status") != "success":
        return updated
    body = fetched.get("full_text")
    if not isinstance(body, str) or not body.strip() or not updated.get("content_hash"):
        return updated
    updated["evidence_count"] = 2
    updated["evidence_basis"] = ["captured_rss_entry", "separately_fetched_article"]
    updated["article_content_hash"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return updated
