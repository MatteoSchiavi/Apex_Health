"""Deterministic progress gates and comparisons, runnable without DB fixtures."""
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace as Row
import pytest
from app.services.sport_progress import (adherence, aerobic_trend, best_duration_power,
    consistency, date_bounds, history_buckets, long_run_progression, outcome,
    power_curve, recent_body_mass, recorded_best_efforts, stream_distribution, utc_bounds, volume_bucket)

DAY = date(2026, 10, 12)
AT = datetime(2026, 10, 12, 10, tzinfo=UTC)


def activity(ident=1, days=0, **changes):
    return Row(**{"id":ident,"start_time":AT+timedelta(days=days),"distance_m":10000,
        "duration_s":3600,"elevation_gain_m":None,"source_metrics":{},"data_completeness":"full",
        "weather_snapshot":None, **changes})


def samples(seconds=3600, **changes):
    return [Row(t_offset_s=i,hr=120,speed=3,power=200,cadence=80,**changes) for i in range(seconds+1)]


def test_range_default_and_exact_inclusive_cap():
    assert date_bounds(None,None,"UTC",now=AT) == (DAY-timedelta(days=83),DAY)
    assert date_bounds(DAY-timedelta(days=729),DAY,"UTC") == (DAY-timedelta(days=729),DAY)
    for start,end in ((DAY+timedelta(days=1),DAY),(DAY-timedelta(days=730),DAY)):
        with pytest.raises(ValueError):
            date_bounds(start,end,"UTC")


def test_account_today_and_dst_boundaries():
    assert date_bounds(None,None,"America/Los_Angeles",now=datetime(2026,10,12,1,tzinfo=UTC))[1] == date(2026,10,11)
    left,right = utc_bounds(date(2026,3,8),date(2026,3,8),"America/New_York")
    assert (right-left).total_seconds() == 23*3600


def test_volume_missing_never_zero_partial_revealed_and_actual_zero_retained():
    empty = volume_bucket([],DAY,DAY)
    assert empty["distance_m"] is None and empty["duration_s"] is None and empty["activity_count"] == 0
    missing = volume_bucket([activity(distance_m=None)],DAY,DAY)
    assert missing["distance_m"] is None and missing["quality"]["partial_measurements"]
    measured = volume_bucket([activity(distance_m=0,elevation_gain_m=0),activity(ident=2,distance_m=None)],DAY,DAY)
    assert measured["distance_m"] == 0 and measured["elevation_gain_m"] == 0
    assert measured["observed"]["distance"] == 1


@pytest.mark.parametrize("bad", [None,-1,float("nan"),float("inf"),True])
def test_invalid_volumes_do_not_turn_into_real_measurements(bad):
    assert volume_bucket([activity(distance_m=bad)],DAY,DAY)["distance_m"] is None


def test_weekly_monthly_frequency_history_and_partial_weeks():
    rows = [activity(1,days=-1),activity(2,days=0),activity(3,days=1)]
    weeks = history_buckets(rows,DAY-timedelta(days=2),DAY+timedelta(days=1),"UTC")
    assert [w["activity_count"] for w in weeks] == [1,2]
    assert sum(w["distance_m"] for w in weeks) == 30000
    months = history_buckets(rows,DAY-timedelta(days=30),DAY+timedelta(days=1),"UTC",monthly=True)
    assert [m["activity_count"] for m in months] == [0,3]
    assert months[0]["distance_m"] is None
    result = consistency(rows,weeks,"UTC")
    assert result["value"]["training_days"] == 3 and result["value"]["active_week_pct"] == 100
    assert consistency(rows,weeks,"UTC",complete=False)["value"] is None


def test_exact_longest_prior_30d_excludes_same_timestamp_later_and_outside():
    current = activity(distance_m=15000)
    history = [current,activity(2,-30,distance_m=10000),activity(3,-29,distance_m=12000),
        activity(4,-31,distance_m=99999),activity(5,0,distance_m=90000),activity(6,1,distance_m=99999)]
    result = long_run_progression(current,history,"UTC")
    assert result["value"]["change_pct"] == 25
    assert result["value"]["reference_activity_id"] == 3
    assert result["value"]["reference_distance_m"] == 12000
    assert result["value"]["window_start"] == "2026-09-12T10:00:00+00:00"
    assert result["value"]["window_end_exclusive"] == "2026-10-12T10:00:00+00:00"
    indexed = {a.start_time.date():[a] for a in history if a.id != 5}
    assert long_run_progression(current,history,"UTC",day_index=indexed)["value"] == result["value"]


