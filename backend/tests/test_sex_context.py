"""Sex support verified against explicit numbers and real profile boundaries."""
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import update

from app.agent.entrypoint import _build_snapshot
from app.api.labs import _to_out
from app.features.engine import _compute_day, compute_user_day
from app.features.load import activity_trimp, hr_max_for
from app.medical.labs import record_lab_panel
from app.metrics.physiology import physiological_context
from app.metrics.registry import METRIC_REGISTRY
from app.models.activity import Activity, ActivityStream
from app.models.medical import LabMetric
from app.models.user import User
from app.models.wellness import DailyBiometric
from app.queries.labs import get_lab_trend
from app.reports.periodic import build_period_data_pack
from app.schemas.changes import ProposeIn
from app.schemas.labs import LabPanelIn
from app.services.changes import propose, apply
from app.services.evidence import EvidenceError, snapshot_revision
from tests.helpers.domain_db import clean_domain_tables  # noqa: F401
from tests.test_garmin_sync import make_garmin_user
from tests.test_metric_registry import DAY, make_window


@pytest.mark.parametrize("sex", ["male", "female", "other", None])
def test_shared_formulas_match_hand_calculation_for_each_profile(sex):
    result = _compute_day(SimpleNamespace(id=1, dob=None, sex=sex), DAY, make_window())
    daily = result["daily"]
    # REM=0%, deep=20%, sleep efficiency=25/26. Sleep=800/13.
    # Recovery: .4*.9 + .3*.8 + .2*(8/13) + .1*.6 = 509/650.
    # Readiness: .5*(509/650) + .3*(8/13), ACWR=4 => zero load component.
    assert daily["sleep_architecture_score"] == pytest.approx(800 / 13)
    assert daily["recovery_score"] == pytest.approx(1018 / 13)
    assert daily["readiness_score"] == pytest.approx(749 / 13)
    assert daily["acwr"] == 4
    assert daily["strain_score"] == 0
    assert daily["calculation_provenance"]["physiological_context"]["sex"] == sex


def test_female_hrv_uses_her_own_baseline_not_a_male_reference():
    female = _compute_day(SimpleNamespace(id=1, dob=None, sex="female"), DAY, make_window())
    male_window = make_window()
    male_window["hrv_by_local_day"] = {d: 60 if d == DAY else 80 for d in male_window["hrv_by_local_day"]}
    male = _compute_day(SimpleNamespace(id=2, dob=None, sex="male"), DAY, male_window)
    assert female["daily"]["hrv_deviation_from_baseline"] == 20
    assert male["daily"]["hrv_deviation_from_baseline"] == -25
    assert female["daily"]["recovery_score"] - male["daily"]["recovery_score"] == pytest.approx(36)


def test_shared_tanaka_edwards_model_has_no_banister_sex_constants():
    # Tanaka: a 40-year-old adult => 180 bpm. Edwards: 10 min at 80%
    # contributes 40 points, 10 min at 60% contributes 20, total 60.
    assert hr_max_for(40) == 180
    activity = Activity(duration_s=1200)
    streams = [ActivityStream(t_offset_s=0, hr=144), ActivityStream(t_offset_s=600, hr=108)]
    assert activity_trimp(activity, streams, 180) == pytest.approx(60)
    assert hr_max_for(None) is None
    assert activity_trimp(activity, streams, None) is None


def test_unknown_profile_has_no_male_scientific_default_or_inferred_cycle():
    assert physiological_context(SimpleNamespace(), DAY)["sex"] is None
    assert physiological_context(SimpleNamespace(sex="female"), DAY)["reproductive_context"] == "not_structurally_recorded"
    for definition in METRIC_REGISTRY.values():
        assert definition.sex_handling


async def test_profile_change_invalidates_evidence_and_pending_approval(db_session):
    user, _ = await make_garmin_user(db_session)
    user.sex = "male"
    await db_session.commit()
    other, _ = await make_garmin_user(db_session)
    original = await snapshot_revision(db_session, user.id)
    other_revision = await snapshot_revision(db_session, other.id)
    draft = await propose(db_session, user.id, ProposeIn.model_validate({
        "change": {"kind": "context_patch", "doc_kind": "preferences", "operation": "append", "text": "Easy training"},
        "reason": "Recorded preference",
    }))
    await db_session.commit()
    await db_session.execute(update(User).where(User.id == user.id).values(sex="female"))
    await db_session.commit()
    assert await snapshot_revision(db_session, user.id) != original
    assert await snapshot_revision(db_session, other.id) == other_revision
    with pytest.raises(EvidenceError) as caught:
        await apply(db_session, user.id, draft["id"], draft["payload_hash"])
    assert caught.value.code == "CONFLICT"
    await db_session.rollback()


