"""Owner-scoped, explicitly reviewed comparison context edits."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.activity import Activity, ActivitySourceLink
from app.models.lab import ChangeAudit
from app.models.user import User
from app.schemas.activity_comparison import ComparisonContextUpdate
from app.services.activity_comparison import comparison_view, context_revision, update_assertion
from app.services.evidence import scope_lock

router = APIRouter(prefix="/activities", tags=["activity-comparison"])


async def owned_activity(session, user_id: int, activity_id: int, *, lock: bool = False):
    query = select(Activity).where(Activity.id == activity_id, Activity.user_id == user_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    activity = await session.scalar(query)
    if activity is None:
        raise HTTPException(404, "activity not found")
    return activity


async def linked_providers(session, user_id: int, activity_id: int) -> list[str]:
    sources = (await session.scalars(select(ActivitySourceLink.source).where(
        ActivitySourceLink.activity_id == activity_id, ActivitySourceLink.user_id == user_id).distinct())).all()
    # Provider keys are never supplied freely by the client. Exclude unexpected
    # legacy keys rather than granting access to arbitrary metadata namespaces.
    import re
    return sorted(source for source in sources if re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", source))[:16]


@router.get("/{activity_id}/comparison-context")
async def read_context(activity_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    activity = await owned_activity(session, user.id, activity_id)
    return comparison_view(activity, await linked_providers(session, user.id, activity_id))


@router.put("/{activity_id}/comparison-context")
async def save_context(activity_id: int, payload: ComparisonContextUpdate, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    # Same transaction-scoped lock used by imports/other user mutations, then
    # row lock and refresh: review cannot overwrite a concurrent context edit.
    await scope_lock(session, user.id, "changes")
    activity = await owned_activity(session, user.id, activity_id, lock=True)
    providers = await linked_providers(session, user.id, activity_id)
    before_revision = context_revision(activity.source_metrics, providers)
    try:
        updated = update_assertion(activity.source_metrics, providers, payload, user_id=user.id)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    activity.source_metrics = updated
    session.add(ChangeAudit(user_id=user.id, action="activity_comparison_context_saved" if payload.context else "activity_comparison_context_removed", payload={
        "activity_id": activity.id, "provider": payload.provider, "before_revision": before_revision,
        "after_revision": context_revision(updated, providers), "context": payload.context.model_dump() if payload.context else None,
        "provenance": "athlete_asserted_not_provider_verified",
    }))
    await session.commit()
    return comparison_view(activity, providers)
