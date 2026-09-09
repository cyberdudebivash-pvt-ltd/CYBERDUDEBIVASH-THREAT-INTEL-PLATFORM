#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  CYBERDUDEBIVASH® SENTINEL APEX — AI Predictions Engine v143.0.0           ║
║                                                                              ║
║  Engine 1: Isolation Forest Anomaly Radar                                   ║
║    - scikit-learn IsolationForest (contamination=0.10)                      ║
║    - 8 engineered features from STIX feed items                             ║
║    - Anomaly score >= 0.90 → "Zero-Day Candidate" flag                      ║
║    - Output: data/ai_predictions/anomalies.json                             ║
║                                                                              ║
║  Engine 2: Gradient Boosting 30-Day Sector Forecasts                        ║
║    - scikit-learn GradientBoostingRegressor per sector                      ║
║    - Sectors: Energy, Healthcare, Government, Finance, Technology,           ║
║               Manufacturing, Critical Infrastructure                         ║
║    - Sliding 90-day window of OBSERVED advisories only (v201.1)            ║
║    - Sectors with < MIN_REAL_SAMPLES observations are DECLINED, not        ║
║      forecast: no synthetic history, no placeholder numbers                ║
║    - Output: data/ai_predictions/forecasts.json                             ║
║                                                                              ║
║  Access: Enterprise + MSSP tier only (served via /api/v1/predict/enterprise)║
║  Atomic writes: .tmp → os.replace() on all outputs                         ║
║  Fallback: OLS trend extrapolation if scikit-learn unavailable (labelled)   ║
║                                                                              ║
║  CLI: python3 scripts/ai_predictions_engine.py                              ║
║       [--feed PATH]  [--history-dir PATH]  [--output-dir PATH]              ║
║       [--contamination FLOAT]  [--horizon INT]  [--dry-run]                 ║
║                                                                              ║
║  (c) 2026 CyberDudeBivash Pvt. Ltd.   GSTIN: 21ARKPN8270G1ZP              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
# v201.1: `import random` removed. The only RNG in this engine seeded a
# synthetic training-history generator that has been deleted; the engine is
# now deterministic end to end. Re-introducing randomness into a forecast
# path is what the T36 regression gate exists to prevent.
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("sentinel.ai_predictions")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)

ROOT         = Path(__file__).parent.parent
FEED_PATH    = ROOT / "api" / "feed.json"
HISTORY_DIR  = ROOT / "data" / "ai_predictions" / "history"
OUTPUT_DIR   = ROOT / "data" / "ai_predictions"

ENGINE_VERSION      = "143.0.0"
ZERO_DAY_THRESHOLD  = 0.90      # Isolation Forest anomaly score threshold
CONTAMINATION       = 0.10      # Expected outlier fraction
FORECAST_HORIZON    = 30        # Days to forecast ahead
BOOTSTRAP_DAYS      = 90        # v201.1: observation LOOKBACK WINDOW in days.
                                # Formerly the length of a synthetic history series
                                # (now removed). Name kept to avoid churning every
                                # call site; it no longer bootstraps anything.
# v201.1: minimum VALIDATED out-of-sample skill a forecast must demonstrate
# before it is published at all. Holdout R2 <= 0 means the model predicts unseen
# days no better than simply returning the mean -- there is nothing to sell a
# customer there, and a forecast series rendered as a trend line implies a skill
# the model does not have. Sectors below this floor are reported as
# NO_PREDICTIVE_SKILL with their measured score, never as a forecast.
MIN_FORECAST_CONFIDENCE = 0.10

MIN_REAL_SAMPLES    = 15        # v201.1: minimum OBSERVED advisories with risk scores
                                # before a sector is forecast at all. Declared since the
                                # engine was written but referenced nowhere until now;
                                # enforced in run_sector_forecasts().

# ── Sector Classification ─────────────────────────────────────────────────────

SECTOR_KEYWORDS: Dict[str, List[str]] = {
    "energy":                 ["energy", "power", "grid", "utility", "oil", "gas",
                               "nuclear", "pipeline", "ics", "scada", "ot"],
    "healthcare":             ["health", "hospital", "medical", "pharma", "fda",
                               "patient", "clinical", "ehr", "hipaa", "bio"],
    "government":             ["gov", "federal", "cisa", "nist", "dod", "military",
                               "state", "congress", "white house", "election", "nato"],
    "finance":                ["bank", "finance", "fintech", "swift", "payment",
                               "crypto", "trading", "sec", "treasury", "insurance"],
    "technology":             ["cloud", "saas", "software", "vendor", "api",
                               "crowdstrike", "microsoft", "google", "aws", "zero-day"],
    "manufacturing":          ["manufactur", "industrial", "supply chain", "logistics",
                               "automotive", "aerospace", "defense", "semiconductor"],
    "critical_infrastructure":["infrastructure", "telecom", "transport", "water",
                               "waste", "food", "chemical", "dam"],
}

