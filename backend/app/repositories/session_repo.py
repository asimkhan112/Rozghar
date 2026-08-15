"""Refresh-session persistence.

Every method here works on the token *hash*. The raw token exists only in the
request that carried it and in the response that issues it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select, update

from app.core.enums import SessionRevokeReason
from app.models.admin import AdminSession
from app.repositories.base import BaseRepository


class SessionRepository(BaseRepository[AdminSession]):
    model = AdminSession

    async def get_by_hash(
        self, token_hash: str, *, for_update: bool = False
    ) -> AdminSession | None:
        """Look a session up by token hash.

        `for_update` takes a row lock so two concurrent refreshes with the same
        token serialise. Without it both would read an unrevoked row, both
        would rotate, and the second would look like token theft.
        """
        stmt = select(AdminSession).where(AdminSession.token_hash == token_hash)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def create(
        self,
        *,
        admin_id: UUID,
        token_hash: str,
        family_id: UUID,
        expires_at: datetime,
        user_agent: str | None = None,
        ip_hash: str | None = None,
    ) -> AdminSession:
        session_row = AdminSession(
            admin_id=admin_id,
            token_hash=token_hash,
            family_id=family_id,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_hash=ip_hash,
        )
        self.session.add(session_row)
        await self.session.flush()
        return session_row

    async def revoke(
        self,
        session_row: AdminSession,
        reason: SessionRevokeReason,
        *,
        replaced_by: UUID | None = None,
    ) -> None:
        session_row.revoked_at = datetime.now(UTC)
        session_row.revoked_reason = reason
        if replaced_by is not None:
            session_row.replaced_by = replaced_by
        await self.session.flush()

    async def revoke_family(self, family_id: UUID, reason: SessionRevokeReason) -> int:
        """Revoke every live session in a rotation lineage.

        The response to detected token reuse: the attacker and the legitimate
        holder are both signed out, because there is no way to tell which is
        which.
        """
        stmt = (
            update(AdminSession)
            .where(AdminSession.family_id == family_id, AdminSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
            .returning(AdminSession.id)
        )
        revoked = (await self.session.execute(stmt)).scalars().all()
        await self.session.flush()
        return len(revoked)

    async def revoke_all_for_admin(self, admin_id: UUID, reason: SessionRevokeReason) -> int:
        """Sign an admin out everywhere — used on password and role change."""
        stmt = (
            update(AdminSession)
            .where(AdminSession.admin_id == admin_id, AdminSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
            .returning(AdminSession.id)
        )
        revoked = (await self.session.execute(stmt)).scalars().all()
        await self.session.flush()
        return len(revoked)

    async def list_active_for_admin(self, admin_id: UUID) -> list[AdminSession]:
        stmt = (
            select(AdminSession)
            .where(
                AdminSession.admin_id == admin_id,
                AdminSession.revoked_at.is_(None),
                AdminSession.expires_at > datetime.now(UTC),
            )
            .order_by(AdminSession.issued_at.desc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def purge_expired(self, *, before: datetime | None = None) -> int:
        """Housekeeping. Expired rows carry no security value and only grow the
        table — a scheduled task calls this."""
        cutoff = before or datetime.now(UTC)
        stmt = (
            delete(AdminSession).where(AdminSession.expires_at < cutoff).returning(AdminSession.id)
        )
        deleted = (await self.session.execute(stmt)).scalars().all()
        await self.session.flush()
        return len(deleted)
