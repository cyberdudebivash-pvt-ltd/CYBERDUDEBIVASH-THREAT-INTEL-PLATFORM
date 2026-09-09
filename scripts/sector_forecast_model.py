#!/usr/bin/env python3
"""
===============================================================================
CYBERDUDEBIVASH(R) SENTINEL APEX
scripts/sector_forecast_model.py -- VALIDATED TIME-SERIES FORECASTING CORE
===============================================================================
WHY THIS MODULE REPLACES THE PREVIOUS FORECAST
----------------------------------------------
The 2026-09-09 audit found three independent, fatal design errors in the
sector forecast that ai_predictions_engine.py used to produce. They were not
tuning problems -- no choice of hyper-parameters could have fixed any of them:

  1. THE TARGET WAS NOT A TIME SERIES.
     It regressed each advisory's `risk_score` on a `day_index`. Measured on
     the live feed, the energy sector's 57 advisories fell on just 3 distinct
     days (up to 30 advisories sharing one day). Many y-values per x is not a
     function of time; fitting it recovers noise around a sector mean, which
     is why validated out-of-sample R2 was exactly 0.0.

  2. THE MODEL COULD NOT EXTRAPOLATE.
     GradientBoostingRegressor is a tree ensemble, and trees are piecewise
     constant: outside the training range every input falls in the boundary
     leaf. The published "30-day forecast" was verified to return the
     identical value (6.7800) for all 30 days -- a flat line by mathematical
     necessity, rendered in the UI as a trend.

  3. THERE WAS NO HISTORY TO LEARN FROM.
     api/feed.json is a rolling current-window snapshot, not an archive. The
     whole feed spanned 8 days across 4 distinct publish dates. The engine
     compensated by fabricating 91 days of synthetic history per sector (see
     the previous commit); remove the fabrication and there is almost nothing
     left.

THE DESIGN HERE
---------------
Forecast the quantity that genuinely IS a time series: per-sector daily
threat intensity (risk-weighted advisory volume), supplied by
scripts/sector_history_store.py, which durably accumulates one observation
per sector per day.

Rather than assert a model, run a competition and let measured skill decide:

    naive                 -- last observed value carried forward (the benchmark)
    seasonal_naive        -- value from m days ago (m=7, weekly publishing cycle)
    mean                  -- historical mean
    drift                 -- last value plus the average historical slope
    ses                   -- simple exponential smoothing        (alpha grid)
    holt_damped           -- level + damped trend                (alpha,beta,phi)
    seasonal_naive_drift  -- last cycle repeated, plus linear drift
    holt_winters          -- level + damped trend + seasonality  (alpha,beta,gamma,phi)

The last two exist because testing found the suite could not forecast a series
carrying BOTH a trend and weekly seasonality -- the shape daily advisory
intensity actually has. seasonal_naive ignores the trend, holt_damped ignores
the season, so on such a series neither beat the naive benchmark and every
sector was declined. With them, a rising series is forecast by
seasonal_naive_drift and a falling one by holt_winters.

Every candidate is scored by ROLLING-ORIGIN BACKTESTING: fit on data up to an
origin, predict the next `horizon` days, score against what actually happened,
advance the origin, repeat. Nothing is ever scored on data it was fitted on --
the specific mistake that let the old in-sample R2 look respectable.

The score is MASE (Mean Absolute Scaled Error): mean absolute forecast error
divided by the mean absolute error of a one-step naive forecast on the
training data. MASE is scale-free and has an unambiguous decision point:

    MASE <  1.0  -- beats the naive benchmark; the model adds information
    MASE >= 1.0  -- does not beat "tomorrow looks like today"; publishing it
                    would assert skill the model does not have

`select_and_forecast()` returns publishable=False when the winner fails that
test, when history is too short, or when coverage is too sparse. A caller must
honour that: declining to forecast is a correct outcome, not an error path.

Prediction intervals are EMPIRICAL -- taken from the distribution of actual
backtest errors at each horizon step, not from a Gaussian assumption the
residuals have not been shown to satisfy.

CONTRACT
--------
  * Pure standard library. No numpy, no sklearn, no network.
  * Deterministic: fixed parameter grids, fixed tie-breaking, no RNG. Identical
    input always yields byte-identical output.
  * Never fabricates an observation. Gaps are gaps; see require_coverage.
  * Pure functions; no file or global state.

(c) 2026 CyberDudeBivash Pvt. Ltd. All Rights Reserved. CONFIDENTIAL.
===============================================================================
"""

