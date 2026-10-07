"""Metric explanations expose stored snapshots, never inferred constituents."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.api.metrics import _acwr_calculation_inputs, metric_trend
from app.models.features import DailyFeature
from app.models.wellness import DailyBiometric
from tests.test_garmin_sync import make_garmin_user

END = date(2026, 10, 5)
METADATA = {"method": "garmin_recorded", "unit": "Garmin load"}


@pytest.mark.parametrize("ratio,acute,chronic,metadata", [
    (None, 120, 100, METADATA), (1.2, None, 100, METADATA),
    (1.2, 120, None, METADATA), (1.2, 120, 0, METADATA),
    (1.2, 120, -1, METADATA), (1.2, -120, 100, METADATA),
    (float("nan"), 120, 100, METADATA), (float("inf"), 120, 100, METADATA),
    (1.2, float("inf"), 100, METADATA), (1.2, 120, float("nan"), METADATA),
    (1.2, 120, 100, None), (1.2, 120, 100, {}),
    (1.2, 120, 100, {"method": "", "unit": "Garmin load"}),
    (1.2, 120, 100, {"method": "garmin_recorded", "unit": None}),
])
def test_invalid_snapshots_have_no_contributors(ratio, acute, chronic, metadata):
    assert _acwr_calculation_inputs((END, ratio, acute, chronic, metadata)) is None


def test_stored_method_is_not_invented_or_relabelled():
    output = _acwr_calculation_inputs((END, Decimal("1.2"), Decimal("120"), Decimal("100"),
                                     {"method": "future_method", "unit": "recorded unit"}))
    assert output.methodology == "future_method"
    assert output.contributors[0].unit == "recorded unit/week"
    assert _acwr_calculation_inputs(None) is None


@pytest.mark.asyncio
async def test_acwr_inputs_match_latest_available_displayed_row(db_session):
    user, _ = await make_garmin_user(db_session)
    other, _ = await make_garmin_user(db_session)
    measured = END - timedelta(days=2)
    db_session.add_all([
        DailyFeature(user_id=user.id, date=measured, acwr=1.2,
                     training_load_acute=120, training_load_chronic=100, load_metadata=METADATA),
        DailyFeature(user_id=user.id, date=END, acwr=None,
                     training_load_acute=900, training_load_chronic=300, load_metadata=METADATA),
        DailyFeature(user_id=user.id, date=END+timedelta(days=1), acwr=2,
                     training_load_acute=400, training_load_chronic=200, load_metadata=METADATA),
        DailyFeature(user_id=other.id, date=END, acwr=4,
                     training_load_acute=4000, training_load_chronic=1000, load_metadata=METADATA),
    ])
    await db_session.flush()
    output = await metric_trend("acwr", user=user, session=db_session, days=7, end=END)
    inputs = output.calculation_inputs
    assert output.stats["latest"] == 1.2
    assert inputs.metric == output.metric == "acwr"
    assert inputs.as_of == next(p.date for p in reversed(output.points) if p.value is not None) == measured.isoformat()
    assert inputs.model_dump() == {
        "metric": "acwr", "as_of": measured.isoformat(), "methodology": "garmin_recorded",
        "contributors": [
            {"metric": "acute_load", "value": 120.0, "unit": "Garmin load/week"},
            {"metric": "chronic_load", "value": 100.0, "unit": "Garmin load/week"},
        ],
    }


@pytest.mark.asyncio
async def test_missing_latest_snapshot_does_not_borrow_older_inputs(db_session):
    user, _ = await make_garmin_user(db_session)
    db_session.add_all([
        DailyFeature(user_id=user.id, date=END-timedelta(days=1), acwr=1.2,
                     training_load_acute=120, training_load_chronic=100, load_metadata=METADATA),
        DailyFeature(user_id=user.id, date=END, acwr=1.5,
                     training_load_acute=150, training_load_chronic=100, load_metadata=None),
    ])
    await db_session.flush()
    output = await metric_trend("acwr", user=user, session=db_session, days=7, end=END)
    assert output.stats["latest"] == 1.5
    assert output.calculation_inputs is None
    stale_view = await metric_trend("acwr", user=user, session=db_session, days=7, end=END+timedelta(days=10))
    assert stale_view.points == []
    assert stale_view.calculation_inputs is None


@pytest.mark.asyncio
async def test_recovery_and_resting_hr_do_not_gain_inferred_inputs(db_session):
    user, _ = await make_garmin_user(db_session)
    db_session.add_all([
        DailyFeature(user_id=user.id, date=END, recovery_score=80, acwr=1.2,
                     training_load_acute=120, training_load_chronic=100, load_metadata=METADATA),
        DailyBiometric(user_id=user.id, date=END, resting_hr=55),
    ])
    await db_session.flush()
    for metric, value in (("recovery", 80), ("resting_hr", 55)):
        output = await metric_trend(metric, user=user, session=db_session, days=7, end=END)
        assert output.stats["latest"] == value
        assert output.calculation_inputs is None
