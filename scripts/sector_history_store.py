#!/usr/bin/env python3
"""
===============================================================================
CYBERDUDEBIVASH(R) SENTINEL APEX
scripts/sector_history_store.py -- DURABLE DAILY OBSERVATION STORE
===============================================================================
THE PROBLEM THIS SOLVES
-----------------------
The 2026-09-09 audit traced the sector forecast's failure past the model to its
root cause: THE PLATFORM RETAINS NO HISTORICAL TIME SERIES.

  * api/feed.json is a rolling current-window snapshot, not an archive. The
    entire live feed spanned 8 days across 4 distinct publish dates.
  * data/stix/ is likewise a rolling window; its usable observation history was
    14 days across a 16-day span.
  * ai_predictions_engine.py declared HISTORY_DIR =
    data/ai_predictions/history and never referenced it. The directory has
    never existed.

That is why the previous engine fabricated 91 days of synthetic history per
sector: there was nothing real to fit. No choice of model fixes this. A
forecast needs history, and history has to be accumulated deliberately,
one day at a time, before any of it can be forecast.

This module is that accumulation. Every pipeline run appends the current day's
observed threat intensity per sector to a durable, git-committed store. The
store grows by roughly 1 KB/day and becomes the substrate the forecaster reads.

WHAT IS RECORDED
----------------
Per sector per day:
    count        -- advisories published that day for that sector
    intensity    -- risk-weighted volume: the sum of each advisory's risk_score
                    (falling back to its severity weight when unscored). This is
                    the forecast target: it captures both how much is happening
                    and how bad it is, and unlike a per-advisory risk score it
                    is genuinely one value per day.
    mean_risk    -- mean risk of that day's advisories, or null if none

OBSERVED-ZERO IS NOT THE SAME AS NOT-OBSERVED
---------------------------------------------
The single most important correctness property here. A day on which the
pipeline ran and saw no energy-sector advisories is a real observation of zero,
and a forecaster must learn from it. A day on which the pipeline did not run is
not an observation at all, and recording zero for it would fabricate data --
precisely the class of defect this audit removed elsewhere.

So each day carries a `source`:

    "live"      -- written by a pipeline run on that date. Every sector is
                   recorded, including the ones at zero: we looked and saw
                   nothing, which is evidence.
    "bootstrap" -- inferred from an archive (STIX bundles, current feed) for a
                   date that already passed. Only sectors with at least one
                   observed advisory are recorded. A bootstrap day CANNOT
                   distinguish "no advisories" from "pipeline did not run",
                   so zeros are never invented for it.

Days absent from the store are unknown, never zero. build_series() reports
observed vs span so the forecaster's coverage gate can refuse a gappy series.

CONTRACT
--------
  * Pure standard library. Deterministic. No network, no Cloudflare calls.
  * IDEMPOTENT: re-running for the same date recomputes that date's row from
    the same inputs and replaces it. Running twice a day is safe and is the
    normal case (the pipeline fires every 6h).
  * APPEND-ONLY across dates: an update for today never rewrites history for
    an earlier date that was recorded live.
  * Atomic writes; a crash mid-write cannot corrupt the store.

CLI:
    python3 scripts/sector_history_store.py                  # update today
    python3 scripts/sector_history_store.py --bootstrap      # seed from archives
    python3 scripts/sector_history_store.py --report         # coverage summary

(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved. CONFIDENTIAL.
===============================================================================
"""

import argparse
import glob
import json
import logging
import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [sector_history] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("CDB-SECTOR-HISTORY")

REPO_ROOT  = Path(__file__).resolve().parent.parent
FEED_PATH  = REPO_ROOT / "api" / "feed.json"
STIX_DIR   = REPO_ROOT / "data" / "stix"
STORE_PATH = REPO_ROOT / "data" / "ai_predictions" / "sector_history.json"

SCHEMA = "sentinel-apex-sector-history-v1"

#: Severity fallback when an advisory carries no numeric risk_score. Mirrors
#: ai_predictions_engine.SEVERITY_WEIGHT; an advisory with neither a risk score
#: nor a recognised severity contributes to `count` but not to `intensity`,
#: rather than being assigned an invented weight.
SEVERITY_WEIGHT: Dict[str, float] = {
    "CRITICAL": 10.0, "HIGH": 7.5, "MEDIUM": 5.0, "LOW": 2.5, "INFO": 1.0,
}

