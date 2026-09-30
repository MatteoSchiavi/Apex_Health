"""Lifestyle module — nutrition + supplement ingestion (MASTER_SPEC §6.4,
§23 Phase 4). Thin, validated write paths over the lifestyle tables; the
agent tools (§8.3 propose_supplement_change) and future report tasks read
through the same models. All inserts are plain rows: manual entries have no
(source, external_id) key to upsert on — the §17 idempotency law targets
sync/ingest operations.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medical import NutritionLog, SupplementLog, SupplementProtocol


def _decimal(value: float | int | str | Decimal | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


async def record_nutrition_log(
    session: AsyncSession,
    *,
    user_id: int,
    timestamp: datetime,
    source: str = "manual",
    calories: int | None = None,
    protein_g: float | None = None,
    carbs_g: float | None = None,
    fat_g: float | None = None,
    water_ml: int | None = None,
    alcohol_units: float | None = None,
    caffeine_mg: float | None = None,
) -> NutritionLog:
    log = NutritionLog(
        user_id=user_id,
        timestamp=timestamp,
        source=source,
        calories=calories,
        protein_g=_decimal(protein_g),
        carbs_g=_decimal(carbs_g),
        fat_g=_decimal(fat_g),
        water_ml=water_ml,
        alcohol_units=_decimal(alcohol_units),
        caffeine_mg=_decimal(caffeine_mg),
    )
    session.add(log)
    return log


async def create_supplement_protocol(
    session: AsyncSession,
    *,
    user_id: int,
    supplement_name: str,
    dose: str | None = None,
    schedule_cron: str | None = None,
    start_date: date | None = None,
    reason: str | None = None,
) -> SupplementProtocol:
    protocol = SupplementProtocol(
        user_id=user_id,
        supplement_name=supplement_name,
        dose=dose,
        schedule_cron=schedule_cron,
        active=True,
        start_date=start_date,
        reason=reason,
    )
    session.add(protocol)
    await session.flush()
    return protocol


async def end_supplement_protocol(
    session: AsyncSession, protocol: SupplementProtocol, end_date: date
) -> SupplementProtocol:
    """Soft-stop a protocol (kept for history; adherence logs stay attached)."""
    protocol.active = False
    protocol.end_date = end_date
    return protocol


async def record_supplement_intake(
    session: AsyncSession,
    *,
    protocol: SupplementProtocol,
    taken_at: datetime,
    adherence: bool,
) -> SupplementLog:
    log = SupplementLog(
        protocol_id=protocol.id, taken_at=taken_at, adherence=adherence
    )
    session.add(log)
    return log


async def active_protocols(
    session: AsyncSession, user_id: int
) -> list[SupplementProtocol]:
    rows = await session.scalars(
        select(SupplementProtocol)
        .where(
            SupplementProtocol.user_id == user_id,
            SupplementProtocol.active.is_(True),
        )
        .order_by(SupplementProtocol.supplement_name)
    )
    return list(rows)
