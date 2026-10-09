"""Strict optional athlete assertions; empty context remains a valid profile."""
from datetime import date as CalendarDate, time
from typing import Literal
from pydantic import Field, model_validator
from app.schemas.changes import Strict

Focus = Literal["gym", "running", "cycling"]
Day = Literal[0, 1, 2, 3, 4, 5, 6]


class TargetEvent(Strict):
    title: str = Field(max_length=200)
    date: CalendarDate | None = None
    distance_km: float | None = Field(default=None, gt=0, le=5000)
    priority: Literal[1, 2, 3] = 2


class FocusContext(Strict):
    level: Literal["new", "beginner", "intermediate", "experienced"] | None = None
    weekly_frequency: int | None = Field(default=None, ge=0, le=21)
    weekly_distance_km: float | None = Field(default=None, ge=0, le=5000)
    weekly_duration_min: int | None = Field(default=None, ge=0, le=10080)
    longest_distance_km: float | None = Field(default=None, ge=0, le=5000)
    preferred_days: list[Day] = Field(default_factory=list, max_length=7)
    long_session_day: Day | None = None
    goal: Literal["maintain", "health", "body_composition", "performance", "event"] | None = None
    event: TargetEvent | None = None
    equipment: list[str] = Field(default_factory=list, max_length=30)
    constraints: str = Field(default="", max_length=2000)
    power_available: bool | None = None
    @model_validator(mode="after")
    def unique_days(self):
        if len(self.preferred_days) != len(set(self.preferred_days)):
            raise ValueError("Preferred days must be unique")
        if any(len(s) > 120 for s in self.equipment):
            raise ValueError("Equipment names must be at most 120 characters")
        return self


class AvailabilityWindow(Strict):
    day: Day
    start: time
    end: time
    @model_validator(mode="after")
    def valid_window(self):
        if self.start >= self.end or self.start.tzinfo or self.end.tzinfo:
            raise ValueError("Use increasing local times within one day")
        return self


class ConfirmedFTP(Strict):
    watts: float = Field(gt=0, le=2000)
    measured_on: CalendarDate
    confirmed: Literal[True]


class ZoneBand(Strict):
    name: str = Field(min_length=1, max_length=40)
    lower: float = Field(ge=0, le=5000)
    upper: float = Field(gt=0, le=5000)
    @model_validator(mode="after")
    def increasing(self):
        if self.lower >= self.upper:
            raise ValueError("Zone upper bound must exceed lower bound")
        return self


class ConfiguredZones(Strict):
    effective_from: CalendarDate
    bands: list[ZoneBand] = Field(min_length=1, max_length=10)
    @model_validator(mode="after")
    def distinct(self):
        if len({b.name for b in self.bands}) != len(self.bands):
            raise ValueError("Zone names must be unique")
        for a, b in zip(self.bands, self.bands[1:]):
            if a.upper > b.lower:
                raise ValueError("Zones must be ordered and non-overlapping")
        return self


class AthleteContext(Strict):
    focuses: dict[Focus, FocusContext] = Field(default_factory=dict)
    main_goal: str = Field(default="", max_length=1000)
    weekly_time_budget_min: int | None = Field(default=None, ge=0, le=10080)
    preferred_rest_day: Day | None = None
    availability: list[AvailabilityWindow] = Field(default_factory=list, max_length=28)
    sleep_work_schedule: str = Field(default="", max_length=1000)
    schedule_constraints: str = Field(default="", max_length=2000)
    gym_experience_years: float | None = Field(default=None, ge=0, le=100)
    gym_split: str = Field(default="", max_length=200)
    preferred_exercises: str = Field(default="", max_length=1000)
    rpe_preference: bool | None = None
    self_declared_restrictions: str = Field(default="", max_length=2000)
    athlete_notes: str = Field(default="", max_length=8000)
    existing_plan: Literal["yes", "no", "unsure"] | None = None
    recent_consistency: str = Field(default="", max_length=1000)
    event_history: str = Field(default="", max_length=2000)
    devices: str = Field(default="", max_length=1000)
    coaching_style: str = Field(default="", max_length=1000)
    ftp: ConfirmedFTP | None = None
    hr_zones: ConfiguredZones | None = None
    power_zones: ConfiguredZones | None = None
    onboarding_step: int = Field(default=0, ge=0, le=5)
    @model_validator(mode="after")
    def no_overlap(self):
        for i, a in enumerate(self.availability):
            for b in self.availability[i+1:]:
                if a.day == b.day and a.start < b.end and b.start < a.end:
                    raise ValueError("Availability windows must not overlap")
        return self


class AthleteUpdate(Strict):
    expected_revision: int = Field(ge=0)
    training_focus: list[Focus] = Field(default_factory=list, max_length=3)
    context: AthleteContext = Field(default_factory=AthleteContext)
    @model_validator(mode="after")
    def unique_focus(self):
        if len(self.training_focus) != len(set(self.training_focus)):
            raise ValueError("Training priorities must be unique and ordered")
        if not set(self.context.focuses) <= set(self.training_focus):
            raise ValueError("Focus details must refer to selected training priorities")
        return self


class ConsentUpdate(Strict):
    active: bool
    policy_version: str = Field(max_length=80)
    provider_identity: str = Field(max_length=2000)
