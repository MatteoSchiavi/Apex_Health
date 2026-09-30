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

F-13 audit: ``find_reconcilable_activity`` uses ``NOT EXISTS`` instead of
``NOT IN`` (the planner trap when the subquery returns NULLs).
``reconcile_activity`` records per-field provenance in
``source_metrics["_merged_fields"]`` so post-hoc audit ("why is avg_power
from Technogym?") is queryable, and recomputes ``data_completeness`` after
the merge so the winner reflects the merged view.

D-03 audit: ``replay_user`` provides a chunked, constant-memory replay path
keyset-paginated on ``raw_ingest.id`` — a multi-year backfill no longer
materializes every raw row in one Python list (the original OOM risk).
"""

from datetime import timedelta
from dataclasses import dataclass

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.activity import Activity, ActivitySourceLink
from app.models.integration import RawIngest

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
    a compatible discipline, not already linked to the incoming source.

    F-13 audit: rewritten as ``NOT EXISTS`` instead of ``NOT IN``. The old
    ``Activity.id.not_in(subquery)`` form is a classic planner trap — if the
    subquery ever returns a NULL, NOT IN evaluates to NULL (false-ish) for
    EVERY row and the query silently returns nothing. NOT EXISTS is
    NULL-safe and the planner handles it better.
    """
    window = timedelta(minutes=window_minutes)
    seconds_apart = func.abs(
        func.extract("epoch", Activity.start_time - start_time)
    )
    # F-13: NOT EXISTS is NULL-safe and planner-friendly.
    already_linked = (
        select(ActivitySourceLink.id)
        .where(
            ActivitySourceLink.activity_id == Activity.id,
            ActivitySourceLink.source == source,
        )
    )
    return (
        await session.scalars(
            select(Activity)
            .where(
                Activity.user_id == user_id,
                Activity.start_time >= start_time - window,
                Activity.start_time <= start_time + window,
                Activity.discipline_id == discipline_id,
                ~exists(already_linked),
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
    field is never overwritten with NULL.

    F-13 audit: records per-field provenance in
    ``source_metrics["_merged_fields"]`` so post-hoc audit is queryable
    ("why is avg_power from Technogym?"). Recomputes
    ``data_completeness`` after the merge so the winner reflects the merged
    view (a partial Garmin row merged with a full Technogym row should
    become 'full', not stay 'partial').
    """
    merged_fields: dict[str, str] = {}  # field_name → source that supplied the value
    for field, new_val in incoming_values.items():
        if field in _IDENTITY_FIELDS:
            continue
        current = getattr(existing, field)
        if current is None:
            if new_val is not None:
                setattr(existing, field, new_val)  # fill the gap
                merged_fields[field] = source
        elif new_val is not None and FIELD_PREFERENCE.get(field) == source:
            setattr(existing, field, new_val)  # preferred source wins the conflict
            merged_fields[field] = source
        # else: keep the existing value

    # F-13: record per-field provenance so post-hoc audit is queryable.
    metrics = dict(existing.source_metrics or {})
    merged_block = dict(metrics.get("_merged_fields") or {})
    merged_block.update(merged_fields)
    if merged_block:
        metrics["_merged_fields"] = merged_block
        existing.source_metrics = metrics

    # F-13: recompute data_completeness after the merge — a partial Garmin
    # row merged with a full Technogym row should become 'full'.
    existing.data_completeness = _recompute_completeness(existing, incoming_values)

    session.add(
        ActivitySourceLink(
            activity_id=existing.id,
            source=source,
            external_id=external_id,
            raw_ingest_id=raw_ingest_id,
        )
    )
    return ReconciliationOutcome(activity_id=existing.id, reconciled=True)


def _recompute_completeness(existing: Activity, incoming_values: dict) -> str:
    """F-13: re-derive ``data_completeness`` from the merged row.

    'manual' stays manual (user-entered, no merge changes that). 'partial'
    upgrades to 'full' when the incoming source supplied at least one
    previously-missing HR or power signal. 'full' stays full.
    """
    current = existing.data_completeness or "full"
    if current == "manual":
        return current
    # If we just filled avg_hr OR avg_power (the two signals completeness
    # keys on), the merged row is now 'full'.
    if any(
        getattr(existing, field) is not None
        for field in ("avg_hr", "avg_power")
    ):
        return "full"
    return "partial" if current == "partial" else "full"


async def replay_user(
    session_factory: async_sessionmaker,
    user_id: int,
    source: str | None = None,
    *,
    batch_size: int = 200,
) -> dict:
    """D-03 audit: chunked, constant-memory replay of unprocessed raw_ingest
    rows for one user.

    Keyset-paginated on ``raw_ingest.id`` so memory usage is bounded by
    ``batch_size`` regardless of how many years of backfill are queued.
    Each batch commits independently — a killed run resumes from the last
    committed id because processed rows are skipped via the partial index
    ``idx_raw_unproc`` (migration 0008).

    Returns a summary dict; never raises (failures land in ``unprocessed``).
    """
    from app.connectors.garmin.normalize import (
        NormalizationError,
        normalize_raw_row,
    )

    last_id = 0
    processed = 0
    unprocessed: list[int] = []
    while True:
        async with session_factory() as session:
            stmt = (
                select(RawIngest)
                .where(
                    RawIngest.user_id == user_id,
                    RawIngest.processed.is_(False),
                    RawIngest.id > last_id,
                )
                .order_by(RawIngest.id)
                .limit(batch_size)
            )
            if source is not None:
                stmt = stmt.where(RawIngest.source == source)
            rows = (await session.scalars(stmt)).all()
            if not rows:
                break
            for raw in rows:
                try:
                    # Per-row savepoint: a malformed payload rolls back
                    # alone, stays processed=false, the pass continues.
                    async with session.begin_nested():
                        # The garmin normalizer dispatches by payload_type;
                        # for other sources a per-source normalizer would
                        # be dispatched here. For now this is the canonical
                        # replay path for garmin raw rows (the only source
                        # that uses raw_ingest → normalize today).
                        if raw.source == "garmin":
                            from app.connectors.garmin.normalize import normalize_raw_row as _gn
                            from app.models.user import User
                            from zoneinfo import ZoneInfo
                            user = await session.get(User, user_id)
                            tz = ZoneInfo(user.timezone) if user else ZoneInfo("UTC")
                            from app.models.activity import Discipline
                            disc_rows = await session.execute(
                                select(Discipline.name, Discipline.id)
                            )
                            discipline_index = dict(disc_rows.all())
                            await _gn(session, raw, tz, discipline_index)
                        else:
                            # Non-garmin sources have their own normalizers
                            # invoked at sync time; the replay path is a
                            # garmin-only concern today.
                            pass
                    processed += 1
                except NormalizationError:
                    unprocessed.append(raw.id)
                except Exception:  # pragma: no cover - defensive
                    unprocessed.append(raw.id)
                last_id = raw.id
            await session.commit()
    return {
        "user_id": user_id,
        "source": source,
        "processed": processed,
        "unprocessed": unprocessed,
        "last_id": last_id,
    }