def test_long_run_exact_elapsed_window_includes_earlier_same_day_and_respects_dst():
    current = activity()
    earlier = activity(2,start_time=AT-timedelta(hours=1),distance_m=18000)
    boundary = activity(3,start_time=AT-timedelta(days=30),distance_m=20000)
    outside = activity(4,start_time=AT-timedelta(days=30,seconds=1),distance_m=99999)
    result = long_run_progression(current,[earlier,boundary,outside],"America/Los_Angeles")
    assert result["value"]["reference_activity_id"] == boundary.id
    result = long_run_progression(current,[earlier,outside],"America/Los_Angeles")
    assert result["value"]["reference_activity_id"] == earlier.id
    from zoneinfo import ZoneInfo
    current.start_time = datetime(2026,3,9,0,30,tzinfo=ZoneInfo("America/New_York"))
    dst = long_run_progression(current,[],"America/New_York")
    left = datetime.fromisoformat(dst["quality"]["window_start"])
    right = datetime.fromisoformat(dst["quality"]["window_end_exclusive"])
    assert (right-left).total_seconds() == 30*86400


@pytest.mark.parametrize("changes",[{"distance_m":0},{"distance_m":None},{"distance_m":float("nan")},
    {"duration_s":0},{"data_completeness":"unknown"}])
def test_long_run_invalid_current_or_reference(changes):
    assert long_run_progression(activity(**changes),[activity(2,-1)],"UTC")["value"] is None
    assert long_run_progression(activity(),[activity(2,-1,**changes)],"UTC")["value"] is None


def test_long_run_no_reference_incomplete_negative_and_tie():
    assert long_run_progression(activity(),[],"UTC")["unavailable_reason"] == "no_eligible_prior_30_day_run"
    refs = [activity(2,-2,distance_m=20000),activity(3,-1,distance_m=20000)]
    result = long_run_progression(activity(),refs,"UTC")
    assert result["value"]["change_pct"] == -50 and result["value"]["reference_activity_id"] == 2
    assert long_run_progression(activity(),refs,"UTC",complete=False)["value"] is None


def test_adherence_requires_confirmed_session_identity_not_same_day():
    plans = [Row(id=i,date=DAY) for i in (10,11,12,13)]
    links = [Row(activity_id=1,planned_session_id=10,method="user_confirmed"),Row(activity_id=2,planned_session_id=13,method="automatic")]
    checks = [Row(id=1,revision=1,planned_session_id=11,status="partial"),Row(id=2,revision=1,planned_session_id=12,status="skipped")]
    result = adherence(plans,links,checks,[activity(),activity(2)],DAY)["value"]
    assert result == {"planned_count":4,"completed_count":1,"partial_count":1,"skipped_count":1,"unresolved_count":1,"completed_session_ids":[10],"completion_pct":25}
    assert adherence([],[],[],[],DAY)["value"] is None
    assert adherence(plans,links,checks,[activity()],DAY,complete=False)["value"] is None


def test_explicit_partial_feedback_does_not_become_completed_association():
    link = Row(activity_id=1,planned_session_id=10,method="user_confirmed")
    check = Row(id=2,revision=3,planned_session_id=10,status="partial")
    value = adherence([Row(id=10,date=DAY)],[link],[check],[activity()],DAY)["value"]
    assert value["partial_count"] == 1 and value["completion_pct"] == 0


def test_dense_power_exact_best_windows_and_zero_no_sparse_interpolation():
    a = activity(duration_s=600)
    rows = samples(600)
    for row in rows[300:305]:
        row.power = 500
    result = {m["key"]:m for m in best_duration_power(a,rows)}
    assert result["best_power_5s"]["value"] == 500
    assert result["best_power_300s"]["value"] == 205
    assert result["best_power_1200s"]["value"] is None
    assert all(m["value"] is None for m in best_duration_power(a,rows[::10]))
    for row in rows:
        row.power = 0
    assert best_duration_power(a,rows)[0]["value"] == 0


