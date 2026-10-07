"""Authenticated feedback: durable commit precedes best-effort notification."""
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.admin import Feedback
from app.models.user import User, AuthCredential
from app.services.owner_notifications import enqueue, best_effort_dispatch
router = APIRouter(prefix="/api/feedback", tags=["feedback"])

class FeedbackIn(BaseModel):
    category: Literal["bug", "idea", "other"] = "other"
    message: str = Field(min_length=1, max_length=2000)
    page_url: str | None = Field(default=None, max_length=500)

    @field_validator("message")
    @classmethod
    def clean_message(cls, value):
        value = ''.join(c for c in value.strip() if c in '\n\t' or ord(c) >= 32)
        # Redact obvious credentials submitted accidentally; never send URLs' queries.
        value = re.sub(r'(?i)bearer\s+[^\s]+', 'Bearer [redacted]', value)
        value = re.sub(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[redacted]', value)
        value = re.sub(r'(?i)(token|password|secret|authorization|api[_-]?key)\s*[:=]\s*\S+', r'\1=[redacted]', value)
        value = re.sub(r'https?://[^\s]+', lambda m: cls.clean_url(m[0]) or '/', value)
        if not value:
            raise ValueError("Message is required")
        return value

    @field_validator("page_url")
    @classmethod
    def clean_url(cls, value):
        if not value:
            return None
        parsed = urlsplit(value)
        # Store only the route, never userinfo, host, query, fragment or invite capability.
        path = parsed.path if parsed.path.startswith('/') else '/'
        return re.sub(r'(?i)(/invite/)[^/]+', r'\1[redacted]', path)[:200]

@router.post("", status_code=201)
async def create_feedback(payload: FeedbackIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    # Lock the account row: concurrent submissions cannot bypass DB rate limit.
    await session.execute(select(User.id).where(User.id == user.id).with_for_update())
    count = await session.scalar(select(func.count()).select_from(Feedback).where(Feedback.user_id == user.id, Feedback.created_at > datetime.now(UTC)-timedelta(hours=1)))
    if count >= 5:
        raise HTTPException(429, "Feedback limit reached; try again later")
    row = Feedback(user_id=user.id, category=payload.category, message=payload.message, page_url=payload.page_url)
    session.add(row)
    await session.flush()
    credential = await session.get(AuthCredential, user.id)
    identity = FeedbackIn.clean_message(user.name.strip() or f"User #{user.id}")[:100]
    email = credential.email[:254] if credential else "unavailable"
    notification = enqueue(session, "feedback", f"Apex Health feedback #{row.id} · user #{user.id} · {row.category}\nFrom: {identity} ({email})\nTime: {row.created_at.isoformat()}\n{row.message}\nPage: {row.page_url or '/'}", feedback_id=row.id)
    await session.commit()
    feedback_id, created_at, notification_id = row.id, row.created_at, notification.id
    delivered = await best_effort_dispatch(session, notification_id)
    return {"id": feedback_id, "created_at": created_at, "notification_status": "delivered" if delivered else "pending"}