async def test_coach_report_and_constraints_receive_only_the_owned_profile(db_session):
    user, _ = await make_garmin_user(db_session)
    user.sex, user.dob = "female", date(1990, 1, 1)
    await db_session.commit()
    now = datetime(2026, 10, 5, 12, tzinfo=UTC)
    snapshot = await _build_snapshot(db_session, user.id, now)
    assert snapshot["profile"]["sex"] == "female"
    assert snapshot["profile"]["age_years"] == 36
    assert snapshot["daily_decision"]["constraints"]["physiological_context"]["sex"] == "female"
    pack = await build_period_data_pack(db_session, user.id, DAY - timedelta(days=6), DAY)
    assert pack.payload["profile"]["sex"] == "female"


async def test_worker_refreshes_detached_profile_before_computing(db_session):
    user, _ = await make_garmin_user(db_session)
    user.sex = "male"
    db_session.add(DailyBiometric(user_id=user.id, date=DAY, resting_hr=50))
    await db_session.commit()
    stale = SimpleNamespace(id=user.id, dob=None, sex="male", timezone="UTC")
    await db_session.execute(update(User).where(User.id == user.id).values(sex="female"))
    await db_session.commit()
    result = await compute_user_day(db_session, stale, DAY)
    assert result["daily"]["calculation_provenance"]["physiological_context"]["sex"] == "female"


async def test_lab_intervals_preserve_female_report_and_missing_measurement(db_session):
    user, _ = await make_garmin_user(db_session)
    user.sex = "female"
    panel = await record_lab_panel(db_session, user_id=user.id, panel_date=DAY, panel_type="blood",
        hemoglobin=12.5, reference_ranges={"hemoglobin": (12, 16), "hematocrit": (36, 46)})
    await db_session.flush()
    from sqlalchemy import select
    markers = (await db_session.scalars(select(LabMetric).where(LabMetric.lab_panel_id == panel.id))).all()
    output = _to_out(panel, markers)
    assert next(m for m in output.markers if m["marker"] == "hemoglobin")["ref_low"] == 12
    assert next(m for m in output.markers if m["marker"] == "hematocrit")["value"] is None
    trend = await get_lab_trend(db_session, user.id, "hematocrit")
    assert trend[0]["value"] is None and trend[0]["ref_low"] == 36


async def test_lab_migration_downgrade_preserves_data_or_refuses(db_session):
    import importlib.util
    from pathlib import Path
    from alembic.operations import Operations
    from alembic.migration import MigrationContext
    from sqlalchemy import delete, select, text
    user, _ = await make_garmin_user(db_session)
    panel = await record_lab_panel(db_session, user_id=user.id, panel_date=DAY, panel_type="blood",
        hemoglobin=12.5, reference_ranges={"hematocrit": (36, 46)})
    await db_session.flush()
    spec = importlib.util.spec_from_file_location("lab_null_migration", Path(__file__).parents[1] / "alembic/versions/0023_unreported_lab_markers.py")
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    connection = await db_session.connection()
    def run(connection, operation):
        migration.op = Operations(MigrationContext.configure(connection))
        getattr(migration, operation)()
    with pytest.raises(RuntimeError, match="Cannot downgrade"):
        await connection.run_sync(lambda conn: run(conn, "downgrade"))
    # Refusal does not remove the unreported interval or replace it with zero.
    assert (await db_session.scalar(select(LabMetric).where(LabMetric.lab_panel_id == panel.id, LabMetric.metric_name == "hematocrit"))).value is None
    await db_session.execute(delete(LabMetric).where(LabMetric.lab_panel_id == panel.id, LabMetric.value.is_(None)))
    await connection.run_sync(lambda conn: run(conn, "downgrade"))
    nullable = await db_session.scalar(text("SELECT is_nullable FROM information_schema.columns WHERE table_name='lab_metrics' AND column_name='value'"))
    assert nullable == "NO"
    assert float(await db_session.scalar(select(LabMetric.value).where(LabMetric.lab_panel_id == panel.id))) == 12.5
    await connection.run_sync(lambda conn: run(conn, "upgrade"))
    assert await db_session.scalar(text("SELECT is_nullable FROM information_schema.columns WHERE table_name='lab_metrics' AND column_name='value'")) == "YES"


@pytest.mark.parametrize("bounds", [(16, 12), (float("nan"), 16), (12, float("inf"))])
def test_invalid_lab_ranges_are_rejected(bounds):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        LabPanelIn(panel_date=DAY, panel_type="blood", reference_ranges={"hemoglobin": bounds})
