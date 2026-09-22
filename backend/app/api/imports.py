"""CSV import API (owner feature batch): Apple Health / Google Fit / generic
CSV upload -> canonical tables via app/services/csv_import.py."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.user import User
from app.services.csv_import import import_csv

router = APIRouter(tags=["imports"])

_MAX_BYTES = 20 * 1024 * 1024  # 20 MB — a decade of daily rows fits easily


@router.post("/imports/csv")
async def upload_csv(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Upload one CSV (workouts or daily metrics). Idempotent per file+row:
    re-uploading the same file imports nothing twice."""
    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="file too large (20 MB cap)"
        )
    if not content.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="empty file")
    report = await import_csv(
        session, user.id, file.filename or "upload.csv", content, user.timezone
    )
    await session.commit()
    return {"filename": file.filename, **report.as_dict()}