SEVERITY_WEIGHT: Dict[str, float] = {
    "CRITICAL": 10.0,
    "HIGH":     7.5,
    "MEDIUM":   5.0,
    "LOW":      2.5,
    "INFO":     1.0,
}


# ── Feed Loading ──────────────────────────────────────────────────────────────

def load_feed(feed_path: Path) -> List[Dict]:
    """Load and normalize api/feed.json."""
    if not feed_path.exists():
        logger.warning(f"Feed not found: {feed_path}")
        return []
    try:
        raw = json.loads(feed_path.read_bytes())
        if isinstance(raw, list):
            return raw
        for key in ("items", "data", "results", "feed"):
            if key in raw and isinstance(raw[key], list):
                return raw[key]
        return []
    except Exception as e:
        logger.error(f"Feed load error: {e}")
        return []


def classify_sector(item: Dict) -> str:
    """Classify an advisory into its primary sector."""
    blob = " ".join([
        str(item.get("title", "")),
        str(item.get("description", "")),
        str(item.get("threat_type", "")),
        " ".join(item.get("tags", [])) if isinstance(item.get("tags"), list) else str(item.get("tags", "")),
        str(item.get("source_url", "")),
        str(item.get("actor_tag", "")),
    ]).lower()

    scores: Dict[str, int] = {s: 0 for s in SECTOR_KEYWORDS}
    for sector, keywords in SECTOR_KEYWORDS.items():
        for kw in keywords:
            if kw in blob:
                scores[sector] += 1

    best = max(scores, key=lambda s: scores[s])
    return best if scores[best] > 0 else "technology"


def extract_features(item: Dict) -> List[float]:
    """
    Extract 8 numerical features for Isolation Forest / Gradient Boosting.

    Features:
      [0] risk_score           — 0–10 direct field
      [1] apex_ai_score        — 0–10 AI confidence score
      [2] severity_weight      — numeric CRITICAL=10 ... INFO=1
      [3] confidence_score     — 0–100, normalised to 0–10
      [4] ioc_count            — number of IOCs (log1p normalised)
      [5] ttp_density          — TTP tags density proxy
      [6] predictive_risk      — apex_ai.predictive_risk (0–10)
      [7] source_quality_score — HIGH=10, MEDIUM=5, LOW=2
    """
    risk_score     = float(item.get("risk_score") or 5.0)
    apex_ai_score  = float(item.get("apex_ai_score") or item.get("apex_ai", {}).get("ai_confidence", 5) or 5.0)
    severity       = str(item.get("severity", "MEDIUM")).upper()
    sev_weight     = SEVERITY_WEIGHT.get(severity, 5.0)
    conf_raw       = float(item.get("confidence_score") or item.get("confidence") or 50)
    conf_norm      = conf_raw / 10.0

    # IOC count
    iocs = item.get("iocs") or []
    ioc_count_raw  = int(item.get("ioc_count") or len(iocs) if isinstance(iocs, list) else 0)
    ioc_feat       = math.log1p(ioc_count_raw)

    # TTP density — approximate from tags length + threat type
    tags = item.get("tags") or []
    ttp_density    = min(len(tags) / 5.0, 10.0)

    # Predictive risk
    apex_ai_block  = item.get("apex_ai") or {}
    if isinstance(apex_ai_block, str):
        try:
            apex_ai_block = json.loads(apex_ai_block.replace("'", '"'))
        except Exception:
            apex_ai_block = {}
    pred_risk      = float(apex_ai_block.get("predictive_risk") or risk_score)

    # Source quality
    sq_map         = {"HIGH": 10.0, "MEDIUM": 5.0, "LOW": 2.0}
    sq             = sq_map.get(str(item.get("source_quality", "HIGH")).upper(), 5.0)

    return [risk_score, apex_ai_score, sev_weight, conf_norm, ioc_feat, ttp_density, pred_risk, sq]


# ── Statistical Fallback (no scikit-learn) ────────────────────────────────────