def test_best_power_gap_not_crossed_and_history_provenance():
    a,b = activity(1,duration_s=600),activity(2,duration_s=600)
    stream = samples(600)
    stream[300].power = None
    assert next(m for m in best_duration_power(a,stream) if m["key"] == "best_power_600s")["value"] is None
    streams = {1:samples(600),2:samples(600)}
    for s in streams[2]:
        s.power = 250
    winner = power_curve([a,b],streams,complete=False)[0]
    assert winner["value"] == 250 and winner["quality"]["activity_id"] == 2
    assert winner["quality"]["history_complete"] is False


def test_recorded_best_efforts_provider_and_elapsed_moving_stay_separate():
    first = activity(source_metrics={"garmin":{"best_efforts":[{"distance_m":5000,"duration_s":1400,"duration_convention":"elapsed"}]}})
    second = activity(2,source_metrics={"garmin":{"best_efforts":[{"distance_m":5000,"duration_s":1300,"duration_convention":"elapsed"},
        {"distance_m":5000,"duration_s":1200,"duration_convention":"moving"}]},"strava":{"best_efforts":[{"distance_m":5000,"duration_s":1250,"duration_convention":"elapsed"}]}})
    result = recorded_best_efforts([first,second])
    assert len(result) == 3
    assert result[0]["value"]["duration_s"] == 1300
    assert all(r["kind"] == "recorded" for r in result)
    assert recorded_best_efforts([activity()])[0]["value"] is None


@pytest.mark.parametrize("effort",[{"distance_m":20000,"duration_s":1000,"duration_convention":"elapsed"},
    {"distance_m":5000,"duration_s":4000,"duration_convention":"elapsed"},
    {"distance_m":5000,"duration_s":1200},{"distance_m":0,"duration_s":1200,"duration_convention":"elapsed"}])
def test_invalid_or_implicit_best_efforts_not_verified(effort):
    assert recorded_best_efforts([activity(source_metrics={"garmin":{"best_efforts":[effort]}})])[0]["value"] is None


def easy(ident,days,speed=3,hr=120,**ctx):
    a = activity(ident,days,source_metrics={"garmin":{"comparison_context":{"effort_type":"easy","route_id":"route-1","terrain":"road","indoor":True,"time_convention":"elapsed",**ctx}}})
    s = samples()
    for row in s:
        row.speed, row.hr = speed,hr
    return a,s


def test_speed_hr_trend_comparable_measured_speed():
    a,s = easy(1,-10)
    b,t = easy(2,0,speed=3.3,hr=122)
    metric = aerobic_trend([a,b],{1:s,2:t},{1:"running",2:"running"},"UTC")
    assert metric["value"]["speed_change_pct"] == pytest.approx(10)
    assert metric["value"]["reference_hr_bpm"] == 120
    assert metric["value"]["current_hr_bpm"] == 122


@pytest.mark.parametrize("fault", ["no_context","different_route","different_hr","intervals","no_weather","sparse","discipline","same_day"])
def test_insufficient_aerobic_comparisons_are_explicit(fault):
    a,s = easy(1,-10)
    b,t = easy(2,0,speed=3.3)
    names = {1:"running",2:"running"}
    if fault == "no_context": b.source_metrics = {}
    if fault == "different_route": b.source_metrics["garmin"]["comparison_context"]["route_id"] = "route2"
    if fault == "different_hr":
        for row in t: row.hr = 140
    if fault == "intervals":
        for row in t: row.speed = 2 if row.t_offset_s%2 else 5
    if fault == "no_weather": b.source_metrics["garmin"]["comparison_context"]["indoor"] = False
    if fault == "sparse": t = t[::10]
    if fault == "discipline": names[2] = "road_cycling"
    if fault == "same_day": a.start_time = b.start_time-timedelta(hours=1)
    result = aerobic_trend([a,b],{1:s,2:t},names,"UTC")
    assert result["value"] is None and result["unavailable_reason"] == "insufficient_comparable_easy_steady_recordings"


def observation(**changes):
    return Row(**{"id":1,"revision":2,"measured_at":AT-timedelta(days=3),"current":True,"availability":"available",
        "unit":"kg","value":{"value":70},"quality_flags":[],"origin":"garmin","acquisition":"verified_import",**changes})


