"""Explicit athlete assertions, deliberately separate from provider measurements."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, field_validator


Identity = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=120)]
Provider = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")]


class ComparisonContextIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_id: Identity
    terrain: Literal["paved", "trail", "track", "treadmill", "gravel", "mixed", "other"]
    indoor: StrictBool
    time_convention: Literal["elapsed", "moving"]
    effort_type: Literal["easy", "steady"]

    @field_validator("route_id")
    @classmethod
    def printable_identity(cls, value: str) -> str:
        if any(not char.isprintable() for char in value):
            raise ValueError("Route identity must contain printable characters")
        return value


class ComparisonContextUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Provider
    expected_revision: Annotated[str, StringConstraints(strict=True, pattern=r"^[a-f0-9]{64}$")]
    context: ComparisonContextIn | None
    reviewed: StrictBool

    @field_validator("reviewed")
    @classmethod
    def explicit_review(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Review the comparison context before saving")
        return value
