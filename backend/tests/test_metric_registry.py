"""Scientific definitions and authentic computation snapshots (no database needed)."""
from datetime import date, datetime, timedelta, timezone
import json
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.features import scores, load
from app.features.discipline import aerobic_decoupling
from app.features.engine import _compute_day, _readings_by_local_day, _select_hrv_series
from app.features.weights import load_weight_selection, load_weights
from app.metrics.provenance import baseline_snapshot, metric_snapshot, valid_snapshot
from app.metrics.registry import METRIC_REGISTRY, metric_catalog
from app.models.wellness import DailyBiometric, HrvReading, SleepSession
from app.models.activity import Activity, ActivityStream

DAY = date(2026, 10, 5)
WEIGHTS = {
    "recovery_score": {"hrv_deviation": 0.4, "resting_hr_deviation": 0.3,
                       "sleep_quality": 0.2, "prior_day_strain": 0.1},
    "sleep_architecture_score": {"rem_pct": 0.3, "deep_pct": 0.3, "efficiency": 0.4},
    "readiness_score": {"recovery": 0.5, "sleep_architecture": 0.3, "acwr": 0.2},
    "systemic_stress_signal": {"hrv_drop": 0.3, "resting_hr_elevation": 0.3,
                               "respiration_elevation": 0.2, "journal_soreness_fatigue": 0.2},
    "load_spike_indicator": {"acwr_spike": 0.5, "load_spike": 0.5},
}


def make_window(observations=7):
    prior = [DAY - timedelta(days=i) for i in range(1, observations + 1)]
    midnight = datetime(2026, 10, 5, tzinfo=timezone.utc)
    return {
        "tz": ZoneInfo("Europe/Rome"),
        "activities": [Activity(id=1, user_id=1, local_date=DAY - timedelta(days=1),
                                duration_s=3600, avg_hr=None,
                                source_metrics={"garmin": {"training_load": 120, "training_load_method": "garmin_activity_training_load"}})],
        "disciplines": {},
        "streams_by_activity": {}, "hrv_by_local_day": {**{d: 50. for d in prior}, DAY: 60.},
        "biometrics": {d: DailyBiometric(user_id=1, date=d, resting_hr=50 if d != DAY else 52)
                       for d in prior + [DAY]},
        "sleep_sessions": [SleepSession(user_id=1, id=1, local_date=DAY,
                                         start_time=midnight, end_time=midnight + timedelta(hours=8),
                                         total_sleep_s=25000, rem_s=0, deep_s=5000, awake_s=1000,
                                         sleep_score=80, respiration_avg=16)],
        "sleep_awake": {}, "journal_entries": [], "weights": WEIGHTS,
        "weight_selection": {feature: {component: {"value": value, "id": i + 1,
                                                    "version": 3, "effective_from": "2026-10-01T00:00:00+00:00"}
                                        for i, (component, value) in enumerate(weights.items())}
                             for feature, weights in WEIGHTS.items()},
    }


def test_registry_covers_scientific_and_api_contracts():
    required = {"hrv_baseline", "hrv_deviation", "resting_hr_deviation", "sleep_duration",
                "sleep_score", "strain", "recovery", "readiness", "acute_load", "chronic_load",
                "acwr", "aerobic_decoupling", "efficiency_factor", "estimated_ftp",
                "cross_discipline_fatigue", "provider_readiness", "provider_recovery",
                "systemic_stress", "load_spike"}
    assert required <= METRIC_REGISTRY.keys()
    assert "illness_risk" not in METRIC_REGISTRY and "injury_risk" not in METRIC_REGISTRY
    assert len(metric_catalog()) == 26
    for key, definition in METRIC_REGISTRY.items():
        assert definition.id == key
        for field in ("description", "minimum_data_requirements", "missing_data_behavior",
                      "baseline_requirements", "source_requirements", "validation_level",
                      "interpretation", "limitations", "allowed_claims", "prohibited_claims"):
            assert getattr(definition, field)
        assert definition.formula_version if definition.kind in {"derived", "heuristic"} else definition.formula_version is None
        json.dumps(definition.to_dict(), allow_nan=False)
    for metric in ("recovery", "readiness", "sleep_score", "strain", "systemic_stress", "load_spike"):
        assert METRIC_REGISTRY[metric].kind == "heuristic"
        assert METRIC_REGISTRY[metric].validation_level == "heuristic"
    assert METRIC_REGISTRY["provider_sleep_score"].semantic_type == "provider_proprietary"
    assert metric_catalog()["sleep_duration"]["scale"] == 3600
    assert "No universal optimal or healthy ratio band." in METRIC_REGISTRY["acwr"].limitations


