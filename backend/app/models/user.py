from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, EmailStr, Field


class UserRole(StrEnum):
    ADMIN = "admin"
    EDITOR = "editor"


EDITORIAL_ROLES = (UserRole.ADMIN, UserRole.EDITOR)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=72)


class UserProfileUpdate(BaseModel):
    display_name: str = Field(min_length=2, max_length=80)
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=10, max_length=72)


class AdminUserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=72)
    display_name: str = Field(min_length=2, max_length=80)
    role: UserRole = UserRole.EDITOR


class AdminUserUpdateRequest(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(default=None, min_length=10, max_length=72)
    display_name: str | None = Field(default=None, min_length=2, max_length=80)
    role: UserRole | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    display_name: str
    role: UserRole
    avatar_media_id: str | None = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
