"""Read a user's Fitbit food diary through the official Nutrition Web API.

No food is entered or stored here. OAuth tokens live encrypted in Integration;
the Food view requests one day directly from Fitbit with nutrition scope.

Fitbit reference endpoints:
https://dev.fitbit.com/build/reference/web-api/nutrition/get-food-log/
https://dev.fitbit.com/build/reference/web-api/developer-guide/authorization/
"""

import base64
import logging
import math
import secrets
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_session
from app.core.encryption import decrypt_json, encrypt_json
from app.core.redis import get_redis_dependency
from app.models.integration import Integration
from app.models.user import User
from app.services.evidence import scope_lock

router = APIRouter(tags=["nutrition-integrations"])
logger = logging.getLogger(__name__)
_STATE_PREFIX = "fitbit:nutrition:oauth:"
_USER_STATE_PREFIX = "fitbit:nutrition:oauth:user:"
_LOCK_RESOURCE = "fitbit_nutrition"
_TOKEN_URL = "https://api.fitbit.com/oauth2/token"
_AUTHORIZE_URL = "https://www.fitbit.com/oauth2/authorize"
_FOOD_URL = "https://api.fitbit.com/1/user/-/foods/log/date/{day}.json"


def _configured() -> bool:
    settings = get_settings()
    return bool(settings.fitbit_client_id and settings.fitbit_client_secret)


def _basic_auth() -> str:
    settings = get_settings()
    encoded = base64.b64encode(
        f"{settings.fitbit_client_id}:{settings.fitbit_client_secret}".encode()
    ).decode("ascii")
    return f"Basic {encoded}"


async def _token_request(data: dict[str, str]) -> dict:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                _TOKEN_URL,
                data=data,
                headers={"Authorization": _basic_auth()},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Fitbit token exchange failed: %s", type(exc).__name__)
        raise HTTPException(502, "Fitbit authorization is temporarily unavailable") from exc
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise HTTPException(502, "Fitbit returned an invalid authorization response")
    return payload


def _credentials(payload: dict) -> dict:
    try:
        expires = max(0, int(payload.get("expires_in", 28800)))
    except (TypeError, ValueError) as exc:
        raise HTTPException(502, "Fitbit returned an invalid authorization response") from exc
    return {
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token"),
        "expires_at": (datetime.now(UTC) + timedelta(seconds=expires)).isoformat(),
        "scope": _scope_text(payload.get("scope")),
    }


def _scope_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return " ".join(value)
    return ""


def _has_nutrition_scope(value: object) -> bool:
    return "nutrition" in _scope_text(value).split()


def _number(value: object) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _food_entry(item: object) -> dict | None:
    if not isinstance(item, dict):
        return None
    logged = item.get("loggedFood")
    logged = logged if isinstance(logged, dict) else {}
    unit = logged.get("unit")
    unit_name = unit.get("name") if isinstance(unit, dict) else unit
    values = item.get("nutritionalValues")
    values = values if isinstance(values, dict) else {}
    return {
        "name": logged.get("name") if isinstance(logged.get("name"), str) else None,
        "amount": _number(logged.get("amount")),
        "unit": unit_name if isinstance(unit_name, str) else None,
        "meal_type_id": _number(logged.get("mealTypeId")),
        "calories": _number(values.get("calories")),
    }


async def _owned_integration(session: AsyncSession, user_id: int, *, lock=False):
    statement = select(Integration).where(
        Integration.user_id == user_id, Integration.provider == "fitbit"
    )
    if lock:
        statement = statement.with_for_update()
    return (await session.scalars(statement)).first()


@router.get("/nutrition/fitbit/status")
async def fitbit_status(
    session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
):
    row = await _owned_integration(session, user.id)
    return {
        "configured": _configured(),
        "connected": bool(row and row.status == "active" and row.credentials_encrypted),
        "provider": "fitbit",
    }


@router.post("/nutrition/fitbit/authorize")
async def fitbit_authorize(
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis_dependency),
    session: AsyncSession = Depends(get_session),
):
    if not _configured():
        raise HTTPException(409, "Fitbit app credentials are not configured")
    settings = get_settings()
    state = secrets.token_urlsafe(32)
    await scope_lock(session, user.id, _LOCK_RESOURCE)
    user_key = _USER_STATE_PREFIX + str(user.id)
    previous = await redis.get(user_key)
    if previous:
        await redis.delete(_STATE_PREFIX + previous)
    await redis.set(_STATE_PREFIX + state, str(user.id), ex=600)
    await redis.set(user_key, state, ex=600)
    await session.commit()
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.fitbit_client_id,
            "redirect_uri": settings.fitbit_redirect_uri,
            "scope": "nutrition",
            "state": state,
        }
    )
    return {"authorize_url": f"{_AUTHORIZE_URL}?{query}"}