from typing import Callable, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "SEASONAL_PERIOD",
    "DEFAULT_MIN_HISTORY_DAYS",
    "MASE_PUBLISH_THRESHOLD",
    "forecast_naive",
    "forecast_seasonal_naive",
    "forecast_mean",
    "forecast_drift",
    "forecast_ses",
    "forecast_holt_damped",
    "forecast_seasonal_naive_drift",
    "forecast_holt_winters",
    "CANDIDATES",
    "mase_scale",
    "rolling_origin_backtest",
    "select_and_forecast",
]

# Weekly publishing cycle: security advisories cluster on weekdays.
SEASONAL_PERIOD = 7

#: Minimum observed days before any forecast is attempted. Two seasonal cycles
#: to see the weekly pattern twice, plus room for the horizon and several
#: backtest origins. Below this, MASE is estimated from too few errors to mean
#: anything, so a "validated" model would be validated by luck.
DEFAULT_MIN_HISTORY_DAYS = 35

#: A model must beat the naive benchmark outright. Not 1.05 "close enough":
#: at MASE >= 1 the honest forecast is the naive one, which needs no model.
MASE_PUBLISH_THRESHOLD = 1.0

#: Fraction of days in the covered span that must actually be observed. A
#: series with large gaps is not a daily series, and smoothing across the gaps
#: would invent the missing days.
DEFAULT_MIN_COVERAGE = 0.80


# -----------------------------------------------------------------------------
# Forecast methods
#
# Every method takes the observed history and a horizon, and returns exactly
# `horizon` values. None of them look at data beyond what they are given --
# that property is what makes the backtest below meaningful.
# -----------------------------------------------------------------------------

def forecast_naive(y: Sequence[float], horizon: int, **_) -> List[float]:
    """Carry the last observation forward. The benchmark all others must beat."""
    return [float(y[-1])] * horizon


def forecast_seasonal_naive(y: Sequence[float], horizon: int,
                            m: int = SEASONAL_PERIOD, **_) -> List[float]:
    """Repeat the value from the same weekday m days ago."""
    if len(y) < m:
        return forecast_naive(y, horizon)
    return [float(y[-m + (h % m)]) for h in range(horizon)]


def forecast_mean(y: Sequence[float], horizon: int, **_) -> List[float]:
    """Historical mean. Wins when a series is level noise with no trend."""
    mu = float(sum(y)) / len(y)
    return [mu] * horizon


def forecast_drift(y: Sequence[float], horizon: int, **_) -> List[float]:
    """Last value plus the average slope across the whole history."""
    if len(y) < 2:
        return forecast_naive(y, horizon)
    slope = (float(y[-1]) - float(y[0])) / (len(y) - 1)
    return [float(y[-1]) + slope * (h + 1) for h in range(horizon)]


def forecast_ses(y: Sequence[float], horizon: int, alpha: float = 0.3, **_) -> List[float]:
    """Simple exponential smoothing: a flat forecast at the smoothed level."""
    level = float(y[0])
    for v in y[1:]:
        level = alpha * float(v) + (1.0 - alpha) * level
    return [level] * horizon


