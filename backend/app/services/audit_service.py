"""Audit trail.

Every privileged mutation writes a row here, inside the same transaction as the
change it describes. If the change commits, so does its audit entry; if it rolls
back, the entry goes with it. A trail that can disagree with the data is worse
than none, because it is trusted.

Only changed fields are recorded. Snapshotting whole rows on every edit turns
this table into a second, slower copy of the database.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

#: Values that must never reach the audit trail even if a caller passes them.
_REDACTED_FIELDS = frozenset(
    {"password", "password_hash", "token", "token_hash", "secret", "apply_url_raw"}
)


def _serialise(value: Any) -> Any:
    """JSON-safe representation for a column value."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list | tuple):
        return [_serialise(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialise(v) for k, v in value.items()}
    return str(value)


def diff(before: dict[str, Any], after: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reduce two snapshots to only the fields that actually changed."""
    changed = [
        key for key in after if key not in _REDACTED_FIELDS and before.get(key) != after.get(key)
    ]
    return (
        {k: _serialise(before.get(k)) for k in changed},
        {k: _serialise(after.get(k)) for k in changed},
    )


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        admin_id: UUID | None,
        action: str,
        entity_type: str,
        entity_id: UUID | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        ip_hash: str | None = None,
    ) -> AuditLog:
        """Append an entry. Never commits — the caller owns the transaction."""
        entry = AuditLog(
            admin_id=admin_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before={k: _serialise(v) for k, v in before.items()} if before else None,
            after={k: _serialise(v) for k, v in after.items()} if after else None,
            ip_hash=ip_hash,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def record_many(
        self,
        *,
        admin_id: UUID | None,
        action: str,
        entity_type: str,
        entries: list[tuple[UUID, dict[str, Any] | None, dict[str, Any] | None]],
        ip_hash: str | None = None,
    ) -> int:
        """One INSERT for many entries that share an action.

        `record` flushes on every call, which is correct for a single mutation
        and ruinous for a bulk one: publishing five hundred listings through it
        is five hundred sequential inserts against a database that may be tens
        of milliseconds away. This writes them as a single multi-row statement.

        The trail is not thinned to compensate. Each listing still gets its own
        row with its own `entity_id` and `before`/`after` — for the purge those
        rows are the only surviving record that the listing existed at all, so
        collapsing the batch into one summary entry would be losing the thing
        the audit log is for.

        `id` is a database identity and `created_at` a server default, so
        neither needs generating here.
        """
        if not entries:
            return 0

        rows = [
            {
                "admin_id": admin_id,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "before": {k: _serialise(v) for k, v in before.items()} if before else None,
                "after": {k: _serialise(v) for k, v in after.items()} if after else None,
                "ip_hash": ip_hash,
            }
            for entity_id, before, after in entries
        ]
        await self.session.execute(insert(AuditLog).values(rows))
        return len(rows)

    async def record_change(
        self,
        *,
        admin_id: UUID | None,
        action: str,
        entity_type: str,
        entity_id: UUID,
        before: dict[str, Any],
        after: dict[str, Any],
        ip_hash: str | None = None,
    ) -> AuditLog | None:
        """Record only if something changed.

        A PATCH that sets every field to its current value is a no-op, and an
        audit row claiming otherwise is noise in the one place that must stay
        readable.
        """
        before_changed, after_changed = diff(before, after)
        if not after_changed:
            return None
        return await self.record(
            admin_id=admin_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=before_changed,
            after=after_changed,
            ip_hash=ip_hash,
        )
