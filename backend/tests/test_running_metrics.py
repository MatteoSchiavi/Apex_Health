from types import SimpleNamespace as Row
from math import sqrt
import pytest
from app.services.endurance_metrics import running_metrics


def activity(**changes):
    return Row(**{"id": 1, "duration_s": 3600, "distance_m": 10000, "elevation_gain_m": 100, "source_metrics": {}, **changes})


def stream(seconds=3600, **changes):
    return [Row(t_offset_s=i, hr=120 if i < seconds/2 else 132, speed=3, **changes) for i in range(seconds+1)]


def metrics(a=None, rows=None, laps=None, **kwargs):
    return {m["key"]: m for m in running_metrics(a or activity(), rows or [], laps or [], **kwargs)}


def test_correct_pace_vertical_cv_efficiency_drift_and_separate_rpe():
    a = activity(source_metrics={"garmin": {"moving_time_s": 3600, "avg_cadence": 170, "hr_zones": [{"name": "zone1", "duration_s": 600}]}})
    laps = [Row(lap_index=i, distance_m=1000, duration_s=360) for i in range(10)]
    result = metrics(a, stream(), laps, rpe=6, rpe_dependency="checkin:1:1")
    assert result["average_pace"]["value"] == 360
    assert result["moving_pace"]["value"] == 360
    assert result["cadence"]["value"] == 170 and result["cadence"]["kind"] == "recorded"
    assert result["vertical_speed"]["value"] == 100
    assert result["split_consistency"]["value"] == 0
    assert result["aerobic_efficiency"]["value"] == pytest.approx(3 / 126)
    assert result["cardiac_drift"]["value"] == pytest.approx(10)
    assert result["hr_zone_time"]["value"][0]["duration_s"] == 600
    assert result["session_rpe_load"]["value"] == 360 and result["session_rpe_load"]["unit"] == "session-RPE min"
    for row in result.values():
        assert row["formula_version"] and row["source_dependencies"] and row["limitations"]


@pytest.mark.parametrize("changes", [{"distance_m": None}, {"distance_m": 0}, {"duration_s": 0}, {"distance_m": float('nan')}])
def test_no_division_or_invented_pace(changes):
    result = metrics(activity(**changes))
    assert result["average_pace"]["value"] is None and result["average_pace"]["unavailable_reason"]


def test_moving_pace_requires_explicit_reliable_moving_time():
    assert metrics()["moving_pace"]["value"] is None
    assert metrics(activity(source_metrics={"garmin": {"moving_time_s": 4000}}))["moving_pace"]["value"] is None
    assert metrics(activity(source_metrics={"strava": {"moving_time_s": 3000}}))["moving_pace"]["value"] == 300


def test_split_cv_known_and_coverage_threshold():
    laps = [Row(lap_index=i, duration_s=value, distance_m=1000) for i, value in enumerate([300, 360, 420])]
    result = metrics(activity(distance_m=3000), laps=laps)
    assert result["split_consistency"]["value"] == pytest.approx(sqrt(2400)/360*100)
    assert metrics(activity(distance_m=10000), laps=laps)["split_consistency"]["value"] is None
    assert metrics(activity(distance_m=3000), laps=laps[:2])["split_consistency"]["value"] is None


@pytest.mark.parametrize("fault", ["missing_hr", "missing_speed", "sparse", "paused", "short"])
def test_drift_unavailable_for_missing_sparse_paused_or_short_effort(fault):
    rows = stream()
    a = activity()
    if fault == "missing_hr":
        for row in rows: row.hr = None
    if fault == "missing_speed":
        for row in rows: row.speed = None
    if fault == "sparse": rows = rows[::10]
    if fault == "paused":
        for row in rows[1700:2000]: row.speed = 0
    if fault == "short":
        rows, a = stream(1200), activity(duration_s=1200)
    value = metrics(a, rows)["cardiac_drift"]
    assert value["value"] is None and value["availability"] == "unavailable"


def test_no_hr_zones_without_explicit_zone_information_and_rpe_zero_honest():
    assert metrics(rows=stream())["hr_zone_time"]["value"] is None
    assert metrics(rpe=None)["session_rpe_load"]["value"] is None
    assert metrics(rpe=0)["session_rpe_load"]["value"] == 0
