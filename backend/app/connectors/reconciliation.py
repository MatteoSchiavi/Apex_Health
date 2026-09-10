"""Multi-source activity reconciliation (MASTER_SPEC §12, Phase 6 AC2).

On ingesting an activity, check for an existing row for the same user with
`start_time` within ±10 minutes and a compatible discipline. If found: NO new
`activities` row — add an `activity_source_links` entry and merge fields,
preferring the richer source per field (Garmin for HR/GPS, Technogym for
machine power/resistance/incline), never overwriting a populated field with
NULL. If not found: the caller creates the row plus its first source link.

Documented judgment calls (surfaced to the owner like every §12 "compatible"):
- "compatible discipline" = the SAME seeded discipline (§17: disciplines are
  fixed seed rows). A Garmin road ride and a Technogym treadmill run ten
  minutes apart are different sessions, so category-level matching would
  wrongly fuse them.
- Candidates already linked to the INCOMING source are excluded: two
  Technogym machine sessions five minutes apart (a superset circuit) are two
  workouts, not one — cross-source is what §12 reconciles.
- Field preference follows §12's parenthetical: HR -> Garmin (optical/wrist
  HR beats grip-based machine HR), machine power -> Technogym. GPS-derived
  fields (distance/elevation) are Garmin-preferred per the same sentence;
  where Garmin carries no value they are filled from Technogym, whose
  machine-recorded originals stay queryable via the linked raw_ingest row
  (§3 raw store).
- duration/calories/np and every other field: existing wins, gaps get filled
  — first-come data is never degraded.
"""

from datetime import timedelta
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity, ActivitySourceLink

RECONCILIATION_WINDOW_MINUTES = 10

# §12: the richer source per field, on conflict.
FIELD_PREFERENCE: dict[str, str] = {
    # Garmin for HR (wrist/strap beats machine grips)
    "avg_hr": "garmin",
    "max_hr": "garmin",
    # Technogym for machine power
    "avg_power": "technogym",
    "np_power": "technogym",
}

# Fields managed by the reconciliation/window logic itself — never merged.
_IDENTITY_FIELDS = {
    "user_id",
    "discipline_id",
    "start_time",
    "start_tz_offset_minutes",
    "local_date",
    "data_completeness",
}


@dataclass
class ReconciliationOutcome:
    activity_id: int
    reconciled: bool  # True = merged into an existing row; False = created new


async def find_reconcilable_activity(
    session: AsyncSession,
    *,
    user_id: int,
    start_time,
    discipline_id: int,
    source: str,
    window_minutes: int = RECONCILIATION_WINDOW_MINUTES,
) -> Activity | None:
    """Closest existing activity for this user inside the ±10 min window with
    a compatible discipline, not already linked to the incoming source."""
    window = timedelta(minutes=window_minutes)
    seconds_apart = func.abs(
        func.extract("epoch", Activity.start_time - start_time)
    )
    return (
        await session.scalars(
            select(Activity)
            .where(
                Activity.user_id == user_id,
                Activity.start_time >= start_time - window,
                Activity.start_time <= start_time + window,
                Activity.discipline_id == discipline_id,
                Activity.id.not_in(
                    select(ActivitySourceLink.activity_id).where(
                        ActivitySourceLink.source == source
                    )
                ),
            )
            .order_by(seconds_apart)
            .limit(1)
        )
    ).first()


async def reconcile_activity(
    session: AsyncSession,
    *,
    existing: Activity,
    incoming_values: dict,
    source: str,
    external_id: str,
    raw_ingest_id: int | None,
) -> ReconciliationOutcome:
    """Attach the incoming source to an existing activity and merge fields
    per §12: preference map wins on conflict, gaps get filled, a populated
    field is never overwritten with NULL."""
    for field, new_val in incoming_values.items():
        if field in _IDENTITY_FIELDS:
            continue
        current = getattr(existing, field)
        if current is None:
            if new_val is not None:
                setattr(existing, field, new_val)  # fill the gap
        elif new_val is not None and FIELD_PREFERENCE.get(field) == source:
            setattr(existing, field, new_val)  # preferred source wins the conflict
        # else: keep the existing value

    session.add(
        ActivitySourceLink(
            activity_id=existing.id,
            source=source,
            external_id=external_id,
            raw_ingest_id=raw_ingest_id,
        )
    )
    return ReconciliationOutcome(activity_id=existing.id, reconciled=True)
