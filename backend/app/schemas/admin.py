"""Admin account and session schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import EmailStr, Field, model_validator

from app.core.enums import SessionRevokeReason
from app.schemas.common import ORMModel, StrictModel
from app.schemas.rbac import RoleRead


class AdminCreate(StrictModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    #: Minimum length only. Complexity rules punish users without meaningfully
    #: raising entropy; length is the control that matters.
    password: str = Field(min_length=12, max_length=128)
    role_id: UUID


class AdminUpdate(StrictModel):
    """Email is immutable — changing it changes identity, so it is a separate
    verified flow rather than a field on a general update.

    `role_id` is here rather than on a dedicated endpoint because it is an
    ordinary field edit from the client's point of view. The service treats it
    as anything but: a role change revokes the account's sessions and bumps the
    permission cache, and it is refused if it would leave nobody able to
    administer the platform.
    """

    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    is_active: bool | None = None
    role_id: UUID | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> AdminUpdate:
        if self.full_name is None and self.is_active is None and self.role_id is None:
            raise ValueError("supply at least one field to change")
        return self


class AdminRoleAssign(StrictModel):
    role_id: UUID


class AdminPasswordChange(StrictModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class AdminRead(ORMModel):
    """Public-facing admin record. Never carries `password_hash`."""

    id: UUID
    email: EmailStr
    full_name: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


class AdminDetail(AdminRead):
    role: RoleRead
    #: Resolved permission keys. The client gates UI on these rather than
    #: inferring capability from a role name.
    permissions: list[str] = Field(default_factory=list)


class AdminSessionRead(ORMModel):
    """One active session, as shown in a "your devices" list."""

    id: UUID
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    revoked_reason: SessionRevokeReason | None
    user_agent: str | None
    #: `token_hash`, `family_id` and `ip_hash` are deliberately not exposed.


class AdminSessionDetail(AdminSessionRead):
    """A session on the platform-wide list, where whose it is matters."""

    admin_id: UUID
    admin_email: EmailStr
    admin_name: str


class SessionRevokeRequest(StrictModel):
    session_id: UUID


class PasswordResetIssued(ORMModel):
    """Returned exactly once.

    The token is not stored in a recoverable form and cannot be shown again.
    Delivering it is a human step, on purpose: this platform has no mail
    infrastructure and inventing one inside an auth flow is how mail
    infrastructure ends up unmonitored.
    """

    token: str
    expires_at: datetime


class PasswordResetConsume(StrictModel):
    token: str = Field(min_length=16, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class RevocationResult(ORMModel):
    revoked: int
