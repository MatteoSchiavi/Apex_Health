"""A single calendar record per dated profile goal; date-only means no start hour asserted."""
from datetime import date, datetime, time
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.models.coach import UserEvent

async def sync_profile_events(session, user, context):
    rows = (await session.scalars(select(UserEvent).where(UserEvent.user_id == user.id, UserEvent.profile_focus.is_not(None)))).all()
    existing = {r.profile_focus: r for r in rows}
    desired = {focus: value["event"] for focus, value in context.get("focuses", {}).items()
        if value.get("event", {}).get("date")}
    for focus, row in existing.items():
        if focus not in desired:
            await session.delete(row)
    for focus, target in desired.items():
        row = existing.get(focus)
        if row is None:
            row = UserEvent(user_id=user.id, profile_focus=focus, taper_days=0)
            session.add(row)
        row.title, row.priority = target["title"], target["priority"]
        row.kind = {"running": "run", "cycling": "ride", "gym": "gym"}[focus]
        row.starts_at = datetime.combine(date.fromisoformat(target["date"]), time.min, tzinfo=ZoneInfo(user.timezone))
        row.ends_at, row.date_only = None, True
        row.notes = None
