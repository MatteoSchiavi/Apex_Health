"""Private documents, portable exports and reviewable source erasure."""

import csv
import hashlib
import io
import json
from urllib.parse import quote
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import Field
from app.auth.deps import get_current_user
from app.core.db import get_session
from app.core.encryption import decrypt_bytes, encrypt_bytes
from app.models.lab import LabDocument, Observation, ChangeAudit
from app.models.training import PlannedSession, TrainingPlan
from app.models.user import AuthCredential, User
from app.schemas.changes import Strict, ApproveIn
from app.services.evidence import digest, scope_lock, snapshot_revision

router = APIRouter(prefix="/lab", tags=["lab-assets"])


class DocumentConfirmation(Strict):
    content_hash: str = Field(min_length=64, max_length=64)
    reviewed_text: str = Field(min_length=1, max_length=16000)


def document_dict(row):
    return {
        "id": row.id,
        "filename": row.filename,
        "media_type": row.media_type,
        "content_hash": row.content_hash,
        "status": row.status,
        "revision": row.revision,
        "excerpt": decrypt_bytes(row.excerpt_ciphertext).decode()
        if row.excerpt_ciphertext
        else None,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/documents")
async def documents(
    session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    rows = (
        await session.scalars(
            select(LabDocument)
            .where(LabDocument.user_id == user.id, LabDocument.status != "source_file")
            .order_by(LabDocument.id.desc())
            .limit(100)
        )
    ).all()
    return [document_dict(r) for r in rows]


@router.post("/documents", status_code=201)
async def upload_document(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    content = await file.read(5 * 1024 * 1024 + 1)
    if not content or len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "Document must be 1 byte–5 MB")
    name = (file.filename or "document").replace("\\", "/").rsplit("/", 1)[-1][:200]
    if not name.lower().endswith((".txt", ".md", ".pdf")):
        raise HTTPException(422, "Use TXT, Markdown or PDF")
    excerpt = None
    if not name.lower().endswith(".pdf"):
        try:
            excerpt = content.decode("utf-8")[:16000]
        except UnicodeDecodeError:
            raise HTTPException(422, "Text documents must use UTF-8") from None
        if "\x00" in excerpt:
            raise HTTPException(422, "Invalid text document")
    elif not content.startswith(b"%PDF-"):
        raise HTTPException(422, "Invalid PDF header")
    await scope_lock(session, user.id, "changes")
    sha = hashlib.sha256(content).hexdigest()
    row = await session.scalar(
        select(LabDocument).where(
            LabDocument.user_id == user.id,
            LabDocument.content_hash == sha,
            LabDocument.status != "source_file",
        )
    )
    if row is None:
        row = LabDocument(
            user_id=user.id,
            filename=name,
            media_type="application/pdf"
            if name.lower().endswith(".pdf")
            else "text/plain",
            content_hash=sha,
            ciphertext=encrypt_bytes(content),
            excerpt_ciphertext=encrypt_bytes(excerpt.encode()) if excerpt else None,
        )
        session.add(row)
        await session.flush()
    await session.commit()
    return document_dict(row)


async def owned_document(session, user_id, ident):
    row = await session.scalar(
        select(LabDocument)
        .where(LabDocument.user_id == user_id, LabDocument.id == ident)
        .with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Document not found")
    return row


@router.post("/documents/{ident}/confirm")
async def confirm_document(
    ident: int,
    payload: DocumentConfirmation,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    await scope_lock(session, user.id, "changes")
    row = await owned_document(session, user.id, ident)
    if row.status == "source_file" or row.content_hash != payload.content_hash:
        raise HTTPException(409, "Original file changed or cannot become AI context")
    row.excerpt_ciphertext = encrypt_bytes(payload.reviewed_text.encode())
    row.status = "confirmed"
    row.revision += 1
    session.add(
        ChangeAudit(
            user_id=user.id,
            action="document_confirmed",
            payload={"document_id": ident, "revision": row.revision},
        )
    )
    await session.commit()
    return document_dict(row)


@router.get("/documents/{ident}/original")
async def original_document(
    ident: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    row = await owned_document(session, user.id, ident)
    return Response(
        decrypt_bytes(row.ciphertext),
        media_type=row.media_type,
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"document-{ident}\"; "
                f"filename*=UTF-8''{quote(row.filename, safe='')}"
            ),
            "Cache-Control": "no-store",
        },
    )


@router.delete("/documents/{ident}", status_code=204)
async def delete_document(
    ident: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    await scope_lock(session, user.id, "changes")
    row = await owned_document(session, user.id, ident)
    if row.status == "source_file":
        raise HTTPException(
            409, "Delete the FIT source to remove its derived activities too"
        )
    await session.delete(row)
    await session.commit()


@router.get("/export/observations.csv")
async def export_observations(
    session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    # Streaming database cursor + bounded response size; exports contain no credentials.
    stream = await session.stream_scalars(
        select(Observation)
        .where(Observation.user_id == user.id)
        .order_by(Observation.id)
        .limit(100000)
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "id",
            "metric",
            "value",
            "unit",
            "origin",
            "measured_at",
            "local_date",
            "timezone",
            "fetched_at",
            "revision",
            "current",
        ]
    )
    async for r in stream:
        writer.writerow(
            [
                r.id,
                r.metric,
                r.value.get("value"),
                r.unit,
                r.origin,
                r.measured_at.isoformat(),
                r.local_date,
                r.timezone,
                r.fetched_at.isoformat(),
                r.revision,
                r.current,
            ]
        )
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="apex-observations.csv"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/export/account.json")
async def export_account(
    session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    # Explicit column whitelist. Never export sessions, tokens, provider secrets or ciphertext.
    credential = await session.get(AuthCredential, user.id)
    tables = {
        "feedbacks": "id,category,message,page_url,created_at",
        "lab_observations": "id,metric,value,unit,origin,measured_at,local_date,timezone,fetched_at,revision,current,metadata_json",
        "athlete_entries": "id,kind,date,payload,revision",
        "user_context_docs": "doc_kind,content,updated_at",
        "user_events": "id,title,kind,starts_at,ends_at,priority,taper_days,notes",
        "decision_records": "id,date,output,outcome",
        "change_drafts": "id,kind,status,before,after,reason,receipt",
        "activities": "id,discipline_id,start_time,local_date,duration_s,distance_m,avg_hr,avg_power,source_metrics",
        "journal_entries": "id,date,free_text_notes,tags",
        "nutrition_logs": "*",
        "session_feedback": "id,date,rpe,soreness,injury_flag,notes",
        "gear": "*",
        "gym_day_plans": "*",
        "gym_set_logs": "*",
        "lab_documents": "id,filename,media_type,content_hash,status,revision",
        "training_plans": "id,week_start,status,created_by",
        "raw_ingest": "id,source,payload_type,fetched_at,raw_json,processed",
    }
    result = {
        "version": "apex-private-export-v1",
        "exported_at": datetime.now(UTC).isoformat(),
        "limits": {"rows_per_table": 100000},
        "scope": "Selected account records; original uploaded file bytes, credentials and security sessions are excluded. Download individual originals from Documents. Request a full access response from the operator.",
        "profile": {
            "id": user.id,
            "email": credential.email if credential else None,
            "name": user.name,
            "dob": user.dob,
            "sex": user.sex,
            "height_cm": user.height_cm,
            "timezone": user.timezone,
            "locale": user.locale,
            "theme": user.theme,
            "units": user.units,
            "created_at": user.created_at,
        },
    }
    for table, columns in tables.items():
        result[table] = [
            dict(row)
            for row in (
                await session.execute(
                    text(
                        f"SELECT {columns} FROM {table} WHERE user_id=:owner LIMIT 100000"
                    ),
                    {"owner": user.id},
                )
            ).mappings()
        ]
    # Chat messages have no user_id of their own. Restrict them through the
    # user's chat sessions rather than exposing another person's messages.
    for table, columns, owner_filter in (
        (
            "ai_chat_sessions",
            "id,title,started_at,last_activity_at",
            "user_id=:owner",
        ),
        (
            "ai_chat_messages",
            "id,session_id,role,content,model_tier,referenced_data,created_at",
            "session_id IN (SELECT id FROM ai_chat_sessions WHERE user_id=:owner)",
        ),
        (
            "ai_reports",
            "id,report_type,period_start,period_end,generated_at,content_md,model_used",
            "user_id=:owner",
        ),
    ):
        result[table] = [
            dict(row)
            for row in (
                await session.execute(
                    text(f"SELECT {columns} FROM {table} WHERE {owner_filter} LIMIT 100000"),
                    {"owner": user.id},
                )
            ).mappings()
        ]
    from app.models.medical import LabPanel, LabMetric
    from app.medical.labs import decrypt_notes

    panels = (
        await session.scalars(
            select(LabPanel)
            .where(LabPanel.user_id == user.id)
            .order_by(LabPanel.id)
            .limit(100000)
        )
    ).all()
    result["lab_panels"] = [
        {
            c.name: getattr(r, c.key)
            for c in LabPanel.__table__.columns
            if c.name != "notes"
        }
        | {"notes": decrypt_notes(r)}
        for r in panels
    ]
    markers = (
        await session.scalars(
            select(LabMetric)
            .join(LabPanel, LabMetric.lab_panel_id == LabPanel.id)
            .where(LabPanel.user_id == user.id)
            .limit(100000)
        )
    ).all()
    result["lab_metrics"] = [
        {c.name: getattr(r, c.key) for c in LabMetric.__table__.columns}
        for r in markers
    ]
    result["limits"]["tables_at_limit"] = [
        k for k, v in result.items() if isinstance(v, list) and len(v) >= 100000
    ]
    return Response(
        json.dumps(result, default=str, ensure_ascii=False),
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="apex-private-export.json"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/workouts/{ident}/export")
async def export_workout(
    ident: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    row = await session.scalar(
        select(PlannedSession)
        .join(TrainingPlan, PlannedSession.training_plan_id == TrainingPlan.id)
        .where(TrainingPlan.user_id == user.id, PlannedSession.id == ident)
    )
    if row is None:
        raise HTTPException(404, "Workout not found")
    payload = {
        "format": "apex-workout-v1",
        "date": str(row.date),
        "session_type": row.session_type,
        "duration_min": row.target_duration_min,
        "description": row.description,
        "delivery_state": "exported",
        "device_delivery": "not_requested",
        "note": "Portable workout description; importing or copying this file does not confirm device delivery.",
    }
    session.add(
        ChangeAudit(
            user_id=user.id,
            action="workout_exported",
            payload={"session_id": ident, "state": "exported"},
        )
    )
    await session.commit()
    return Response(
        json.dumps(payload),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="apex-workout-{ident}.json"'
        },
    )


SOURCES = {
    "garmin",
    "fit",
    "strava",
    "whoop",
    "oura",
    "coros",
    "technogym",
    "csv_import",
    "manual",
}


async def source_preview(session, user_id, source):
    if source not in SOURCES:
        raise HTTPException(422, "Unknown source")
    counts = {}
    for table, column in (
        ("lab_observations", "origin"),
        ("raw_ingest", "source"),
        ("activity_source_links", "source"),
    ):
        counts[table] = await session.scalar(
            text(
                f"SELECT count(*) FROM {table} WHERE user_id=:owner AND {column}=:source"
            ),
            {"owner": user_id, "source": source},
        )
    revision = await snapshot_revision(session, user_id)
    return {
        "source": source,
        "counts": counts,
        "scope": "Source observations/raw records and canonical activities linked to this source, including merged rows. Legacy wellness has no reliable per-source lineage and is erased for wearable sources. Cached analyses, chats and reports are erased. Disconnect pauses new imports; reconnecting can restore upstream data.",
        "payload_hash": digest([user_id, source, counts, revision]),
        "irreversible": True,
    }


@router.get("/sources/{source}/deletion-preview")
async def deletion_preview(
    source: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    return await source_preview(session, user.id, source)


@router.post("/sources/{source}/delete")
async def erase_source(
    source: str,
    payload: ApproveIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    # Match the connector's session lock before taking evidence locks. Erasure
    # must never race a remote import or restore revoked credentials.
    import hashlib

    key = int.from_bytes(
        hashlib.sha256(f"sync:{source}:{user.id}".encode()).digest()[:8],
        "big",
        signed=True,
    )
    if not await session.scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
    ):
        raise HTTPException(
            409,
            "Source import is running; cancel or wait, then review a fresh deletion preview",
        )
    await scope_lock(session, user.id, "changes")
    preview = await source_preview(session, user.id, source)
    if preview["payload_hash"] != payload.payload_hash:
        raise HTTPException(409, "Source changed; review a fresh deletion preview")
    params = {"owner": user.id, "source": source}
    ids = "SELECT activity_id FROM activity_source_links WHERE user_id=:owner AND source=:source"
    # Delete dependent canonical rows before source links, so provenance is never orphaned.
    for table in (
        "activity_streams",
        "activity_laps",
        "activity_gear_links",
        "segment_efforts",
    ):
        await session.execute(
            text(f"DELETE FROM {table} WHERE activity_id IN ({ids})"), params
        )
    activity_ids = list((await session.scalars(text(ids), params)).all())
    if activity_ids:
        await session.execute(
            text(
                "DELETE FROM activity_source_links WHERE user_id=:owner AND activity_id=ANY(:ids)"
            ),
            {"owner": user.id, "ids": activity_ids},
        )
        await session.execute(
            text("DELETE FROM activities WHERE user_id=:owner AND id=ANY(:ids)"),
            {"owner": user.id, "ids": activity_ids},
        )
    if source in {"garmin", "whoop", "oura", "coros", "csv_import"}:
        for table in (
            "sleep_sessions",
            "hrv_readings",
            "stress_readings",
            "daily_biometrics",
        ):
            await session.execute(
                text(f"DELETE FROM {table} WHERE user_id=:owner"), params
            )
    await session.execute(
        delete(Observation).where(
            Observation.user_id == user.id, Observation.origin == source
        )
    )
    # Keep allowed alternate raw records, detach references to erased records.
    await session.execute(
        text(
            "UPDATE activity_source_links SET raw_ingest_id=NULL WHERE user_id=:owner AND raw_ingest_id IN (SELECT id FROM raw_ingest WHERE user_id=:owner AND source=:source)"
        ),
        params,
    )
    await session.execute(
        text("DELETE FROM raw_ingest WHERE user_id=:owner AND source=:source"), params
    )
    await session.execute(
        text(
            "DELETE FROM embeddings WHERE source_table='ai_reports' AND source_id IN (SELECT id FROM ai_reports WHERE user_id=:owner)"
        ),
        params,
    )
    for table in (
        "analysis_results",
        "ai_reports",
        "daily_features",
        "discipline_features",
        "weekly_rollups",
        "monthly_rollups",
        "decision_records",
        "lab_feed_states",
        "lab_notifications",
    ):
        await session.execute(text(f"DELETE FROM {table} WHERE user_id=:owner"), params)
    await session.execute(
        text(
            "DELETE FROM agent_tool_calls WHERE user_id=:owner OR session_id IN (SELECT id FROM ai_chat_sessions WHERE user_id=:owner)"
        ),
        params,
    )
    await session.execute(
        text(
            "DELETE FROM ai_chat_messages WHERE session_id IN (SELECT id FROM ai_chat_sessions WHERE user_id=:owner)"
        ),
        params,
    )
    await session.execute(
        text("DELETE FROM ai_chat_sessions WHERE user_id=:owner"), params
    )
    await session.execute(
        text(
            "UPDATE change_drafts SET status='rejected' WHERE user_id=:owner AND status='draft'"
        ),
        params,
    )
    await session.execute(
        text(
            "UPDATE lab_jobs SET cancel_requested=true,state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END WHERE user_id=:owner AND state IN ('queued','running')"
        ),
        params,
    )
    await session.execute(
        text(
            "UPDATE integrations SET status='revoked',credentials_encrypted=NULL WHERE user_id=:owner AND provider=:source"
        ),
        params,
    )
    await session.execute(
        text(
            "UPDATE lab_jobs SET progress=jsonb_build_object('source_erased',true) WHERE user_id=:owner"
        ),
        params,
    )
    if source == "fit":
        await session.execute(
            delete(LabDocument).where(
                LabDocument.user_id == user.id, LabDocument.status == "source_file"
            )
        )
    session.add(
        ChangeAudit(
            user_id=user.id,
            action="source_erased",
            payload={"source": source, "counts": preview["counts"]},
        )
    )
    await session.commit()
    return {"state": "deleted", "source": source, "cache_invalidation": "complete"}
