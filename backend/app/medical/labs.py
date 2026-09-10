"""Medical module — lab panel ingestion (MASTER_SPEC §6.4, §17, §23 Phase 4).

Every panel entry flows through `record_lab_panel`:
- fixed marker columns are written as structured data (SQL-queryable, §8.3),
- EVERY provided marker also gets a `lab_metrics` row (value/unit/ref range),
  so `get_lab_trend` has one uniform series path,
- `notes` is encrypted at the application layer BEFORE it touches disk (§17)
  and is only ever decrypted through `decrypt_notes`,
- a ferritin value below the panel's own lab-provided reference low (or the
  configured default when the lab gave none) fires a `low_ferritin` alert —
  DB-backed first, pushed to Telegram by the caller after commit (§21).
"""

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.encryption import decrypt_bytes, encrypt_bytes
from app.models.alert import Alert
from app.models.medical import LabMetric, LabPanel

logger = logging.getLogger("medical.labs")

# Canonical marker names for the fixed panel columns, with their units.
# Extra markers (anything not listed here) land only in lab_metrics.
STANDARD_MARKERS: dict[str, str] = {
    "hemoglobin": "g/dL",
    "hematocrit": "%",
    "ferritin": "ng/mL",
    "iron": "µg/dL",
    "wbc": "10³/µL",
    "plt": "10³/µL",
}
# Aliases accepted for trend lookups, mapping to the canonical marker name.
MARKER_ALIASES: dict[str, str] = {
    "ferritin_ng_ml": "ferritin",
    "hemoglobin_g_dl": "hemoglobin",
    "hematocrit_pct": "hematocrit",
}


def _decimal(value: float | int | str | Decimal | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def encrypt_notes(plaintext: str | None) -> str | None:
    """§17: ciphertext only — the plaintext never reaches the DB layer."""
    if plaintext is None:
        return None
    return encrypt_bytes(plaintext.encode("utf-8")).decode("ascii")


def decrypt_notes(panel: LabPanel) -> str | None:
    if panel.notes_ciphertext is None:
        return None
    return decrypt_bytes(panel.notes_ciphertext.encode("ascii")).decode("utf-8")


async def record_lab_panel(
    session: AsyncSession,
    *,
    user_id: int,
    panel_date: date,
    panel_type: str,
    donation_type: str | None = None,
    hemoglobin: float | Decimal | None = None,
    hematocrit: float | Decimal | None = None,
    ferritin: float | Decimal | None = None,
    iron: float | Decimal | None = None,
    wbc: float | Decimal | None = None,
    plt: float | Decimal | None = None,
    next_eligible_date: date | None = None,
    source: str = "manual",
    notes: str | None = None,
    extra_markers: list[dict] | None = None,
    reference_ranges: dict[str, tuple[float | None, float | None]] | None = None,
) -> LabPanel:
    """Insert one lab panel row + its lab_metrics mirror rows (caller commits).

    `reference_ranges` carries the lab's own reference intervals for the
    standard markers, e.g. {"ferritin": (30, 400)} — stored on the
    lab_metrics row and consumed by the ferritin alert rule.
    """
    ranges = reference_ranges or {}
    column_values = {
        "hemoglobin_g_dl": _decimal(hemoglobin),
        "hematocrit_pct": _decimal(hematocrit),
        "ferritin_ng_ml": _decimal(ferritin),
        "iron": _decimal(iron),
        "wbc": _decimal(wbc),
        "plt": _decimal(plt),
    }
    panel = LabPanel(
        user_id=user_id,
        date=panel_date,
        panel_type=panel_type,
        donation_type=donation_type,
        next_eligible_date=next_eligible_date,
        source=source,
        notes_ciphertext=encrypt_notes(notes),
        **column_values,
    )
    session.add(panel)
    await session.flush()

    # lab_metrics mirror: one row per provided marker (standard + extra) so
    # trends read a single uniform table with units and reference ranges.
    for marker, value in (
        ("hemoglobin", column_values["hemoglobin_g_dl"]),
        ("hematocrit", column_values["hematocrit_pct"]),
        ("ferritin", column_values["ferritin_ng_ml"]),
        ("iron", column_values["iron"]),
        ("wbc", column_values["wbc"]),
        ("plt", column_values["plt"]),
    ):
        if value is None and marker not in ranges:
            continue
        ref_low, ref_high = ranges.get(marker, (None, None))
        session.add(
            LabMetric(
                lab_panel_id=panel.id,
                metric_name=marker,
                value=value if value is not None else _decimal(ref_low) or Decimal(0),
                unit=STANDARD_MARKERS[marker],
                ref_low=_decimal(ref_low),
                ref_high=_decimal(ref_high),
            )
        )
    for m in extra_markers or []:
        session.add(
            LabMetric(
                lab_panel_id=panel.id,
                metric_name=m["name"],
                value=_decimal(m["value"]),
                unit=m.get("unit"),
                ref_low=_decimal(m.get("ref_low")),
                ref_high=_decimal(m.get("ref_high")),
            )
        )
    return panel


async def ferritin_reference_low(session: AsyncSession, panel: LabPanel) -> Decimal:
    """The threshold the low-ferritin rule compares against.

    The lab's own reference low wins when the panel carries one; otherwise
    the configured default applies (LOW_FERRITIN_NG_ML, 30 ng/mL — a
    commonly used depleted-iron-stores cutoff for blood donors; the spec
    leaves the exact number open, so it is the single documented tunable).
    """
    row = await session.scalar(
        select(LabMetric.ref_low)
        .where(
            LabMetric.lab_panel_id == panel.id,
            LabMetric.metric_name.in_(("ferritin", "ferritin_ng_ml")),
            LabMetric.ref_low.is_not(None),
        )
        .limit(1)
    )
    if row is not None:
        return row
    return Decimal(str(get_settings().low_ferritin_ng_ml))


async def evaluate_ferritin_alert(
    session: AsyncSession, panel: LabPanel
) -> Alert | None:
    """AC1 (§23 Phase 4): a low-ferritin entry fires an alert.

    Only a value actually below the threshold fires; a panel without a
    ferritin value never fires. The alert row is added to the session —
    the caller commits, then pushes it to Telegram (§21 pattern from
    app/connectors/telegram/alerts.py).
    """
    if panel.ferritin_ng_ml is None:
        return None
    threshold = await ferritin_reference_low(session, panel)
    if panel.ferritin_ng_ml >= threshold:
        return None
    alert = Alert(
        user_id=panel.user_id,
        type="low_ferritin",
        severity="warning",
        message=(
            f"Ferritin {panel.ferritin_ng_ml} ng/mL is below the "
            f"{threshold} ng/mL reference — iron stores may be depleted"
            + (" after a donation" if panel.donation_type else "")
        ),
    )
    session.add(alert)
    return alert
