"""Rolling personal baselines (§7: "rolling personal baseline").

A baseline for day D looks at the prior 28 local days [D-28, D-1].

Two series semantics live in this system and must not be mixed:
- Wellness metrics (HRV, resting HR, respiration): a missing day is a MISSING
  OBSERVATION — baselines skip it and require MIN_OBS observations, else the
  baseline is None and every consumer treats the component as unavailable.
- The training-load series (load.py): a missing day is a real ZERO-LOAD day
  (a rest day). Its mean/std come from load.load_distribution, zero-filled.

All blend weights come from feature_weights (§17); the windows and minimum
observation counts here are functional-form constants, pinned by the
golden-dataset regression tests.
"""

from datetime import date, timedelta

BASELINE_DAYS = 28
MIN_OBS = 7


def _window(day: date, days: int) -> list[date]:
    return [day - timedelta(days=offset) for offset in range(1, days + 1)]


def mean_baseline(
    daily_values: dict[date, float], day: date, days: int = BASELINE_DAYS
) -> float | None:
    """Mean over observed days in [day - days, day - 1]; None under MIN_OBS."""
    obs = [
        daily_values[d]
        for d in _window(day, days)
        if d in daily_values
    ]
    if len(obs) < MIN_OBS:
        return None
    return sum(obs) / len(obs)


def peak_baseline(
    daily_values: dict[date, float], day: date, days: int = BASELINE_DAYS
) -> float:
    """Max over [day - days, day - 1], zero-filled (a rest day is 0, never a
    gap). Callers gate on the series being meaningful (e.g. the discipline
    was active in the last 7 days) and apply their own floor."""
    return max(
        (daily_values.get(d, 0.0) for d in _window(day, days)),
        default=0.0,
    )