def test_baseline_counts_observations_excludes_today_and_future():
    observations = {DAY - timedelta(days=i): 50. for i in range(1, 7)}
    observations[DAY] = 500.
    observations[DAY + timedelta(days=1)] = 500.
    snapshot = baseline_snapshot(observations, DAY, None)
    assert snapshot["observed_days"] == 6
    assert snapshot["required_days"] == 7
    assert snapshot["value"] is None and not snapshot["sufficient"]
    assert snapshot["window_end"] == (DAY - timedelta(days=1)).isoformat()


def test_compute_snapshots_reproduce_every_weighted_score():
    result = _compute_day(SimpleNamespace(id=1, dob=None), DAY, make_window())
    provenance = result["daily"]["calculation_provenance"]
    assert provenance["as_of"] == DAY.isoformat()
    assert provenance["timezone"] == "Europe/Rome"
    for key in ("recovery", "sleep_score", "readiness", "systemic_stress", "load_spike"):
        record = provenance["metrics"][key]
        active = [v for v in record["components"].values() if v["active"]]
        reproduced = sum(v["value"] * v["normalized_weight"] for v in active) * 100
        assert record["value"] == pytest.approx(reproduced, abs=1e-6)
        assert record["value"] == pytest.approx(result["daily"][METRIC_REGISTRY[key].column], abs=1e-6)
        assert all(v["version"] == 3 for v in record["weights"].values())
        assert valid_snapshot(provenance, key, DAY.isoformat(), record["value"]) is record
    recovery = provenance["metrics"]["recovery"]
    assert recovery["baselines"]["hrv"]["value"] == 50
    assert recovery["baselines"]["hrv"]["observed_days"] == 7
    assert recovery["inputs"]["hrv_deviation"] == 20
    assert recovery["sources"]["sleep_quality"] == {"attribution": "apex_derived", "metric": "sleep_score"}
    assert recovery["formula_version"] == "recovery-v2"
    # A true recorded stage duration of zero is an available zero component.
    assert provenance["metrics"]["sleep_score"]["components"]["rem_pct"]["value"] == 0
    json.dumps(provenance, allow_nan=False)


def test_insufficient_baseline_is_absent_in_composite_not_normal():
    result = _compute_day(SimpleNamespace(id=1, dob=None), DAY, make_window(observations=6))
    recovery = result["daily"]["calculation_provenance"]["metrics"]["recovery"]
    assert recovery["inputs"]["hrv_deviation"] is None
    assert recovery["components"]["hrv_deviation"]["value"] is None
    assert not recovery["components"]["hrv_deviation"]["active"]
    assert recovery["baselines"]["hrv"]["observed_days"] == 6
    assert recovery["baselines"]["hrv"]["value"] is None
    assert "hrv_deviation" in recovery["missing_inputs"]
    assert recovery["coverage"]["status"] == "limited_coverage"
    assert recovery["components"]["sleep_quality"]["normalized_weight"] == pytest.approx(2/3)


def test_no_usable_components_has_no_score_or_imputed_confidence():
    components = scores.recovery_components(None, None, None, None)
    assert scores.recovery_score(WEIGHTS["recovery_score"], None, None, None, None) is None
    record = metric_snapshot("recovery", None, {name: None for name in components},
                             components=components, weights=WEIGHTS["recovery_score"])
    assert record["value"] is None
    assert record["coverage"]["available_components"] == 0
    assert all(v["normalized_weight"] is None for v in record["components"].values())
    assert "confidence" not in record


@pytest.mark.parametrize("change", ["missing", "wrong_day", "wrong_value", "nan", "wrong_version"])
def test_stale_or_invalid_snapshot_cannot_explain_assessed_value(change):
    snapshot = {"schema_version": 1, "as_of": DAY.isoformat(), "metrics": {
        "recovery": metric_snapshot("recovery", 80., {"sleep_quality": 80.})}}
    if change == "missing": snapshot = None
    elif change == "wrong_day": snapshot["as_of"] = (DAY - timedelta(days=1)).isoformat()
    elif change == "wrong_value": snapshot["metrics"]["recovery"]["value"] = 79.
    elif change == "nan": snapshot["metrics"]["recovery"]["value"] = float("nan")
    elif change == "wrong_version": snapshot["schema_version"] = 2
    assert valid_snapshot(snapshot, "recovery", DAY.isoformat(), 80) is None


