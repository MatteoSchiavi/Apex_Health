"""Settings endpoints (MASTER_SPEC §18 Settings resource).

Owner-only surface (§18 "enforced by role"):
  POST   /settings/invites          mint an invite code (§15)
  GET    /settings/invites          list invites + redemption state
  DELETE /settings/invites/{id}     revoke an unused invite
  PATCH  /settings/users/{id}/ai-tier   raise/lower a friend's AI tier (§8)

Judgment call (documented in README): /settings/integrations (§18) stays in
app/api/integrations.py and remains PER-USER rather than owner-only — under
§15 friend onboarding every friend connects their own Garmin/Technogym
accounts and the data model is user-scoped throughout (integrations.user_id).
Friends manage their own connectors; account creation and AI-cost privileges
are what actually need the owner.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_owner
from app.auth.invites import InviteError, create_invite, is_expired, revoke_invite
from app.core.db import get_session
from app.models.user import AuthCredential, Invite, User
from app.schemas.auth import AiTierUpdateRequest, InviteCreateRequest, InviteOut

router = APIRouter(prefix="/settings", tags=["settings"])


def _to_out(invite: Invite) -> InviteOut:
    return InviteOut(
        id=invite.id,
        code=invite.code,
        created_by=invite.created_by,
        used_by=invite.used_by,
        expires_at=invite.expires_at,
        created_at=invite.created_at,
        expired=is_expired(invite),
    )


@router.post("/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
async def mint_invite(
    payload: InviteCreateRequest | None = None,
    session: AsyncSession = Depends(get_session),
    owner: AuthCredential = Depends(require_owner),
) -> InviteOut:
    """Mint one invite code. The code is returned ONCE per call and stored
    in plaintext by design (§6.4: code is the capability; anyone holding a
    live code can create one friend account — treat it like a password)."""
    body = payload or InviteCreateRequest()
    invite = await create_invite(
        session, created_by=owner.user_id, expires_in_days=body.expires_in_days
    )
    return _to_out(invite)


@router.get("/invites", response_model=list[InviteOut])
async def list_invites(
    session: AsyncSession = Depends(get_session),
    owner: AuthCredential = Depends(require_owner),
) -> list[InviteOut]:
    invites = (
        await session.scalars(
            select(Invite).order_by(Invite.created_at.desc(), Invite.id.desc()).limit(200)
        )
    ).all()
    return [_to_out(i) for i in invites]


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invite(
    invite_id: int,
    session: AsyncSession = Depends(get_session),
    owner: AuthCredential = Depends(require_owner),
) -> None:
    try:
        found = await revoke_invite(session, invite_id, owner.user_id)
    except InviteError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Invite already redeemed; redemption history cannot be revoked",
        )
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found")


@router.patch("/users/{user_id}/ai-tier")
async def update_ai_tier(
    user_id: int,
    payload: AiTierUpdateRequest,
    session: AsyncSession = Depends(get_session),
    owner: AuthCredential = Depends(require_owner),
) -> dict:
    """§18 /settings/users/{id}/ai-tier — flip a friend between cheap_only
    and full (§8.6 budget applies per user either way). The owner's own tier
    is fixed at 'full': the account that pays for the platform doesn't
    downgrade its own AI."""
    target_cred = await session.get(AuthCredential, user_id)
    if target_cred is None:
        target_user = await session.get(User, user_id)
        if target_user is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User has no credentials")
    if target_cred.role == "owner":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The owner's AI tier is fixed at 'full'",
        )
    target_cred.ai_access_tier = payload.ai_access_tier
    await session.commit()
    return {
        "user_id": user_id,
        "email": target_cred.email,
        "role": target_cred.role,
        "ai_access_tier": target_cred.ai_access_tier,
    }
