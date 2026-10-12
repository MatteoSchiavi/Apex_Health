"""Explicit workout instructions and typed athlete-entered targets, never inferred zones."""
from typing import Literal
from pydantic import Field, model_validator
from app.schemas.changes import Strict


class WorkoutTarget(Strict):
    kind: Literal['pace_s_km', 'hr_bpm', 'power_w', 'rpe']
    lower: float = Field(ge=0)
    upper: float = Field(gt=0)

    @model_validator(mode='after')
    def bounded(self):
        cap = {'pace_s_km':3600,'hr_bpm':300,'power_w':4000,'rpe':10}[self.kind]
        if self.lower > self.upper or self.upper > cap or (self.kind in {'pace_s_km','hr_bpm'} and self.lower <= 0):
            raise ValueError('Use an increasing plausible target range in the declared units')
        return self


class WorkoutStep(Strict):
    id: str = Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    kind: Literal['warmup','easy','endurance','tempo','threshold','interval','recovery','cooldown','strength','technical','repeat']
    duration_s: int | None = Field(default=None,gt=0,le=86400)
    distance_m: float | None = Field(default=None,gt=0,le=500000)
    target: WorkoutTarget | None = None
    description: str = Field(default='',max_length=1000)
    exercise: str | None = Field(default=None,max_length=200)
    sets: int | None = Field(default=None,ge=1,le=100)
    reps: int | None = Field(default=None,ge=1,le=100)
    load_kg: float | None = Field(default=None,ge=0,le=1500)
    repetitions: int = Field(default=1,ge=1,le=50)
    steps: list['WorkoutStep'] = Field(default_factory=list,max_length=20)

    @model_validator(mode='after')
    def structure(self):
        if self.duration_s is not None and self.distance_m is not None:
            raise ValueError('Choose duration or distance for a block; do not prescribe competing stop conditions')
        if self.kind == 'repeat':
            if not self.steps or any(s.kind == 'repeat' for s in self.steps) or self.duration_s or self.distance_m or self.target:
                raise ValueError('A repeat block needs explicit non-repeating child blocks and no separate stop/target')
        elif self.steps or self.repetitions != 1:
            raise ValueError('Use a repeat block for repeated groups')
        if self.kind != 'strength' and any(v is not None for v in (self.exercise,self.sets,self.reps,self.load_kg)):
            raise ValueError('Exercise details belong to strength blocks')
        return self


class WorkoutStructure(Strict):
    title: str = Field(default='',max_length=200)
    objective: str = Field(default='',max_length=1000)
    steps: list[WorkoutStep] = Field(min_length=1,max_length=100)

    @model_validator(mode='after')
    def stable_steps(self):
        flat = [s for block in self.steps for s in ([block]+block.steps)]
        if len(flat) > 200 or len({s.id for s in flat}) != len(flat):
            raise ValueError('Workout blocks need distinct stable identities and at most 200 blocks')
        expanded = sum(s.repetitions*len(s.steps) if s.kind=='repeat' else 1 for s in self.steps)
        if expanded > 1000:
            raise ValueError('Workout expands to too many blocks')
        seconds = total_seconds(self.steps)
        if seconds is not None and seconds > 86400:
            raise ValueError('A workout must fit within one day')
        return self


def total_seconds(steps):
    total = 0
    for step in steps:
        if step.kind == 'repeat':
            value = total_seconds(step.steps)
            if value is None:
                return None
            total += value * step.repetitions
        elif step.duration_s is None:
            return None
        else:
            total += step.duration_s
    return total


class WorkoutDraftIn(Strict):
    expected_plan_revision: int = Field(ge=1)
    expected_workout_revision: int = Field(default=0,ge=0)
    structure: WorkoutStructure


class WorkoutConfirmationIn(Strict):
    payload_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
