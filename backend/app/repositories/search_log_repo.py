"""Search telemetry persistence.

`search_logs` is partitioned by month and append-only. Writes go through a raw
INSERT rather than the ORM because the table has no natural single-column
primary key to hydrate and nothing ever reads a row back individually.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class SearchLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        *,
        raw_query: str,
        normalised_query: str,
        result_count: int,
        response_ms: int,
        was_degraded: bool,
        filters: dict | None = None,
        session_id: UUID | None = None,
    ) -> None:
        """Append one search.

        `session_id` is NOT NULL on the table, so an anonymous search that
        arrives without one gets a throwaway. Losing the ability to stitch that
        single search into a session is a better outcome than losing the row.
        """
        await self.session.execute(
            text(
                """
                INSERT INTO search_logs (
                    session_id, raw_query, normalised_query, filters,
                    result_count, was_degraded, response_ms
                ) VALUES (
                    :session_id, :raw_query, :normalised_query, CAST(:filters AS jsonb),
                    :result_count, :was_degraded, :response_ms
                )
                """
            ),
            {
                "session_id": str(session_id or uuid4()),
                "raw_query": raw_query,
                "normalised_query": normalised_query,
                "filters": json.dumps(filters or {}),
                "result_count": result_count,
                "was_degraded": was_degraded,
                "response_ms": response_ms,
            },
        )

    async def zero_result_queries(
        self, *, since: date, limit: int = 50
    ) -> list[tuple[str, int]]:
        """The most actionable search report: demand the catalogue cannot meet.

        Reads the partial index on `occurred_at WHERE result_count = 0`.
        """
        rows = await self.session.execute(
            text(
                """
                SELECT normalised_query, count(*) AS n
                  FROM search_logs
                 WHERE result_count = 0 AND occurred_at >= :since
                 GROUP BY normalised_query
                 ORDER BY n DESC
                 LIMIT :limit
                """
            ),
            {"since": since, "limit": limit},
        )
        return [(r[0], r[1]) for r in rows.all()]

    async def top_queries(self, *, since: date, limit: int = 50) -> list[tuple[str, int, int]]:
        rows = await self.session.execute(
            text(
                """
                SELECT normalised_query,
                       count(*) AS searches,
                       count(*) FILTER (WHERE result_count = 0) AS zero_results
                  FROM search_logs
                 WHERE occurred_at >= :since
                 GROUP BY normalised_query
                 ORDER BY searches DESC
                 LIMIT :limit
                """
            ),
            {"since": since, "limit": limit},
        )
        return [(r[0], r[1], r[2]) for r in rows.all()]

    async def latency_percentile(self, *, since: datetime, percentile: float = 0.95) -> float:
        row = await self.session.execute(
            text(
                """
                SELECT percentile_disc(:p) WITHIN GROUP (ORDER BY response_ms)
                  FROM search_logs
                 WHERE occurred_at >= :since AND response_ms IS NOT NULL
                """
            ),
            {"p": percentile, "since": since},
        )
        return float(row.scalar_one() or 0)
