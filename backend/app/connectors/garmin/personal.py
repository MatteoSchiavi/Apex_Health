"""Garmin Personal API, verified against Garmin's October 2026 OpenAPI and SDK.

No SDK disk cache is used. The caller encrypts ``dump_tokens`` in the owning
integration record. JWT claims only schedule renewal; Garmin validates access.
Original FIT archives are stored before parsing; aggregate exercise summaries
are never treated as individual recorded sets.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import binascii
import json
import math
import time
from datetime import UTC, date, datetime
from typing import Any

import httpx

from app.connectors.garmin.client import GarminAuthError

BASE_URL = "https://personal.connectapi.garmin.com"
TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"


class GarminPersonalError(RuntimeError):
    """Safe operational error: no request, credentials or provider body attached."""

    def __init__(self, message: str, *, error_class: str = "transport", status_code: int | None = None):
        super().__init__(message)
        self.error_class = error_class
        self.status_code = status_code


def _expiration(token: str) -> float:
    try:
        part = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        value = float(claims["exp"])
        if not math.isfinite(value):
            raise ValueError
        return value
    except (IndexError, KeyError, TypeError, ValueError, binascii.Error):
        raise GarminAuthError("Garmin returned an invalid access token") from None


def _epoch_ms(value: Any) -> int:
    # The Personal schema declares date-time strings (the description also
    # mentions ms). Accept numeric epoch ms for that documented ambiguity.
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(value):
                raise ValueError
            return round(value)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return round(parsed.replace(tzinfo=UTC).timestamp() * 1000) if parsed.tzinfo is None else round(parsed.timestamp() * 1000)
    except (TypeError, ValueError, AttributeError, OverflowError):
        raise GarminPersonalError("Garmin sleep timestamp is invalid", error_class="normalization") from None


class GarminPersonalClient:
    """Account-local async client; construction performs no I/O."""

    # No application-imposed 30-day history limit.
    initial_sync_days = None
    api_activity_archives = True

    unsupported_capabilities = frozenset({
        "exercise_sets", "stress_timeseries",
        "training_readiness", "training_status", "recovery_time",
    })

    def __init__(self, credentials: dict[str, Any], *, http_client: httpx.AsyncClient | None = None):
        key = credentials.get("api_key")
        if not isinstance(key, str) or not key.strip() or any(c.isspace() for c in key):
            raise GarminAuthError("A valid Garmin Personal API key is required")
        self._api_key = key
        self._access_token = None
        self._expires_at = 0.0
        token = credentials.get("access_token")
        if isinstance(token, str) and token:
            try:
                expiry = min(float(credentials.get("expires_at", 0)), _expiration(token), time.time() + 86400)
                if math.isfinite(expiry) and expiry > time.time() + 60:
                    self._access_token, self._expires_at = token, expiry
            except (TypeError, ValueError, GarminAuthError):
                pass  # A damaged/expired cache is renewed using this account's key.
        self._http = http_client or httpx.AsyncClient(timeout=httpx.Timeout(20, connect=5), follow_redirects=False)
        self._auth_lock = asyncio.Lock()
        self._profile_documents_fetched = False

    def dump_tokens(self) -> dict[str, Any]:
        result = {"auth_type": "personal_api_key", "api_key": self._api_key}
        if self._access_token:
            result.update(access_token=self._access_token, expires_at=self._expires_at)
        return result

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, authorization: str, *, params=None, max_bytes: int = 4 * 1024 * 1024) -> httpx.Response:
        for attempt in range(3):
            try:
                async with self._http.stream(
                    method, BASE_URL + path, headers={"Authorization": authorization, "Accept": "*/*"},
                    params=params, follow_redirects=False,
                ) as incoming:
                    chunks, size = [], 0
                    async for chunk in incoming.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise GarminPersonalError("Garmin API response exceeds the supported size", error_class="normalization")
                        chunks.append(chunk)
                    response = httpx.Response(incoming.status_code, headers={k: v for k, v in incoming.headers.items() if k.lower() not in {"content-encoding", "content-length"}},
                                              content=b"".join(chunks), request=incoming.request)
            except httpx.TransportError as exc:
                code = "timeout" if isinstance(exc, httpx.TimeoutException) else "transport"
                if attempt == 2:
                    raise GarminPersonalError("Garmin Personal API is temporarily unreachable", error_class=code) from None
            else:
                if response.status_code != 429 and response.status_code < 500:
                    return response
                if attempt == 2:
                    raise GarminPersonalError("Garmin Personal API is temporarily unavailable", status_code=response.status_code)
                retry_after = response.headers.get("Retry-After", "")
                try:
                    delay = min(30.0, max(0.0, float(retry_after)))
                except ValueError:
                    delay = 2 ** attempt
                await asyncio.sleep(delay)
                continue
            await asyncio.sleep(2 ** attempt)
        raise AssertionError("unreachable")

    async def authenticate(self, *, force: bool = True) -> None:
        """Validate the key by exchanging it; lazy reads may reuse a valid token."""
        async with self._auth_lock:
            if not force and self._access_token and self._expires_at > time.time() + 60:
                return
            self._access_token, self._expires_at = None, 0.0
            response = await self._request("POST", TOKEN_PATH, f"ApiKey {self._api_key}")
            if response.status_code in {400, 401, 403}:
                raise GarminAuthError("Garmin Personal API key was rejected or expired; reconnect Garmin")
            if response.status_code != 200:
                raise GarminPersonalError("Garmin token exchange failed", status_code=response.status_code)
            token = response.text.strip()
            expiry = min(_expiration(token), time.time() + 86400)
            if expiry <= time.time() + 60:
                raise GarminAuthError("Garmin Personal API key or token is expired; reconnect Garmin")
            self._access_token, self._expires_at = token, expiry

    async def _get(self, path: str, *, params=None, expected: type | tuple[type, ...] = dict, no_content: bool = False):
        await self.authenticate(force=False)
        for attempt in range(2):
            response = await self._request("GET", path, f"Bearer {self._access_token}", params=params)
            if response.status_code != 401:
                break
            self._access_token, self._expires_at = None, 0.0
            if attempt:
                raise GarminAuthError("Garmin access was revoked or expired; reconnect Garmin")
            await self.authenticate(force=True)
        if response.status_code == 403:
            raise GarminPersonalError("Garmin denied access to this data", error_class="permission", status_code=403)
        if response.status_code == 204 and no_content:
            return {} if isinstance(expected, tuple) else expected()
        if response.status_code != 200:
            raise GarminPersonalError("Garmin data request failed", status_code=response.status_code)
        try:
            payload = response.json()
        except ValueError:
            raise GarminPersonalError("Garmin returned invalid JSON", error_class="normalization") from None
        if not isinstance(payload, expected):
            raise GarminPersonalError("Garmin returned an unexpected data shape", error_class="normalization")
        return payload

    async def get_activities(self, start: int, limit: int) -> list[dict[str, Any]]:
        payload = await self._get("/activitylist-service/activities/search/activities", params={
            "start": start, "limit": limit, "sortOrder": "desc", "excludeChildren": "true",
        }, expected=list)
        if any(not isinstance(row, dict) for row in payload):
            raise GarminPersonalError("Garmin returned an invalid activity summary", error_class="normalization")
        # Keep the original fields and add only verified contract aliases.
        # IDs, meters, seconds, bpm, watts and steps/min retain their units.
        mapped = []
        for original in payload:
            summary = dict(original)
            for personal, canonical in (("avgPower", "averagePower"), ("normPower", "normalizedPower"),
                                        ("averageRunningCadenceInStepsPerMinute", "averageRunCadence")):
                if personal in summary:
                    summary[canonical] = summary[personal]
            manual = summary.get("isManualActivity")
            if manual is None:
                manual = summary.get("manualActivity")
            if manual is not None:
                summary["manual"] = manual
            mapped.append(summary)
        return mapped

    async def get_sleep_data(self, local_date: str) -> dict[str, Any]:
        original = await self._get("/sleep-service/sleep/dailySleep", params={"date": local_date}, no_content=True)
        dto = dict(original)
        for key in ("sleepStartTimestampGMT", "sleepEndTimestampGMT"):
            if dto.get(key) is not None:
                dto[key] = _epoch_ms(dto[key])
        for personal, canonical in (("averageRespirationValue", "avgRespirationValue"), ("averageSpO2Value", "avgSpO2Value")):
            if personal in dto:
                dto[canonical] = dto[personal]
        return {"dailySleepDTO": dto, "_personal_api_payload": original}

    async def get_hrv_data(self, local_date: str) -> dict[str, Any]:
        payload = await self._get(f"/hrv-service/hrv/{local_date}", no_content=True)
        return {**payload, "_garmin_api": True} if payload else {}

    async def get_stats(self, local_date: str) -> dict[str, Any]:
        payload = await self._get("/usersummary-service/usersummary/daily", params={"calendarDate": local_date}, no_content=True)
        return {**payload, "_garmin_api": True} if payload else {}

    async def get_body_composition(self, local_date: str) -> dict[str, Any]:
        # The live /range endpoint returns grams, despite the shared OpenAPI
        # DateWeightDTO description saying kilograms. Keep its grams for the
        # established normalizer, verified against an actual dated measurement.
        # Garmin's official SDK uses range + includeAll. The documented /all
        # route returns 400 for a valid real account. Adjacent graph-context weights are not
        # measurements for the requested day.
        original = await self._get(f"/weight-service/weight/range/{local_date}/{local_date}", params={"includeAll": "true"}, no_content=True)
        if not original:
            return {}
        summaries = original.get("dailyWeightSummaries")
        if not isinstance(summaries, list):
            raise GarminPersonalError("Garmin returned invalid daily weight summaries", error_class="normalization")
        rows = []
        for summary in summaries:
            if not isinstance(summary, dict):
                raise GarminPersonalError("Garmin returned an invalid weight summary", error_class="normalization")
            if summary.get("summaryDate") != local_date:
                continue
            measurements = summary.get("allWeightMetrics")
            if measurements is None:
                measurements = [summary["latestWeight"]] if summary.get("latestWeight") is not None else []
            if not isinstance(measurements, list) or any(not isinstance(row, dict) for row in measurements):
                raise GarminPersonalError("Garmin returned invalid weight measurements", error_class="normalization")
            rows.extend(row for row in measurements if row.get("calendarDate", local_date) == local_date)
        total = {}
        for key in ("weight", "bodyFat"):
            values = [row[key] for row in rows if isinstance(row, dict) and isinstance(row.get(key), (int, float)) and not isinstance(row[key], bool) and math.isfinite(row[key])]
            if values:
                total[key] = sum(values) / len(values)
        return {"totalAverage": total, "_personal_api_payload": original, "_personal_api_weight_unit": "g"}

    async def get_api_documents(self, local_date: str, *, today: str | None = None):
        """Fetch additional read surfaces, recording optional failures explicitly.

        No source document is flattened or assigned an inferred medical unit.
        Authentication failure stops the account; missing permissions do not
        erase already imported data from other feeds.
        """
        from app.connectors.garmin.documents import DAILY_DOCUMENTS, PROFILE_DOCUMENTS
        day = date.fromisoformat(local_date).isoformat()
        routes = dict(DAILY_DOCUMENTS)
        if not self._profile_documents_fetched:
            routes.update(PROFILE_DOCUMENTS)
        documents, errors = {}, {}
        for name, (path, params) in routes.items():
            substitutions = {"day": day, "today": today or date.today().isoformat()}
            path = path.format(**substitutions)
            params = {k: v.format(**substitutions) for k, v in (params or {}).items()}
            try:
                value = await self._get(path, params=params, expected=(dict, list), no_content=True)
            except GarminPersonalError as error:
                errors[name] = {"error_class": error.error_class, "status_code": error.status_code}
            else:
                if value:
                    documents[name] = {"endpoint": path, "requested_date": day, "payload": value}
            await asyncio.sleep(0.1)
        self._profile_documents_fetched = True
        return documents, errors

    async def get_activity_documents(self, activity_id: int):
        documents, errors = {}, {}
        for name, suffix in (("activity_detail", ""), ("activity_workouts", "/workouts")):
            path = f"/activity-service/activity/{activity_id}{suffix}"
            try:
                payload = await self._get(path, expected=(dict, list), no_content=True)
            except GarminPersonalError as error:
                errors[name] = {"error_class": error.error_class, "status_code": error.status_code}
            else:
                if payload:
                    documents[name] = {"endpoint": path, "activity_id": activity_id, "payload": payload}
            await asyncio.sleep(0.1)
        return documents, errors

    async def get_activity_archive(self, activity_id: int) -> dict[str, Any]:
        """Download the original through the same account's API bearer token.

        The raw archive is returned for durable storage BEFORE FIT decoding.
        No caller-supplied host, redirected URL or filesystem extraction is used.
        """
        if isinstance(activity_id, bool) or not isinstance(activity_id, int) or activity_id <= 0:
            raise GarminPersonalError("Invalid Garmin activity identifier", error_class="normalization")
        await self.authenticate(force=False)
        for attempt in range(2):
            response = await self._request("GET", f"/download-service/files/activity/{activity_id}",
                f"Bearer {self._access_token}", max_bytes=20 * 1024 * 1024)
            if response.status_code != 401:
                break
            self._access_token, self._expires_at = None, 0.0
            if attempt:
                raise GarminAuthError("Garmin API access was revoked; reconnect Garmin")
            await self.authenticate(force=True)
        if response.status_code == 204:
            return {}
        if response.status_code == 403:
            raise GarminPersonalError("Garmin denied access to this original activity", error_class="permission", status_code=403)
        if response.status_code != 200:
            raise GarminPersonalError("Garmin original activity download failed", status_code=response.status_code)
        content = response.content
        if not content:
            return {}
        return {"activity_id": activity_id, "format": "original_zip", "sha256": hashlib.sha256(content).hexdigest(),
                "encoding": "base64", "content": base64.b64encode(content).decode("ascii")}

    async def get_activity_samples(self, activity_id: int) -> list[dict[str, Any]]:
        raise NotImplementedError("Use the raw-first Garmin API original archive ingestion path")

    async def get_activity_exercise_sets(self, activity_id: int) -> dict[str, Any]:
        raise NotImplementedError("Garmin API has no dedicated per-set JSON feed; original FIT may carry recorded sets")

    async def get_stress_data(self, local_date: str) -> dict[str, Any]:
        raise NotImplementedError("Personal API daily stress is available in get_stats; no stress time series")
