"""Category, location, source and company persistence.

All four share a shape: slug-addressed, deactivated rather than deleted, and
carrying a denormalised `job_count` maintained with atomic arithmetic.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update

from app.models.company import Company
from app.models.taxonomy import Category, Location, Source
from app.repositories.base import BaseRepository


class _SlugRepository[ModelT](BaseRepository[ModelT]):
    """Shared behaviour for the slug-addressed reference tables."""

    async def get_by_slug(self, slug: str) -> ModelT | None:
        stmt = select(self.model).where(self.model.slug == slug)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def slug_exists(self, slug: str, *, exclude_id: UUID | None = None) -> bool:
        stmt = select(func.count()).select_from(self.model).where(self.model.slug == slug)
        if exclude_id is not None:
            stmt = stmt.where(self.model.id != exclude_id)
        return (await self.session.execute(stmt)).scalar_one() > 0

    async def exists(self, entity_id: UUID) -> bool:
        stmt = select(func.count()).select_from(self.model).where(self.model.id == entity_id)
        return (await self.session.execute(stmt)).scalar_one() > 0

    async def adjust_job_count(self, entity_id: UUID, delta: int) -> None:
        """Atomic, and floored at zero.

        A counter is a cache. If it ever drifts, going negative would violate
        the CHECK constraint and take down an unrelated write, so the floor is
        deliberate.
        """
        await self.session.execute(
            update(self.model)
            .where(self.model.id == entity_id)
            .values(job_count=func.greatest(self.model.job_count + delta, 0))
        )
        await self.session.flush()

    async def create(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        return entity


class CategoryRepository(_SlugRepository[Category]):
    model = Category

    async def list_active(self) -> list[Category]:
        stmt = (
            select(Category)
            .where(Category.is_active.is_(True))
            .order_by(Category.sort_order, Category.name)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_all(self) -> list[Category]:
        stmt = select(Category).order_by(Category.sort_order, Category.name)
        return list((await self.session.execute(stmt)).scalars().all())

    async def is_active(self, category_id: UUID) -> bool:
        stmt = select(Category.is_active).where(Category.id == category_id)
        return bool((await self.session.execute(stmt)).scalar_one_or_none())


class LocationRepository(_SlugRepository[Location]):
    model = Location

    async def list_active(self, *, country: str | None = None) -> list[Location]:
        stmt = select(Location).where(Location.is_active.is_(True))
        if country:
            stmt = stmt.where(Location.country == country)
        return list(
            (await self.session.execute(stmt.order_by(Location.is_remote, Location.display_name)))
            .scalars()
            .all()
        )

    async def list_all(self) -> list[Location]:
        stmt = select(Location).order_by(Location.is_remote, Location.display_name)
        return list((await self.session.execute(stmt)).scalars().all())


class SourceRepository(_SlugRepository[Source]):
    model = Source

    async def list_active(self) -> list[Source]:
        stmt = select(Source).where(Source.is_active.is_(True)).order_by(Source.name)
        return list((await self.session.execute(stmt)).scalars().all())

    async def list_all(self) -> list[Source]:
        stmt = select(Source).order_by(Source.name)
        return list((await self.session.execute(stmt)).scalars().all())

    async def get_manual(self) -> Source | None:
        """The seeded fallback assigned when a caller supplies no source."""
        return await self.get_by_slug("manual")

    async def adjust_job_count(self, entity_id: UUID, delta: int) -> None:
        """Sources carry no counter — per-source volume comes from analytics."""
        return None


class CompanyRepository(_SlugRepository[Company]):
    model = Company

    async def list_paginated(self, *, limit: int, offset: int) -> list[Company]:
        stmt = select(Company).order_by(Company.name).limit(limit).offset(offset)
        return list((await self.session.execute(stmt)).scalars().all())

    async def count(self) -> int:
        return (await self.session.execute(select(func.count()).select_from(Company))).scalar_one()
