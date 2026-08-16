"""Materialised vocabularies backing the autocomplete endpoint.

Both tables are derived data — every row can be rebuilt from `jobs` and
`search_logs` — and both are refreshed by a scheduled task rather than written
on the request path. They exist because their sources cannot be queried fast
enough per keystroke: skills are a JSONB array with no index, and `search_logs`
is partitioned by month.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SkillTerm(Base):
    """One distinct skill, harvested from `jobs.requirements`."""

    __tablename__ = "skill_terms"

    term: Mapped[str] = mapped_column(String(120), primary_key=True)
    #: Lowercased and unaccented at write time, so the query side compares a
    #: plain column against a plain literal and the trigram index applies.
    term_norm: Mapped[str] = mapped_column(String(120), nullable=False)
    #: Published listings mentioning this skill. The tiebreak within a tier.
    job_count: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_skill_terms_norm_trgm",
            "term_norm",
            postgresql_using="gin",
            postgresql_ops={"term_norm": "gin_trgm_ops"},
        ),
        # `text_pattern_ops` is what makes `LIKE 'react%'` indexable whatever
        # the database collation is — the prefix tier is the hottest path here.
        Index(
            "ix_skill_terms_norm_prefix",
            "term_norm",
            postgresql_ops={"term_norm": "text_pattern_ops"},
        ),
    )


class PopularQuery(Base):
    """A search people actually run, aggregated out of `search_logs`."""

    __tablename__ = "popular_queries"

    query_norm: Mapped[str] = mapped_column(String(200), primary_key=True)
    hits: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_popular_queries_prefix",
            "query_norm",
            postgresql_ops={"query_norm": "text_pattern_ops"},
        ),
    )
