"""Audit trail viewer.

Read-only, and structurally incapable of being anything else: there is no
repository method to update or delete an entry, and no schema to write one. A
trail that can be edited is not a trail.

Gated on AUDIT_VIEW rather than ADMIN_MANAGE — reading what happened and
changing who can do things are different powers, and an auditor should need
only the first.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.v1.deps import DbSession, require
from app.core.permissions import Permission
from app.repositories.audit_repo import AuditFilters, AuditRepository
from app.schemas.audit import AuditActorRead, AuditLogRead
from app.schemas.common import Paginated
from app.services.auth_service import Principal

router = APIRouter(prefix="/admin/audit", tags=["admin:audit"])


@router.get("", response_model=Paginated[AuditLogRead], summary="Recent privileged actions")
async def list_audit(
    session: DbSession,
    _: Annotated[Principal, Depends(require(Permission.AUDIT_VIEW))],
    admin_id: UUID | None = None,
    entity_type: Annotated[str | None, Query(max_length=32)] = None,
    entity_id: UUID | None = None,
    action: Annotated[
        str | None, Query(max_length=64, description="Prefix, e.g. `job.` or `report.resolve`")
    ] = None,
    since: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Paginated[AuditLogRead]:
    """Newest first. `action` matches by prefix so `job.` selects every job
    verb without the caller enumerating them."""
    repo = AuditRepository(session)
    filters = AuditFilters(
        admin_id=admin_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action_prefix=action,
        since=since,
    )

    total = await repo.count(filters)
    rows = await repo.list(filters, limit=per_page, offset=(page - 1) * per_page)

    return Paginated[AuditLogRead](
        items=[
            AuditLogRead(
                id=entry.id,
                admin_id=entry.admin_id,
                # Absent when the account was deleted, or when the action had
                # no human behind it — an expiry sweep, for instance.
                actor=(
                    AuditActorRead(id=actor.id, email=actor.email, full_name=actor.full_name)
                    if actor is not None
                    else None
                ),
                action=entry.action,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                before=entry.before,
                after=entry.after,
                created_at=entry.created_at,
            )
            for entry, actor in rows
        ],
        page=page,
        per_page=per_page,
        total=total,
        total_pages=(total + per_page - 1) // per_page if per_page else 0,
        has_more=page * per_page < total,
    )
