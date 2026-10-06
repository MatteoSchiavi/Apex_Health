"""Manual Apple Health export.zip upload."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.db import get_session
from app.models.user import User
from app.services.apple_health_import import AppleHealthImportError, import_apple_health

router = APIRouter(tags=["imports"])
_MAX_BYTES = 100 * 1024 * 1024


@router.post("/imports/apple-health")
async def upload_apple_health(
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    content = await file.read(_MAX_BYTES + 1)
    if len(content) > _MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File exceeds 100 MB")
    try:
        result = await import_apple_health(session, user, file.filename or "export.zip", content)
    except AppleHealthImportError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    await session.commit()
    return {"filename": file.filename, **result}