def forecast_holt_damped(y: Sequence[float], horizon: int, alpha: float = 0.3,
                         beta: float = 0.1, phi: float = 0.9, **_) -> List[float]:
    """Holt's linear method with a damped trend (Gardner & McKenzie).

    Damping (phi < 1) makes the trend flatten as the horizon extends instead of
    extrapolating a straight line indefinitely -- the standard defence against
    a short-run slope producing an absurd long-run level, which matters here
    because the horizon is long relative to the history.
    """
    if len(y) < 2:
        return forecast_naive(y, horizon)
    level = float(y[0])
    trend = float(y[1]) - float(y[0])
    for v in y[1:]:
        prev_level = level
        level = alpha * float(v) + (1.0 - alpha) * (level + phi * trend)
        trend = beta * (level - prev_level) + (1.0 - beta) * phi * trend
    out, damp_sum = [], 0.0
    for h in range(1, horizon + 1):
        damp_sum += phi ** h
        out.append(level + damp_sum * trend)
    return out


def forecast_seasonal_naive_drift(y: Sequence[float], horizon: int,
                                  m: int = SEASONAL_PERIOD, **_) -> List[float]:
    """Seasonal naive plus a linear drift term.

    Repeats the last observed cycle (capturing the weekly publishing pattern)
    and adds the average historical slope (capturing the level moving). Added
    after testing showed the suite could not forecast a series with BOTH a
    trend and weekly seasonality: seasonal_naive ignores the trend and
    holt_damped ignores the season, so on a trending seasonal series neither
    beat the naive benchmark and every such sector was declined.
    """
    if len(y) < m + 1:
        return forecast_drift(y, horizon)
    slope = (float(y[-1]) - float(y[0])) / (len(y) - 1)
    return [float(y[-m + (h % m)]) + slope * (h + 1) for h in range(horizon)]


def forecast_holt_winters(y: Sequence[float], horizon: int, alpha: float = 0.3,
                          beta: float = 0.1, gamma: float = 0.2,
                          phi: float = 0.95, m: int = SEASONAL_PERIOD,
                          **_) -> List[float]:
    """Additive Holt-Winters with a damped trend: level + trend + seasonality.

    The textbook method for a series carrying both a trend and a fixed-period
    season, which is exactly the shape of daily advisory intensity (weekday
    publishing cycle plus a drifting overall level).
    """
    n = len(y)
    if n < 2 * m:
        return forecast_holt_damped(y, horizon, alpha=alpha, beta=beta, phi=phi)

    vals = [float(v) for v in y]
    first = sum(vals[:m]) / m
    second = sum(vals[m:2 * m]) / m
    level = first
    trend = (second - first) / m
    season = [vals[i] - first for i in range(m)]

    for t in range(n):
        s_idx = t % m
        s_old = season[s_idx]
        prev_level = level
        level = alpha * (vals[t] - s_old) + (1.0 - alpha) * (level + phi * trend)
        trend = beta * (level - prev_level) + (1.0 - beta) * phi * trend
        season[s_idx] = gamma * (vals[t] - level) + (1.0 - gamma) * s_old

    out, damp = [], 0.0
    for h in range(1, horizon + 1):
        damp += phi ** h
        out.append(level + damp * trend + season[(n + h - 1) % m])
    return out


#: (name, function, parameter grid). Grids are coarse and fixed: this is
#: model selection, not hyper-parameter mining, and every extra grid point is
#: another chance to win the backtest by luck. Order is fixed so that ties
#: resolve deterministically toward the simpler model listed first.
CANDIDATES: List[Tuple[str, Callable, List[Dict]]] = [
    ("naive",          forecast_naive,          [{}]),
    ("seasonal_naive", forecast_seasonal_naive, [{"m": SEASONAL_PERIOD}]),
    ("mean",           forecast_mean,           [{}]),
    ("drift",          forecast_drift,          [{}]),
    ("ses",            forecast_ses,            [{"alpha": a} for a in (0.1, 0.3, 0.5, 0.7, 0.9)]),
    ("seasonal_naive_drift", forecast_seasonal_naive_drift, [{"m": SEASONAL_PERIOD}]),
    ("holt_damped",    forecast_holt_damped,
     [{"alpha": a, "beta": b, "phi": p}
      for a in (0.2, 0.4, 0.6)
      for b in (0.05, 0.15, 0.30)
      for p in (0.80, 0.90, 0.98)]),
    ("holt_winters",   forecast_holt_winters,
     [{"alpha": a, "beta": b, "gamma": g, "phi": p, "m": SEASONAL_PERIOD}
      for a in (0.2, 0.5)
      for b in (0.05, 0.20)
      for g in (0.10, 0.30)
      for p in (0.90, 0.98)]),
]


