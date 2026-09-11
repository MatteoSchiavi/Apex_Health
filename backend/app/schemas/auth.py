"""Auth request/response schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class AuthUserOut(BaseModel):
    user_id: int
    email: str
    role: str
    ai_access_tier: str


class LoginResponse(AuthUserOut):
    pass


class RedeemInviteRequest(BaseModel):
    """§18 /auth/invite/redeem — the friend picks their own email+password
    here; the invite code alone authorizes account creation."""

    code: str = Field(min_length=8, max_length=256)
    name: str = Field(min_length=1, max_length=80)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class InviteCreateRequest(BaseModel):
    expires_in_days: int = Field(default=7, ge=1, le=90)


class InviteOut(BaseModel):
    id: int
    code: str
    created_by: int
    used_by: int | None
    expires_at: datetime
    created_at: datetime
    expired: bool


class AiTierUpdateRequest(BaseModel):
    ai_access_tier: Literal["cheap_only", "full"]
