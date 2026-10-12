"""Review-only, partial athlete facts and genuinely undated weekly rows."""
from datetime import date, time
from typing import Any, Literal
from pydantic import Field, model_validator
from app.schemas.changes import Strict
from app.schemas.athlete import AthleteContext, Focus
from app.schemas.athlete_training import ReviewedPlan, ReviewedWorkout
from app.schemas.workouts import WorkoutStep

BLOCKED_CONTEXT = {"ftp", "hr_zones", "power_zones"}


class ProfileProposal(Strict):
    training_focus: list[Focus] | None = Field(default=None, max_length=3)
    context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def partial_context(self):
        if self.training_focus is not None and len(set(self.training_focus)) != len(self.training_focus):
            raise ValueError("Training priorities must be unique")
        if set(self.context) & BLOCKED_CONTEXT:
            raise ValueError("FTP and zones require the existing explicit profile confirmation")
        # Validate using canonical types, preserving only supplied fields and
        # nested facts instead of turning defaults into extracted assertions.
        validated = AthleteContext.model_validate(self.context)
        self.context = validated.model_dump(mode="json", exclude_unset=True)
        return self


class WeeklyWorkout(Strict):
    id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    day: int = Field(ge=0, le=6)
    discipline: str = Field(min_length=1, max_length=80)
    session_type: str | None = Field(default=None, max_length=80)
    duration_min: int | None = Field(default=None, ge=0, le=1440)
    distance_m: float | None = Field(default=None, ge=0, le=5000000)
    start_time: time | None = None
    description: str = Field(default="", max_length=2000)
    intensity_targets: dict[Literal["hr_bpm", "power_w", "pace_s_km", "rpe"], str] = Field(default_factory=dict)
    protected: bool = False
    steps: list[WorkoutStep] = Field(default_factory=list,max_length=100)

    @model_validator(mode="after")
    def shared_workout_rules(self):
        ReviewedWorkout.model_validate(self.model_dump(exclude={"id", "day"}))
        return self


class WeeklyProposal(Strict):
    title: str = Field(default="", max_length=200)
    rows: list[WeeklyWorkout] = Field(min_length=1, max_length=100)
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def stable_unique_rows(self):
        if len({row.id for row in self.rows}) != len(self.rows):
            raise ValueError("Weekly row identities must be unique")
        return self


class ImportIssue(Strict):
    field: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=1000)
    required: bool = False


class ImportSource(Strict):
    field: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=2000)
    certainty: Literal["explicit", "uncertain", "contradictory"]


class ImportProposal(Strict):
    profile: ProfileProposal = Field(default_factory=ProfileProposal)
    weekly: WeeklyProposal | None = None
    dated: ReviewedPlan | None = None
    issues: list[ImportIssue] = Field(default_factory=list, max_length=100)
    sources: list[ImportSource] = Field(default_factory=list, max_length=100)


class AthleteImportIn(Strict):
    document_id: int = Field(gt=0)
    expected_document_revision: int = Field(ge=1)
    use_ai: bool = False


class ImportHash(Strict):
    payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ImportReviewIn(ImportHash):
    proposal: ImportProposal


class ImportProfileConfirmation(ImportHash):
    expected_profile_revision: int = Field(ge=0)
    fields: list[str] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def approved_fields(self):
        allowed = {"training_focus"} | {"context."+key for key in AthleteContext.model_fields if key not in BLOCKED_CONTEXT}
        if len(self.fields) != len(set(self.fields)) or not set(self.fields) <= allowed:
            raise ValueError("Choose distinct known profile fields; FTP and zones use profile editing")
        return self


class TemplatePreviewIn(Strict):
    expected_revision: int = Field(ge=1)
    starts_on: date
    ends_on: date

    @model_validator(mode="after")
    def explicit_date_range(self):
        if not 0 <= (self.ends_on-self.starts_on).days <= 366:
            raise ValueError("Choose explicit dates covering at most 367 days")
        return self
