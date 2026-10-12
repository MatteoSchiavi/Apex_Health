"""Pure explicit-goal and recorded-segmentation gates; no database needed."""
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace as Row
import pytest
from app.services.gym_progression import gym_progression
from app.services.interval_detection import automatic_intervals
from app.services.sport_progress import goal_progress, history_buckets

TODAY = date(2026,10,12)
AT = datetime(2026,10,12,10,tzinfo=UTC)


def activity(ident=1, **changes):
    return Row(**{"id":ident,"start_time":AT-timedelta(days=1),"duration_s":600,
        "distance_m":6000,"source_metrics":{},"data_completeness":"full",**changes})


def streams(step=1, field="speed", interval=True):
    rows = []
    for i in range(0,601,step):
        high = 120 <= i < 180 or 240 <= i < 300 or 360 <= i < 420
        value = (5 if high else 3) if interval else 3
        rows.append(Row(t_offset_s=i,speed=value,power=value*100))
    return rows


def goal(metric="weekly_distance_km",target=20,**fields):
    return {"measurable_goal":{"metric":metric,"target":target,**fields}}


def test_goal_baselines_and_events_never_become_explicit_targets():
    assert goal_progress({"weekly_distance_km":20,"event":{"title":"Marathon"}},[])["value"] is None


def test_latest_completed_week_exact_units_provenance_and_no_stale_fallback():
    rows = [activity(),activity(2,start_time=AT-timedelta(days=7))]
    weeks = history_buckets(rows,TODAY-timedelta(days=14),TODAY,"UTC")
    result = goal_progress(goal(),weeks,end=TODAY,today=TODAY,profile_revision=3)
    assert result["value"]["measurement"] == 12
    assert result["value"]["progress_pct"] == 60
    assert result["value"]["measurement_unit"] == "km"
    assert result["quality"]["window_start"] == "2026-10-05"
    assert result["quality"]["window_end"] == "2026-10-11"
    assert "activity:2" in result["source_dependencies"]
    duration = goal_progress(goal("weekly_duration_min",30),weeks,end=TODAY,today=TODAY)
    assert duration["value"]["measurement"] == 20
    assert goal_progress(goal(),weeks[1:],end=TODAY,today=TODAY,complete=False)["value"] is None
    assert goal_progress(goal(),history_buckets([],TODAY-timedelta(days=14),TODAY,"UTC"),end=TODAY,today=TODAY)["value"] is None


def test_weekly_goal_refuses_clipped_week_and_missing_distance():
    rows = [activity(),activity(2,distance_m=None)]
    weeks = history_buckets(rows,TODAY-timedelta(days=7),TODAY,"UTC")
    assert goal_progress(goal(),weeks,end=TODAY,today=TODAY)["value"] is None
    clipped = history_buckets([activity()],TODAY-timedelta(days=3),TODAY,"UTC")
    assert goal_progress(goal(),clipped,end=TODAY,today=TODAY)["value"] is None


def test_longest_goal_selects_matching_recorded_winner_and_incomplete_unavailable():
    rows = [activity(),activity(2,distance_m=15000)]
    result = goal_progress(goal("longest_distance_km",20),[],rows=rows)
    assert result["value"]["measurement"] == 15 and result["value"]["activity_id"] == 2
    assert result["source_dependencies"][-1] == "activity:2:distance_m"
    assert goal_progress(goal("longest_distance_km",20),[],rows=rows,complete=False)["value"] is None
    rows[0].distance_m = None
    assert goal_progress(goal("longest_distance_km",20),[],rows=rows)["value"] is None


def test_power_goal_uses_maximum_exact_duration_not_average_or_shorter_effort():
    rows = [activity(),activity(2)]
    data = {1:streams(),2:streams(interval=False)}
    for r in data[2]: r.power = 450
    result = goal_progress(goal("best_power_w",500,duration_s=45),[],rows=rows,streams=data)
    assert result["value"]["measurement"] == 500
    assert result["value"]["activity_id"] == 1
    assert result["value"]["duration_s"] == 45
    assert goal_progress(goal("best_power_w",500),[],rows=rows,streams=data)["value"] is None
    assert goal_progress(goal("best_power_w",500,duration_s=45),[],rows=rows,streams=data,streams_complete=False)["value"] is None
    for r in data[1]: r.power = None
    assert goal_progress(goal("best_power_w",500,duration_s=45),[],rows=rows,streams=data)["value"]["measurement"] == 450


