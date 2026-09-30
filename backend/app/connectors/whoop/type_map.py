"""Whoop sport_name -> canonical Discipline mapping.

The v2 API carries a human `sport_name` string per workout (e.g. "running").
Strategy: exact/lowercase match against the seeded disciplines first, then
an alias table, then None (the normalizer stores the raw sport_name in
source_metrics and the activity keeps discipline_id NULL — never invent a
discipline, §17).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Discipline

# Whoop sport_name (lowercased) -> our seeded discipline name.
# Extensible: unknown names degrade to a documented fallback, never an error.
SPORT_ALIASES = {
    "running": "running",
    "running_indoor": "running",
    "treadmill": "running",
    "trail_running": "running",
    "cycling": "road_cycling",
    "cycling_indoor": "road_cycling",
    "road_cycling": "road_cycling",
    "mountain_biking": "enduro",
    "gravel_cycling": "road_cycling",
    "skiing": "skiing",
    "alpine_skiing": "skiing",
    "cross_country_skiing": "skiing",
    "snowboarding": "snowboard",
    "strength_training": "strength",
    "weight_training": "strength",
    "gym": "gym_general",
    "functional_fitness": "gym_general",
    "sailing": "sailing",
    "kitesurfing": "kitesurf",
    "windsurfing": "windsurf",
    "tennis": "tennis",
    "surfing": "surf",
    "wakeboarding": "wakeboard",
    "motocross": "enduro",
    "enduro": "enduro",
}


async def build_discipline_index(session: AsyncSession) -> dict[str, int]:
    rows = await session.execute(select(Discipline.name, Discipline.id))
    return {name.lower(): discipline_id for name, discipline_id in rows.all()}


def resolve_discipline(
    sport_name: str | None,
    discipline_index: dict[str, int],
) -> tuple[int | None, str | None]:
    """Returns (discipline_id, fallback_note). The note names the alias that
    matched so the sync report can surface mapping decisions."""
    if not sport_name:
        return None, None
    key = str(sport_name).strip().lower()
    if key in discipline_index:
        return discipline_index[key], None
    if key in SPORT_ALIASES:
        alias = SPORT_ALIASES[key]
        if alias in discipline_index:
            return discipline_index[alias], f"whoop:{sport_name}->{alias}"
    return None, None
