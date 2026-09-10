"""Weather-domain model (MASTER_SPEC §6.4 — forecast_cache).

The table itself is created by migration 0001 verbatim from the spec DDL;
this mapping exists so Phase 7 code (and everything after it) reads and
writes forecast_cache through the ORM like every other table.

Idempotency law (§17): the natural key is UNIQUE (lat, lon, date) — the
refresh upserts on it, so re-running never doubles rows (spec: "Gear/weather/
rollup accumulation jobs are idempotent — re-running must not double-count").
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ForecastCache(Base):
    __tablename__ = "forecast_cache"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lat: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    lon: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
