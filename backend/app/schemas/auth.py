"""Authentication request and response shapes."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field

from app.schemas.common import ORMModel, StrictModel


class LoginRequest(StrictModel):
    email: EmailStr
    #: No maximum-complexity rules. Length is the control that matters, and an
    #: upper bound only exists to stop a megabyte password reaching Argon2.
    password: str = Field(min_length=1, max_length=128)


class PrincipalResponse(ORMModel):
    """The caller, as the admin UI needs to know them.

    `permissions` is the important field: the client hides actions the caller
    cannot perform by testing this set, never by comparing a role name.
    """

    id: UUID
    email: EmailStr
    full_name: str
    role: str
    permissions: list[str]


class TokenResponse(ORMModel):
    """Login and refresh both return this.

    The refresh token is deliberately absent — it travels only as an httpOnly
    cookie, so JavaScript cannot read it and an XSS cannot exfiltrate it.
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    expires_at: datetime


class LoginResponse(TokenResponse):
    admin: PrincipalResponse
