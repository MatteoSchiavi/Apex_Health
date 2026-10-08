"""Lab panel API schemas (§18 /labs). Markers are optional — a panel may
carry any subset; extra non-standard markers ride in `extra_markers`."""

from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LabPanelIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    panel_date: date
    panel_type: str = Field(min_length=1)
    donation_type: str | None = None
    hemoglobin: float | None = None
    hematocrit: float | None = None
    ferritin: float | None = None
    iron: float | None = None
    wbc: float | None = None
    plt: float | None = None
    next_eligible_date: date | None = None
    notes: str | None = None
    extra_markers: list[dict[str, Any]] = Field(default_factory=list)
    reference_ranges: dict[str, tuple[float | None, float | None]] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def ordered_reference_ranges(self):
        for marker, (low, high) in self.reference_ranges.items():
            if marker not in {"hemoglobin", "hematocrit", "ferritin", "iron", "wbc", "plt"}:
                raise ValueError("Use extra_markers for non-standard markers and their intervals")
            if low is not None and high is not None and low > high:
                raise ValueError("Reference lower bound must not exceed upper bound")
        return self


class LabPanelOut(BaseModel):
    id: int
    panel_date: date
    panel_type: str
    donation_type: str | None
    hemoglobin: float | None
    hematocrit: float | None
    ferritin: float | None
    iron: float | None
    wbc: float | None
    plt: float | None
    next_eligible_date: date | None
    source: str | None
    markers: list[dict[str, Any]] = Field(default_factory=list)
    notes: str | None  # decrypted here, never at rest (§17)