def test_hrv_does_not_mix_sdnn_or_unknown_method_into_rmssd():
    instant = datetime(2026, 10, 5, 8, tzinfo=timezone.utc)
    rows = [HrvReading(id=i, user_id=1, timestamp=instant, reading_type=kind, hrv_ms=value)
            for i, (kind, value) in enumerate([("overnight_avg", 50), ("sdnn", 500),
                                               ("unknown", 300), ("5min", 10)], 1)]
    assert _readings_by_local_day(rows, ZoneInfo("Europe/Rome"), DAY, DAY) == {DAY: 50.}
    assert _readings_by_local_day(rows[1:3], ZoneInfo("Europe/Rome"), DAY, DAY) == {}


@pytest.mark.asyncio
async def test_weight_selection_retains_version_and_deterministic_tie_break():
    effective = datetime(2026, 10, 1, tzinfo=timezone.utc)
    captured = []
    class Session:
        async def execute(self, statement, parameters):
            captured.append((str(statement), parameters))
            return SimpleNamespace(fetchall=lambda: [("sleep_quality", 0.2, 17, 3, effective)])
    selected = await load_weight_selection(Session(), "recovery_score", effective)
    assert selected == {"sleep_quality": {"value": .2, "id": 17, "version": 3,
                                          "effective_from": effective.isoformat()}}
    assert "effective_from DESC, id DESC" in captured[0][0]
    assert "effective_from <= :cutoff" in captured[0][0]
    assert await load_weights(Session(), "recovery_score", effective) == {"sleep_quality": .2}


def test_missing_load_source_does_not_fabricate_rest_or_improve_recovery():
    window = make_window()
    window["activities"] = []
    daily = _compute_day(SimpleNamespace(id=1, dob=None), DAY, window)["daily"]
    assert daily["strain_score"] is None
    assert daily["training_load_acute"] is None
    assert daily["training_load_chronic"] is None
    recovery = daily["calculation_provenance"]["metrics"]["recovery"]
    assert recovery["inputs"]["prior_day_strain"] is None
    assert not recovery["components"]["prior_day_strain"]["active"]
    assert daily["load_metadata"]["availability"] == "unavailable"


def test_excluded_session_is_unknown_load_even_with_earlier_source_history():
    window = make_window()
    window["activities"].append(Activity(id=2, user_id=1, local_date=DAY,
                                         duration_s=3600, avg_hr=None, source_metrics={}))
    daily = _compute_day(SimpleNamespace(id=1, dob=None), DAY, window)["daily"]
    assert daily["strain_score"] is None
    assert daily["load_metadata"]["excluded_sessions"] == 1
    assert daily["data_completeness"] == "partial"


def test_cold_start_load_distribution_component_is_absent_not_normal():
    assert scores.load_spike_component(100, 0, 0, active_days=6) is None
    assert scores.load_spike_indicator({"acwr_spike": .5, "load_spike": .5},
                                       2., 100, 0, 0, active_days=6) == 100
    daily = _compute_day(SimpleNamespace(id=1, dob=None), DAY, make_window())["daily"]
    spike = daily["calculation_provenance"]["metrics"]["load_spike"]
    assert spike["formula_version"] == "load-spike-v2"
    assert spike["components"]["load_spike"]["value"] is None
    assert spike["components"]["acwr_spike"]["normalized_weight"] == 1
    assert not spike["baselines"]["load_distribution"]["sufficient"]


@pytest.mark.parametrize("second_half_hr,expected", [(150, 0.), (165, 100 * (1 - 150/165))])
def test_decoupling_aligns_second_half_offsets(second_half_hr, expected):
    activity = Activity(id=1, user_id=1, duration_s=1200)
    streams = [ActivityStream(t_offset_s=offset, power=200, hr=hr)
               for offset, hr in [(0, 150), (300, 150), (600, second_half_hr), (900, second_half_hr)]]
    assert aerobic_decoupling(activity, streams) == pytest.approx(expected)


