"""Authenticated event capture and owner-only aggregate utility measures."""
from datetime import UTC, datetime, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.deps import get_current_user, require_owner
from app.core.db import get_session
from app.models.alpha import AlphaEvent
from app.models.lab import ChangeDraft, DecisionRecord
from app.models.user import User
from app.services.alpha_events import record_event

router = APIRouter(tags=['alpha'])


class ClientEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event: Literal['overview_viewed', 'metric_explanation_opened']
    metric: str | None = Field(default=None, max_length=80)


@router.post('/alpha/events', status_code=204)
async def capture(payload: ClientEvent, user: User = Depends(get_current_user),
                  session: AsyncSession = Depends(get_session)):
    # Suppress render/retry bursts; this measures utility, not page-view precision.
    from app.services.evidence import scope_lock
    from app.metrics.registry import METRIC_REGISTRY
    from fastapi import HTTPException
    if payload.metric is not None and payload.metric not in METRIC_REGISTRY:
        raise HTTPException(422, 'Unknown metric')
    await scope_lock(session, user.id, 'alpha-event:' + payload.event)
    since = datetime.now(UTC) - timedelta(minutes=1)
    metadata = {'metric': payload.metric} if payload.metric else {}
    existing = await session.scalar(select(AlphaEvent.id).where(
        AlphaEvent.user_id == user.id, AlphaEvent.event == payload.event,
        AlphaEvent.created_at >= since,
        AlphaEvent.metadata_json == metadata).limit(1))
    if not existing:
        record_event(session, user.id, payload.event, metadata)
        await session.commit()


@router.get('/api/admin/alpha', dependencies=[Depends(require_owner)])
async def aggregates(days: int = Query(28, ge=7, le=90),
                     session: AsyncSession = Depends(get_session)):
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=days)
    counts = dict((await session.execute(select(AlphaEvent.event, func.count())
        .where(AlphaEvent.created_at >= cutoff).group_by(AlphaEvent.event))).all())
    activity_events = {'overview_viewed', 'metric_explanation_opened', 'agent_question_asked',
        'integration_connected', 'decision_feedback_submitted', 'change_accepted',
        'change_rejected', 'change_edited', 'experiment_created'}
    active = await session.scalar(select(func.count(func.distinct(AlphaEvent.user_id)))
        .where(AlphaEvent.created_at >= now - timedelta(days=7), AlphaEvent.event.in_(activity_events)))
    ai_users = await session.scalar(select(func.count(func.distinct(AlphaEvent.user_id)))
        .where(AlphaEvent.created_at >= cutoff, AlphaEvent.event == 'agent_question_asked'))
    drafts = dict((await session.execute(select(ChangeDraft.status, func.count())
        .where(ChangeDraft.created_at >= cutoff).group_by(ChangeDraft.status))).all())
    proposals = sum(drafts.values())
    accepted = sum(drafts.get(k, 0) for k in ('applied_locally', 'undone'))
    rejected = drafts.get('rejected', 0)
    proposal_ids = select(ChangeDraft.id).where(ChangeDraft.created_at >= cutoff)
    edited = await session.scalar(select(func.count(func.distinct(AlphaEvent.metadata_json['draft_id'].astext)))
        .where(AlphaEvent.event == 'change_edited', AlphaEvent.created_at >= cutoff,
               AlphaEvent.metadata_json['draft_id'].astext.cast(BigInteger).in_(proposal_ids))) or 0
    feedback = (await session.scalars(select(DecisionRecord.outcome).where(
        DecisionRecord.created_at >= cutoff, DecisionRecord.outcome.is_not(None)))).all()
    answered = [o for o in feedback if isinstance(o, dict) and o.get('influenced_plan') in {'yes', 'partly', 'no'}]
    influence = sum(o['influenced_plan'] in {'yes', 'partly'} for o in answered)
    provider_name = AlphaEvent.metadata_json['provider'].astext
    failures = dict((await session.execute(select(provider_name,
        func.count()).where(AlphaEvent.created_at >= cutoff,
        AlphaEvent.event == 'integration_sync_failure').group_by(provider_name))).all())
    return {'window_days': days, 'weekly_active_alpha_users': active or 0,
        'ai_users': ai_users or 0, 'proposals': proposals,
        'acceptance_rate': accepted / proposals if proposals else None,
        'edit_rate': edited / proposals if proposals else None,
        'rejection_rate': rejected / proposals if proposals else None,
        'decision_influence_rate': influence / len(answered) if answered else None,
        'decision_feedback_responses': len(answered),
        'provider_failure_counts': {k or 'unknown': v for k, v in failures.items()},
        'events': counts,
        'formula': 'Decision influence = latest yes or partly outcomes / latest yes, partly or no outcomes for decisions created in the window. Missing responses are excluded; this measures reported influence, not physiological benefit.'}