RETAIN_DAYS = 400   # ~13 months: enough for annual seasonality, bounded growth


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _parse_date(value) -> Optional[date]:
    """Parse an ISO timestamp to a UTC date, or None. Never raises."""
    if not value:
        return None
    try:
        t = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(timezone.utc).date()


def _item_date(item: Dict) -> Optional[date]:
    for key in ("published_at", "published", "timestamp", "processed_at"):
        d = _parse_date(item.get(key))
        if d:
            return d
    return None


def _item_risk(item: Dict) -> Optional[float]:
    """Risk weight for one advisory, or None when it carries no risk signal."""
    raw = item.get("risk_score")
    if raw is None:
        raw = item.get("score")
    if raw is not None:
        try:
            return max(0.0, min(10.0, float(raw)))
        except (TypeError, ValueError):
            pass
    sev = str(item.get("severity") or item.get("risk_level") or "").strip().upper()
    return SEVERITY_WEIGHT.get(sev)


def _atomic_write_json(path: Path, payload: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".shs_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        shutil.move(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_store(path: Path = STORE_PATH) -> Dict:
    """Load the store, or return an empty one. Never raises."""
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("days"), dict):
                return data
            log.warning("Store at %s has an unexpected shape; starting a new one", path)
        except Exception as exc:  # noqa: BLE001
            log.warning("Store at %s unreadable (%s); starting a new one", path, exc)
    return {"schema": SCHEMA, "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": None, "days": {}}


# -----------------------------------------------------------------------------
# Aggregation
# -----------------------------------------------------------------------------

def aggregate_day(items: List[Dict], classify, sectors: List[str],
                  all_sectors_zero: bool) -> Dict[str, Dict]:
    """Aggregate one day's advisories into per-sector rows.

    Args:
        all_sectors_zero: when True (a live observation), sectors with no
            advisories are recorded at zero -- we looked and saw nothing.
            When False (a bootstrap inference), they are omitted, because an
            archive cannot distinguish "nothing happened" from "we weren't
            watching".
    """
    buckets: Dict[str, List[float]] = {}
    counts: Dict[str, int] = {}
    for it in items:
        sec = classify(it)
        counts[sec] = counts.get(sec, 0) + 1
        risk = _item_risk(it)
        if risk is not None:
            buckets.setdefault(sec, []).append(risk)

    rows: Dict[str, Dict] = {}
    for sec in sectors:
        risks = buckets.get(sec, [])
        n = counts.get(sec, 0)
        if n == 0 and not all_sectors_zero:
            continue
        rows[sec] = {
            "count": n,
            "intensity": round(sum(risks), 3),
            "mean_risk": round(sum(risks) / len(risks), 3) if risks else None,
        }
    return rows


#: How far behind "today" the newest advisory in the feed may be before this
#: module refuses to record a live observation. See update_today().
MAX_FEED_LAG_DAYS = 2


def update_today(store: Dict, items: List[Dict], classify, sectors: List[str],
                 today: Optional[date] = None,
                 max_feed_lag_days: int = MAX_FEED_LAG_DAYS) -> Tuple[Dict, str]:
    """Record today's observation. Idempotent: replaces today's row if present.

    STALE-FEED GUARD. Recording a live day writes a zero for every sector with
    no advisories, on the reasoning that we looked and saw nothing. That
    reasoning only holds if we actually looked at current data. When the feed
    itself has not refreshed -- during this audit its newest advisory was
    2026-08-26 while the date was 2026-09-09 -- "no advisories today" is
    indistinguishable from "the feed is 14 days behind", and writing zeros
    would manufacture a fortnight of false observations. That is the same
    fabrication this store exists to avoid, so a stale feed records nothing at
    all and says why.
    """
    today = today or datetime.now(timezone.utc).date()

    item_dates = [d for d in (_item_date(it) for it in items) if d is not None]
    newest = max(item_dates) if item_dates else None
    if newest is None:
        return store, "skipped_no_dated_items"
    lag = (today - newest).days
    if lag > max_feed_lag_days:
        log.warning(
            "Feed's newest advisory is %s (%d days behind %s, tolerance %d) — "
            "not recording a live observation; zeros would be fabricated",
            newest.isoformat(), lag, today.isoformat(), max_feed_lag_days,
        )
        return store, f"skipped_stale_feed({lag}d)"

    todays_items = [it for it in items if _item_date(it) == today]
    rows = aggregate_day(todays_items, classify, sectors, all_sectors_zero=True)
    key = today.isoformat()
    existed = key in store["days"]
    store["days"][key] = {
        "source": "live",
        "advisories": len(todays_items),
        "sectors": rows,
    }
    store["updated_at"] = datetime.now(timezone.utc).isoformat()
    return store, ("replaced" if existed else "added")


