"""Garmin activity typeKey -> disciplines.name mapping.

The disciplines table holds exactly the §6.1 seed (14 rows) — §17 forbids
inventing disciplines ad hoc, so Garmin typeKeys outside the owner's sports
resolve to a documented generic bucket instead of a new row.

Fallback: `gym_general` (the generic indoor bucket). Flagged for owner review
alongside the Phase 0 seed-mapping note; a different fallback (or extra seed
rows via migration) is the owner's call.

Case-insensitive lookup (fix): Garmin's payload is normally lower_snake_case
but the typeKey can arrive in mixed case (e.g. ``Street_Running`` from some
export paths); ``resolve_type_key`` now normalizes with ``.strip().lower()``
before lookup so the canonical lowercase aliases below match regardless of
the upstream casing.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Discipline

# Garmin typeKey (activityType.typeKey) -> disciplines.name
TYPE_KEY_MAP: dict[str, str] = {
    # running family -> running
    "running": "running",
    "street_running": "running",
    "indoor_running": "running",
    "trail_running": "running",
    "treadmill_running": "running",
    "track_running": "running",
    "ultra_run": "running",
    "virtual_run": "running",
    # cycling family -> road_cycling / enduro
    "cycling": "road_cycling",
    "road_biking": "road_cycling",
    "road": "road_cycling",
    "biking": "road_cycling",
    "cyclocross": "road_cycling",
    "track_cycling": "road_cycling",
    "gravel_cycling": "road_cycling",
    "virtual_ride": "road_cycling",
    "bike_to_work": "road_cycling",
    "mountain_biking": "enduro",
    "downhill_biking": "enduro",
    "enduro_motorcycling": "enduro",
    # strength family -> strength / gym_general
    "strength_training": "strength",
    "indoor_strength": "strength",
    "gym": "gym_general",
    "fitness_equipment": "gym_general",
    "indoor_cardio": "gym_general",
    "indoor_rowing": "gym_general",
    "elliptical": "gym_general",
    "stair_stepper": "gym_general",
    "yoga": "gym_general",
    "pilates": "gym_general",
    "walking": "gym_general",
    "hiking": "gym_general",
    # technical sports -> the matching seeded discipline
    "resort_skiing": "skiing",
    "backcountry_skiing": "skiing",
    "cross_country_skiing": "skiing",
    "sailing": "sailing",
    "kitesurf": "kitesurf",
    "kiteboarding": "kitesurf",
    "windsurf": "windsurf",
    "windsurfing": "windsurf",
    "tennis": "tennis",
    "wakeboard": "wakeboard",
    "wakeboarding": "wakeboard",
    "snowboard": "snowboard",
    "snowboarding": "snowboard",
    "surf": "surf",
    "surfing": "surf",
    "stand_up_paddleboarding": "surf",
    "sup": "surf",
}

# Documented fallback for typeKeys outside the owner's seeded disciplines.
FALLBACK_DISCIPLINE = "gym_general"


async def load_discipline_index(session: AsyncSession) -> dict[str, int]:
    """Return {disciplines.name: id} for every seeded discipline."""
    rows = await session.execute(select(Discipline.name, Discipline.id))
    return dict(rows.all())


def resolve_type_key(
    type_key: str | None, discipline_index: dict[str, int]
) -> tuple[int, str]:
    """Map a Garmin typeKey to a discipline id.

    The lookup is case-insensitive: ``type_key`` is normalized with
    ``.strip().lower()`` before hitting the alias map so mixed-case payloads
    (``Street_Running``, ``SUP``) resolve the same as their canonical
    lower-snake forms.

    Returns (discipline_id, source) where source is 'mapped' or 'fallback' —
    the caller logs fallbacks so unmapped upstream types stay visible.
    """
    normalized = (type_key or "").strip().lower()
    mapped = normalized in TYPE_KEY_MAP
    name = TYPE_KEY_MAP.get(normalized, FALLBACK_DISCIPLINE)
    if name not in discipline_index:
        name = FALLBACK_DISCIPLINE
    return discipline_index[name], ("mapped" if mapped else "fallback")
