"""/me — profile + UI preferences (the account IS the prefs store, migration
0007). The SPA mirrors locale/theme/units into localStorage for instant first
paint and reconciles on load."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CREDENTIALS_EXCEPTION, get_current_user, get_current_session
from app.core.security import hash_password, verify_password
from app.core.db import get_session
from app.models.integration import Integration
from app.models.user import AuthCredential, User, UserSession
from app.schemas.ui import MeOut, PasswordChange, ProfileUpdate

logger = logging.getLogger("app.api.me")
router = APIRouter(prefix="/me", tags=["me"])


async def _me_out(user: User, cred: AuthCredential, session) -> MeOut:
    from app.api.athlete import profile_out
    from app.services.ai_access import effective_access
    athlete = await profile_out(session, user.id)
    return MeOut(
        user_id=user.id,
        email=cred.email,
        name=user.name,
        dob=user.dob,
        sex=user.sex,
        height_cm=float(user.height_cm) if user.height_cm else None,
        timezone=user.timezone,
        locale=user.locale,
        theme=user.theme,
        units=user.units,
        role=cred.role,
        is_owner=cred.role == "owner",
        ai_access_tier=cred.ai_access_tier,
        main_integration_id=user.main_integration_id,
        training_focus=athlete["training_focus"], athlete_context=athlete["context"],
        athlete_revision=athlete["revision"], effective_ai_access=await effective_access(session, user.id),
    )


@router.get("", response_model=MeOut)
async def get_me(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeOut:
    cred = await session.get(AuthCredential, user.id)
    if cred is None:
        raise CREDENTIALS_EXCEPTION
    return await _me_out(user, cred, session)


@router.put("", response_model=MeOut)
async def update_me(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MeOut:
    from app.services.evidence import scope_lock
    await scope_lock(session, user.id, "changes")
    await session.refresh(user)
    cred = await session.get(AuthCredential, user.id)
    if cred is None:
        raise CREDENTIALS_EXCEPTION

    if payload.name is not None:
        user.name = payload.name
    if "dob" in payload.model_fields_set:
        user.dob = payload.dob
    if "sex" in payload.model_fields_set:
        user.sex = payload.sex
    if "height_cm" in payload.model_fields_set:
        user.height_cm = payload.height_cm
    if payload.timezone is not None:
        try:
            from zoneinfo import ZoneInfo

            ZoneInfo(payload.timezone)
        except Exception as exc:  # noqa: BLE001 — any tz error = bad input
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "unknown timezone"
            ) from exc
        user.timezone = payload.timezone
    if payload.locale is not None:
        user.locale = payload.locale
    if payload.theme is not None:
        user.theme = payload.theme
    if payload.units is not None:
        user.units = payload.units
    if "main_integration_id" in payload.model_fields_set:
        if payload.main_integration_id is None:
            user.main_integration_id = None
        else:
            integration = await session.get(Integration, payload.main_integration_id)
            if integration is None or integration.user_id != user.id:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    "integration does not belong to this account",
                )
            user.main_integration_id = integration.id
    if payload.athlete_profile is not None:
        from app.api.athlete import update_profile
        await update_profile(payload.athlete_profile, user, session)
    await session.commit()
    return await _me_out(user, cred, session)


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChange,
    principal: tuple[User, UserSession] = Depends(get_current_session),
    session: AsyncSession = Depends(get_session),
) -> None:
    user, current_session = principal
    cred = await session.scalar(
        select(AuthCredential).where(AuthCredential.user_id == user.id).with_for_update()
    )
    if cred is None:
        raise CREDENTIALS_EXCEPTION
    if not verify_password(cred.password_hash, payload.current_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "current password is incorrect"
        )
    cred.password_hash = hash_password(payload.new_password)
    await session.execute(delete(UserSession).where(
        UserSession.user_id == user.id, UserSession.id != current_session.id,
    ))
    await session.commit()
    logger.info("password changed for user %s", user.id)
