"""Comparison annotations: strict schema, non-destructive edits and progress gates."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as Row

import pytest
from pydantic import ValidationError

from app.schemas.activity_comparison import ComparisonContextIn, ComparisonContextUpdate
from app.services.activity_comparison import assertion_key, comparison_view, context_revision, update_assertion
from app.services.sport_progress import aerobic_trend, comparable_context

AT = datetime(2026, 10, 12, 10, tzinfo=UTC)
CONTEXT = {"route_id": "River loop clockwise", "terrain": "paved", "indoor": True, "time_convention": "elapsed", "effort_type": "easy"}


def request(metrics=None, providers=None, **changes):
    providers = providers or ["strava"]
    return ComparisonContextUpdate.model_validate({"provider": "strava", "expected_revision": context_revision(metrics, providers), "context": CONTEXT, "reviewed": True, **changes})


def activity(ident=1, **changes):
    return Row(**{"id": ident, "start_time": AT, "duration_s": 3600, "distance_m": 10000,
                  "source_metrics": {}, "weather_snapshot": None, **changes})


@pytest.mark.parametrize("field,value", [("route_id", 42), ("route_id", " "), ("route_id", "r" * 121), ("route_id", "river\nloop"),
    ("indoor", "false"), ("indoor", 1), ("terrain", {}), ("effort_type", "maximal"), ("time_convention", "timer")])
def test_context_strict_bounded_identity_and_finite_enums(field, value):
    with pytest.raises(ValidationError):
        ComparisonContextIn.model_validate({**CONTEXT, field: value})


def test_review_is_explicit_and_cannot_write_measurements_or_weather():
    for changes in ({"reviewed": False}, {"reviewed": 1}, {"expected_revision": "1"}, {"provider": "user_asserted:strava"},
                    {"context": {**CONTEXT, "temperature_c": 20}}, {"context": {**CONTEXT, "verified": True}}, {"private": "override"}):
        with pytest.raises(ValidationError):
            request(**changes)


def test_save_preserves_provider_private_metrics_and_tracks_user_provenance():
    metrics = {"strava": {"private": {"token": "private-test-value"}, "distance_m": 10000}, "garmin": ["legacy"]}
    updated = update_assertion(metrics, ["strava"], request(metrics), user_id=7, now=AT)
    assert updated["strava"] == metrics["strava"] and updated["garmin"] == metrics["garmin"]
    assert assertion_key("strava") not in metrics
    block = updated[assertion_key("strava")]
    assert block["comparison_context"] == CONTEXT
    assert block["provenance"]["asserted_by_user_id"] == 7 and block["provenance"]["verified"] is False
    view = comparison_view(activity(source_metrics=updated), ["strava"])
    assert "private-test-value" not in str(view) and view["assertions"][0]["provider"] == "strava"


def test_stale_review_unlinked_provider_and_namespace_collision_preserve_data():
    metrics = update_assertion({}, ["strava"], request(), user_id=1, now=AT)
    with pytest.raises(RuntimeError):
        update_assertion(metrics, ["strava"], request(), user_id=1)
    with pytest.raises(ValueError):
        update_assertion({}, ["garmin"], request(), user_id=1)
    collision = {assertion_key("strava"): {"private": "imported"}}
    with pytest.raises(ValueError):
        update_assertion(collision, ["strava"], request(collision), user_id=1)
    assert collision[assertion_key("strava")] == {"private": "imported"}
    with pytest.raises(ValueError):
        update_assertion(["legacy"], ["strava"], request(["legacy"]), user_id=1)


def test_removal_only_removes_assertion_and_provider_updates_invalidate_review():
    metrics = update_assertion({"strava": {"distance_m": 10000}}, ["strava"], request(), user_id=1, now=AT)
    edited = {**metrics, "strava": {"comparison_context": CONTEXT, "distance_m": 10000}}
    with pytest.raises(RuntimeError):
        update_assertion(edited, ["strava"], request(metrics, context=None), user_id=1)
    assert update_assertion(metrics, ["strava"], request(metrics, context=None), user_id=1) == {"strava": {"distance_m": 10000}}


def test_annotation_reaches_comparable_easy_steady_but_does_not_fabricate_weather():
    metrics = update_assertion({}, ["strava"], request(), user_id=1, now=AT)
    a = activity(source_metrics=metrics)
    assert comparable_context(a)[0] == assertion_key("strava")
    outdoor = update_assertion({}, ["strava"], request(context={**CONTEXT, "indoor": False}), user_id=1, now=AT)
    assert comparable_context(activity(source_metrics=outdoor)) is None
    assert comparison_view(activity(source_metrics=outdoor, weather_snapshot={"temperature_2m_mean": 20}), ["strava"])["outdoor_weather_available"] is False
    b = activity(ident=2, start_time=AT + timedelta(days=7), source_metrics=metrics)
    def samples(speed):
        return [Row(t_offset_s=i, hr=120, speed=speed) for i in range(3601)]
    result = aerobic_trend([a, b], {1: samples(3), 2: samples(3.15)}, {1: "running", 2: "running"}, "UTC")
    assert result["value"]["speed_change_pct"] == pytest.approx(5)
    mismatch = update_assertion({}, ["strava"], request(context={**CONTEXT, "route_id": "Different loop"}), user_id=1, now=AT)
    b.source_metrics = mismatch
    assert aerobic_trend([a, b], {1: samples(3), 2: samples(3.15)}, {1: "running", 2: "running"}, "UTC")["value"] is None
