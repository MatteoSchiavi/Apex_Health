"""Garmin activity typeKey -> seeded disciplines.name mappings.

Only explicit known aliases are mapped. Unknown Garmin sports remain NULL so
they stay visibly unknown instead of being misreported as a gym workout.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Discipline

# Garmin typeKey (activityType.typeKey) -> disciplines.name
TYPE_KEY_MAP: dict[str, str] = {
    # running family
    "running": "running",
    "street_running": "running",
    "indoor_running": "running",
    "trail_running": "running",
    "treadmill_running": "running",
    "track_running": "running",
    "ultra_run": "running",
    "virtual_run": "running",
    # cycling family
    "cycling": "road_cycling",
    "road_biking": "road_cycling",
    "road": "road_cycling",
    "biking": "road_cycling",
    "cyclocross": "road_cycling",
    "track_cycling": "road_cycling",
    "indoor_cycling": "road_cycling",
    "virtual_ride": "road_cycling",
    "bike_to_work": "road_cycling",
    "mountain_biking": "mountain_biking",
    "downhill_biking": "mountain_biking",
    "e_mountain_biking": "mountain_biking",
    "gravel_cycling": "gravel_cycling",
    # strength and indoor activities
    "strength_training": "strength",
    "indoor_strength": "strength",
    "gym": "gym_general",
    "fitness_equipment": "gym_general",
    "indoor_cardio": "gym_general",
    "elliptical": "gym_general",
    "stair_stepper": "gym_general",
    "indoor_rowing": "rowing",
    "yoga": "yoga",
    "pilates": "pilates",
    # outdoor and water sports
    "walking": "walking",
    "hiking": "hiking",
    "swimming": "swimming",
    "lap_swimming": "swimming",
    "pool_swimming": "swimming",
    "open_water_swimming": "swimming",
    "rowing": "rowing",
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
    # Garmin enduro is a motorcycling activity, separate from mountain biking.
    "enduro_motorcycling": "enduro",
}


async def load_discipline_index(session: AsyncSession) -> dict[str, int]:
    """Return {disciplines.name: id} for every seeded discipline."""
    rows = await session.execute(select(Discipline.name, Discipline.id))
    return dict(rows.all())


def resolve_type_key(
    type_key: str | None, discipline_index: dict[str, int]
) -> tuple[int | None, str]:
    """Return the explicit seeded discipline id, or None for unknown sports.

    The key is case-insensitive because Garmin export paths can return mixed
    case. The second item remains ``mapped`` / ``fallback`` for sync reporting;
    ``fallback`` now means the source sport is unknown and was left unmapped.
    """
    normalized = (type_key or "").strip().lower()
    name = TYPE_KEY_MAP.get(normalized)
    if name is None:
        return None, "fallback"
    discipline_id = discipline_index.get(name)
    if discipline_id is None:
        return None, "fallback"
    return discipline_id, "mapped"
