"""User edits create a fresh reviewable draft; they never execute a change."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.lab import ChangeAudit
from app.models.user import User
from app.schemas.changes import Strict, ProposeIn
from app.services.changes import owned_draft, propose
from app.services.evidence import scope_lock
from app.services.alpha_events import record_event

router = APIRouter(prefix='/lab/changes', tags=['changes'])


class SessionDraftEdit(Strict):
    target_duration_min: int | None = Field(default=None, ge=0, le=1440)
    description: str | None = Field(default=None, max_length=2000)
    session_type: str | None = Field(default=None, max_length=80)
    reason: str | None = Field(default=None, min_length=1, max_length=2000)


@router.post('/{ident}/edit')
async def edit_draft(ident: int, payload: SessionDraftEdit,
                     user: User = Depends(get_current_user),
                     session: AsyncSession = Depends(get_session)):
    await scope_lock(session, user.id, 'changes')
    original = await owned_draft(session, user.id, ident)
    if original.status != 'draft' or original.kind != 'session_patch':
        raise HTTPException(409, 'Only an unapplied session draft can be edited')
    updates = payload.model_dump(exclude_none=True, exclude={'reason'})
    if not updates:
        raise HTTPException(422, 'Specify a session change')
    proposed = ProposeIn(change={**original.payload, **updates},
        reason=payload.reason or original.reason, evidence_ids=original.evidence_ids)
    replacement = await propose(session, user.id, proposed)
    original.status = 'superseded'
    session.add(ChangeAudit(user_id=user.id, draft_id=original.id, action='edited',
        payload={'replacement_draft_id': replacement['id']}))
    record_event(session, user.id, 'change_edited', {'draft_id': original.id})
    await session.commit()
    return replacement