def bootstrap(store: Dict, classify, sectors: List[str],
              feed_path: Path = FEED_PATH, stix_dir: Path = STIX_DIR) -> Tuple[Dict, int]:
    """Seed the store from whatever genuine history the archives still hold.

    Never overwrites a day already recorded live: a live observation is
    stronger evidence than an inference from an archive.
    """
    by_day: Dict[date, List[Dict]] = {}

    def absorb(item: Dict) -> None:
        d = _item_date(item)
        if d:
            by_day.setdefault(d, []).append(item)

    try:
        feed = json.loads(feed_path.read_text(encoding="utf-8"))
        for it in (feed if isinstance(feed, list) else []):
            absorb(it)
    except Exception as exc:  # noqa: BLE001
        log.warning("Feed unreadable during bootstrap: %s", exc)

    for fp in sorted(glob.glob(str(stix_dir / "*.json"))):
        try:
            bundle = json.loads(Path(fp).read_text(encoding="utf-8"))
        except Exception:
            continue
        objs = bundle.get("objects") if isinstance(bundle, dict) else bundle
        for o in (objs or []):
            if not isinstance(o, dict):
                continue
            # STIX objects carry their own field names; map to what the
            # classifier and risk extractor expect without inventing values.
            absorb({
                "title": o.get("name") or o.get("title") or "",
                "description": o.get("description") or "",
                "labels": o.get("labels") or [],
                "published_at": o.get("created") or o.get("published") or o.get("valid_from"),
                "risk_score": o.get("risk_score"),
                "severity": o.get("severity"),
            })

    added = 0
    for d, items in sorted(by_day.items()):
        key = d.isoformat()
        if store["days"].get(key, {}).get("source") == "live":
            continue
        rows = aggregate_day(items, classify, sectors, all_sectors_zero=False)
        if not rows:
            continue
        store["days"][key] = {
            "source": "bootstrap",
            "advisories": len(items),
            "sectors": rows,
        }
        added += 1

    store["updated_at"] = datetime.now(timezone.utc).isoformat()
    return store, added


def prune(store: Dict, retain_days: int = RETAIN_DAYS,
          today: Optional[date] = None) -> int:
    """Drop days older than the retention window. Bounded, predictable growth."""
    today = today or datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=retain_days)
    stale = [k for k in store["days"] if (_parse_date(k) or today) < cutoff]
    for k in stale:
        del store["days"][k]
    return len(stale)


# -----------------------------------------------------------------------------
# Series construction (what the forecaster consumes)
# -----------------------------------------------------------------------------