def _statistical_anomaly_score(features: List[float]) -> float:
    """
    Statistical anomaly proxy when sklearn is unavailable.
    Combines z-score distance from mean with severity emphasis.
    Returns a score in [0, 1].
    """
    weights    = [0.25, 0.15, 0.20, 0.10, 0.10, 0.05, 0.10, 0.05]
    baseline   = [5.0,  5.0,  5.0,  5.0,  0.5,  2.0,  5.0,  5.0 ]
    stdev      = [2.0,  2.0,  2.5,  2.5,  0.5,  1.5,  2.0,  2.0 ]
    z_scores   = [abs(f - b) / s for f, b, s in zip(features, baseline, stdev)]
    weighted_z = sum(w * z for w, z in zip(weights, z_scores))
    # Logistic transform → [0, 1]
    return 1.0 / (1.0 + math.exp(-0.5 * (weighted_z - 2.0)))


# ── Engine 1: Isolation Forest Anomaly Radar ──────────────────────────────────

def run_anomaly_detection(
    items:         List[Dict],
    contamination: float = CONTAMINATION,
    threshold:     float = ZERO_DAY_THRESHOLD,
) -> Dict:
    """
    Run Isolation Forest anomaly detection on feed items.
    Falls back to statistical scoring if scikit-learn is unavailable.
    """
    if not items:
        return _empty_anomaly_report(contamination, threshold)

    feature_matrix = [extract_features(it) for it in items]
    sklearn_available = False
    anomaly_scores: List[float] = []

    # Try sklearn IsolationForest
    try:
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import StandardScaler
        import numpy as np

        X = np.array(feature_matrix, dtype=float)
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        clf = IsolationForest(
            n_estimators=200,
            contamination=contamination,
            max_samples="auto",
            random_state=42,
            n_jobs=-1,
        )
        clf.fit(X_scaled)

        # decision_function returns negative values for anomalies
        # Convert: higher score = more anomalous (0–1 range)
        raw_scores = clf.decision_function(X_scaled)
        # Normalise: min→0, max→1, invert (low decision = high anomaly)
        s_min, s_max = raw_scores.min(), raw_scores.max()
        if s_max > s_min:
            norm = (raw_scores - s_min) / (s_max - s_min)
        else:
            norm = np.zeros_like(raw_scores)
        anomaly_scores = (1.0 - norm).tolist()
        sklearn_available = True
        logger.info(f"IsolationForest: {len(items)} items, sklearn OK")

    except ImportError:
        logger.warning("scikit-learn not available — using statistical anomaly scorer")
        anomaly_scores = [_statistical_anomaly_score(f) for f in feature_matrix]
    except Exception as e:
        logger.error(f"IsolationForest error: {e} — falling back to statistical scorer")
        anomaly_scores = [_statistical_anomaly_score(f) for f in feature_matrix]

    # Build annotated anomaly records
    annotated: List[Dict] = []
    zero_day_count = 0

    for item, score, features in zip(items, anomaly_scores, feature_matrix):
        is_candidate = score >= threshold
        if is_candidate:
            zero_day_count += 1

        rec = {
            "stix_id":              item.get("stix_id", item.get("id", "")),
            "title":                item.get("title", "")[:120],
            "published_at":         item.get("published_at", item.get("published", "")),
            "severity":             item.get("severity", "UNKNOWN"),
            "threat_type":          item.get("threat_type", ""),
            "risk_score":           round(float(item.get("risk_score") or 0), 2),
            "apex_ai_score":        round(float(item.get("apex_ai_score") or 0), 2),
            "anomaly_score":        round(score, 4),
            "anomaly_pct":          round(score * 100, 1),
            "is_zero_day_candidate": is_candidate,
            "sector":               classify_sector(item),
            "soc_priority":         _derive_soc_priority(score, item),
            "anomaly_features": {
                "risk_score":       round(features[0], 2),
                "apex_ai_score":    round(features[1], 2),
                "severity_weight":  round(features[2], 2),
                "confidence_norm":  round(features[3], 2),
                "ioc_density":      round(features[4], 4),
                "ttp_density":      round(features[5], 2),
                "predictive_risk":  round(features[6], 2),
                "source_quality":   round(features[7], 2),
            },
            "report_url": item.get("report_url", ""),
        }
        annotated.append(rec)

    # Sort by anomaly_score descending
    annotated.sort(key=lambda r: r["anomaly_score"], reverse=True)

    return {
        "generated_at":        datetime.now(timezone.utc).isoformat(),
        "model":               "IsolationForest" if sklearn_available else "StatisticalScorer",
        "version":             ENGINE_VERSION,
        "sklearn_available":   sklearn_available,
        "contamination":       contamination,
        "zero_day_threshold":  threshold,
        "total_analyzed":      len(items),
        "zero_day_candidates": zero_day_count,
        "high_anomaly_count":  sum(1 for a in annotated if a["anomaly_score"] >= 0.75),
        "anomalies":           annotated,
        "metadata": {
            "gstin":        "21ARKPN8270G1ZP",
            "vendor":       "CyberDudeBivash Pvt. Ltd.",
            "access_tier":  "ENTERPRISE",
            "endpoint":     "/api/v1/anomalies/critical",
        },
    }


