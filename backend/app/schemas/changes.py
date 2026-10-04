"""The model drafts these exact unions; authenticated application routes approve."""

from datetime import date as CalendarDate
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ContextPatch(Strict):
    kind: Literal["context_patch"]
    doc_kind: Literal[
        "profile", "goals", "injuries", "equipment", "preferences", "season_plan"
    ]
    operation: Literal["append", "replace_fragment", "remove_fragment"]
    fragment: str = Field(default="", max_length=2000)
    text: str = Field(default="", max_length=2000)


class SessionPatch(Strict):
    kind: Literal["session_patch"]
    target_id: int = Field(gt=0)
    date: CalendarDate | None = None
    target_duration_min: int | None = Field(default=None, ge=0, le=1440)
    description: str | None = Field(default=None, max_length=2000)
    session_type: str | None = Field(default=None, max_length=80)


class JournalCreate(Strict):
    kind: Literal["journal_create"]
    date: CalendarDate
    notes: str = Field(min_length=1, max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=20)


class PlanSession(Strict):
    date: CalendarDate
    discipline: str
    session_type: str = Field(max_length=80)
    target_duration_min: int = Field(ge=5, le=1440)
    description: str = Field(default="", max_length=2000)


class PlanCreate(Strict):
    kind: Literal["plan_create"]
    week_start: CalendarDate
    sessions: list[PlanSession] = Field(min_length=1, max_length=21)


Change = Annotated[
    ContextPatch | SessionPatch | JournalCreate | PlanCreate,
    Field(discriminator="kind"),
]
CHANGE_ADAPTER = TypeAdapter(Change)


class ProposeIn(Strict):
    change: Change
    reason: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=30)


class ApproveIn(Strict):
    payload_hash: str = Field(pattern="^[0-9a-f]{64}$")