def test_mass_recent_current_recorded_source_not_user_confirmation():
    result = recent_body_mass([observation()],AT)
    assert result["value"]["kg"] == 70 and result["value"]["user_asserted"] is False
    assert result["source_dependencies"] == ["observation:1:2"]
    manual = recent_body_mass([observation(origin="manual",acquisition="user_assertion")],AT)
    assert manual["value"]["user_asserted"] is True
    assert recent_body_mass([observation()],AT,excluded={1})["value"] is None
    assert recent_body_mass([observation()],AT,complete=False)["value"] is None


@pytest.mark.parametrize("changes",[{"measured_at":AT+timedelta(seconds=1)},{"measured_at":AT-timedelta(days=31)},
    {"unit":"lb"},{"current":False},{"availability":"not_measured"},{"quality_flags":["invalid"]},
    {"value":{"value":0}},{"value":{"value":float("nan")}}])
def test_mass_stale_future_invalid_missing_or_excluded(changes):
    assert recent_body_mass([observation(**changes)],AT)["value"] is None


def test_distributions_time_weighted_and_missing_coverage():
    a = activity(duration_s=300)
    rows = samples(300)
    metric = stream_distribution(a,rows,"hr",10,"bpm")
    assert metric["value"] == [{"lower":120,"upper":130,"duration_s":300,"unit":"bpm"}]
    assert stream_distribution(a,rows[::10],"hr",10,"bpm")["value"] is None
    assert outcome("missing",None,"s","requires_recording",reason="missing")["unavailable_reason"] == "missing"

# Advanced calculations remain conditional on recorded inputs and protocols.
from app.services.sport_progress import (recorded_running_dynamics,distance_half_split,
    lap_average_distribution,cadence_relationship,critical_speed,efficiency_retention,
    route_progress,climb_progress,unsupported)


def test_recorded_dynamics_explicit_units_and_provider_no_inferred_fields():
    a = activity(source_metrics={"garmin":{"running_dynamics":{"ground_contact_time_ms":250,"vertical_oscillation_cm":8,"stride_length_m":1.2}},
        "coros":{"running_dynamics":{"ground_contact_time_ms":260,"stride_length_m":float("nan"),"vertical_oscillation":7}}})
    result = recorded_running_dynamics(a)
    assert result["kind"] == "recorded" and len(result["value"]) == 4
    assert {r["unit"] for r in result["value"]} == {"ms","cm","m"}
    assert result["value"][-1]["provider"] == "coros"
    assert recorded_running_dynamics(activity())["value"] is None
    assert recorded_running_dynamics(activity(source_metrics={"garmin":{"running_dynamics":{"stride_length_m":float("inf"),"ground_contact_time_ms":-1}}}))["value"] is None


def laps_for_split(times=(300,300,330,330),distance=1000,**extras):
    return [Row(lap_index=i,distance_m=distance,duration_s=t,extras=extras,avg_hr=120+i*10,avg_power=200+i*20) for i,t in enumerate(times)]


def test_positive_negative_and_even_equal_distance_lap_halves():
    a = activity(distance_m=4000,duration_s=1260)
    value = distance_half_split(a,[],laps_for_split())["value"]
    assert value["classification"] == "positive" and value["pace_change_pct"] == pytest.approx(10)
    assert value["first_distance_m"] == value["second_distance_m"] == 2000
    assert value["duration_convention"] == "timer" and value["method"] == "recorded_equal_distance_laps"
    assert distance_half_split(a,[],laps_for_split((330,330,300,300)))["value"]["classification"] == "negative"
    assert distance_half_split(a,[],laps_for_split((300,300,300,300)))["value"]["classification"] == "even"


@pytest.mark.parametrize("fault",["missing","coverage","duplicate","convention","unequal_boundary"])
def test_split_invalid_laps_do_not_interpolate_or_guess(fault):
    a = activity(distance_m=4000,duration_s=1260)
    laps = laps_for_split()
    if fault == "missing": laps[1].distance_m = None
    if fault == "coverage": a.distance_m = 10000
    if fault == "duplicate": laps[1].lap_index = laps[0].lap_index
    if fault == "convention": laps[0].extras = {"duration_convention":"elapsed"}
    if fault == "unequal_boundary": laps[0].distance_m,laps[3].distance_m = 1200,800
    assert distance_half_split(a,[],laps)["value"] is None