def test_decoupling_absent_second_half_hr_is_unavailable():
    activity = Activity(id=1, user_id=1, duration_s=1200)
    streams = [ActivityStream(t_offset_s=offset, power=200, hr=150 if offset < 600 else 0)
               for offset in (0, 300, 600, 900)]
    assert aerobic_decoupling(activity, streams) is None


def test_invalid_contributor_cannot_gain_explanation_from_finite_score():
    snapshot = {"schema_version": 1, "as_of": DAY.isoformat(), "metrics": {
        "recovery": metric_snapshot("recovery", 80., {"sleep_quality": float("nan")})}}
    assert valid_snapshot(snapshot, "recovery", DAY.isoformat(), 80) is None


def hrv_context_rows():
    rows = []
    for index in range(8):
        local_day = DAY - timedelta(days=index)
        for provider, hour, value in (("garmin", 6, 50), ("whoop", 7, 70)):
            rows.append(HrvReading(id=len(rows) + 1, user_id=1,
                                   timestamp=datetime.combine(local_day, datetime.min.time(), timezone.utc) + timedelta(hours=hour),
                                   reading_type="overnight_avg", origin=provider, method="RMSSD",
                                   hrv_ms=value + 10 if index == 0 else value))
    return rows


@pytest.mark.parametrize("main,expected_today,expected_baseline", [("garmin", 60, 50), ("whoop", 80, 70)])
def test_hrv_main_provider_selects_one_baseline_context(main, expected_today, expected_baseline):
    values, provenance = _select_hrv_series(hrv_context_rows(), ZoneInfo("Europe/Rome"),
                                           DAY - timedelta(days=28), DAY, main)
    assert values[DAY] == expected_today
    assert all(value == expected_baseline for day, value in values.items() if day < DAY)
    assert {source["provider"] for source in provenance.values()} == {main}
    assert {source["measurement_method"] for source in provenance.values()} == {"RMSSD"}
    assert len(values) == 8


def test_hrv_selection_without_main_is_deterministic_latest_current_context():
    rows = hrv_context_rows()
    values, provenance = _select_hrv_series(rows, ZoneInfo("Europe/Rome"), DAY - timedelta(days=28), DAY)
    reverse_values, _ = _select_hrv_series(list(reversed(rows)), ZoneInfo("Europe/Rome"), DAY - timedelta(days=28), DAY)
    assert values == reverse_values
    assert values[DAY] == 80
    assert provenance[DAY]["provider"] == "whoop"


def test_hrv_source_change_does_not_borrow_legacy_or_overnight_baseline():
    legacy = [HrvReading(id=i, user_id=1, timestamp=datetime.combine(DAY - timedelta(days=i), datetime.min.time(), timezone.utc),
                         reading_type="overnight_avg", hrv_ms=50) for i in range(1, 8)]
    current = HrvReading(id=9, user_id=1, timestamp=datetime(2026, 10, 5, 8, tzinfo=timezone.utc),
                         reading_type="overnight_avg", origin="garmin", method="RMSSD", hrv_ms=60)
    values, provenance = _select_hrv_series(legacy + [current], ZoneInfo("Europe/Rome"), DAY - timedelta(days=28), DAY)
    assert values == {DAY: 60}
    current.reading_type = "5min"
    overnight = [row for row in hrv_context_rows() if row.origin == "garmin" and row.timestamp.date() < DAY]
    values, provenance = _select_hrv_series(overnight + [current], ZoneInfo("Europe/Rome"), DAY - timedelta(days=28), DAY)
    assert values == {DAY: 60}
    assert provenance[DAY]["measurement_context"] == "daytime"


def test_hrv_recorded_sdnn_and_unknown_origin_cannot_feed_generic_rmssd():
    instant = datetime(2026, 10, 5, 8, tzinfo=timezone.utc)
    rows = [HrvReading(id=i, user_id=1, timestamp=instant, reading_type="overnight_avg", origin=origin, method=method, hrv_ms=50)
            for i, (origin, method) in enumerate([("apple_healthkit", "SDNN"), ("garmin", "SDNN"),
                                                ("unknown_vendor", "RMSSD"), ("garmin", None)], 1)]
    assert _readings_by_local_day(rows, ZoneInfo("Europe/Rome"), DAY, DAY) == {}


