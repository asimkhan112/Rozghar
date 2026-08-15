"""Audit log schemas.

Read-only. There is no create or update model because nothing outside the
service layer may write an audit row, and nothing at all may modify one.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.schemas.common import ORMModel


class AuditActorRead(ORMModel):
    id: UUID
    email: str
    full_name: str


class AuditLogRead(ORMModel):
    id: int
    admin_id: UUID | None
    actor: AuditActorRead | None = None
    action: str
    entity_type: str
    entity_id: UUID | None
    before: dict | None
    after: dict | None
    created_at: datetime
    #: `ip_hash` is intentionally not exposed — it exists for investigation,
    #: not for display.
