"""Category, location, source and company management.

Reference data is deactivated, never deleted. Jobs reference all four with
`ON DELETE RESTRICT`, so a delete would either fail loudly or orphan live
listings — `is_active` says "stop offering this" without rewriting history.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.countries import country_name
from app.core.exceptions import Conflict, NotFound
from app.core.slug import slugify
from app.models.company import Company
from app.models.taxonomy import Category, Location, Source
from app.repositories.taxonomy_repo import (
    CategoryRepository,
    CompanyRepository,
    LocationRepository,
    SourceRepository,
)
from app.services.audit_service import AuditService
from app.services.auth_service import Principal


def _snapshot(entity: Any) -> dict[str, Any]:
    return {
        c.name: getattr(entity, c.name)
        for c in entity.__table__.columns
        if c.name not in {"updated_at", "created_at", "job_count"}
    }


class _BaseTaxonomyService:
    entity_name: str
    slug_source: str = "name"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session)

    async def _ensure_slug(
        self, repo: Any, supplied: str | None, source_value: str, *, exclude_id: UUID | None = None
    ) -> str:
        """Use the supplied slug, or derive one from the display name.

        Unlike job slugs, these never auto-discriminate: a duplicate category
        name is an editorial mistake worth surfacing, not something to paper
        over with a numeric suffix.
        """
        candidate = supplied or slugify(source_value)
        if not candidate:
            raise Conflict(f"Could not derive a slug for this {self.entity_name}.")
        if await repo.slug_exists(candidate, exclude_id=exclude_id):
            raise Conflict(f"A {self.entity_name} with the slug '{candidate}' already exists.")
        return candidate

    async def _audit_create(self, principal: Principal, entity: Any, ip_hash: str | None) -> None:
        await self.audit.record(
            admin_id=principal.admin_id,
            action=f"{self.entity_name}.create",
            entity_type=self.entity_name,
            entity_id=entity.id,
            after=_snapshot(entity),
            ip_hash=ip_hash,
        )

    async def _audit_update(
        self, principal: Principal, entity: Any, before: dict[str, Any], ip_hash: str | None
    ) -> None:
        await self.audit.record_change(
            admin_id=principal.admin_id,
            action=f"{self.entity_name}.update",
            entity_type=self.entity_name,
            entity_id=entity.id,
            before=before,
            after=_snapshot(entity),
            ip_hash=ip_hash,
        )


class CategoryService(_BaseTaxonomyService):
    entity_name = "category"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repo = CategoryRepository(session)

    async def list_public(self) -> list[Category]:
        return await self.repo.list_active()

    async def list_all(self) -> list[Category]:
        return await self.repo.list_all()

    async def create(
        self, data: dict[str, Any], *, principal: Principal, ip_hash: str | None = None
    ) -> Category:
        slug = await self._ensure_slug(self.repo, data.pop("slug", None), data["name"])
        category = Category(**data, slug=slug)
        await self.repo.create(category)
        await self._audit_create(principal, category, ip_hash)
        return category

    async def update(
        self,
        category_id: UUID,
        changes: dict[str, Any],
        *,
        principal: Principal,
        ip_hash: str | None = None,
    ) -> Category:
        category = await self.repo.get(category_id)
        if category is None:
            raise NotFound("No category exists with that identifier.")

        # Deactivating a category with live listings would leave them
        # unreachable through the filters that reference it.
        if changes.get("is_active") is False and category.job_count > 0:
            raise Conflict(
                f"This category still has {category.job_count} published listing(s). "
                "Move or expire them before deactivating it."
            )

        before = _snapshot(category)
        for field, value in changes.items():
            setattr(category, field, value)
        await self.session.flush()
        await self._audit_update(principal, category, before, ip_hash)
        return category


def _label_parts(location: Location) -> dict[str, Any]:
    """The fields a location's label is composed from, as `_display_name` wants
    them. `display_name` is deliberately absent: including it would make the
    composer echo the stored value back instead of deriving a fresh one."""
    return {
        "city": location.city,
        "region": location.region,
        "country": location.country,
        "is_remote": location.is_remote,
    }


class LocationService(_BaseTaxonomyService):
    entity_name = "location"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repo = LocationRepository(session)

    async def list_all(self) -> list[Location]:
        """Every location, archived ones included.

        The admin screen needs this and the public projection cannot provide
        it: deactivating a location removes it from `list_active`, so a console
        built on the public list could archive a row and then have no way to
        show it again."""
        return await self.repo.list_all()

    async def list_public(self, *, country: str | None = None) -> list[Location]:
        return await self.repo.list_active(country=country)

    #: Fields the composed label is built from. Changing any of them without
    #: recomposing leaves the label describing where the location used to be.
    _LABEL_PARTS = frozenset({"city", "region", "country", "is_remote"})

    @classmethod
    def _display_name(cls, data: dict[str, Any]) -> str:
        """Compose the label the UI shows, so it is consistent everywhere.

        Names come from the full ISO 3166-1 table rather than a handful of
        hardcoded entries. The five-country map this replaced fell through to
        the raw code for everywhere else, so a listing in Germany read
        "Berlin, DE" beside "Lahore, Pakistan" — the exact inconsistency the
        old comment warned about, for all but five markets.
        """
        if data.get("display_name"):
            return str(data["display_name"])
        if data.get("is_remote"):
            region = data.get("region")
            scope = region or country_name(data.get("country")) or "Worldwide"
            return f"Remote – {scope}"
        city = data.get("city") or ""
        return f"{city}, {country_name(data.get('country'))}".strip(", ")

    async def create(
        self, data: dict[str, Any], *, principal: Principal, ip_hash: str | None = None
    ) -> Location:
        display_name = self._display_name(data)
        data["display_name"] = display_name
        slug = await self._ensure_slug(self.repo, data.pop("slug", None), display_name)
        location = Location(**data, slug=slug)
        await self.repo.create(location)
        await self._audit_create(principal, location, ip_hash)
        return location

    async def update(
        self,
        location_id: UUID,
        changes: dict[str, Any],
        *,
        principal: Principal,
        ip_hash: str | None = None,
    ) -> Location:
        location = await self.repo.get(location_id)
        if location is None:
            raise NotFound("No location exists with that identifier.")
        if changes.get("is_active") is False and location.job_count > 0:
            raise Conflict(f"This location still has {location.job_count} published listing(s).")

        before = _snapshot(location)

        # Was the stored label composed by us, or written by hand? The model
        # has no flag for it — but a generated label is reproducible, so
        # recomposing the *current* parts and comparing answers the question
        # without one. A hand-written label differs, and must survive an edit
        # to the fields it deliberately ignores.
        was_generated = location.display_name == self._display_name(_label_parts(location))

        for field, value in changes.items():
            setattr(location, field, value)

        # Recompose when the parts it is built from move. Skipped for a label
        # the caller is setting now, and for one somebody wrote by hand.
        if was_generated and "display_name" not in changes and self._LABEL_PARTS & changes.keys():
            location.display_name = self._display_name(_label_parts(location))

        await self.session.flush()
        await self._audit_update(principal, location, before, ip_hash)
        return location


class SourceService(_BaseTaxonomyService):
    entity_name = "source"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repo = SourceRepository(session)

    async def list_all(self) -> list[Source]:
        """Every source, paused ones included — see `LocationService.list_all`."""
        return await self.repo.list_all()

    async def list_public(self) -> list[Source]:
        return await self.repo.list_active()

    async def create(
        self, data: dict[str, Any], *, principal: Principal, ip_hash: str | None = None
    ) -> Source:
        slug = await self._ensure_slug(self.repo, data.pop("slug", None), data["name"])
        if data.get("base_url") is not None:
            data["base_url"] = str(data["base_url"])
        source = Source(**data, slug=slug)
        await self.repo.create(source)
        await self._audit_create(principal, source, ip_hash)
        return source

    async def update(
        self,
        source_id: UUID,
        changes: dict[str, Any],
        *,
        principal: Principal,
        ip_hash: str | None = None,
    ) -> Source:
        source = await self.repo.get(source_id)
        if source is None:
            raise NotFound("No source exists with that identifier.")

        # Every job carries a source, and one with no source supplied falls
        # back to 'manual'. Deactivating it would break job creation.
        if source.slug == "manual" and changes.get("is_active") is False:
            raise Conflict("The manual source cannot be deactivated.")

        before = _snapshot(source)
        if changes.get("base_url") is not None:
            changes["base_url"] = str(changes["base_url"])
        for field, value in changes.items():
            setattr(source, field, value)
        await self.session.flush()
        await self._audit_update(principal, source, before, ip_hash)
        return source


class CompanyService(_BaseTaxonomyService):
    entity_name = "company"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repo = CompanyRepository(session)

    async def list_paginated(self, *, page: int, per_page: int) -> tuple[list[Company], int]:
        total = await self.repo.count()
        items = (
            await self.repo.list_paginated(limit=per_page, offset=(page - 1) * per_page)
            if total
            else []
        )
        return items, total

    async def create(
        self, data: dict[str, Any], *, principal: Principal, ip_hash: str | None = None
    ) -> Company:
        slug = await self._ensure_slug(self.repo, data.pop("slug", None), data["name"])
        for url_field in ("logo_url", "website"):
            if data.get(url_field) is not None:
                data[url_field] = str(data[url_field])
        # Derived once so a listing without a logo image still renders a mark.
        if not data.get("monogram"):
            data["monogram"] = "".join(w[0] for w in data["name"].split()[:2]).upper()[:2]
        company = Company(**data, slug=slug)
        await self.repo.create(company)
        await self._audit_create(principal, company, ip_hash)
        return company

    async def update(
        self,
        company_id: UUID,
        changes: dict[str, Any],
        *,
        principal: Principal,
        ip_hash: str | None = None,
    ) -> Company:
        company = await self.repo.get(company_id)
        if company is None:
            raise NotFound("No company exists with that identifier.")
        before = _snapshot(company)
        for url_field in ("logo_url", "website"):
            if changes.get(url_field) is not None:
                changes[url_field] = str(changes[url_field])
        for field, value in changes.items():
            setattr(company, field, value)
        await self.session.flush()
        await self._audit_update(principal, company, before, ip_hash)
        return company