def _derive_soc_priority(anomaly_score: float, item: Dict) -> str:
    """Derive SOC priority from anomaly score + severity."""
    sev = str(item.get("severity", "MEDIUM")).upper()
    if anomaly_score >= 0.90 or sev == "CRITICAL":
        return "P1"
    if anomaly_score >= 0.75 or sev == "HIGH":
        return "P2"
    if anomaly_score >= 0.50 or sev == "MEDIUM":
        return "P3"
    return "P4"


def _empty_anomaly_report(contamination: float, threshold: float) -> Dict:
    return {
        "generated_at":        datetime.now(timezone.utc).isoformat(),
        "model":               "IsolationForest",
        "version":             ENGINE_VERSION,
        "contamination":       contamination,
        "zero_day_threshold":  threshold,
        "total_analyzed":      0,
        "zero_day_candidates": 0,
        "anomalies":           [],
        "warning":             "Feed is empty — no anomaly analysis possible",
    }


# ── Engine 2: Gradient Boosting 30-Day Sector Forecasts ───────────────────────

SECTOR_BASELINES: Dict[str, Dict] = {
    "energy":                {"base_risk": 7.1, "volatility": 1.2, "trend_bias": +0.04},
    "healthcare":            {"base_risk": 6.4, "volatility": 0.9, "trend_bias": +0.03},
    "government":            {"base_risk": 7.8, "volatility": 1.4, "trend_bias": +0.05},
    "finance":               {"base_risk": 6.9, "volatility": 1.1, "trend_bias": +0.02},
    "technology":            {"base_risk": 6.2, "volatility": 1.0, "trend_bias": +0.01},
    "manufacturing":         {"base_risk": 5.8, "volatility": 0.8, "trend_bias": +0.02},
    "critical_infrastructure":{"base_risk": 7.5, "volatility": 1.3, "trend_bias": +0.04},
}


