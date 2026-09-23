"""Activity-domain models (MASTER_SPEC §6.4): disciplines, activities,
activity_source_links, activity_streams.

Idempotency law (§17): syncs upsert keyed on (source, external_id) — that key
lives on activity_source_links; the activity row it points at is updated in
place, never duplicated.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Discipline(Base):
    __tablename__ = "disciplines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    ftp_model_type: Mapped[str | None] = mapped_column(Text, nullable=True)


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discipline_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    start_tz_offset_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    # §17 day-boundary rule: calendar date of the LOCAL start_time (users.timezone).
    local_date: Mapped[date] = mapped_column(Date, nullable=False)
    duration_s: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_m: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    elevation_gain_m: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    avg_hr: Mapped[int | None] = mapped_column(nullable=True)
    max_hr: Mapped[int | None] = mapped_column(nullable=True)
    avg_power: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    np_power: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    calories: Mapped[int | None] = mapped_column(nullable=True)
    training_load: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    data_completeness: Mapped[str] = mapped_column(
        Text, nullable=False, default="full", server_default="full"
    )
    # §14: NULL means "not weathered yet" — the weather connector's enrichment
    # pass selects on IS NULL. JSONB's default binds explicit Python None to
    # JSON 'null' (not SQL NULL), which would make such rows invisible to that
    # sweep forever; none_as_null pins the column to one unambiguous meaning.
    weather_snapshot: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    # Provider-specific quantities that must NOT be folded into unit-
    # compatible canonical columns (Whoop Strain 0-21 ≠ training_load,
    # zone durations, relative effort...). Written by the owning connector,
    # keyed {"whoop": {...}, "strava": {...}, ...} — migration 0006.
    source_metrics: Mapped[dict | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class ActivitySourceLink(Base):
    __tablename__ = "activity_source_links"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    raw_ingest_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_ingest.id"), nullable=True
    )


class ActivityStream(Base):
    __tablename__ = "activity_streams"

    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), primary_key=True)
    t_offset_s: Mapped[int] = mapped_column(Integer, primary_key=True)
    hr: Mapped[int | None] = mapped_column(nullable=True)
    power: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    cadence: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    speed: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    altitude: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    lat: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    lon: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)

class ActivityLap(Base):
    """Per-lap splits parsed from FIT files (migration 0007).

    Garmin Connect's JSON API carries lap summaries only for some sports and
    inconsistently; the FIT file is authoritative. Keyed
    (activity_id, lap_index) — the enrichment pass upserts idempotently.
    """

    __tablename__ = "activity_laps"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id"), nullable=False
    )
    lap_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_s: Mapped[int | None] = mapped_column(nullable=True)
    distance_m: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    avg_hr: Mapped[int | None] = mapped_column(nullable=True)
    max_hr: Mapped[int | None] = mapped_column(nullable=True)
    avg_power: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    calories: Mapped[int | None] = mapped_column(nullable=True)
    extras: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
