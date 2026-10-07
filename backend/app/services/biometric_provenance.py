"""Attribute every canonical biometric write, including equal-value refreshes.

Value equality is not provider ownership. Legacy rows without attribution
remain unknown until a provider actually writes the field.
"""

FIELDS = {"resting_hr", "weight_kg", "body_fat_pct", "vo2max", "steps", "floors", "spo2_avg", "hydration_ml"}


def biometric_origin(row, field):
    return ((row.source_metrics or {}).get("_canonical_sources") or {}).get(field)


def set_biometric(row, field, value, origin):
    if field not in FIELDS or not isinstance(origin, str) or not origin:
        raise ValueError("Canonical biometric field and origin are required")
    setattr(row, field, value)
    metrics = dict(row.source_metrics or {})
    owners = dict(metrics.get("_canonical_sources") or {})
    if value is None:
        owners.pop(field, None)
    else:
        owners[field] = origin
    if owners:
        metrics["_canonical_sources"] = owners
    else:
        metrics.pop("_canonical_sources", None)
    if origin != "apple_healthkit" and "apple_healthkit" in metrics:
        apple = dict(metrics["apple_healthkit"] or {})
        supplied = dict(apple.get("canonical_supplier_fields") or {})
        supplied.pop(field, None)
        apple["canonical_supplier_fields"] = supplied
        metrics["apple_healthkit"] = apple
    row.source_metrics = metrics