def _build_sector_history(
    items: List[Dict],
    sector: str,
    n_days: int = BOOTSTRAP_DAYS,
) -> Tuple[List[float], List[float]]:
    """
    Build (X: day_index, y: risk_score) training pairs for a sector from
    OBSERVED advisories only.

    ══════════════════════════════════════════════════════════════════════════
    v201.1 ANTI-FABRICATION FIX (AI plane audit, 2026-09-09)
    ══════════════════════════════════════════════════════════════════════════
    This function previously manufactured 91 days of history per sector from a
    hardcoded SECTOR_BASELINES constant plus Gaussian noise and a sine
    "weekly seasonality", then overlaid whatever real advisories existed.
    Measured against the live feed at audit time, the resulting training set
    for the paid Enterprise/MSSP 30-day forecast was:

        energy                   synthetic=91  real=27   77.1% synthetic
        healthcare               synthetic=91  real= 2   97.8% synthetic
        government               synthetic=91  real= 7   92.9% synthetic
        finance                  synthetic=91  real=12   88.3% synthetic
        technology               synthetic=91  real= 8   91.9% synthetic
        manufacturing            synthetic=91  real= 0  100.0% synthetic
        critical_infrastructure  synthetic=91  real= 1   98.9% synthetic
        ---------------------------------------------------------------
        TOTAL                    synthetic=637 real=57   91.8% synthetic

    A GradientBoostingRegressor fitted on that is not forecasting threat
    activity; it is restating SECTOR_BASELINES. Manufacturing, with zero real
    observations, published a pure random walk around a constant as a sector
    risk prediction.

    The seed compounded it: `random.Random(hash(sector) % (2**31))` keys on
    hash() of a str, which Python randomises per process unless PYTHONHASHSEED
    is set. Three consecutive runs produced seeds 1681237532 / 2038321344 /
    669586364, so identical inputs yielded different "forecasts" every run --
    movement a customer would reasonably read as changing threat conditions.

    Synthetic history is removed outright rather than reduced. There is no
    ratio of fabricated-to-real training data that makes a forecast honest,
    and no RNG remains in this path, so the engine is now deterministic.
    Sectors without enough observed history are handled by the caller, which
    declines to forecast rather than inventing one -- see MIN_REAL_SAMPLES
    enforcement in run_sector_forecasts().
    ══════════════════════════════════════════════════════════════════════════

    Returns:
        (history_x, history_y) built exclusively from observed advisories.
        Empty lists when the sector has no usable observations.
    """
    now_ts = datetime.now(timezone.utc)
    history: List[Tuple[float, float]] = []

    for it in items:
        if classify_sector(it) != sector:
            continue
        pub_str = it.get("published_at") or it.get("published") or ""
        try:
            pub_dt = datetime.fromisoformat(str(pub_str).replace("Z", "+00:00"))
        except (ValueError, TypeError, AttributeError):
            continue
        if pub_dt.tzinfo is None:
            pub_dt = pub_dt.replace(tzinfo=timezone.utc)

        day_ago = (now_ts - pub_dt).days
        if not (0 <= day_ago <= n_days):
            continue

        # An advisory with no risk score contributes no risk evidence. It used
        # to fall back to the sector's hardcoded base_risk, which injected the
        # very constant this fix removes.
        raw_risk = it.get("risk_score")
        if raw_risk is None:
            continue
        try:
            risk = float(raw_risk)
        except (TypeError, ValueError):
            continue

        history.append((float(n_days - day_ago), max(0.0, min(10.0, risk))))

    # Chronological order, so the caller's "most recent observations" slice is
    # genuinely the most recent. The old synthetic loop produced ordered output
    # by construction and real items were appended unordered behind it.
    history.sort(key=lambda pair: pair[0])

    return [x for x, _ in history], [y for _, y in history]


def _gradient_boosting_forecast(
    X_train: List[float],
    y_train: List[float],
    horizon:   int   = FORECAST_HORIZON,
    n_history: int   = BOOTSTRAP_DAYS,
) -> Tuple[List[float], float, str]:
    """
    Fit GradientBoostingRegressor on (day_index → risk_score) pairs.

    Returns (forecast[horizon], confidence, confidence_basis).

    ══════════════════════════════════════════════════════════════════════════
    v201.1 HONEST-CONFIDENCE FIX (AI plane audit, 2026-09-09)
    ══════════════════════════════════════════════════════════════════════════
    `confidence` was computed as in-sample R² -- the model scored against the
    very rows it was fitted on -- then clamped with max(0.50, ...). Two
    independent problems:

      1. In-sample R² measures how well the model memorised its training data,
         not how well it predicts unseen days. On the smooth synthetic series
         the old _build_sector_history() produced, it was inflated by
         construction.
      2. The 0.50 floor meant a model performing WORSE than simply predicting
         the mean (negative R²) still published "confidence: 0.50". The number
         could not go below one-in-two no matter how badly the model fit, so
         it carried no information at its low end at all.

    Confidence is now estimated on a held-out tail: the model is refitted on
    the earlier portion of the series and scored on the most recent held-out
    days it never saw, which is the closest available proxy for forecasting
    unseen future days. It is NOT floored -- a poor fit is reported as a poor
    fit, clamped only into the valid [0.0, 0.95] reporting range. Every return
    path states its basis so a consumer knows what the number means.
    ══════════════════════════════════════════════════════════════════════════
    """
    n = len(X_train)

    try:
        from sklearn.ensemble import GradientBoostingRegressor
        from sklearn.metrics import r2_score
        import numpy as np

        Xarr = np.array(X_train).reshape(-1, 1)
        yarr = np.array(y_train)

        def _fit(x, y):
            m = GradientBoostingRegressor(
                n_estimators=200,
                learning_rate=0.05,
                max_depth=4,
                subsample=0.8,
                random_state=42,   # fixed seed: fitting is deterministic
            )
            m.fit(x, y)
            return m

        # Hold out the most recent ~20% (at least 3 points) to estimate
        # out-of-sample skill. Below 2x the holdout we cannot both fit and
        # validate, so we say so rather than substituting an in-sample number.
        holdout = max(3, int(round(n * 0.2)))
        if n - holdout >= max(5, holdout):
            m_val = _fit(Xarr[:-holdout], yarr[:-holdout])
            r2_out = r2_score(yarr[-holdout:], m_val.predict(Xarr[-holdout:]))
            confidence = max(0.0, min(0.95, float(r2_out)))
            conf_basis = f"holdout_r2(n_train={n - holdout},n_holdout={holdout})"
        else:
            confidence = 0.0
            conf_basis = f"insufficient_samples_for_validation(n={n})"

        model = _fit(Xarr, yarr)
        future_x = np.arange(n_history + 1, n_history + 1 + horizon, dtype=float).reshape(-1, 1)
        predictions = np.clip(model.predict(future_x), 0.0, 10.0)

        return predictions.tolist(), round(confidence, 3), conf_basis

    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"GBR fit error: {e}")

    # Fallback: ordinary least-squares trend extrapolation. Reported as such --
    # this is not a gradient-boosting forecast and must not claim to be.
    if n >= 2:
        sx  = sum(X_train)
        sy  = sum(y_train)
        sxy = sum(x * y for x, y in zip(X_train, y_train))
        sxx = sum(x * x for x in X_train)
        denom = n * sxx - sx * sx
        if abs(denom) > 1e-9:
            slope = (n * sxy - sx * sy) / denom
            intercept = (sy - slope * sx) / n
            preds = [max(0.0, min(10.0, intercept + slope * (n_history + 1 + i)))
                     for i in range(horizon)]
            # Coefficient of determination of the fitted line, not a floor.
            mean_y = sy / n
            ss_tot = sum((yy - mean_y) ** 2 for yy in y_train)
            ss_res = sum((yy - (intercept + slope * xx)) ** 2
                         for xx, yy in zip(X_train, y_train))
            r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 1e-9 else 0.0
            return preds, round(max(0.0, min(0.95, r2)), 3), "linear_insample_r2(sklearn_unavailable)"

    # No usable signal. Previously this returned a hardcoded 5.0 series at
    # "confidence 0.50"; an invented mid-scale risk score is exactly the
    # fabrication this audit removes. The caller's evidence gate should have
    # declined this sector before reaching here.
    return [], 0.0, "no_usable_signal"


