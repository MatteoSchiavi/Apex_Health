"""Strava sport_type -> seeded Discipline mapping.

Known activity types map to their closest matching seeded sport. Unknown
activities resolve to None instead of being mislabeled as generic gym work.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Discipline

SPORT_ALIASES = {
    "run": "running",
    "trailrun": "running",
    "virtualrun": "running",
    "treadmill": "running",
    "ride": "road_cycling",
    "gravelride": "gravel_cycling",
    "virtualride": "road_cycling",
    "ridefixedgear": "road_cycling",
    "mountainbikeride": "mountain_biking",
    "ebikeride": "road_cycling",
    "emountainbikeride": "mountain_biking",
    "mountain_bike_ride": "mountain_biking",
    "gravel_ride": "gravel_cycling",
    "hike": "hiking",
    "hiking": "hiking",
    "walk": "walking",
    "walking": "walking",
    "swim": "swimming",
    "swimming": "swimming",
    "row": "rowing",
    "rowing": "rowing",
    "yoga": "yoga",
    "pilates": "pilates",
    "alpineski": "skiing",
    "skitour": "skiing",
    "nordicski": "skiing",
    "snowboard": "snowboard",
    "iceskate": "skiing",
    "sail": "sailing",
    "kitesurf": "kitesurf",
    "kite": "kitesurf",
    "windsurf": "windsurf",
    "surf": "surf",
    "surfing": "surf",
    "tennis": "tennis",
    "weighttraining": "strength",
    "workout": "gym_general",
    "crossfit": "strength",
    "hiit": "gym_general",
}


async def build_discipline_index(session: AsyncSession) -> dict[str, int]:
    rows = await session.execute(select(Discipline.name, Discipline.id))
    return {name.lower(): discipline_id for name, discipline_id in rows.all()}


def resolve_discipline(
    sport_type: str | None,
    discipline_index: dict[str, int],
) -> tuple[int | None, str | None]:
    if not sport_type:
        return None, None
    key = str(sport_type).strip().lower()
    if key in discipline_index:
        return discipline_index[key], None
    if key in SPORT_ALIASES:
        alias = SPORT_ALIASES[key]
        if alias in discipline_index:
            return discipline_index[alias], f"strava:{sport_type}->{alias}"
    return None, None
