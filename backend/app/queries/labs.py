"""Labs reads (§8.2 shared query layer — §8.3 tools get_lab_trend,
get_donation_status). The same functions the future agent tools and report
tasks call; Phase 4 maps the ORM models these were reading via SQL before.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.medical.labs import MARKER_ALIASES
from app.models.medical import LabMetric, LabPanel


async def get_lab_trend(
    session: AsyncSession,
    user_id: int,
    marker: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    """One marker's series across panels (§8.3 get_lab_trend), with the lab's
    reference range attached when recorded. Accepts canonical names
    ("ferritin") and column aliases ("ferritin_ng_ml")."""
    canonical = MARKER_ALIASES.get(marker, marker)
    rows = (
        await session.execute(
            select(LabPanel.date, LabMetric.value, LabMetric.unit, LabMetric.ref_low, LabMetric.ref_high)
            .join(LabMetric, LabMetric.lab_panel_id == LabPanel.id)
            .where(LabPanel.user_id == user_id, LabMetric.metric_name == canonical)
            .order_by(LabPanel.date)
        )
    ).all()
    if start_date is not None:
        rows = [r for r in rows if r[0] >= start_date]
    if end_date is not None:
        rows = [r for r in rows if r[0] <= end_date]
    return [
        {
            "date": r.date,
            "value": float(r.value),
            "unit": r.unit,
            "ref_low": float(r.ref_low) if r.ref_low is not None else None,
            "ref_high": float(r.ref_high) if r.ref_high is not None else None,
        }
        for r in rows
    ]


async def get_donation_status(
    session: AsyncSession, user_id: int, today: date
) -> dict | None:
    """Last donation + eligibility (§8.3 get_donation_status)."""
    panel = (
        await session.scalars(
            select(LabPanel)
            .where(
                LabPanel.user_id == user_id,
                LabPanel.donation_type.is_not(None),
            )
            .order_by(LabPanel.date.desc())
            .limit(1)
        )
    ).first()
    if panel is None:
        return None
    return {
        "donation_type": panel.donation_type,
        "date": panel.date,
        "next_eligible_date": panel.next_eligible_date,
        "days_since": (today - panel.date).days,
    }
