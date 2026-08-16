"""Audit log reads.

Append-only from every other layer's point of view — there is no create method
here because `AuditService` owns writing, and no update or delete method
because a trail that can be edited is not a trail.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select

from app.models.admin import Admin
from app.models.audit import AuditLog
from app.repositories.base import BaseRepository


@dataclass(frozen=True)
class AuditFilters:
    admin_id: UUID | None = None
    entity_type: str | None = None
    entity_id: UUID | None = None
    #: Prefix match, so `job.` selects every job verb at once.
    action_prefix: str | None = None
    since: datetime | None = None


class AuditRepository(BaseRepository[AuditLog]):
    model = AuditLog

    def _apply(self, stmt: Select, filters: AuditFilters) -> Select:
        if filters.admin_id is not None:
            stmt = stmt.where(AuditLog.admin_id == filters.admin_id)
        if filters.entity_type is not None:
            stmt = stmt.where(AuditLog.entity_type == filters.entity_type)
        if filters.entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == filters.entity_id)
        if filters.action_prefix:
            stmt = stmt.where(AuditLog.action.startswith(filters.action_prefix))
        if filters.since is not None:
            stmt = stmt.where(AuditLog.created_at >= filters.since)
        return stmt

    async def count(self, filters: AuditFilters) -> int:
        return (
            await self.session.execute(
                self._apply(select(func.count()).select_from(AuditLog), filters)
            )
        ).scalar_one()

    async def list(
        self, filters: AuditFilters, *, limit: int, offset: int
    ) -> list[tuple[AuditLog, Admin | None]]:
        """Entries newest first, each with the admin who caused it.

        Outer-joined rather than lazy-loaded: the trail outlives the accounts
        in it (`admin_id` is SET NULL on delete), so the actor is legitimately
        absent sometimes and an inner join would silently drop exactly the
        entries most worth keeping.
        """
        stmt = (
            self._apply(select(AuditLog, Admin), filters)
            .outerjoin(Admin, Admin.id == AuditLog.admin_id)
            .order_by(AuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [(row[0], row[1]) for row in (await self.session.execute(stmt)).all()]


__all__ = ["AuditFilters", "AuditRepository"]
