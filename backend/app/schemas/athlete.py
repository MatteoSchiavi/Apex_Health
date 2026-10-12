"""Strict optional athlete assertions; empty context remains a valid profile."""
from datetime import date as CalendarDate, time
from typing import Annotated, Literal
from pydantic import Field, model_validator
from app.schemas.changes import Strict

Focus = Literal["gym", "running", "cycling"]
Day = Literal[0, 1, 2, 3, 4, 5, 6]


class TargetEvent(Strict):
    title: str = Field(max_length=200)
    date: CalendarDate | None = None
    distance_km: float | None = Field(default=None, gt=0, le=5000)
    priority: Literal[1, 2, 3] = 2


class MeasurableGoal(Strict):
    metric: Literal["weekly_distance_km", "weekly_duration_min", "longest_distance_km", "best_power_w", "exercise_estimated_1rm_kg"]
    target: float = Field(gt=0, le=100000, allow_inf_nan=False, strict=True)
    duration_s: int | None = Field(default=None, ge=1, le=3600, strict=True)
    exercise: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def required_reference(self):
        maximum = {"weekly_distance_km":5000, "weekly_duration_min":10080, "longest_distance_km":5000,
            "best_power_w":5000, "exercise_estimated_1rm_kg":2000}[self.metric]
        if self.target > maximum:
            raise ValueError("Goal exceeds the supported range for this measurement")
        if self.metric == "best_power_w" and self.duration_s is None:
            raise ValueError("Power goals require an explicit duration")
        if self.metric == "exercise_estimated_1rm_kg" and not (self.exercise or "").strip():
            raise ValueError("Strength goals require a comparable exercise")
        if self.metric != "best_power_w" and self.duration_s is not None:
            raise ValueError("Duration applies only to power goals")
        if self.metric != "exercise_estimated_1rm_kg" and self.exercise is not None:
            raise ValueError("Exercise applies only to strength goals")
        return self


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
    measurable_goal: MeasurableGoal | None = None
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
    watts: float = Field(gt=0, le=2000, allow_inf_nan=False)
    measured_on: CalendarDate
    confirmed: Literal[True]
    source: Literal["manual", "tested", "imported", "estimated"] = "manual"
    methodology: str = Field(default="", max_length=500)
    source_reference: str = Field(default="", max_length=300)
    protocol: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def provenance_required(self):
        if self.source != "manual" and not self.methodology.strip():
            raise ValueError("Non-manual FTP requires its methodology")
        if self.source == "tested" and not self.protocol.strip():
            raise ValueError("Tested FTP requires a recorded protocol; user confirmation is not protocol validation")
        if self.source == "imported" and not self.source_reference.strip():
            raise ValueError("Imported FTP requires a source reference")
        return self


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


class SeasonalFocus(Strict):
    starts_on: CalendarDate
    ends_on: CalendarDate
    priorities: list[Focus] = Field(min_length=1,max_length=3)

    @model_validator(mode="after")
    def valid_range(self):
        if self.starts_on > self.ends_on:
            raise ValueError("Seasonal focus requires increasing inclusive dates")
        if len(self.priorities) != len(set(self.priorities)):
            raise ValueError("Seasonal priorities must be unique")
        return self


class AthleteContext(Strict):
    focuses: dict[Focus, FocusContext] = Field(default_factory=dict)
    focus_mode: Literal["prioritized","balanced"] = "prioritized"
    supporting_focus: list[Focus] = Field(default_factory=list,max_length=3)
    weekly_allocation_min: dict[Focus,Annotated[int,Field(strict=True,ge=0,le=10080)]] = Field(default_factory=dict)
    seasonal_focus: list[SeasonalFocus] = Field(default_factory=list,max_length=30)
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
        if len(self.supporting_focus) != len(set(self.supporting_focus)):
            raise ValueError("Supporting focuses must be unique")
        if self.weekly_time_budget_min is not None and sum(self.weekly_allocation_min.values()) > self.weekly_time_budget_min:
            raise ValueError("Sport allocations exceed the weekly time budget")
        for i,a in enumerate(self.seasonal_focus):
            for b in self.seasonal_focus[i+1:]:
                if a.starts_on <= b.ends_on and b.starts_on <= a.ends_on:
                    raise ValueError("Seasonal focus date ranges must not overlap")
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
        for focus, details in self.context.focuses.items():
            goal = details.measurable_goal
            if goal and ((goal.metric == "best_power_w" and focus != "cycling") or
                         (goal.metric == "exercise_estimated_1rm_kg" and focus != "gym") or
                         (focus == "gym" and goal.metric in {"weekly_distance_km", "longest_distance_km"})):
                raise ValueError("Goal metric must be compatible with the selected sport")
        referenced = set(self.context.supporting_focus) | set(self.context.weekly_allocation_min)
        referenced.update(focus for season in self.context.seasonal_focus for focus in season.priorities)
        if not referenced <= set(self.training_focus):
            raise ValueError("Supporting, allocated and seasonal focuses must be selected training priorities")
        return self


class ConsentUpdate(Strict):
    active: bool
    policy_version: str = Field(max_length=80)
    provider_identity: str = Field(max_length=2000)