def build_series(store: Dict, sector: str, lookback_days: int = 180,
                 field: str = "intensity",
                 today: Optional[date] = None) -> Dict:
    """Build a contiguous daily series for one sector.

    Interior gaps are linearly interpolated so the series is contiguous, and
    the count of interpolated days is reported alongside it. Nothing is hidden:
    the forecaster's coverage gate refuses a series whose observed fraction is
    too low, and `interpolated_days` travels with the published output.

    Returns:
        {values, observed_days, span_days, interpolated_days, start, end}
        `values` is empty when the sector has no observations at all.
    """
    today = today or datetime.now(timezone.utc).date()
    earliest = today - timedelta(days=lookback_days)

    observed: Dict[date, float] = {}
    for key, day in store.get("days", {}).items():
        d = _parse_date(key)
        if not d or d < earliest or d > today:
            continue
        row = (day.get("sectors") or {}).get(sector)
        if row is None:
            continue
        val = row.get(field)
        if val is None:
            continue
        try:
            observed[d] = float(val)
        except (TypeError, ValueError):
            continue

    if not observed:
        return {"values": [], "observed_days": 0, "span_days": 0,
                "interpolated_days": 0, "start": None, "end": None}

    start, end = min(observed), max(observed)
    span = (end - start).days + 1

    values: List[float] = []
    interpolated = 0
    for i in range(span):
        d = start + timedelta(days=i)
        if d in observed:
            values.append(observed[d])
            continue
        # Linear interpolation between the nearest observed neighbours.
        prev_d = max((k for k in observed if k < d), default=None)
        next_d = min((k for k in observed if k > d), default=None)
        if prev_d is None or next_d is None:
            values.append(observed[prev_d if prev_d is not None else next_d])
        else:
            frac = (d - prev_d).days / float((next_d - prev_d).days)
            values.append(observed[prev_d] + frac * (observed[next_d] - observed[prev_d]))
        interpolated += 1

    return {
        "values": values,
        "observed_days": len(observed),
        "span_days": span,
        "interpolated_days": interpolated,
        "start": start.isoformat(),
        "end": end.isoformat(),
    }


def coverage_report(store: Dict, sectors: List[str], lookback_days: int = 180) -> Dict:
    """Human- and CI-readable summary of how much history exists."""
    days = store.get("days", {})
    live = sum(1 for d in days.values() if d.get("source") == "live")
    out = {
        "total_days": len(days),
        "live_days": live,
        "bootstrap_days": len(days) - live,
        "sectors": {},
    }
    for sec in sectors:
        s = build_series(store, sec, lookback_days)
        out["sectors"][sec] = {
            "observed_days": s["observed_days"],
            "span_days": s["span_days"],
            "interpolated_days": s["interpolated_days"],
        }
    return out


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------

def _load_classifier():
    """Reuse ai_predictions_engine's sector classifier -- one definition only."""
    import importlib.util
    p = REPO_ROOT / "scripts" / "ai_predictions_engine.py"
    spec = importlib.util.spec_from_file_location("ai_predictions_engine", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ai_predictions_engine"] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop("ai_predictions_engine", None)
    return mod.classify_sector, list(mod.SECTOR_KEYWORDS.keys())


def main() -> int:
    ap = argparse.ArgumentParser(description="Sector daily observation store")
    ap.add_argument("--store", default=str(STORE_PATH))
    ap.add_argument("--feed", default=str(FEED_PATH))
    ap.add_argument("--bootstrap", action="store_true",
                    help="seed from STIX/feed archives before updating today")
    ap.add_argument("--report", action="store_true", help="print coverage and exit")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    store_path = Path(args.store)
    classify, sectors = _load_classifier()
    store = load_store(store_path)

    if args.report:
        rep = coverage_report(store, sectors)
        print(json.dumps(rep, indent=2, sort_keys=True))
        return 0

    if args.bootstrap:
        store, added = bootstrap(store, classify, sectors)
        log.info("Bootstrap: %d day(s) seeded from archives", added)

    try:
        feed = json.loads(Path(args.feed).read_text(encoding="utf-8"))
        items = feed if isinstance(feed, list) else []
    except Exception as exc:  # noqa: BLE001
        log.error("Feed unreadable: %s", exc)
        items = []

    store, action = update_today(store, items, classify, sectors)
    dropped = prune(store)

    rep = coverage_report(store, sectors)
    log.info("Store: %d day(s) total (%d live, %d bootstrap); today %s; %d pruned",
             rep["total_days"], rep["live_days"], rep["bootstrap_days"], action, dropped)
    for sec, s in sorted(rep["sectors"].items()):
        log.info("  %-24s observed=%-4d span=%-4d interpolated=%d",
                 sec, s["observed_days"], s["span_days"], s["interpolated_days"])

    if args.dry_run:
        log.info("Dry-run: store not written")
        return 0

    _atomic_write_json(store_path, store)
    log.info("Written: %s", store_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
