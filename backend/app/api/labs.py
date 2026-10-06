"""Labs endpoints (MASTER_SPEC §18): GET /labs, GET /labs/{id}, POST /labs.

Session-protected like every non-public route (§17); POST is state-changing
so it requires the CSRF header (§22.3). POST evaluates the low-ferritin rule
(§23 Phase 4 AC1) and stores any resulting alert for the in-app inbox.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.db import get_session
from app.medical.labs import (
    decrypt_notes,
    evaluate_ferritin_alert,
    record_lab_panel,
)
from app.models.medical import LabPanel, LabMetric
from app.models.user import User
from app.schemas.labs import LabPanelIn, LabPanelOut

router = APIRouter(prefix="/labs", tags=["labs"])


def _to_out(panel: LabPanel, markers=None) -> LabPanelOut:
    return LabPanelOut(
        id=panel.id,
        panel_date=panel.date,
        panel_type=panel.panel_type,
        donation_type=panel.donation_type,
        hemoglobin=float(panel.hemoglobin_g_dl)
        if panel.hemoglobin_g_dl is not None
        else None,
        hematocrit=float(panel.hematocrit_pct)
        if panel.hematocrit_pct is not None
        else None,
        ferritin=float(panel.ferritin_ng_ml)
        if panel.ferritin_ng_ml is not None
        else None,
        iron=float(panel.iron) if panel.iron is not None else None,
        wbc=float(panel.wbc) if panel.wbc is not None else None,
        plt=float(panel.plt) if panel.plt is not None else None,
        next_eligible_date=panel.next_eligible_date,
        source=panel.source,
        notes=decrypt_notes(panel),
        markers=[
            {
                "marker": r.metric_name,
                "value": float(r.value),
                "unit": r.unit,
                "ref_low": float(r.ref_low) if r.ref_low is not None else None,
                "ref_high": float(r.ref_high) if r.ref_high is not None else None,
            }
            for r in markers or []
        ],
    )


@router.get("", response_model=list[LabPanelOut])
async def list_panels(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[LabPanelOut]:
    panels = (
        await session.scalars(
            select(LabPanel)
            .where(LabPanel.user_id == user.id)
            .order_by(LabPanel.date.desc(), LabPanel.id.desc())
            .limit(100)
        )
    ).all()
    markers = (
        (
            await session.scalars(
                select(LabMetric).where(
                    LabMetric.lab_panel_id.in_([p.id for p in panels])
                )
            )
        ).all()
        if panels
        else []
    )
    by_panel = {}
    for r in markers:
        by_panel.setdefault(r.lab_panel_id, []).append(r)
    return [_to_out(p, by_panel.get(p.id)) for p in panels]


@router.get("/{panel_id}", response_model=LabPanelOut)
async def get_panel(
    panel_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> LabPanelOut:
    panel = await session.get(LabPanel, panel_id)
    if panel is None or panel.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Panel not found")
    markers = (
        await session.scalars(
            select(LabMetric).where(LabMetric.lab_panel_id == panel.id)
        )
    ).all()
    return _to_out(panel, markers)


@router.post("", response_model=LabPanelOut, status_code=status.HTTP_201_CREATED)
async def create_panel(
    payload: LabPanelIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> LabPanelOut:
    panel = await record_lab_panel(
        session,
        user_id=user.id,
        panel_date=payload.panel_date,
        panel_type=payload.panel_type,
        donation_type=payload.donation_type,
        hemoglobin=payload.hemoglobin,
        hematocrit=payload.hematocrit,
        ferritin=payload.ferritin,
        iron=payload.iron,
        wbc=payload.wbc,
        plt=payload.plt,
        next_eligible_date=payload.next_eligible_date,
        source="web",
        notes=payload.notes,
        extra_markers=payload.extra_markers,
        reference_ranges=payload.reference_ranges,
    )
    await evaluate_ferritin_alert(session, panel)
    await session.commit()

    markers = (
        await session.scalars(
            select(LabMetric).where(LabMetric.lab_panel_id == panel.id)
        )
    ).all()
    return _to_out(panel, markers)