def run_sector_forecasts(
    items:   List[Dict],
    horizon: int = FORECAST_HORIZON,
) -> Dict:
    """Run 30-day Gradient Boosting forecasts for all sectors."""
    sectors_output: Dict[str, Dict] = {}
    today = datetime.now(timezone.utc).date()

    declined: List[str] = []

    for sector in SECTOR_KEYWORDS:
        X, y = _build_sector_history(items, sector)
        advisories_30d = sum(1 for it in items if classify_sector(it) == sector)

        # ------------------------------------------------------------------
        # v201.1 EVIDENCE GATE. MIN_REAL_SAMPLES has been declared since this
        # engine was written and was never referenced anywhere in the file --
        # the documented evidence threshold did not exist in code. It is
        # enforced here. A sector without enough observed history gets an
        # explicit INSUFFICIENT_EVIDENCE record carrying its real sample
        # count, and NO invented numbers: no forecast series, no peak, no
        # trend, no confidence. Publishing "we do not have the data" is
        # correct; publishing a number derived from a constant is not.
        # ------------------------------------------------------------------
        if len(y) < MIN_REAL_SAMPLES:
            declined.append(sector)
            sectors_output[sector] = {
                "sector":             sector.replace("_", " ").title(),
                "status":             "INSUFFICIENT_EVIDENCE",
                "real_observations":  len(y),
                "required_observations": MIN_REAL_SAMPLES,
                "synthetic_observations": 0,
                "advisories_30d":     advisories_30d,
                "reason": (
                    f"{len(y)} observed advisories with risk scores in the last "
                    f"{BOOTSTRAP_DAYS} days; {MIN_REAL_SAMPLES} required to fit a "
                    "forecast. No forecast is produced for this sector."
                ),
            }
            logger.info(
                f"  {sector}: DECLINED — {len(y)}/{MIN_REAL_SAMPLES} observed samples"
            )
            continue

        forecasts, confidence, conf_basis = _gradient_boosting_forecast(X, y, horizon)

        # Defence in depth: the evidence gate above should already have
        # declined any sector that cannot produce a forecast, but an empty
        # series here must degrade to INSUFFICIENT_EVIDENCE rather than raise
        # on max([]) -- and must never be backfilled with a placeholder.
        if not forecasts:
            declined.append(sector)
            sectors_output[sector] = {
                "sector":             sector.replace("_", " ").title(),
                "status":             "INSUFFICIENT_EVIDENCE",
                "real_observations":  len(y),
                "required_observations": MIN_REAL_SAMPLES,
                "synthetic_observations": 0,
                "advisories_30d":     advisories_30d,
                "reason": "model produced no usable forecast series for this sector",
            }
            logger.warning(f"  {sector}: DECLINED — model returned no forecast series")
            continue

        # ------------------------------------------------------------------
        # v201.1 PREDICTIVE-SKILL GATE. Having enough observations is not the
        # same as being able to forecast them. A model whose validated
        # out-of-sample score is at or near zero predicts unseen days no
        # better than returning the mean; rendering its output as a 30-day
        # trend line asserts a capability it does not have. Report the
        # measured score and decline, rather than publishing the series.
        # ------------------------------------------------------------------
        if confidence < MIN_FORECAST_CONFIDENCE:
            declined.append(sector)
            sectors_output[sector] = {
                "sector":                sector.replace("_", " ").title(),
                "status":                "NO_PREDICTIVE_SKILL",
                "real_observations":     len(y),
                "synthetic_observations": 0,
                "advisories_30d":        advisories_30d,
                "measured_confidence":   confidence,
                "confidence_basis":      conf_basis,
                "required_confidence":   MIN_FORECAST_CONFIDENCE,
                "reason": (
                    f"validated confidence {confidence} is below the "
                    f"{MIN_FORECAST_CONFIDENCE} floor required to publish a forecast; "
                    "the model showed no out-of-sample skill on this sector's observed history"
                ),
            }
            logger.info(
                f"  {sector}: DECLINED — no predictive skill "
                f"(confidence={confidence}, basis={conf_basis}, {len(y)} observed samples)"
            )
            continue

        current_risk  = round(float(sum(y[-7:]) / max(len(y[-7:]), 1)), 2)
        peak_val      = max(forecasts)
        peak_day      = forecasts.index(peak_val) + 1
        trough_val    = min(forecasts)
        trend_delta   = forecasts[-1] - forecasts[0]
        trend_pct     = round(trend_delta / max(forecasts[0], 0.1) * 100, 1)

        if trend_delta > 0.3:
            trend = "RISING"
        elif trend_delta < -0.3:
            trend = "DECLINING"
        else:
            trend = "STABLE"

        # Risk level classification from peak forecast
        if peak_val >= 8.0:
            risk_level = "CRITICAL"
        elif peak_val >= 6.5:
            risk_level = "HIGH"
        elif peak_val >= 4.5:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        # Generate daily labels
        daily_labels = [(today + timedelta(days=i + 1)).isoformat() for i in range(horizon)]

        sectors_output[sector] = {
            "sector":           sector.replace("_", " ").title(),
            "status":           "FORECAST",
            "current_risk":     current_risk,
            "forecast_30d":     [round(v, 2) for v in forecasts],
            "daily_labels":     daily_labels,
            "trend":            trend,
            "trend_pct":        trend_pct,
            "risk_level":       risk_level,
            "peak_day":         peak_day,
            "peak_risk":        round(peak_val, 2),
            "trough_risk":      round(trough_val, 2),
            "confidence":       confidence,
            "advisories_30d":   advisories_30d,
            # v201.1 provenance: every forecast now states the evidence it was
            # fitted on, so a consumer can weigh it instead of taking the
            # number on faith. synthetic_observations is always 0 by
            # construction -- see _build_sector_history().
            "real_observations":      len(y),
            "synthetic_observations": 0,
            "confidence_basis":       conf_basis,
        }
        logger.info(
            f"  {sector}: risk={current_risk} trend={trend} peak={round(peak_val,2)} "
            f"conf={confidence} ({conf_basis}) on {len(y)} observed samples"
        )

    return {
        "generated_at":     datetime.now(timezone.utc).isoformat(),
        "model":            "GradientBoostingRegressor",
        "version":          ENGINE_VERSION,
        "forecast_horizon": horizon,
        "total_items_used": len(items),
        # v201.1 top-level evidence summary. A consumer must be able to see at
        # a glance how much of this report is an actual forecast.
        "sectors_forecast":  len(sectors_output) - len(declined),
        "sectors_declined":  sorted(declined),
        "min_real_samples":  MIN_REAL_SAMPLES,
        "synthetic_training_data": False,
        "sectors":          sectors_output,
        "metadata": {
            "gstin":       "21ARKPN8270G1ZP",
            "vendor":      "CyberDudeBivash Pvt. Ltd.",
            "access_tier": "ENTERPRISE",
            "endpoint":    "/api/v1/predict/enterprise",
        },
    }


