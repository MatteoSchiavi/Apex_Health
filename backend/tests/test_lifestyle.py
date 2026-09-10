"""Lifestyle module tests (§23 Phase 4): nutrition + supplement ingestion
round-trips through the §6.4 tables."""

from datetime import UTC, date, datetime

from sqlalchemy import select

from app.medical.lifestyle import (
    active_protocols,
    create_supplement_protocol,
    end_supplement_protocol,
    record_nutrition_log,
    record_supplement_intake,
)
from app.models.medical import NutritionLog, SupplementLog
from tests.helpers.telegram import (
    clean_bot_tables,  # noqa: F401 — autouse per-test truncate
)


async def _owner_id(db_session) -> int:
    from sqlalchemy import text

    return (await db_session.execute(text("SELECT id FROM users ORDER BY id LIMIT 1"))).scalar_one()


async def test_nutrition_log_roundtrip(db_session):
    user_id = await _owner_id(db_session)
    log = await record_nutrition_log(
        db_session,
        user_id=user_id,
        timestamp=datetime(2025, 5, 2, 13, 30, tzinfo=UTC),
        source="telegram_text",
        calories=1850,
        protein_g=140.5,
        carbs_g=180.0,
        fat_g=62.0,
        water_ml=2600,
        caffeine_mg=180,
    )
    await db_session.commit()
    fresh = await db_session.get(NutritionLog, log.id)
    assert fresh.calories == 1850
    assert float(fresh.protein_g) == 140.5
    assert float(fresh.caffeine_mg) == 180
    assert fresh.source == "telegram_text"


async def test_supplement_protocol_lifecycle_and_adherence(db_session):
    user_id = await _owner_id(db_session)
    protocol = await create_supplement_protocol(
        db_session,
        user_id=user_id,
        supplement_name="Ferrous sulfate",
        dose="80 mg",
        schedule_cron="0 8 * * *",
        start_date=date(2025, 5, 1),
        reason="post-donation ferritin 12 ng/mL",
    )
    await db_session.commit()
    assert (await active_protocols(db_session, user_id))[0].id == protocol.id

    taken = await record_supplement_intake(
        db_session, protocol=protocol,
        taken_at=datetime(2025, 5, 2, 8, 5, tzinfo=UTC), adherence=True,
    )
    missed = await record_supplement_intake(
        db_session, protocol=protocol,
        taken_at=datetime(2025, 5, 3, 8, 0, tzinfo=UTC), adherence=False,
    )
    await end_supplement_protocol(db_session, protocol, date(2025, 6, 1))
    await db_session.commit()

    logs = (
        await db_session.scalars(
            select(SupplementLog).where(SupplementLog.protocol_id == protocol.id)
        )
    ).all()
    assert [(l.id, l.adherence) for l in logs] == [(taken.id, True), (missed.id, False)]
    assert await active_protocols(db_session, user_id) == []
