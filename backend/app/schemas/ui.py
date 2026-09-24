"""Schemas for the web UI surface: profile/prefs, dashboard, activities,
sleep, metric trends, coach chats, devices."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# --- /me -------------------------------------------------------------------


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    dob: date | None = None
    sex: Literal["male", "female", "other"] | None = None
    height_cm: float | None = Field(default=None, gt=80, lt=260)
    timezone: str | None = Field(default=None, max_length=64)
    locale: Literal["en", "it"] | None = None
    theme: Literal["dark", "light"] | None = None
    units: Literal["metric", "imperial"] | None = None
    main_integration_id: int | None = None


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


class MeOut(BaseModel):
    user_id: int
    email: str
    name: str
    dob: date | None
    sex: str | None
    height_cm: float | None
    timezone: str
    locale: str
    theme: str
    units: str
    role: str
    ai_access_tier: str
    main_integration_id: int | None


# --- /dashboard/overview ----------------------------------------------------


class ScoreBlock(BaseModel):
    value: float | None
    delta_7d: float | None = None


class OverviewOut(BaseModel):
    date: str
    # False when the anchor day itself has nothing recorded and the endpoint
    # fell back to the most recent day that does (fresh-connect reality:
    # history exists, "today" doesn't until the device reports it).
    anchor_is_today: bool = True
    readiness: ScoreBlock
    recovery: ScoreBlock
    strain: ScoreBlock
    sleep_score: ScoreBlock
    sleep_hours: float | None
    hrv_ms: float | None
    hrv_baseline_ms: float | None
    hrv_norm_30d: float | None = None
    resting_hr: int | None
    resting_hr_delta_7d: float | None = None
    spo2_avg: float | None
    spo2_delta_7d: float | None = None
    respiration_avg: float | None
    steps: int | None
    weight_kg: float | None
    vo2max: float | None
    acute_load: float | None
    chronic_load: float | None
    acwr: float | None
    training_load_7d: float | None
    activities: list[dict[str, Any]]
    sleep: dict[str, Any] | None
    integration_status: list[dict[str, Any]]
    alerts: list[dict[str, Any]]


# --- /activities -------------------------------------------------------------


class ActivityOut(BaseModel):
    id: int
    start_time: datetime
    local_date: date
    discipline: str | None
    duration_s: int
    distance_m: float | None
    elevation_gain_m: float | None
    avg_hr: int | None
    max_hr: int | None
    avg_power: float | None
    np_power: float | None
    calories: int | None
    training_load: float | None
    data_completeness: str
    sources: list[str] = []


class ActivityListOut(BaseModel):
    items: list[ActivityOut]
    total: int
    limit: int
    offset: int


class ActivityDetailOut(ActivityOut):
    has_streams: bool = False
    stream_types: list[str] = []
    laps: list[dict[str, Any]] = []
    weather: dict[str, Any] | None = None
    source_metrics: dict[str, Any] | None = None
    gear: list[dict[str, Any]] = []


class StreamOut(BaseModel):
    """Stream series are column arrays for compact transfer: t[] plus one
    array per requested type. Aligned by index; nulls = missing sample."""

    activity_id: int
    t: list[int]
    columns: dict[str, list[float | None]]


# --- /sleep ------------------------------------------------------------------


class SleepSessionOut(BaseModel):
    local_date: date
    start_time: datetime
    end_time: datetime
    total_sleep_s: int | None
    deep_s: int | None
    light_s: int | None
    rem_s: int | None
    awake_s: int | None
    sleep_score: float | None
    respiration_avg: float | None
    spo2_avg: float | None
    restlessness: float | None
    sources: list[str] = []


class SleepDayOut(BaseModel):
    date: str
    session: SleepSessionOut | None
    biometrics: dict[str, Any]
    hrv_readings: list[dict[str, Any]]


class SleepStagesOut(BaseModel):
    """Epoch-level stage timeline for one night (hypnogram feed).

    `segments` is None when the raw payload carries no usable stage
    timeline — the UI then renders the proportional stage bar instead of
    the hypnogram instead of inventing data."""

    date: str
    segments: list[dict[str, str]] | None = None
    source: str | None = None


class SleepListOut(BaseModel):
    items: list[SleepSessionOut]
    start_date: str
    end_date: str


# --- /metrics/{key} ------------------------------------------------------------


class MetricPoint(BaseModel):
    date: str
    value: float | None


class MetricTrendOut(BaseModel):
    metric: str
    label: str
    unit: str
    start_date: str
    end_date: str
    points: list[MetricPoint]
    stats: dict[str, Any] = {}


# --- /coach/chats --------------------------------------------------------------


class ChatSessionOut(BaseModel):
    id: int
    title: str | None
    started_at: datetime
    last_activity_at: datetime
    message_count: int = 0


class ChatMessageOut(BaseModel):
    id: int
    role: str
    content: str
    model_tier: str | None
    referenced_data: dict[str, Any] | None
    created_at: datetime


class ChatSessionDetailOut(ChatSessionOut):
    messages: list[ChatMessageOut]


class ChatPostIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    tier: Literal["free", "cheap", "powerful", "medical"] | None = None


# --- /settings/devices -----------------------------------------------------------


class DeviceOut(BaseModel):
    integration_id: int
    provider: str
    status: str
    last_synced_at: datetime | None
    is_main: bool
    connected_at: datetime


class MainDeviceUpdate(BaseModel):
    integration_id: int | None