# ── Atomic Write ──────────────────────────────────────────────────────────────

def _atomic_write_json(path: Path, data: Dict, indent: int = 2) -> None:
    """Write JSON atomically via .tmp → os.replace()."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=indent, ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp), str(path))
        logger.info(f"Written: {path}")
    except Exception as e:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Atomic write failed for {path}: {e}") from e


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="SENTINEL APEX AI Predictions Engine v143.0.0"
    )
    parser.add_argument("--feed",          default=str(FEED_PATH),   help="Path to api/feed.json")
    parser.add_argument("--output-dir",    default=str(OUTPUT_DIR),  help="Output directory")
    parser.add_argument("--contamination", type=float, default=CONTAMINATION, help="IF contamination (0.01–0.50)")
    parser.add_argument("--horizon",       type=int,   default=FORECAST_HORIZON, help="Forecast horizon in days")
    parser.add_argument("--dry-run",       action="store_true",       help="Run but do not write output files")
    parser.add_argument("--anomaly-only",  action="store_true",       help="Run anomaly detection only")
    parser.add_argument("--forecast-only", action="store_true",       help="Run forecasts only")
    args = parser.parse_args()

    feed_path  = Path(args.feed)
    output_dir = Path(args.output_dir)
    t_start    = time.time()

    logger.info("=" * 64)
    logger.info("SENTINEL APEX AI Predictions Engine v143.0.0")
    logger.info(f"Feed:      {feed_path}")
    logger.info(f"Output:    {output_dir}")
    logger.info(f"Dry-run:   {args.dry_run}")
    logger.info("=" * 64)

    items = load_feed(feed_path)
    logger.info(f"Feed loaded: {len(items)} items")

    errors = 0

    # ── Engine 1: Anomaly Detection ───────────────────────────────────────
    if not args.forecast_only:
        logger.info("\n[Engine 1] Isolation Forest Anomaly Radar")
        try:
            anomaly_report = run_anomaly_detection(
                items,
                contamination=args.contamination,
                threshold=ZERO_DAY_THRESHOLD,
            )
            zdc = anomaly_report["zero_day_candidates"]
            total = anomaly_report["total_analyzed"]
            logger.info(f"  Zero-Day Candidates: {zdc}/{total} ({zdc/max(total,1)*100:.1f}%)")
            logger.info(f"  Model: {anomaly_report['model']}")

            if not args.dry_run:
                _atomic_write_json(output_dir / "anomalies.json", anomaly_report)
        except Exception as e:
            logger.error(f"[Engine 1] FAILED: {e}", exc_info=True)
            errors += 1

    # ── Engine 2: Sector Forecasts ────────────────────────────────────────
    if not args.anomaly_only:
        logger.info("\n[Engine 2] Gradient Boosting 30-Day Sector Forecasts")
        try:
            forecast_report = run_sector_forecasts(items, horizon=args.horizon)
            # v201.1: was len(forecast_report['sectors']), which counts every
            # sector in the report including the ones that were DECLINED for
            # insufficient evidence -- it reported "7" on a run that actually
            # forecast 2. Report the forecast and declined counts separately.
            logger.info(
                f"  Sectors forecasted: {forecast_report.get('sectors_forecast', 0)}"
                f" | declined (insufficient evidence): {len(forecast_report.get('sectors_declined', []))}"
            )
            logger.info(f"  Model: {forecast_report['model']}")

            if not args.dry_run:
                _atomic_write_json(output_dir / "forecasts.json", forecast_report)
        except Exception as e:
            logger.error(f"[Engine 2] FAILED: {e}", exc_info=True)
            errors += 1

    # ── Summary manifest ─────────────────────────────────────────────────
    if not args.dry_run and errors == 0:
        summary = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version":       ENGINE_VERSION,
            "elapsed_s":     round(time.time() - t_start, 3),
            "feed_items":    len(items),
            "outputs": {
                "anomalies": str(output_dir / "anomalies.json"),
                "forecasts": str(output_dir / "forecasts.json"),
            },
            "status": "OK",
        }
        _atomic_write_json(output_dir / "predictions_summary.json", summary)

    elapsed = time.time() - t_start
    logger.info(f"\nDone in {elapsed:.2f}s | Errors: {errors}")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