def test_speed_integrated_half_split_complete_coverage_and_gaps():
    a = activity(distance_m=900,duration_s=300)
    rows = samples(300)
    value = distance_half_split(a,rows,[])["value"]
    assert value["classification"] == "even" and value["first_distance_m"] == 450
    assert value["method"] == "recorded_speed_sample_hold_integration"
    assert distance_half_split(a,rows[::10],[])["value"] is None
    assert distance_half_split(activity(distance_m=3000,duration_s=300),rows,[])["value"] is None
    assert distance_half_split(a,rows[1:],[])["value"] is None


def test_lap_average_distribution_is_explicitly_distinct_from_sensor_histogram():
    a = activity(duration_s=1200,distance_m=4000)
    laps = laps_for_split((300,300,300,300),avg_cadence=170)
    m = lap_average_distribution(a,laps,"hr",10,"bpm")
    assert len(m["value"]) == 4 and m["quality"]["coverage"] == 1
    assert "lap_means_are_not_sample_distribution" in m["limitations"]
    cadence = lap_average_distribution(a,laps,"cadence",10,"cadence/min")
    assert cadence["value"][0]["duration_s"] == 1200
    laps[0].avg_hr = None
    assert lap_average_distribution(a,laps,"hr",10,"bpm")["value"] is None


def test_cadence_power_hr_relationship_exact_time_weighted_correlation():
    a = activity(duration_s=600)
    rows = samples(600)
    for row in rows:
        row.cadence = 70+row.t_offset_s%20
        row.power = row.cadence*3
        row.hr = 200-row.cadence
    result = cadence_relationship(a,rows,cycling=True)
    pairs = {(r["first"],r["second"]):r["correlation"] for r in result["value"]}
    assert pairs[("cadence","power")] == pytest.approx(1)
    assert pairs[("cadence","hr")] == pytest.approx(-1)
    assert cadence_relationship(a,rows[::10],cycling=True)["value"] is None
    assert cadence_relationship(a,samples(600),cycling=True)["value"] is None
    for row in rows: row.power = float("inf")
    broken = cadence_relationship(a,rows,cycling=True)
    assert next(r for r in broken["quality"]["pairs"] if r["second"] == "power")["correlation"] is None


def performance(ident,days,duration,**changes):
    record = {"verified":True,"maximal":True,"protocol":"time_trial","distance_m":duration*4+100,
        "duration_s":duration,"duration_unit":"s","distance_unit":"m","duration_convention":"elapsed",
        "surface":"track","distance_method":"track_laps",**changes}
    return activity(ident,days,source_metrics={"garmin":{"verified_performance":record}})


def test_critical_speed_only_explicit_verified_maximal_protocols_with_fit_quality():
    rows = [performance(1,-20,180),performance(2,-15,360),performance(3,-10,720)]
    result = critical_speed(rows,AT)
    assert result["value"]["speed_m_s"] == 4 and result["value"]["distance_intercept_m"] == 100
    assert result["value"]["r_squared"] == 1 and result["value"]["estimated"] is True
    assert result["quality"]["fit_count"] == 3 and len(result["source_dependencies"]) == 3
    assert result["quality"]["window_days"] == 180
    assert critical_speed(rows,AT,complete=False)["value"] is None


@pytest.mark.parametrize("changes",[{"verified":False},{"maximal":False},{"protocol":"easy_run"},
    {"duration_unit":"min"},{"duration_convention":"moving"},{"surface":"hilly"},
    {"distance_method":"gps"},{"duration_s":100},{"duration_s":float("nan")},
    {"distance_m":float("inf")}])
def test_critical_speed_rejects_missing_or_mismatched_protocols(changes):
    rows = [performance(1,-20,180),performance(2,-15,360),performance(3,-10,720,**changes)]
    result = critical_speed(rows,AT)
    assert result["value"] is None and result["unavailable_reason"] == "insufficient_protocol_qualified_performances"


