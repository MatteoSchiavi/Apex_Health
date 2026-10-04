"""Evidence backfill/repair jobs with durable progress and cooperative cancellation."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select, text
from app.core.db import engine, sessionmaker
from app.models.integration import Integration, RawIngest
from app.models.lab import LabJob
from app.models.user import User
from app.services.evidence import index_garmin_payload
from app.tasks.celery_app import celery_app
from app.tasks.runtime import run_async


async def dispatch_jobs():
    async with sessionmaker() as session:
        rows = (
            await session.scalars(
                select(LabJob)
                .where(
                    (LabJob.state == "queued")
                    | (
                        (LabJob.state == "running")
                        & (LabJob.updated_at < datetime.now(UTC) - timedelta(minutes=2))
                    )
                )
                .order_by(LabJob.id)
                .limit(20)
            )
        ).all()
        ids = [r.id for r in rows]
    for ident in ids:
        celery_app.send_task("lab.run_job", args=[ident], task_id=f"lab-job-{ident}")
    return {"dispatched": len(ids)}


async def run_job(ident):
    # Session-level lock survives each checkpoint transaction. A crashed worker
    # releases it automatically; resumed jobs use their stored cursor.
    async with engine.connect() as connection:
        if not await connection.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": -800000000000 + ident}
        ):
            return {"state": "already_running"}
        try:
            return await _run(ident)
        finally:
            await connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": -800000000000 + ident}
            )


async def _run(ident):
    async with sessionmaker() as session:
        job = await session.get(LabJob, ident)
        if job is None or job.state not in ("queued", "running"):
            return {"state": "not_pending"}
        user = await session.get(User, job.user_id)
        if user is None:
            return {"state": "not_pending"}
        params, user_id, kind = job.parameters, user.id, job.kind
        tz = ZoneInfo(user.timezone)
        cursor = job.progress.get("cursor", 0)
        job.state = "running"
        job.updated_at = datetime.now(UTC)
        await session.commit()
    if kind == "analysis":
        from app.agent.tools import AnalyticsIn
        from app.services.analytics import run_recipe

        args = AnalyticsIn.model_validate(params)
        async with sessionmaker() as session:
            job = await session.get(LabJob, ident)
            if job.cancel_requested:
                job.state = "cancelled"
                await session.commit()
                return {"state": "cancelled"}
            user = await session.get(User, user_id)
            result = await run_recipe(
                session,
                user,
                args.recipe,
                metric=args.metric,
                start=args.start_date,
                end=args.end_date,
                origin=args.origin,
                activity_id=args.activity_id,
                experiment_id=args.experiment_id,
                for_ai=True,
            )
            job.state = "completed"
            job.updated_at = datetime.now(UTC)
            job.progress = {"completed": 1, "total": 1, "result": result}
            await session.commit()
            return {"state": "completed", "handle": result["handle"]}
    start, end = date.fromisoformat(params["start"]), date.fromisoformat(params["end"])
    if kind == "repair":
        from app.core.encryption import decrypt_json
        from app.connectors.garmin.client import build_live_client
        from app.connectors.garmin.sync import SyncReport, fetch_wellness
        from app.models.activity import Discipline

        # Share the same provider/account lock as the scheduled connector.
        import hashlib
        import asyncio

        lock = int.from_bytes(
            hashlib.sha256(f"sync:garmin:{user_id}".encode()).digest()[:8],
            "big",
            signed=True,
        )
        async with engine.connect() as provider_lock:
            if not await provider_lock.scalar(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": lock}
            ):
                async with sessionmaker() as session:
                    job = await session.get(LabJob, ident)
                    job.state = "queued"
                    await session.commit()
                return {"state": "queued", "reason": "provider_sync_active"}
            try:
                async with sessionmaker() as session:
                    integration = await session.scalar(
                        select(Integration).where(
                            Integration.user_id == user_id,
                            Integration.provider == "garmin",
                            Integration.status == "active",
                        )
                    )
                    if integration is None or not integration.credentials_encrypted:
                        job = await session.get(LabJob, ident)
                        job.state = "auth_required"
                        job.progress = {"error": "Reconnect Garmin"}
                        await session.commit()
                        return {"state": "auth_required"}
                    credentials = decrypt_json(integration.credentials_encrypted)
                    integration_id = integration.id
                    index = dict(
                        (
                            await session.execute(
                                select(Discipline.name, Discipline.id)
                            )
                        ).all()
                    )
                client = await asyncio.to_thread(build_live_client, credentials)
                for offset in range(cursor, (end - start).days + 1):
                    async with sessionmaker() as session:
                        job = await session.get(LabJob, ident)
                        if job.cancel_requested:
                            job.state = "cancelled"
                            await session.commit()
                            return {"state": "cancelled"}
                        day = start + timedelta(days=offset)
                        report = SyncReport(user_id=user_id, mode="repair")
                        await fetch_wellness(
                            session,
                            user_id,
                            client,
                            tz,
                            from_day=day,
                            to_day=day,
                            delay_s=1,
                            empty_gap_days=1,
                            report=report,
                            discipline_index=index,
                            checkpoint=True,
                        )
                        integration = await session.get(Integration, integration_id)
                        if hasattr(client, "dump_tokens"):
                            from app.core.encryption import encrypt_json

                            integration.credentials_encrypted = encrypt_json(
                                client.dump_tokens()
                            )
                        job.updated_at = datetime.now(UTC)
                        job.progress = {
                            "cursor": offset + 1,
                            "completed": offset + 1,
                            "total": (end - start).days + 1,
                            "unprocessed": report.raw_rows_unprocessed,
                        }
                        await session.commit()
            finally:
                await provider_lock.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": lock}
                )
    else:
        # Raw fetched dates are not measurement dates. Map observations first,
        # retain only the requested measured-date range, and preserve lineage.
        while True:
            async with sessionmaker() as session:
                job = await session.get(LabJob, ident)
                if job.cancel_requested:
                    job.state = "cancelled"
                    await session.commit()
                    return {"state": "cancelled"}
                rows = (
                    await session.scalars(
                        select(RawIngest)
                        .where(
                            RawIngest.user_id == user_id,
                            RawIngest.source == "garmin",
                            RawIngest.processed.is_(True),
                            RawIngest.id > cursor,
                        )
                        .order_by(RawIngest.id)
                        .limit(100)
                    )
                ).all()
                if not rows:
                    break
                for raw in rows:
                    try:
                        async with session.begin_nested():
                            await index_garmin_payload(
                                session, raw, tz, start=start, end=end
                            )
                    except (ValueError, TypeError, KeyError):
                        # Keep original raw record; unknown historical shapes
                        # are not guessed or interpreted by an LLM.
                        pass
                    cursor = raw.id
                job.updated_at = datetime.now(UTC)
                job.progress = {
                    "cursor": cursor,
                    "completed": job.progress.get("completed", 0) + len(rows),
                }
                await session.commit()
    async with sessionmaker() as session:
        job = await session.get(LabJob, ident)
        job.state = "completed"
        job.updated_at = datetime.now(UTC)
        await session.commit()
    return {"state": "completed"}


@celery_app.task(name="lab.dispatch_jobs")
def dispatch():
    return run_async(dispatch_jobs())


@celery_app.task(name="lab.run_job", soft_time_limit=600, time_limit=660)
def execute(ident):
    try:
        return run_async(run_job(ident))
    except Exception as exc:
        from app.connectors.garmin.client import GarminAuthError

        auth_required = isinstance(exc, GarminAuthError) or type(exc).__name__ in {
            "GarminConnectAuthenticationError",
            "GarminMFARequired",
        }

        async def fail():
            async with sessionmaker() as session:
                job = await session.get(LabJob, ident)
                if job:
                    job.state = "auth_required" if auth_required else "failed"
                    job.updated_at = datetime.now(UTC)
                    job.progress = {
                        **job.progress,
                        "error": "Reconnect Garmin; the saved cursor is retained."
                        if auth_required
                        else "Maintenance failed; retry from the saved cursor.",
                    }
                    if auth_required:
                        integration = await session.scalar(
                            select(Integration).where(
                                Integration.user_id == job.user_id,
                                Integration.provider == "garmin",
                            )
                        )
                        if integration:
                            integration.status = "error"
                    await session.commit()

        run_async(fail())
        return {"state": "auth_required" if auth_required else "failed"}


async def prune_retained_data():
    """Apply explicit preferences daily. No implicit account-wide erasure."""
    from sqlalchemy import delete
    from app.models.lab import AthleteEntry, Observation, ChangeAudit
    from app.models.ai import AgentToolCall

    async with sessionmaker() as session:
        rows = (
            await session.scalars(
                select(AthleteEntry)
                .where(AthleteEntry.kind == "privacy_preferences")
                .order_by(AthleteEntry.id)
            )
        ).all()
        latest = {r.user_id: r for r in rows}
    result = {}
    for owner, pref in latest.items():
        async with sessionmaker() as session:
            from app.services.evidence import scope_lock

            await scope_lock(session, owner, "changes")
            obs_before = datetime.now(UTC) - timedelta(
                days=pref.payload["observation_retention_days"]
            )
            log_before = datetime.now(UTC) - timedelta(
                days=pref.payload["agent_log_retention_days"]
            )
            removed = await session.execute(
                delete(Observation).where(
                    Observation.user_id == owner, Observation.measured_at < obs_before
                )
            )
            logs = await session.execute(
                delete(AgentToolCall).where(
                    AgentToolCall.user_id == owner,
                    AgentToolCall.created_at < log_before,
                )
            )
            result[str(owner)] = {
                "observations": removed.rowcount,
                "agent_logs": logs.rowcount,
            }
            if removed.rowcount or logs.rowcount:
                session.add(
                    ChangeAudit(
                        user_id=owner,
                        action="retention_applied",
                        payload=result[str(owner)],
                    )
                )
            await session.commit()
    return result


@celery_app.task(name="lab.prune_retained_data")
def prune():
    return run_async(prune_retained_data())