def test_recovery_uses_apex_architecture_not_vendor_sleep_score():
    window = make_window()
    window["sleep_sessions"][0].origin = "garmin"
    first = _compute_day(SimpleNamespace(id=1, dob=None), DAY, window)["daily"]
    window["sleep_sessions"][0].sleep_score = 1
    second = _compute_day(SimpleNamespace(id=1, dob=None), DAY, window)["daily"]
    assert first["recovery_score"] == second["recovery_score"]
    recovery = second["calculation_provenance"]["metrics"]["recovery"]
    assert recovery["inputs"]["sleep_quality"] == second["sleep_architecture_score"]
    architecture = second["calculation_provenance"]["metrics"]["sleep_score"]
    assert architecture["sources"]["rem_pct"]["provider"] == "garmin"


def test_sleep_stages_select_one_coherent_main_source_night():
    window = make_window()
    window["sleep_sessions"][0].origin = "garmin"
    whoop = SleepSession(id=2, user_id=1, origin="whoop", local_date=DAY,
                         start_time=datetime(2026, 10, 4, 20, tzinfo=timezone.utc),
                         end_time=datetime(2026, 10, 5, 7, tzinfo=timezone.utc),
                         total_sleep_s=30000, rem_s=6000, deep_s=6000, awake_s=1000)
    window["sleep_sessions"].append(whoop)
    window["main_provider"] = "garmin"
    record = _compute_day(SimpleNamespace(id=1, dob=None), DAY, window)["daily"]["calculation_provenance"]["metrics"]["sleep_score"]
    assert record["inputs"]["total_sleep_s"] == 25000
    assert record["inputs"]["rem_pct"] == 0
    assert record["sources"]["deep_pct"]["provider"] == "garmin"


@pytest.mark.parametrize("value", [None, -1, float("nan"), float("inf"), float("-inf"), "invalid", True, False])
def test_corrupt_garmin_load_is_excluded_as_unknown(value):
    activity = Activity(id=1, user_id=1, local_date=DAY, duration_s=3600,
                        source_metrics={"garmin": {"training_load": value, "training_load_method": "garmin_activity_training_load"}})
    daily, selected, metadata = load.consistent_window_loads([(activity, [])], None)
    assert daily == {} and selected == {}
    assert metadata["included_sessions"] == 0
    assert metadata["excluded_sessions"] == 1


@pytest.mark.parametrize("value", [0, 123.45, "12.5"])
def test_valid_garmin_load_retains_recorded_scale_and_zero(value):
    activity = Activity(id=1, user_id=1, local_date=DAY, duration_s=3600,
                        source_metrics={"garmin": {"training_load": value, "training_load_method": "garmin_activity_training_load"}})
    daily, selected, metadata = load.consistent_window_loads([(activity, [])], None)
    assert daily == {DAY: float(value)} and selected == {1: float(value)}
    assert metadata["method"] == "garmin_recorded"
    assert metadata["excluded_sessions"] == 0


@pytest.mark.parametrize("field,value", [("inputs", []), ("components", []), ("weights", []),
                                          ("baselines", None), ("sources", []), ("coverage", 0),
                                          ("methodology", "invalid"), ("missing_inputs", None),
                                          ("missing_components", [0]), ("value", True),
                                          ("value", "80"), ("formula_version", 1),
                                          ("components", {"sleep_quality": 80}),
                                          ("weights", {"sleep_quality": 0.2})])
def test_malformed_snapshot_shape_is_not_exposed(field, value):
    snapshot = {"schema_version": 1, "as_of": DAY.isoformat(), "metrics": {
        "recovery": metric_snapshot("recovery", 80., {"sleep_quality": 80.})}}
    snapshot["metrics"]["recovery"][field] = value
    assert valid_snapshot(snapshot, "recovery", DAY.isoformat(), 80) is None


def test_resting_hr_source_change_rebuilds_coverage_without_borrowing_legacy():
    from app.services.biometric_provenance import set_biometric
    window = make_window()
    set_biometric(window['biometrics'][DAY], 'resting_hr', 52, 'whoop')
    for prior, bio in window['biometrics'].items():
        if prior != DAY:
            set_biometric(bio, 'resting_hr', 50, 'garmin')
    record = _compute_day(SimpleNamespace(id=1, dob=None), DAY, window)['daily']['calculation_provenance']['metrics']['recovery']
    assert record['baselines']['resting_hr']['observed_days'] == 0
    assert record['inputs']['resting_hr_deviation'] is None
    assert record['sources']['resting_hr_deviation']['provider'] == 'whoop'
