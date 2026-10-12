"""Pure legacy/detail power parity and truthful missing-data regressions."""
from types import SimpleNamespace as Row

import pytest

from app.features.discipline import normalized_power, variability_index, aerobic_decoupling, efficiency_factor
from app.services.cycling_metrics import dense_power, normalized_power as segmented_np


def rows(seconds=3600):
    return [Row(t_offset_s=i, power=200, hr=120 if i < seconds/2 else 132, speed=8)
        for i in range(seconds+1)]


def test_legacy_and_detail_reject_two_samples_and_sparse_recording():
    activity = Row(duration_s=3600, source_metrics={}, avg_hr=126)
    for stream in (rows()[::10], [rows()[0], rows()[-1]]):
        assert normalized_power(stream, 3600) is None
        assert not dense_power(activity, stream)[1]
        assert variability_index(stream, 3600) is None
        assert aerobic_decoupling(activity, stream) is None
        assert efficiency_factor(activity, stream, 'road_cycling') is None


def test_legacy_and_detail_dense_np_have_identical_complete_window_definition():
    stream = rows()
    for row in stream:
        row.power = 100 if row.t_offset_s < 1800 else 300
    activity = Row(duration_s=3600, source_metrics={})
    segments, valid, _ = dense_power(activity, stream)
    assert valid
    expected = (sum((sum(segments[0][i:i+30])/30)**4
        for i in range(len(segments[0])-29)) / (len(segments[0])-29))**.25
    assert normalized_power(stream, 3600) == pytest.approx(expected)
    assert normalized_power(stream, 3600) == segmented_np(segments)


def test_legacy_dense_steady_decoupling_still_computes_with_hr_drift():
    stream = rows()
    assert normalized_power(stream, 3600) == pytest.approx(200)
    assert variability_index(stream, 3600) == pytest.approx(1)
    assert aerobic_decoupling(Row(duration_s=3600), stream) == pytest.approx(100*(1-120/132))


def test_legacy_interval_decoupling_and_discontinuous_hr_are_unavailable():
    stream = rows()
    for row in stream:
        row.power = 100 if (row.t_offset_s//120)%2 else 300
    assert aerobic_decoupling(Row(duration_s=3600), stream) is None
    stream = rows()
    for row in stream[1200:2400]:
        row.hr = None
    assert aerobic_decoupling(Row(duration_s=3600), stream) is None


def test_np_does_not_interpolate_across_a_gap_or_fill_missing_power():
    stream = rows()
    stream[1800].power = None
    assert normalized_power(stream, 3600) is not None  # remaining coverage/segments eligible
    segments, valid, _ = dense_power(Row(duration_s=3600, source_metrics={}), stream)
    assert valid and len(segments) == 2
    assert normalized_power(stream, 3600) == segmented_np(segments)
    assert normalized_power(rows()[::30], 3600) is None


def test_golden_sparse_discipline_inputs_have_null_efficiency_and_decoupling():
    from tests.helpers.golden import load_fixture
    fixture = load_fixture()
    expected = {row['date']:row for row in fixture['expected']['discipline_rows']}
    for activity in fixture['activities']:
        if activity['discipline'] != 'road_cycling':
            continue
        raw = activity['streams']
        stream = [Row(t_offset_s=t, power=raw['power'][i], hr=raw['hr'][i])
            for i,t in enumerate(raw['t'])]
        a = Row(duration_s=activity['duration_s'], avg_hr=activity['avg_hr'])
        assert normalized_power(stream, a.duration_s) is None
        assert efficiency_factor(a, stream, 'road_cycling') is None
        assert aerobic_decoupling(a, stream) is None
        key = activity['start'][:10]
        assert expected[key]['efficiency_factor'] is None
        assert expected[key]['aerobic_decoupling_pct'] is None
