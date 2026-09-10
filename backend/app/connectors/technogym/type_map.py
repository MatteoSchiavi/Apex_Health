"""Technogym equipment -> disciplines.name mapping (MASTER_SPEC §11, §6.1).

Same law as the Garmin type map: the disciplines table holds exactly the
§6.1 seed (14 rows) — §17 forbids inventing disciplines ad hoc, so equipment
types outside the owner's sports resolve to the documented generic bucket.

Fallback: `gym_general` (the generic indoor bucket), flagged for owner review
exactly like the Garmin fallback.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Discipline

# Technogym equipment/category keys -> disciplines.name
EQUIPMENT_MAP: dict[str, str] = {
    # cardio machines
    "treadmill": "running",
    "run": "running",
    "indoor_run": "running",
    "jog": "running",
    "walk": "gym_general",  # mirrors the Garmin "walking" judgment call
    "indoor_cycle": "road_cycling",  # mirrors Garmin virtual_ride -> road_cycling
    "cycle": "road_cycling",
    "bike": "road_cycling",
    "elliptical": "gym_general",
    "climber": "gym_general",
    "rower": "gym_general",  # no rowing discipline in the seed — flagged
    "recline_bike": "gym_general",
    "upper_body": "gym_general",
    # strength machines / free weights
    "strength": "strength",
    "kinesis": "strength",
    "free_weight": "strength",
    "gym": "gym_general",
    "stretching": "gym_general",
    # class / functional
    "functional": "gym_general",
    "group_class": "gym_general",
}

# Documented fallback for equipment keys outside the owner's seeded disciplines.
FALLBACK_DISCIPLINE = "gym_general"


async def load_discipline_index(session: AsyncSession) -> dict[str, int]:
    """Return {disciplines.name: id} for every seeded discipline."""
    rows = await session.execute(select(Discipline.name, Discipline.id))
    return dict(rows.all())


def resolve_equipment(
    equipment: str | None, discipline_index: dict[str, int]
) -> tuple[int, str]:
    """Map a Technogym equipment key to a discipline id.

    Returns (discipline_id, source) where source is 'mapped' or 'fallback' —
    the caller logs fallbacks so unmapped upstream types stay visible.
    """
    key = (equipment or "").strip().lower()
    mapped = key in EQUIPMENT_MAP
    name = EQUIPMENT_MAP.get(key, FALLBACK_DISCIPLINE)
    if name not in discipline_index:
        name = FALLBACK_DISCIPLINE
    return discipline_index[name], ("mapped" if mapped else "fallback")
