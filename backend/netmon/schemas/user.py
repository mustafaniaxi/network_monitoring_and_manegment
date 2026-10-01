from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, Field

from netmon.models import UserRole
from netmon.schemas.common import Schema

_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$")


def _email(value: str) -> str:
    # Deliberately permissive: lab/intranet domains such as ``.local`` or ``.lan`` are valid.
    value = value.strip().lower()
    if len(value) > 255 or not _EMAIL_RE.match(value):
        raise ValueError("must be a valid e-mail address")
    return value


EmailStr = Annotated[str, AfterValidator(_email)]
Password = Field(min_length=8, max_length=128)


class UserBase(Schema):
    email: EmailStr
    full_name: str = Field(default="", max_length=120)
    role: UserRole = UserRole.VIEWER
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Password


class UserUpdate(Schema):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=120)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserRead(Schema):
    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class TokenResponse(Schema):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth2 token type, not a secret
    expires_in: int
    user: UserRead


class PasswordChange(Schema):
    current_password: str
    new_password: str = Password


class ProfileUpdate(Schema):
    full_name: str = Field(max_length=120)
