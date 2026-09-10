"""Medical/lifestyle-domain models (MASTER_SPEC §6.4): lab_panels,
lab_metrics, nutrition_logs, supplement_protocols, supplement_logs.

`lab_panels.notes` holds APPLICATION-LAYER ciphertext (§17: "lab_panels is
encrypted at the application layer before it touches disk") — the DDL's
encryption comment is attached to this column. The structured marker columns
stay queryable so the §8.3 tools (get_lab_trend, get_donation_status) remain
plain SQL. Encrypt/decrypt lives in app/medical/labs.py, never inline.
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LabPanel(Base):
    __tablename__ = "lab_panels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    panel_type: Mapped[str] = mapped_column(Text, nullable=False)
    donation_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    hemoglobin_g_dl: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    hematocrit_pct: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    ferritin_ng_ml: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    iron: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    wbc: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    plt: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    next_eligible_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Fernet token (URL-safe base64), produced by app.core.encryption.
    notes_ciphertext: Mapped[str | None] = mapped_column("notes", Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class LabMetric(Base):
    __tablename__ = "lab_metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lab_panel_id: Mapped[int] = mapped_column(ForeignKey("lab_panels.id"), nullable=False)
    metric_name: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    unit: Mapped[str | None] = mapped_column(Text, nullable=True)
    ref_low: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    ref_high: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)


class NutritionLog(Base):
    __tablename__ = "nutrition_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        "timestamp", DateTime(timezone=True), nullable=False
    )
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    calories: Mapped[int | None] = mapped_column(nullable=True)
    protein_g: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    carbs_g: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    fat_g: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    water_ml: Mapped[int | None] = mapped_column(nullable=True)
    alcohol_units: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    caffeine_mg: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)


class SupplementProtocol(Base):
    __tablename__ = "supplement_protocols"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    supplement_name: Mapped[str] = mapped_column(Text, nullable=False)
    dose: Mapped[str | None] = mapped_column(Text, nullable=True)
    schedule_cron: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class SupplementLog(Base):
    __tablename__ = "supplement_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    protocol_id: Mapped[int] = mapped_column(
        ForeignKey("supplement_protocols.id"), nullable=False
    )
    taken_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    adherence: Mapped[bool] = mapped_column(nullable=False)
