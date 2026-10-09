from datetime import date as CalendarDate, time
from typing import Literal
from pydantic import Field, model_validator
from app.schemas.changes import Strict


class ReviewedWorkout(Strict):
    date: CalendarDate | None = None
    discipline: str = Field(min_length=1, max_length=80)
    session_type: str | None = Field(default=None, max_length=80)
    duration_min: int | None = Field(default=None, ge=0, le=1440)
    distance_m: float | None = Field(default=None, ge=0, le=5000000)
    start_time: time | None = None
    description: str = Field(default="", max_length=2000)
    intensity_targets: dict[Literal["hr_bpm", "power_w", "pace_s_km", "rpe"], str] = Field(default_factory=dict)
    protected: bool = False


class ReviewedPlan(Strict):
    title: str = Field(default="", max_length=200)
    starts_on: CalendarDate | None = None
    ends_on: CalendarDate | None = None
    weekly_structure: str = Field(default="", max_length=4000)
    sessions: list[ReviewedWorkout] = Field(default_factory=list, max_length=500)
    ambiguities: list[str] = Field(default_factory=list, max_length=50)
    protected: bool = False
    @model_validator(mode="after")
    def valid_range(self):
        if self.starts_on and self.ends_on and (self.ends_on < self.starts_on or (self.ends_on-self.starts_on).days > 366):
            raise ValueError("Plan must cover at most 367 days")
        if self.starts_on and self.ends_on and any(s.date and not self.starts_on <= s.date <= self.ends_on for s in self.sessions):
            raise ValueError("Every workout must lie inside the plan dates")
        if any(len(s) > 1000 for s in self.ambiguities):
            raise ValueError("Ambiguity text exceeds 1000 characters")
        return self


class PlanExtractionIn(Strict):
    expected_document_revision: int = Field(ge=1)
    use_ai: bool = False
    structure: ReviewedPlan | None = None
    @model_validator(mode="after")
    def exactly_one_method(self):
        if self.use_ai == (self.structure is not None):
            raise ValueError("Choose AI extraction or a reviewed manual structure")
        return self


class PlanConfirmationIn(Strict):
    payload_hash: str = Field(pattern="^[0-9a-f]{64}$")
    ambiguities_reviewed: bool = False


class ProtectionIn(Strict):
    protected: bool
    expected_plan_revision: int = Field(ge=1)


class AssociationIn(Strict):
    planned_session_id: int | None = Field(default=None, gt=0)


class CheckinIn(Strict):
    activity_id: int | None = Field(default=None, gt=0)
    planned_session_id: int | None = Field(default=None, gt=0)
    expected_revision: int = Field(default=0, ge=0)
    status: Literal["completed", "partial", "skipped"]
    rpe: int | None = Field(default=None, ge=0, le=10)
    pain: bool | None = None
    felt_unwell: bool | None = None
    note: str = Field(default="", max_length=2000)
    @model_validator(mode="after")
    def identity_required(self):
        if not self.activity_id and not self.planned_session_id:
            raise ValueError("Choose a recorded activity or planned session")
        if self.status == "skipped" and (self.activity_id or self.rpe is not None):
            raise ValueError("Skipped sessions cannot have recorded activities or RPE")
        return self


class LifeEventIn(Strict):
    kind: Literal["travel", "illness", "short_week", "schedule_disruption"]
    starts_on: CalendarDate
    ends_on: CalendarDate
    available_minutes_per_day: int | None = Field(default=None, ge=0, le=1440)
    note: str = Field(default="", max_length=2000)
    @model_validator(mode="after")
    def valid_range(self):
        if self.ends_on < self.starts_on or (self.ends_on-self.starts_on).days > 366:
            raise ValueError("Life event must cover at most 367 days")
        return self
