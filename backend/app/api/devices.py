"""GET /settings/devices + PUT /settings/devices/main — the device panel.

Lists every connected integration with its sync health and marks which one
is the user's MAIN device (users.main_integration_id, migration 0007).
Changing the main device returns the recompute plan: the device priority
law (services/device_merge.py) re-resolves history, so the UI can show a
"rebuilding scores" state instead of a silent fork.
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.integration import Integration
from app.models.user import User
from app.schemas.ui import DeviceOut, MainDeviceUpdate

logger = logging.getLogger("api.devices")

router = APIRouter(prefix="/settings/devices", tags=["devices"])


def _device_out(integration: Integration, user: User) -> DeviceOut:
    return DeviceOut(
        integration_id=integration.id,
        provider=integration.provider,
        status=integration.status,
        last_synced_at=integration.last_synced_at,
        is_main=(
            integration.id == user.main_integration_id
            or (user.main_integration_id is None and integration.provider == "garmin")
        ),
        connected_at=integration.created_at,
    )


@router.get("", response_model=list[DeviceOut])
async def list_devices(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[DeviceOut]:
    rows = (
        await session.scalars(
            select(Integration)
            .where(Integration.user_id == user.id)
            .order_by(Integration.created_at)
        )
    ).all()
    return [_device_out(i, user) for i in rows]


@router.put("/main", response_model=list[DeviceOut])
async def set_main_device(
    payload: MainDeviceUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[DeviceOut]:
    if payload.integration_id is not None:
        integration = await session.get(Integration, payload.integration_id)
        if integration is None or integration.user_id != user.id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "integration does not belong to this account",
            )
        user.main_integration_id = integration.id
    else:
        user.main_integration_id = None
    await session.commit()
    logger.info(
        "main device for user %s set to %s", user.id, payload.integration_id
    )

    # Range recompute so historical scores follow the new priority law
    # (best-effort: the task exists since Phase 3; queue failure must not
    # block the preference change).
    try:
        from app.tasks.feature_engine import recompute_features

        today = datetime.now(UTC).date()
        recompute_features.delay(
            user.id, (today - timedelta(days=365)).isoformat(), today.isoformat()
        )
    except Exception:  # noqa: BLE001 — broker down = recompute at next nightly
        logger.warning("recompute enqueue failed — nightly will cover it")

    rows = (
        await session.scalars(
            select(Integration).where(Integration.user_id == user.id)
        )
    ).all()
    return [_device_out(i, user) for i in rows]
