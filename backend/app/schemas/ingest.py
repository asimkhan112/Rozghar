"""Import run reporting.

A summary, not a job id: the endpoint runs the import before it answers, so
there is nothing to poll.
"""

from __future__ import annotations

from app.schemas.common import ORMModel


class ImportRun(ORMModel):
    #: Announcements the API returned.
    fetched: int
    #: New drafts created by this run.
    created: int
    #: Already imported by an earlier run — the expected result of a repeat.
    skipped: int
    #: Announcements that could not be turned into a valid listing.
    failed: int
    #: The first few failures, for an admin to read. Never the whole list.
    errors: list[str]
