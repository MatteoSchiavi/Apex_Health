"""Owned structured workouts, explicit approval and AI-independent education."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.user import User
from app.models.activity import Discipline
from app.models.structured_workout import StructuredWorkoutDraft, StructuredWorkoutVersion
from sqlalchemy import select
from app.schemas.workouts import WorkoutDraftIn, WorkoutConfirmationIn
from app.services import structured_workouts as service

router = APIRouter(prefix='/athlete',tags=['structured-workouts'])

@router.get('/planned-sessions/{ident}/workout')
async def workout(ident:int,user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)):
    planned,plan = await service.owned(session,user.id,ident)
    version = await service.latest(session,user.id,ident)
    discipline = await session.scalar(select(Discipline.name).where(Discipline.id==planned.discipline_id))
    reason = await service.edit_block_reason(session,user.id,planned,plan)
    pending = await session.scalar(select(StructuredWorkoutDraft).where(
        StructuredWorkoutDraft.user_id==user.id,StructuredWorkoutDraft.planned_session_id==ident,
        StructuredWorkoutDraft.status=='draft').order_by(StructuredWorkoutDraft.id.desc()).limit(1))
    if pending and (pending.plan_revision!=plan.revision or pending.workout_revision!=(version.revision if version else 0)):
        pending = None
    history = (await session.scalars(select(StructuredWorkoutVersion).where(
        StructuredWorkoutVersion.user_id==user.id,StructuredWorkoutVersion.planned_session_id==ident)
        .order_by(StructuredWorkoutVersion.revision.desc()).limit(20))).all()
    return {'planned_session_id':ident,'plan_revision':plan.revision,'protected':planned.protected or plan.protected,
        'editable':reason is None,'edit_block_reason':reason,
        'pending_draft':service.draft_out(pending) if pending else None,
        'history':[service.receipt(row) for row in history],
        'workout':service.receipt(version) if version else None,
        'session':{'date':str(planned.date),'discipline':discipline,'session_type':planned.session_type,
            'duration_min':planned.target_duration_min,'description':planned.description},
        'education':service.education(service.structure_of(version),user.locale) if version else []}

@router.post('/planned-sessions/{ident}/workout-drafts',status_code=201)
async def create_draft(ident:int,payload:WorkoutDraftIn,user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)):
    return await service.create_draft(session,user,payload,ident)

@router.post('/workout-drafts/{ident}/confirm')
async def confirm(ident:int,payload:WorkoutConfirmationIn,user:User=Depends(get_current_user),session:AsyncSession=Depends(get_session)):
    return await service.confirm(session,user,ident,payload)
