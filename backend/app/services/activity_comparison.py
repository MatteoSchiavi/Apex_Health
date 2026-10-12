"""Bounded user comparison annotations without mutating imported measurements."""
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json

from pydantic import ValidationError

from app.schemas.activity_comparison import ComparisonContextIn, ComparisonContextUpdate

PREFIX = "user_asserted:"
PROVENANCE_KIND = "athlete_asserted_comparison_context"


def assertion_key(provider: str) -> str:
    return PREFIX + provider


def context_revision(metrics, providers: list[str]) -> str:
    blocks = metrics if isinstance(metrics, dict) else {}
    # Provider context changes invalidate the review too, without returning any
    # provider/private payload to the editor. Includes provenance to prevent ABA.
    relevant = {
        provider: {
            "assertion": blocks.get(assertion_key(provider)),
            "recorded": blocks.get(provider, {}).get("comparison_context")
            if isinstance(blocks.get(provider), dict) else None,
        } for provider in sorted(providers)
    }
    encoded = json.dumps(relevant, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def comparison_view(activity, providers: list[str]) -> dict:
    blocks = activity.source_metrics if isinstance(activity.source_metrics, dict) else {}
    assertions = []
    recorded_providers = []
    for provider in providers:
        block = blocks.get(assertion_key(provider))
        if isinstance(block, dict) and isinstance(block.get("provenance"), dict) and block["provenance"].get("kind") == PROVENANCE_KIND:
            try:
                context = ComparisonContextIn.model_validate(block.get("comparison_context"))
            except ValidationError:
                context = None
            if context:
                saved_at = block["provenance"].get("asserted_at")
                assertions.append({"provider": provider, "context": context.model_dump(), "provenance": {
                    "kind": PROVENANCE_KIND, "source_provider": provider, "verified": False,
                    "asserted_at": saved_at if isinstance(saved_at, str) and len(saved_at) <= 64 else None,
                }})
        imported = blocks.get(provider)
        if isinstance(imported, dict) and isinstance(imported.get("comparison_context"), dict):
            recorded_providers.append(provider)
    weather = activity.weather_snapshot if isinstance(activity.weather_snapshot, dict) else {}
    fields = ("temperature_c", "relative_humidity", "wind_speed_kmh")
    # Merely communicate input availability; don't substitute daily summaries
    # or user estimates for session measurements.
    from math import isfinite
    def finite_weather(value):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        try:
            return isfinite(value)
        except (OverflowError, ValueError):
            return False
    weather_available = all(finite_weather(weather.get(k)) for k in fields)
    return {"activity_id": activity.id, "revision": context_revision(activity.source_metrics, providers),
            "providers": providers, "assertions": assertions, "recorded_context_providers": recorded_providers,
            "outdoor_weather_available": weather_available}


def update_assertion(metrics, providers: list[str], payload: ComparisonContextUpdate, *, user_id: int, now: datetime | None = None) -> dict:
    """Caller must hold the activity row lock and persist the audit atomically."""
    if payload.provider not in providers:
        raise ValueError("Provider is not linked to this owned activity")
    if metrics is not None and not isinstance(metrics, dict):
        raise ValueError("Malformed source metrics cannot be replaced by a context edit")
    if payload.expected_revision != context_revision(metrics, providers):
        raise RuntimeError("Comparison context changed; reload and review before saving")
    result = deepcopy(metrics or {})
    key = assertion_key(payload.provider)
    existing = result.get(key)
    if existing is not None and (not isinstance(existing, dict) or not isinstance(existing.get("provenance"), dict) or existing["provenance"].get("kind") != PROVENANCE_KIND):
        raise ValueError("Reserved comparison namespace is occupied; imported data was preserved")
    if payload.context is None:
        preserved = {k: v for k, v in (existing or {}).items() if k not in {"comparison_context", "provenance"}}
        if preserved:
            result[key] = preserved
        else:
            result.pop(key, None)
    else:
        result[key] = {**(existing or {}), "comparison_context": payload.context.model_dump(), "provenance": {
            **(existing.get("provenance", {}) if existing else {}),
            "kind": PROVENANCE_KIND, "source_provider": payload.provider, "asserted_by_user_id": user_id,
            "asserted_at": (now or datetime.now(UTC)).isoformat(), "verified": False,
        }}
    return result
