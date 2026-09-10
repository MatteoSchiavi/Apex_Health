"""Auth request/response schemas."""

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
