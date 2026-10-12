"""Finite sharing selectors; there are no arbitrary JSON paths or write grants."""
from datetime import date
from typing import Annotated, Literal, Union
from pydantic import Field, model_validator
from app.schemas.changes import Strict

FeedbackField = Literal['feedback_status', 'rpe', 'fatigue', 'soreness', 'workout_quality',
    'feedback_note', 'modification_reason', 'terrain_notes']
FEEDBACK_FIELDS = {'feedback_status', 'rpe', 'fatigue', 'soreness', 'workout_quality',
    'feedback_note', 'modification_reason', 'terrain_notes'}
ActivityField = Union[Literal['date', 'discipline', 'duration_s', 'distance_m', 'elevation_gain_m',
    'avg_hr', 'max_hr', 'avg_power', 'np_power'], FeedbackField]
WorkoutField = Union[Literal['date', 'discipline', 'duration_min', 'distance_m', 'session_type',
    'start_time', 'description', 'intensity_targets', 'steps'], FeedbackField]
PlanField = Union[Literal['title', 'starts_on', 'ends_on', 'session_count', 'sessions',
    'session_instructions', 'intensity_targets', 'steps'], FeedbackField]


class ResourceSelection(Strict):
    resource_ids: list[int] = Field(min_length=1, max_length=20)
    include_feedback: bool = False

    @model_validator(mode='after')
    def scope_is_explicit(self):
        if any(i <= 0 for i in self.resource_ids) or len(set(self.resource_ids)) != len(self.resource_ids):
            raise ValueError('Choose distinct positive resource identities')
        if len(set(self.fields)) != len(self.fields):
            raise ValueError('Choose distinct allowed fields')
        if set(self.fields) & FEEDBACK_FIELDS and not self.include_feedback:
            raise ValueError('Explicitly enable feedback before choosing feedback fields')
        return self


class ActivitySelection(ResourceSelection):
    type: Literal['activity']
    fields: list[ActivityField] = Field(default_factory=lambda: ['date', 'discipline', 'duration_s', 'distance_m'], min_length=1, max_length=30)


class WorkoutSelection(ResourceSelection):
    type: Literal['workout']
    fields: list[WorkoutField] = Field(default_factory=lambda: ['date', 'discipline', 'duration_min', 'distance_m'], min_length=1, max_length=30)


class PlanSelection(ResourceSelection):
    type: Literal['plan']
    fields: list[PlanField] = Field(default_factory=lambda: ['title', 'starts_on', 'ends_on', 'session_count'], min_length=1, max_length=30)


class ProgressSelection(Strict):
    type: Literal['progress']
    sport: Literal['running', 'cycling']
    starts_on: date
    ends_on: date
    fields: list[Literal['volume', 'consistency', 'adherence', 'goal_progress']] = Field(default_factory=lambda: ['volume', 'consistency'], min_length=1, max_length=4)
    include_feedback: Literal[False] = False

    @model_validator(mode='after')
    def explicit_range(self):
        if len(set(self.fields)) != len(self.fields):
            raise ValueError('Choose distinct allowed fields')
        if not 0 <= (self.ends_on-self.starts_on).days < 730:
            raise ValueError('Choose explicit increasing dates covering at most 730 days')
        return self


ShareSelection = Annotated[Union[ActivitySelection, PlanSelection, WorkoutSelection, ProgressSelection], Field(discriminator='type')]


class SharePreviewIn(Strict):
    selection: ShareSelection
    expires_in_days: int = Field(default=7, ge=1, le=30)


class ShareCreateIn(SharePreviewIn):
    preview_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
