from datetime import date, timedelta
from types import SimpleNamespace as Row
import pytest
from app.services.cycling_metrics import cycling_metrics, normalized_power

DAY = date(2026, 10, 9)


def metrics(*, power=200, hr=120, ftp=250, age=1, confirmed=True, seconds=3600, sparse=False, moving=True):
    a = Row(id=1, duration_s=seconds, distance_m=30000, elevation_gain_m=300, avg_power=power,
        local_date=DAY, source_metrics={"garmin": {"moving_time_s": seconds}} if moving else {})
    rows = [Row(t_offset_s=i, power=power, hr=hr if i < seconds/2 or hr is None else hr*1.1, speed=8,
        cadence=80) for i in range(0, seconds+1, 10 if sparse else 1)]
    ctx = {"ftp": {"watts": ftp, "measured_on": str(DAY-timedelta(days=age)), "confirmed": confirmed}} if ftp else {}
    return {m["key"]: m for m in cycling_metrics(a, rows, [], context=ctx, activity_day=DAY, profile_revision=1)}


def test_cycling_constant_power_work_np_if_tss_vi_decoupling():
    result = metrics()
    assert result["mechanical_work"]["value"] == 720
    assert result["normalized_power"]["value"] == pytest.approx(200)
    assert result["intensity_factor"]["value"] == pytest.approx(.8)
    assert result["tss_style"]["value"] == pytest.approx(64)
    assert result["variability_index"]["value"] == pytest.approx(1)
    assert result["power_hr_decoupling"]["value"] == pytest.approx(10)
    assert result["tss_style"]["unit"] == "Apex TSS-style"
    for metric in result.values():
        assert metric["formula_version"] == "apex-cycling-v1"


def test_np_fourth_power_rolling_average_reference():
    series = [100]*100 + [300]*100
    averages = [sum(series[i:i+30])/30 for i in range(len(series)-29)]
    reference = (sum(x**4 for x in averages)/len(averages))**.25
    assert normalized_power([series]) == pytest.approx(reference)


@pytest.mark.parametrize("kwargs,reason", [({"ftp": None}, "missing_confirmed_ftp"), ({"confirmed": False}, "missing_confirmed_ftp"),
    ({"age": 91}, "stale_ftp"), ({"age": -1}, "ftp_after_activity")])
def test_ftp_must_be_explicit_confirmed_dated_not_stale(kwargs, reason):
    result = metrics(**kwargs)
    assert result["normalized_power"]["value"] == pytest.approx(200)
    for key in ("intensity_factor", "tss_style"):
        assert result[key]["value"] is None and result[key]["unavailable_reason"] == reason


@pytest.mark.parametrize("kwargs", [{"power": None}, {"sparse": True}, {"seconds": 120}])
def test_missing_sparse_or_short_power_is_never_simulated(kwargs):
    result = metrics(**kwargs)
    assert result["normalized_power"]["value"] is None
    assert result["intensity_factor"]["value"] is None and result["tss_style"]["value"] is None
    assert result["vertical_speed"]["value"] is not None


def test_zero_power_no_division_hr_missing_and_moving_time_required_for_work():
    result = metrics(power=0)
    assert result["normalized_power"]["value"] == 0
    assert result["variability_index"]["value"] is None and result["power_hr_decoupling"]["value"] is None
    assert metrics(hr=None)["power_hr_decoupling"]["value"] is None
    assert metrics(moving=False)["mechanical_work"]["value"] is None
