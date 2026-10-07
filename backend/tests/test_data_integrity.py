from datetime import UTC, datetime, date, timedelta
from types import SimpleNamespace
from app.features.load import consistent_window_loads, rolling_sum, acwr_from
from app.services.sleep_summary import awake_seconds, summary_awake
from app.queries.rankings import period_window, _exclusive_end_day


def test_awake_epochs_union_clipped_and_missing_is_unknown():
    start = datetime(2026, 10, 6, 0, tzinfo=UTC)
    end = start + timedelta(hours=1)
    segments = [
        {'activityLevel': 0, 'startGMT': (start-timedelta(minutes=5)).isoformat(), 'endGMT': (start+timedelta(minutes=10)).isoformat()},
        {'activityLevel': 0, 'startGMT': (start+timedelta(minutes=5)).isoformat(), 'endGMT': (start+timedelta(minutes=15)).isoformat()},
    ]
    assert awake_seconds({'sleepLevels': segments}, start, end) == 900
    assert awake_seconds({}, start, end) is None
    night = SimpleNamespace(awake_s=0, total_sleep_s=3000, start_time=start, end_time=end)
    assert summary_awake(night) == 0
    assert summary_awake(night, 900) == 900


def test_provider_load_has_one_scale_for_both_windows():
    day = date(2026, 10, 7)
    activities = [(SimpleNamespace(id=i, local_date=day-timedelta(days=i), duration_s=600,
                    avg_hr=None, training_load=100, source_metrics={'garmin': {}}), []) for i in range(28)]
    loads, selected, metadata = consistent_window_loads(activities, None)
    assert metadata['method'] == 'garmin_recorded'
    assert len(selected) == 28
    assert rolling_sum(loads, day, 7) == 700
    assert rolling_sum(loads, day, 28) == 2800
    assert acwr_from(700, 2800) == 1


def test_incompatible_provider_load_is_excluded():
    activity = SimpleNamespace(id=1, local_date=date(2026, 10, 7), duration_s=600,
                               avg_hr=None, training_load=100, source_metrics={'coros': {}})
    loads, _, metadata = consistent_window_loads([(activity, [])], None)
    assert loads == {}
    assert metadata['excluded_sessions'] == 1


def test_weekly_and_monthly_end_at_now():
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    assert period_window(SimpleNamespace(period='weekly'), now) == (datetime(2026, 10, 5, tzinfo=UTC), now)
    assert period_window(SimpleNamespace(period='monthly'), now) == (datetime(2026, 10, 1, tzinfo=UTC), now)


def test_period_daily_totals_include_today_but_midnight_is_exclusive():
    assert _exclusive_end_day(datetime(2026, 10, 7, 12, tzinfo=UTC)) == date(2026, 10, 8)
    assert _exclusive_end_day(datetime(2026, 10, 7, tzinfo=UTC)) == date(2026, 10, 7)