def test_shared_strength_recipe_same_exercise_latest_comparable_and_reps_gate():
    squat = Row(id=1,name="Squat",equipment="barbell")
    press = Row(id=2,name="Leg press",equipment="machine")
    logs = [(Row(id=1,done_at=AT-timedelta(days=10),reps_done=5,weight_kg=60),squat),
        (Row(id=2,done_at=AT-timedelta(days=1),reps_done=5,weight_kg=75),squat),
        (Row(id=3,done_at=AT-timedelta(days=1),reps_done=12,weight_kg=150),squat),
        (Row(id=4,done_at=AT,reps_done=5,weight_kg=200),press)]
    shared = gym_progression(logs,"UTC")
    result = goal_progress(goal("exercise_estimated_1rm_kg",100,exercise="Squat"),[],strength=shared)
    assert result["value"]["measurement"] == 87.5
    assert result["value"]["reference_estimate_kg"] == 70
    assert result["value"]["change_pct"] == 25
    assert result["quality"]["measurement_formula_version"] == "epley-recorded-sets-v1"
    assert "gym_set_log:4" not in result["source_dependencies"]
    shared["history_complete"] = False
    assert goal_progress(goal("exercise_estimated_1rm_kg",100,exercise="Squat"),[],strength=shared)["value"] is None


def test_strength_missing_weight_is_unavailable_and_same_named_catalog_ids_never_mix():
    exercise = Row(id=1,name="Squat",equipment="barbell")
    log = Row(id=1,done_at=AT,reps_done=5,weight_kg=None)
    shared = gym_progression([(log,exercise)],"UTC")
    assert shared["sessions"][0]["volume_kg"] is None
    assert shared["sessions"][0]["observed_weight_sets"] == 0
    log.weight_kg = 0
    assert gym_progression([(log,exercise)],"UTC")["sessions"][0]["volume_kg"] == 0
    log.weight_kg = 60
    other = Row(id=2,name="Squat",equipment="machine")
    shared = gym_progression([(log,exercise),(Row(id=2,done_at=AT,reps_done=5,weight_kg=100),other)],"UTC")
    assert goal_progress(goal("exercise_estimated_1rm_kg",100,exercise="Squat"),[],strength=shared)["value"] is None


@pytest.mark.parametrize("field",["speed","power"])
def test_interval_candidates_recorded_levels_units_and_irregular_supported_samples(field):
    regular = automatic_intervals(activity(),streams(),field=field)
    irregular = automatic_intervals(activity(),[r for r in streams() if r.t_offset_s%3 != 1],field=field)
    assert regular["value"]["candidate_count"] == 3
    assert irregular["value"]["candidate_count"] == 3
    assert regular["value"]["intervals"][0]["duration_s"] == 60
    assert regular["value"]["signal_unit"] == ("W" if field == "power" else "m/s")
    assert regular["formula_version"] == "recorded-level-segmentation-v1"
    assert "fixed_method_cutoffs_not_physiological_thresholds" in regular["limitations"]


def test_interval_steady_is_eligible_without_candidates_missing_sparse_and_bounds_refused():
    steady = automatic_intervals(activity(),streams(interval=False))
    assert steady["value"]["candidate_count"] == 0
    assert automatic_intervals(activity(),streams(step=10))["value"] is None
    assert automatic_intervals(activity(),streams(),complete=False)["unavailable_reason"] == "input_limit_exceeded"
    rows = streams()
    for r in rows[150:220]: r.speed = None
    assert automatic_intervals(activity(),rows)["value"] is None
    rows = streams()
    rows[200].t_offset_s = rows[199].t_offset_s
    assert automatic_intervals(activity(),rows)["unavailable_reason"] == "invalid_or_nonmonotonic_stream_offsets"
    assert automatic_intervals(activity(duration_s=25000),streams())["value"] is None


def test_missing_bins_never_bridge_effort_recovery_into_repeated_pattern():
    rows = streams()
    # Each gap is small in whole-activity coverage but removes the recovery
    # boundary; detection must not bridge incomplete bins.
    for r in rows:
        if 225 <= r.t_offset_s < 240 or 345 <= r.t_offset_s < 360:
            r.speed = None
    result = automatic_intervals(activity(),rows)
    assert result["value"]["candidate_count"] == 0
