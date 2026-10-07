"""Bounded exact calculation records, produced during computation only.

These records are not statistically estimated confidence. No helper reconstructs
constituents for a historical score or guesses a missing provider identity.
"""
from math import isfinite
from datetime import date, timedelta

from app.metrics.registry import METRIC_REGISTRY


def baseline_snapshot(values: dict[date, float], day: date, value: float | None) -> dict:
    observed = [d for d in values if day - timedelta(days=28) <= d < day]
    return {"value": value, "observed_days": len(observed), "required_days": 7,
            "observations": {d.isoformat(): values[d] for d in sorted(observed)},
            "window_start": (day - timedelta(days=28)).isoformat(),
            "window_end": (day - timedelta(days=1)).isoformat(),
            "aggregation": "mean_observed_days", "sufficient": value is not None}


def metric_snapshot(metric: str, value: float | None, inputs: dict, *,
                    components: dict | None = None, weights: dict | None = None,
                    weight_selection: dict | None = None, baselines: dict | None = None,
                    sources: dict | None = None, methodology: dict | None = None) -> dict:
    definition = METRIC_REGISTRY[metric]
    components = components or {}
    weights = weights or {}
    selected = weight_selection or {}
    active = {name: component for name, component in components.items()
              if component is not None and name in weights}
    weight_sum = sum(weights[name] for name in active)
    component_records = {
        name: {"value": component, "active": name in active,
               "weight": weights.get(name),
               "missing_reason": "input_or_baseline_unavailable" if component is None
                                 else "weight_unavailable" if name not in weights else None,
               "normalized_weight": weights[name] / weight_sum if name in active and weight_sum > 0 else None}
        for name, component in components.items()
    }
    return {"metric": metric, "value": None if value is None else round(value, 6),
            "formula_version": definition.formula_version,
            "validation_level": definition.validation_level,
            "inputs": inputs, "components": component_records,
            "weights": {name: {"value": weight, "id": selected.get(name, {}).get("id"),
                              "version": selected.get(name, {}).get("version"),
                              "effective_from": selected.get(name, {}).get("effective_from")}
                        for name, weight in weights.items()},
            "baselines": baselines or {}, "sources": sources or {},
            "missing_inputs": [name for name, item in inputs.items() if item is None],
            "missing_components": [name for name, item in component_records.items() if not item["active"]],
            "coverage": {"available_components": len(active), "total_components": len(components),
                         "weight_sum": weight_sum,
                         "status": "sufficient_coverage" if components and len(active) == len(components)
                                   else "limited_coverage" if components else "see_source_coverage"},
            "methodology": methodology or {}}


def valid_snapshot(snapshot: dict | None, metric: str, day: str, value: float) -> dict | None:
    """Validate an assessed row's snapshot before a presentation adapter uses it."""
    if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1 or snapshot.get("as_of") != day:
        return None
    record = snapshot.get("metrics", {}).get(metric) if isinstance(snapshot.get("metrics"), dict) else None
    if not isinstance(record, dict) or record.get("metric") != metric:
        return None
    version = record.get("formula_version")
    if not isinstance(version, str) or not version.strip():
        return None
    if any(not isinstance(record.get(key), dict) for key in
           ("inputs", "components", "weights", "baselines", "sources", "coverage", "methodology")):
        return None
    if any(not isinstance(record.get(key), list) or any(not isinstance(item, str) for item in record[key])
           for key in ("missing_inputs", "missing_components")):
        return None
    if isinstance(record.get("value"), bool) or not isinstance(record.get("value"), (int, float)) or isinstance(value, bool):
        return None
    if any(not isinstance(item, dict) for item in record["components"].values()):
        return None
    if any(not isinstance(item, dict) for item in record["weights"].values()):
        return None
    def finite_numbers(item):
        if isinstance(item, (int, float)):
            return isfinite(item)
        if isinstance(item, dict):
            return all(finite_numbers(value) for value in item.values())
        if isinstance(item, list):
            return all(finite_numbers(value) for value in item)
        return True
    if not finite_numbers(record):
        return None
    try:
        assessed, recorded = float(value), float(record["value"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not isfinite(assessed) or not isfinite(recorded) or abs(assessed - recorded) > 0.000001:
        return None
    return record