# -----------------------------------------------------------------------------
# Scoring
# -----------------------------------------------------------------------------

def mase_scale(y_train: Sequence[float], m: int = 1) -> Optional[float]:
    """Denominator for MASE: mean absolute error of an m-step naive forecast.

    Returns None for a constant series, where the scale is 0 and MASE is
    undefined. A constant series is unforecastable in the MASE sense and the
    caller must decline rather than divide by zero.
    """
    if len(y_train) <= m:
        return None
    diffs = [abs(float(y_train[i]) - float(y_train[i - m])) for i in range(m, len(y_train))]
    scale = sum(diffs) / len(diffs)
    return scale if scale > 1e-12 else None


def rolling_origin_backtest(
    y: Sequence[float],
    horizon: int,
    fn: Callable,
    params: Dict,
    min_train: int,
    step: int = 1,
) -> Optional[Dict]:
    """Score one candidate by walk-forward validation.

    At each origin the model sees only y[:origin] and is scored on the
    `horizon` actual values that follow. The model is never scored on a value
    it was fitted on.

    Returns None when the series cannot support even one origin.
    """
    n = len(y)
    origins = list(range(min_train, n - horizon + 1, step))
    if not origins:
        return None

    abs_errors: List[float] = []
    per_step: List[List[float]] = [[] for _ in range(horizon)]
    scales: List[float] = []

    for origin in origins:
        train = y[:origin]
        actual = y[origin:origin + horizon]
        scale = mase_scale(train)
        if scale is None:
            continue
        try:
            pred = fn(train, horizon, **params)
        except Exception:
            return None
        if len(pred) != horizon:
            return None
        scales.append(scale)
        for h in range(horizon):
            err = abs(float(pred[h]) - float(actual[h]))
            abs_errors.append(err)
            per_step[h].append(err)

    if not abs_errors or not scales:
        return None

    scale = sum(scales) / len(scales)
    return {
        "mase": (sum(abs_errors) / len(abs_errors)) / scale,
        "mae": sum(abs_errors) / len(abs_errors),
        "n_origins": len(scales),
        "per_step_errors": per_step,
    }


def _empirical_interval(per_step: List[List[float]], level: float = 0.80) -> List[float]:
    """Half-width per horizon step, from the observed backtest error spread.

    Uses the `level` quantile of absolute errors actually made at that step.
    No distributional assumption: if the errors are skewed or fat-tailed, the
    interval reflects that, because it is those very errors.
    """
    out = []
    carried = 0.0
    for errs in per_step:
        if errs:
            s = sorted(errs)
            idx = min(len(s) - 1, max(0, int(round(level * (len(s) - 1)))))
            carried = s[idx]
        # A step with no observations inherits the previous step's width
        # rather than reporting a falsely narrow interval.
        out.append(round(carried, 3))
    return out


# -----------------------------------------------------------------------------
# Public entry point
# -----------------------------------------------------------------------------

