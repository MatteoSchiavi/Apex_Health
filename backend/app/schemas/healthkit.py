"""Bounded, unit-explicit native HealthKit wire contract."""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictFloat, StrictInt, model_validator


QUANTITIES = {
    "HKQuantityTypeIdentifierHeartRate": ("count/min", 20, 260),
    "HKQuantityTypeIdentifierRestingHeartRate": ("count/min", 20, 180),
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": ("ms", 0.01, 1000),
    "HKQuantityTypeIdentifierStepCount": ("count", 0, 200000),
    "HKQuantityTypeIdentifierActiveEnergyBurned": ("kcal", 0, 20000),
    "HKQuantityTypeIdentifierBodyMass": ("kg", 20, 400),
    "HKQuantityTypeIdentifierBodyFatPercentage": ("%", 1, 75),
    "HKQuantityTypeIdentifierRespiratoryRate": ("count/min", 4, 80),
    "HKQuantityTypeIdentifierOxygenSaturation": ("%", 50, 100),
    "HKQuantityTypeIdentifierVO2Max": ("mL/kg/min", 5, 100),
    "HKQuantityTypeIdentifierBodyTemperature": ("degC", 25, 45),
    "HKQuantityTypeIdentifierBasalBodyTemperature": ("degC", 25, 45),
    "HKQuantityTypeIdentifierAppleSleepingWristTemperature": ("degC", 20, 45),
}
SLEEP_TYPE = "HKCategoryTypeIdentifierSleepAnalysis"
WORKOUT_TYPE = "HKWorkoutType"


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PairingExchange(WireModel):
    code: str = Field(min_length=32, max_length=128)
    name: str = Field(default="Apple Health", min_length=1, max_length=60)


class HealthKitAddition(WireModel):
    uuid: UUID
    type: str = Field(max_length=100)
    start_at: AwareDatetime
    end_at: AwareDatetime
    value: StrictInt | StrictFloat | None = None
    unit: str | None = Field(default=None, max_length=32)
    source_bundle: str = Field(min_length=1, max_length=256)
    source_name: str = Field(min_length=1, max_length=256)
    device: str | None = Field(default=None, max_length=1024)
    metadata: dict[str, Any] = Field(default_factory=dict)
    workout_activity_type: StrictInt | None = None

    @model_validator(mode="after")
    def valid_sample(self):
        if self.end_at < self.start_at:
            raise ValueError("end_at must not precede start_at")
        if self.end_at > datetime.now(UTC) + timedelta(minutes=5):
            raise ValueError("HealthKit timestamps cannot be in the future")
        if self.end_at - self.start_at > timedelta(hours=48):
            raise ValueError("Sample intervals must not exceed 48 hours")
        if self.value is not None and not math.isfinite(self.value):
            raise ValueError("value must be finite")
        if self.type in QUANTITIES:
            unit, low, high = QUANTITIES[self.type]
            if self.unit != unit or self.value is None or not low <= self.value <= high:
                raise ValueError("Invalid unit or implausible quantity")
            if self.workout_activity_type is not None:
                raise ValueError("Quantity samples cannot contain a workout activity type")
        elif self.type == SLEEP_TYPE:
            if self.value not in range(6) or self.unit is not None or self.workout_activity_type is not None:
                raise ValueError("Sleep requires a category code 0..5 and no unit")
            if self.end_at == self.start_at:
                raise ValueError("Sleep intervals must have positive duration")
        elif self.type == WORKOUT_TYPE:
            if self.value is not None or self.unit is not None or self.workout_activity_type is None:
                raise ValueError("Workouts require workout_activity_type and no quantity")
            if not 1 <= self.workout_activity_type <= 3000:
                raise ValueError("Invalid workout activity type")
            if not timedelta(0) < self.end_at - self.start_at <= timedelta(hours=24):
                raise ValueError("Workout duration must be positive and at most 24 hours")
        else:
            raise ValueError("Unsupported HealthKit type identifier")
        if len(self.metadata) > 32:
            raise ValueError("metadata exceeds 32 fields")
        try:
            encoded = json.dumps(self.metadata, allow_nan=False, separators=(",", ":"), ensure_ascii=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("metadata must contain finite JSON values") from exc
        if len(encoded.encode()) > 8192:
            raise ValueError("metadata exceeds 8192 bytes")

        def check_tree(value, depth=0):
            if depth > 6:
                raise ValueError("metadata nesting exceeds six levels")
            if isinstance(value, dict):
                if len(value) > 32 or any(len(key) > 256 for key in value):
                    raise ValueError("metadata object exceeds field bounds")
                for child in value.values():
                    check_tree(child, depth + 1)
            elif isinstance(value, list):
                if len(value) > 128:
                    raise ValueError("metadata array exceeds 128 items")
                for child in value:
                    check_tree(child, depth + 1)
        check_tree(self.metadata)
        return self


class HealthKitDelta(WireModel):
    batch_id: UUID
    expected_checkpoint: StrictInt = Field(ge=0, le=2147483646)
    additions: list[HealthKitAddition] = Field(default_factory=list, max_length=500)
    deletions: list[UUID] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def bounded_batch(self):
        if len(self.additions) + len(self.deletions) > 500:
            raise ValueError("A batch may contain at most 500 additions and deletions combined")
        addition_ids = [sample.uuid for sample in self.additions]
        if len(set(addition_ids)) != len(addition_ids) or len(set(self.deletions)) != len(self.deletions):
            raise ValueError("A UUID may occur only once in each batch list")
        if set(addition_ids) & set(self.deletions):
            raise ValueError("A UUID cannot be added and deleted in the same batch")
        return self
