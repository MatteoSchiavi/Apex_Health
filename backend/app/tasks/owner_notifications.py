"""Operational-only owner notifications and bounded retry outbox."""
from datetime import UTC, datetime, timedelta
from celery.signals import after_setup_logger, after_setup_task_logger, task_failure
from sqlalchemy import delete, func, select
from app.core.db import sessionmaker
from app.models.admin import Feedback, OwnerNotification
from app.models.user import UserSession, AuthCredential
from app.services.owner_notifications import enqueue, dispatch
from app.tasks.celery_app import celery_app
from app.tasks.runtime import run_async

@after_setup_logger.connect
@after_setup_task_logger.connect
def setup_worker_logs(**kwargs):
    from app.core.logging import install_operational_buffer
    install_operational_buffer()

@celery_app.task(name='owner.dispatch',soft_time_limit=120,time_limit=150)
def dispatch_notifications():
    return run_async(_dispatch())

async def _dispatch():
    await _collect_critical_events()
    async with sessionmaker() as session:
        sent=await dispatch(session)
        await session.execute(delete(OwnerNotification).where(OwnerNotification.feedback_id.is_(None), OwnerNotification.delivered_at < datetime.now(UTC)-timedelta(days=30)))
        await session.commit()
        return {'delivered':sent}

@celery_app.task(name='owner.daily_summary',soft_time_limit=30,time_limit=45)
def daily_summary():
    return run_async(_daily_summary())

async def _daily_summary():
    async with sessionmaker() as session:
        from app.services.admin_monitoring import system_metrics
        metrics = await system_metrics(session)
        today=datetime.now(UTC).replace(hour=0,minute=0,second=0,microsecond=0)
        # Beat duplication cannot produce duplicate summaries: transaction advisory lock.
        from sqlalchemy import text
        await session.execute(text("SELECT pg_advisory_xact_lock(73150421)"))
        exists=await session.scalar(select(OwnerNotification.id).where(OwnerNotification.kind=='daily_summary',OwnerNotification.created_at>=today).limit(1))
        if exists: return {'queued':False}
        users=await session.scalar(select(func.count()).select_from(AuthCredential))
        active=await session.scalar(select(func.count()).select_from(UserSession).where(UserSession.expires_at>datetime.now(UTC), (UserSession.absolute_expires_at.is_(None)) | (UserSession.absolute_expires_at>datetime.now(UTC))))
        feedback=await session.scalar(select(func.count()).select_from(Feedback).where(Feedback.created_at>=today-timedelta(days=1)))
        pending=await session.scalar(select(func.count()).select_from(OwnerNotification).where(OwnerNotification.delivered_at.is_(None)))
        cpu, memory, disk, pg, workers = (metrics[key] for key in ('cpu','memory','disk','postgres','celery'))
        resources = f"\nCPU: {cpu.get('utilization_percent')}% · load {cpu.get('load_1m')} · {cpu.get('scope')}\nRAM: {memory.get('used_bytes')}/{memory.get('total_bytes')} bytes · {memory.get('scope')}\nDisk: {disk.get('used_bytes')}/{disk.get('total_bytes')} bytes · {disk.get('scope')}\nPostgreSQL: {pg.get('active_connections', 'unavailable')} active / {pg.get('connections', 'unavailable')} connections (max {pg.get('max_connections', 'unavailable')})\nCelery: {len(workers.get('workers', []))} responding workers · {'available' if workers.get('available') else 'unavailable'}"
        notification=enqueue(session,'daily_summary',f'Apex Health operational summary (UTC)\nAccounts: {users}\nActive sessions: {active}\nFeedback since yesterday UTC: {feedback}\nPending notifications: {pending}' + resources)
        await session.commit();await dispatch(session,1,notification_id=notification.id)
        return {'queued':True}


@task_failure.connect
def capture_task_failure(sender=None, **kwargs):
    import logging
    # Never log args, kwargs, exception, result or traceback from the signal.
    logging.getLogger('tasks.runtime').error('Task failed', extra={'event_code':'task_failed'})

async def _collect_critical_events():
    import json
    from app.core.redis import get_redis
    redis=get_redis()
    try:
        entries=await redis.lrange('apex:operational:critical',0,49)
        async with sessionmaker() as session:
            from sqlalchemy.dialects.postgresql import insert
            for raw in entries:
                try:
                    event=json.loads(raw)
                    key=event['id']
                    source=event['source']
                    code=event['event']
                    if not all(isinstance(x,str) for x in (key,source,code)): continue
                    # Source/code were allowlisted before entering Redis; strip
                    # again because Redis is a separate infrastructure boundary.
                    import re
                    if not re.fullmatch(r'[a-f0-9]{32}',key) or not re.fullmatch(r'[a-zA-Z0-9_.-]{1,80}',source) or not re.fullmatch(r'[a-z_]{1,40}',code): continue
                except (ValueError,KeyError,TypeError): continue
                import hashlib
                group_key=hashlib.sha256(f"{source}:{code}:{datetime.now(UTC).strftime('%Y%m%d%H')}".encode()).hexdigest()
                await session.execute(insert(OwnerNotification).values(kind='system_error',message=f'Apex Health critical system event: {code} · {source}. Review owner operational logs.',event_key=group_key).on_conflict_do_nothing(index_elements=['event_key']))
            await session.commit()
        # Remove only committed entries; a crash before removal is deduplicated
        # by the unique database event_key on the next minute's dispatcher.
        for raw in entries: await redis.lrem('apex:operational:critical',1,raw)
    except Exception:
        pass
    finally:
        await redis.aclose()