def select_and_forecast(
    y: Sequence[float],
    horizon: int,
    min_history: int = DEFAULT_MIN_HISTORY_DAYS,
    observed_days: Optional[int] = None,
    span_days: Optional[int] = None,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    mase_threshold: float = MASE_PUBLISH_THRESHOLD,
) -> Dict:
    """Choose the best-validated model and forecast with it, or decline.

    Args:
        y:             observed daily values, chronological and contiguous.
        horizon:       days ahead to forecast.
        min_history:   minimum observations before forecasting is attempted.
        observed_days: days actually observed (defaults to len(y)).
        span_days:     calendar days the series spans, for coverage checking.
        min_coverage:  minimum observed/span ratio.
        mase_threshold: a model must score strictly below this to publish.

    Returns a dict that ALWAYS carries `publishable` and `reason`. When
    publishable is False there is no forecast series in the result at all --
    there is deliberately nothing a caller could mistake for a prediction.
    """
    n = len(y)

    def decline(reason: str, **extra) -> Dict:
        out = {"publishable": False, "reason": reason, "observations": n,
               "horizon": horizon, "model": None, "mase": None}
        out.update(extra)
        return out

    if n < min_history:
        return decline(
            f"{n} observed days available; {min_history} required before a "
            f"{horizon}-day forecast can be validated"
        )

    if observed_days is not None and span_days:
        coverage = observed_days / float(span_days)
        if coverage < min_coverage:
            return decline(
                f"observation coverage {coverage:.0%} over {span_days} days is below "
                f"the {min_coverage:.0%} minimum; the series has gaps too large to "
                "treat as a daily series",
                coverage=round(coverage, 3),
            )

    # Enough room to both fit and validate: at least two seasonal cycles of
    # training data before the first origin, and at least three origins.
    min_train = max(2 * SEASONAL_PERIOD, min_history - horizon, horizon)
    if n - horizon - min_train < 2:
        return decline(
            f"{n} observed days cannot support rolling-origin validation of a "
            f"{horizon}-day horizon (needs at least {min_train + horizon + 2} days)"
        )

    results: List[Dict] = []
    for name, fn, grid in CANDIDATES:
        for params in grid:
            scored = rolling_origin_backtest(y, horizon, fn, params, min_train)
            if scored is None:
                continue
            results.append({"model": name, "params": params, **scored})

    if not results:
        return decline("no candidate model could be validated on this series")

    # Deterministic: lowest MASE wins; ties break toward the model listed first
    # in CANDIDATES (the simpler one), then toward the earlier grid point.
    order = {name: i for i, (name, _, _) in enumerate(CANDIDATES)}
    results.sort(key=lambda r: (round(r["mase"], 9), order[r["model"]]))
    best = results[0]

    benchmark = next((r for r in results if r["model"] == "naive"), None)

    if best["mase"] >= mase_threshold:
        return decline(
            f"best model '{best['model']}' scored MASE {best['mase']:.3f} over "
            f"{best['n_origins']} backtest origins, which does not beat the naive "
            f"benchmark (MASE < {mase_threshold}); no forecast is published",
            model=best["model"], mase=round(best["mase"], 4),
            n_origins=best["n_origins"],
        )

    point = best_fn_forecast(y, horizon, best)
    interval = _empirical_interval(best["per_step_errors"])

    return {
        "publishable": True,
        "reason": (
            f"'{best['model']}' beat the naive benchmark with MASE "
            f"{best['mase']:.3f} over {best['n_origins']} rolling-origin backtests"
        ),
        "model": best["model"],
        "params": best["params"],
        "mase": round(best["mase"], 4),
        "mae": round(best["mae"], 4),
        "n_origins": best["n_origins"],
        "observations": n,
        "horizon": horizon,
        "forecast": [round(float(v), 3) for v in point],
        "interval_half_width": interval,
        "lower": [round(max(0.0, float(p) - w), 3) for p, w in zip(point, interval)],
        "upper": [round(float(p) + w, 3) for p, w in zip(point, interval)],
        "benchmark_mase": round(benchmark["mase"], 4) if benchmark else None,
        "candidates_evaluated": len(results),
        "validation": "rolling_origin_backtest",
        "interval_method": "empirical_backtest_quantile_80",
    }


def best_fn_forecast(y: Sequence[float], horizon: int, best: Dict) -> List[float]:
    """Refit the winning configuration on the FULL history and forecast."""
    fn = next(f for name, f, _ in CANDIDATES if name == best["model"])
    return fn(y, horizon, **best["params"])
