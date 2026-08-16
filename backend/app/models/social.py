"""Generated social share assets.

A derived artefact: every row here can be rebuilt from the job it points at,
which is what makes it safe to store on local disk and safe to delete. The
table exists to answer two questions cheaply — "has this been generated?" and
"is it still current?" — without opening the file or re-rendering to compare.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import SocialVariant, pg_enum
from app.db.base import Base, UUIDPkMixin

if TYPE_CHECKING:
    from app.models.job import Job


class JobSocialAsset(UUIDPkMixin, Base):
    __tablename__ = "job_social_assets"

    #: CASCADE: the asset is meaningless without the listing, and a card for a
    #: deleted job is a file nothing will ever clean up.
    job_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )

    variant: Mapped[SocialVariant] = mapped_column(
        pg_enum(SocialVariant, "social_variant"), nullable=False
    )

    #: Storage-relative key, never an absolute path — the deployment directory
    #: is not a property of the asset.
    path: Mapped[str] = mapped_column(String(300), nullable=False)

    #: Digest of exactly the job fields the card renders. Comparing it is how
    #: regeneration is decided, so a change to a view counter does not
    #: invalidate an image that would come out byte-identical.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    width: Mapped[int] = mapped_column(Integer(), nullable=False)
    height: Mapped[int] = mapped_column(Integer(), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="0")

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    job: Mapped[Job] = relationship(lazy="noload")

    __table_args__ = (
        # One asset per job per variant. Two rows would mean two files and no
        # way to say which is current.
        UniqueConstraint("job_id", "variant", name="uq_job_social_assets_job_id_variant"),
        CheckConstraint("width > 0 AND height > 0", name="dimensions_positive"),
        Index("ix_job_social_assets_job_id", "job_id"),
    )


__all__ = ["JobSocialAsset"]