@router.get("/integrations/fitbit/callback")
async def fitbit_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis_dependency),
):
    if error or not code or not state:
        raise HTTPException(400, "Fitbit authorization was cancelled or incomplete")
    user_id = await redis.get(_STATE_PREFIX + state)
    if not user_id:
        raise HTTPException(400, "Fitbit authorization expired; start again")
    await scope_lock(session, int(user_id), _LOCK_RESOURCE)
    user_key = _USER_STATE_PREFIX + user_id
    if await redis.get(user_key) != state:
        raise HTTPException(400, "Fitbit authorization expired; start again")
    consumed_user_id = await redis.getdel(_STATE_PREFIX + state)
    if consumed_user_id != user_id:
        raise HTTPException(400, "Fitbit authorization expired; start again")
    await redis.delete(user_key)
    settings = get_settings()
    payload = await _token_request(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.fitbit_redirect_uri,
        }
    )
    if not _has_nutrition_scope(payload.get("scope")):
        raise HTTPException(403, "Fitbit nutrition permission was not granted")
    row = await _owned_integration(session, int(user_id), lock=True)
    if row is None:
        row = Integration(user_id=int(user_id), provider="fitbit")
        session.add(row)
    row.credentials_encrypted = encrypt_json(_credentials(payload))
    row.status = "active"
    row.consecutive_failures = 0
    await session.commit()
    return RedirectResponse("/app/lab?tab=nutrition", status_code=303)


@router.get("/nutrition/fitbit/day/{day}")
async def fitbit_day(
    day: date,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    await scope_lock(session, user.id, _LOCK_RESOURCE)
    row = await _owned_integration(session, user.id, lock=True)
    if row is None or row.status != "active" or not row.credentials_encrypted:
        raise HTTPException(409, "Connect Fitbit to view the food diary")
    credentials = decrypt_json(row.credentials_encrypted)
    if not _has_nutrition_scope(credentials.get("scope")):
        raise HTTPException(403, "Fitbit nutrition permission is required")
    expiry = datetime.fromisoformat(credentials["expires_at"])
    refreshed = False
    if expiry <= datetime.now(UTC) + timedelta(minutes=1):
        if not credentials.get("refresh_token"):
            raise HTTPException(409, "Fitbit connection expired; reconnect it")
        payload = await _token_request(
            {"grant_type": "refresh_token", "refresh_token": credentials["refresh_token"]}
        )
        credentials = _credentials(payload)
        row.credentials_encrypted = encrypt_json(credentials)
        refreshed = True
        if not _has_nutrition_scope(credentials.get("scope")):
            await session.commit()
            raise HTTPException(403, "Fitbit nutrition permission is required")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                _FOOD_URL.format(day=day.isoformat()),
                headers={"Authorization": f"Bearer {credentials['access_token']}"},
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        if refreshed:
            await session.commit()  # Preserve rotated refresh tokens on provider failure.
        if exc.response.status_code in (401, 403):
            raise HTTPException(409, "Fitbit access expired or nutrition permission was revoked") from exc
        if exc.response.status_code == 429:
            raise HTTPException(429, "Fitbit rate limit reached; try again later") from exc
        raise HTTPException(502, "Fitbit food diary is temporarily unavailable") from exc
    except (httpx.HTTPError, ValueError) as exc:
        if refreshed:
            await session.commit()
        raise HTTPException(502, "Fitbit food diary is temporarily unavailable") from exc
    if not isinstance(payload, dict):
        if refreshed:
            await session.commit()
        raise HTTPException(502, "Fitbit returned an invalid food diary")
    summary = payload.get("summary") or {}
    foods = payload.get("foods") or []
    if not isinstance(summary, dict) or not isinstance(foods, list):
        if refreshed:
            await session.commit()
        raise HTTPException(502, "Fitbit returned an invalid food diary")
    row.last_synced_at = datetime.now(UTC)
    await session.commit()
    return {
        "provider": "fitbit",
        "date": day.isoformat(),
        "summary": {
            key: _number(summary.get(key))
            for key in ("calories", "carbs", "fat", "fiber", "protein", "sodium", "water")
        },
        "foods": [entry for item in foods[:200] if (entry := _food_entry(item)) is not None],
    }


@router.delete("/nutrition/fitbit", status_code=204)
async def fitbit_disconnect(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
    redis: Redis = Depends(get_redis_dependency),
):
    await scope_lock(session, user.id, _LOCK_RESOURCE)
    user_key = _USER_STATE_PREFIX + str(user.id)
    pending = await redis.get(user_key)
    if pending:
        await redis.delete(_STATE_PREFIX + pending)
    await redis.delete(user_key)
    row = await _owned_integration(session, user.id, lock=True)
    if row is not None:
        await session.delete(row)
    await session.commit()
