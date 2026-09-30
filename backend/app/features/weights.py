"""feature_weights loading per the §6.4 selection rule.

For a given (feature_name, component_name) and computation date D, the active
row is the one with the latest effective_from <= the START of local day D (in
the user's timezone). Consequences that are deliberate:

- A weight effective at Rome midnight 2025-04-01 applies to local date
  2025-04-01 onward; 2025-03-31 keeps reproducing under the previous version.
- The nightly task (03:00 local on day N, computing day N-1) therefore sees
  exactly the weights that were active for day N-1 — historical daily_features
  are reproducible with the weights that were active then (§6.4).
- Blend weights come from this table, never hardcoded constants (§17).
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def cutoff_for_local_day(day: date, tz: ZoneInfo) -> datetime:
    """The selection cutoff: the start of local `day` in `tz` (§17: local,
    never UTC). A weight effective at or before local midnight of `day` is
    active for that day's features."""
    return datetime(day.year, day.month, day.day, tzinfo=tz)


async def load_weights(
    session: AsyncSession, feature_name: str, cutoff: datetime
) -> dict[str, float]:
    """Active component weights for `feature_name` as of `cutoff` — per
    component the row with the latest effective_from <= cutoff (id breaks
    ties for same-instant rows). Returned as floats: the engine computes in
    float and pins its numerics via the golden-dataset regression tests."""
    rows = await session.execute(
        text(
            "SELECT DISTINCT ON (component_name) "
            "  component_name, weight "
            "FROM feature_weights "
            "WHERE feature_name = :feature_name "
            "  AND effective_from <= :cutoff "
            "ORDER BY component_name, effective_from DESC, id DESC"
        ),
        {"feature_name": feature_name, "cutoff": cutoff},
    )
    return {component: float(weight) for component, weight in rows.fetchall()}
