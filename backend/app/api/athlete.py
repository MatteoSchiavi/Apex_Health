"""Self-service athlete context and separate, voluntary AI consent."""
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.athlete import AthleteProfile, AiConsent
from app.models.lab import ChangeAudit
from app.models.user import User
from app.schemas.athlete import AthleteUpdate, ConsentUpdate
from app.services.ai_access import POLICY_VERSION, PURPOSE, provider_identity, effective_access, budget_state
from app.services.evidence import scope_lock

router = APIRouter(prefix="/athlete", tags=["athlete"])


async def profile_out(session, user_id):
    row = await session.get(AthleteProfile, user_id)
    return {"training_focus": row.training_focus if row else [],
        "context": row.context if row else {}, "revision": row.revision if row else 0}


@router.get("/profile")
async def profile(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return await profile_out(session, user.id)


@router.put("/profile")
async def update_profile(payload: AthleteUpdate, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await scope_lock(session, user.id, "changes")
    row = await session.get(AthleteProfile, user.id, populate_existing=True)
    if payload.expected_revision != (row.revision if row else 0):
        raise HTTPException(409, "Athlete context changed; reload before editing")
    context = payload.context.model_dump(mode="json", exclude_none=True)
    if row is None:
        row = AthleteProfile(user_id=user.id, revision=1)
        session.add(row)
    elif row.training_focus == payload.training_focus and row.context == context:
        return await profile_out(session, user.id)
    else:
        row.revision += 1
    row.training_focus, row.context, row.updated_at = payload.training_focus, context, datetime.now(UTC)
    await session.commit()
    return await profile_out(session, user.id)


@router.delete("/profile", status_code=204)
async def delete_profile(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await scope_lock(session, user.id, "changes")
    row = await session.get(AthleteProfile, user.id)
    # Keep a revision tombstone so a stale editor cannot resurrect deleted notes.
    if row:
        row.training_focus, row.context, row.revision = [], {}, row.revision + 1
        row.updated_at = datetime.now(UTC)
    await session.commit()


@router.get("/ai")
async def ai_state(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    consent = await session.get(AiConsent, user.id)
    return {"effective_access": await effective_access(session, user.id),
        "policy_version": POLICY_VERSION, "purpose": PURPOSE, "provider_identity": provider_identity(),
        "consent": {"active": consent.active, "accepted_at": consent.accepted_at,
            "withdrawn_at": consent.withdrawn_at, "policy_version": consent.policy_version,
            "provider_identity": consent.provider_identity} if consent else None,
        "budget": await budget_state(session, user.id)}


@router.put("/ai/consent")
async def consent_update(payload: ConsentUpdate, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await scope_lock(session, user.id, "ai_access")
    identity = provider_identity()
    if payload.active and (payload.policy_version != POLICY_VERSION or payload.provider_identity != identity or identity == "unconfigured"):
        raise HTTPException(409, "AI policy or provider changed; review the current disclosure")
    row = await session.get(AiConsent, user.id, populate_existing=True)
    now = datetime.now(UTC)
    if row and row.active == payload.active and (not payload.active or (row.policy_version == POLICY_VERSION and row.provider_identity == identity)):
        return await ai_state(user, session)
    if row is None:
        row = AiConsent(user_id=user.id, policy_version=POLICY_VERSION, purpose=PURPOSE, provider_identity=identity)
        session.add(row)
    row.active = payload.active
    if payload.active:
        row.policy_version, row.purpose, row.provider_identity = POLICY_VERSION, PURPOSE, identity
        row.accepted_at, row.withdrawn_at = now, None
    else:
        row.withdrawn_at = now
    session.add(ChangeAudit(user_id=user.id, action="ai_consent_accepted" if payload.active else "ai_consent_withdrawn",
        payload={"policy_version": row.policy_version, "purpose": row.purpose, "provider_identity": row.provider_identity, "timestamp": now.isoformat()}))
    await session.commit()
    return await ai_state(user, session)
