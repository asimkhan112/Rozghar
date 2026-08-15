"""Repository conventions.

Repositories build queries and persist entities. They do not commit, do not
enforce business rules, and do not call one another. The service layer owns the
transaction so that one business operation can span several repositories
atomically.

`flush()` is used where an identifier or a database default is needed before
the transaction ends; it stages the write without ending the unit of work.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base


class BaseRepository[ModelT: Base]:
    """PEP 695 generic — the project targets Python 3.12."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, entity_id: UUID) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    async def list_all(self) -> list[ModelT]:
        result = await self.session.execute(select(self.model))
        return list(result.scalars().all())

    def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        return entity

    async def flush(self, *entities: Any) -> None:
        """Stage pending writes. Never commits — that is the service's call."""
        await self.session.flush(list(entities) or None)