def test_critical_speed_stale_future_distinctness_and_fit_rejection():
    rows = [performance(1,-20,180),performance(2,-15,360),performance(3,-10,720)]
    rows[0].start_time = AT-timedelta(days=181)
    assert critical_speed(rows,AT)["value"] is None
    rows[0].start_time = AT+timedelta(seconds=1)
    assert critical_speed(rows,AT)["value"] is None
    rows = [performance(1,-20,180),performance(2,-15,180),performance(3,-10,180)]
    assert critical_speed(rows,AT)["value"] is None
    rows = [performance(1,-20,180,distance_m=620),performance(2,-15,360,distance_m=1340),performance(3,-10,720,distance_m=2780)]
    assert critical_speed(rows,AT)["unavailable_reason"] == "protocol_records_fail_distance_time_model_fit"


def test_retention_proxy_recorded_steady_halves_and_no_physiological_claim():
    a,rows = easy(1,0)
    for row in rows:
        row.hr = 120 if row.t_offset_s < 1800 else 132
    running = efficiency_retention(a,rows)
    assert running["value"]["retention_pct"] == pytest.approx(100/1.1)
    assert "descriptive_efficiency_proxy_not_measured_durability_or_fatigue" in running["limitations"]
    cycling = efficiency_retention(a,rows,cycling=True)
    assert cycling["value"]["efficiency_unit"] == "W/bpm"
    assert efficiency_retention(activity(),rows)["value"] is None
    assert efficiency_retention(a,rows[::10])["value"] is None
    a.source_metrics["garmin"]["comparison_context"]["time_convention"] = "moving"
    assert efficiency_retention(a,rows)["value"] is None


def test_route_matching_reuses_explicit_identity_and_never_guesses_GPS():
    a,s = easy(1,-10)
    b,t = easy(2,0,speed=3.3,hr=122)
    result = route_progress([a,b],{1:s,2:t},{1:"running",2:"running"},"UTC")
    assert result["key"] == "comparable_route_performance" and result["value"]["speed_change_pct"] == pytest.approx(10)
    b.source_metrics = {}
    assert route_progress([a,b],{1:s,2:t},{1:"running",2:"running"},"UTC")["value"] is None


def climb(ident,days,seconds=600,**ctx):
    segment = {"verified":True,"duration_convention":"elapsed","distance_m":2000,"ascent_m":100,"duration_s":seconds,
        "comparison_context":{"segment_id":"verified-climb-1","terrain":"road","effort_type":"steady","temperature_c":20,"relative_humidity":50,"wind_speed_kmh":5,**ctx}}
    return activity(ident,days,elevation_gain_m=200,source_metrics={"garmin":{"climb_segments":[segment]}})


def test_climb_explicit_verified_segment_context_and_matching_ascent():
    a,b = climb(1,-10),climb(2,0,seconds=500)
    result = climb_progress([a,b],{1:"road_cycling",2:"road_cycling"},AT)
    assert result["value"]["change_pct"] == pytest.approx(20)
    assert result["value"]["reference_ascent_rate_m_h"] == 600
    assert result["value"]["current_ascent_rate_m_h"] == 720
    assert len(result["source_dependencies"]) == 2


@pytest.mark.parametrize("fault",["identity","weather","ascent","discipline","verified","convention","units"])
def test_climb_incompatible_or_missing_segments_remain_unavailable(fault):
    a,b = climb(1,-10),climb(2,0,seconds=500)
    names = {1:"road_cycling",2:"road_cycling"}
    segment = b.source_metrics["garmin"]["climb_segments"][0]
    if fault == "identity": segment["comparison_context"]["segment_id"] = "other-route"
    if fault == "weather": segment["comparison_context"]["wind_speed_kmh"] = 30
    if fault == "ascent": segment["ascent_m"] = 120
    if fault == "discipline": names[2] = "mountain_biking"
    if fault == "verified": segment["verified"] = False
    if fault == "convention": segment["duration_convention"] = "moving"
    if fault == "units": segment["ascent_m"] = float("nan")
    assert climb_progress([a,b],names,AT)["value"] is None


def test_unsupported_model_is_distinct_from_missing_recordings():
    assert all(m["unavailable_reason"].startswith("unsupported_model") for m in unsupported("running"))
    assert unsupported("cycling") == []
