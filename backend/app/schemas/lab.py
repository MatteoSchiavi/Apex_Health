from datetime import date as CalendarDate, datetime
from typing import Annotated, Literal
from pydantic import Field
from app.schemas.changes import Strict


class EntryBase(Strict):
    date: CalendarDate


class DailyCheckin(EntryBase):
    kind: Literal["daily_checkin"]
    energy: int | None = Field(default=None, ge=1, le=10)
    fatigue: int | None = Field(default=None, ge=1, le=10)
    pain: bool = False
    felt_unwell: bool = False
    notes: str = Field(default="", max_length=2000)
    confounders: list[
        Literal[
            "travel",
            "alcohol",
            "late_meal",
            "illness",
            "device_change",
            "heavy_training",
        ]
    ] = Field(default_factory=list, max_length=6)


class Availability(EntryBase):
    kind: Literal["availability"]
    minutes: int = Field(ge=0, le=1440)
    notes: str = Field(default="", max_length=500)


class DeviceChange(EntryBase):
    kind: Literal["device_change"]
    provider: str = Field(min_length=1, max_length=40)
    device_id: str = Field(min_length=1, max_length=120)
    firmware: str = Field(default="", max_length=80)
    metrics: list[str] = Field(min_length=1, max_length=20)
    notes: str = Field(default="", max_length=1000)


class Nutrition(EntryBase):
    kind: Literal["nutrition"]
    calories: int | None = Field(default=None, ge=0, le=20000)
    protein_g: float | None = Field(default=None, ge=0, le=2000)
    carbs_g: float | None = Field(default=None, ge=0, le=3000)
    fat_g: float | None = Field(default=None, ge=0, le=2000)
    water_ml: int | None = Field(default=None, ge=0, le=20000)
    caffeine_mg: int | None = Field(default=None, ge=0, le=3000)
    alcohol_units: float | None = Field(default=None, ge=0, le=50)
    notes: str = Field(default="", max_length=2000)


class Experiment(EntryBase):
    kind: Literal["experiment"]
    title: str = Field(min_length=1, max_length=120)
    intervention: str = Field(min_length=1, max_length=300)
    outcome_metric: Literal[
        "hrv_overnight_rmssd", "resting_hr", "sleep_duration", "sleep_score"
    ]
    origin: Literal["garmin", "manual", "whoop", "oura"] = "garmin"
    end_date: CalendarDate
    outcome_lag_days: int = Field(default=1, ge=0, le=7)
    notes: str = Field(default="", max_length=2000)


class ExperimentCheckin(EntryBase):
    kind: Literal["experiment_checkin"]
    experiment_id: int = Field(gt=0)
    exposed: bool
    confounders: list[
        Literal["travel", "alcohol", "illness", "device_change", "heavy_training"]
    ] = Field(default_factory=list, max_length=5)
    notes: str = Field(default="", max_length=1000)


class NotificationPreferences(EntryBase):
    kind: Literal["notification_preferences"]
    quiet_start_hour: int = Field(default=22, ge=0, le=23)
    quiet_end_hour: int = Field(default=7, ge=0, le=23)
    daily_cap: int = Field(default=5, ge=0, le=20)
    muted_classes: list[
        Literal["sync", "data_quality", "training", "event", "gear", "system"]
    ] = Field(default_factory=list, max_length=6)


class PrivacyPreferences(EntryBase):
    kind: Literal["privacy_preferences"]
    observation_retention_days: int = Field(default=3650, ge=30, le=36500)
    agent_log_retention_days: int = Field(default=90, ge=7, le=365)
    density: Literal["comfortable", "compact"] = "comfortable"


class MetricSettings(EntryBase):
    kind: Literal["metric_settings"]
    sleep_target_h: float | None = Field(default=None, ge=4, le=12)
    ftp_w: float | None = Field(default=None, ge=50, le=600)
    threshold_hr_bpm: int | None = Field(default=None, ge=80, le=220)
    sport: str = Field(default="road_cycling", min_length=1, max_length=80)


class ObservationAnnotation(EntryBase):
    kind: Literal["observation_annotation"]
    observation_id: int = Field(gt=0)
    exclude_from_analysis: bool = True
    notes: str = Field(min_length=1, max_length=1000)


Entry = Annotated[
    DailyCheckin
    | Availability
    | DeviceChange
    | Nutrition
    | Experiment
    | ExperimentCheckin
    | NotificationPreferences
    | PrivacyPreferences
    | MetricSettings
    | ObservationAnnotation,
    Field(discriminator="kind"),
]


class EntryIn(Strict):
    entry: Entry


class OutcomeIn(Strict):
    state: Literal["accepted", "modified", "rejected", "snoozed", "ignored"]
    activity_id: int | None = Field(default=None, gt=0)
    notes: str = Field(default="", max_length=2000)


class NotificationAction(Strict):
    state: Literal["read", "snoozed", "resolved"]
    snooze_hours: int = Field(default=24, ge=1, le=168)


class ObservationIn(Strict):
    metric: str = Field(max_length=80)
    value: float
    measured_at: datetime
    notes: str = Field(default="", max_length=1000)
