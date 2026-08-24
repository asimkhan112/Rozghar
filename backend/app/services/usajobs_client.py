"""The USAJOBS Search API, wrapped.

One endpoint, three headers, no OAuth. The wrapper exists for the parts that
are easy to get wrong rather than for the HTTP: `Fields=Full` is mandatory (the
default response carries no description at all), the row ceiling is 10,000 per
query, and the page size caps at 500.

Reference: https://developer.usajobs.gov/api-reference/get-api-search
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import DomainError

logger = logging.getLogger(__name__)

BASE_URL = "https://data.usajobs.gov/api/search"
#: The API rejects anything larger.
MAX_PAGE_SIZE = 500


class USAJobsUnavailable(DomainError):
    status = 503
    code = "usajobs_unavailable"
    title = "USAJOBS importing is not configured"


class USAJobsFailed(DomainError):
    status = 502
    code = "usajobs_failed"
    title = "The USAJOBS API could not be reached"


class USAJobsClient:
    """Stateless. Holds no connection between calls — a fetch run is a handful
    of requests a few times a day, so a pooled client would idle far longer
    than it is used."""

    def __init__(self, *, api_key: str | None = None, user_agent: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.usajobs_api_key
        self.user_agent = user_agent or settings.usajobs_user_agent

    @property
    def headers(self) -> dict[str, str]:
        # `Host` is required by the API even though httpx would set it. Sending
        # it explicitly is what their documentation specifies.
        return {
            "Host": "data.usajobs.gov",
            "User-Agent": self.user_agent,
            "Authorization-Key": self.api_key,
            "Accept": "application/json",
        }

    async def search(
        self,
        *,
        series: str,
        days_posted: int,
        page_size: int,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """One page of announcements, as raw `MatchedObjectDescriptor` dicts.

        Returns the descriptors rather than the envelope: nothing downstream
        needs the refiners or the relevance rank, and unwrapping here keeps the
        mapper's input the shape its tests use.
        """
        if not self.api_key:
            raise USAJobsUnavailable(
                "USAJOBS importing is not configured on this server. "
                "Set USAJOBS_API_KEY to enable it."
            )

        params = {
            "JobCategoryCode": series,
            "DatePosted": str(max(0, min(days_posted, 60))),
            "ResultsPerPage": str(max(1, min(page_size, MAX_PAGE_SIZE))),
            "Page": str(page),
            # Without this the response has no description, and every listing
            # would fail the 50-character minimum on `jobs.description`.
            "Fields": "Full",
            "WhoMayApply": "Public",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(BASE_URL, params=params, headers=self.headers)
        except httpx.HTTPError as exc:
            logger.warning("usajobs unreachable", extra={"event": "usajobs.unreachable"})
            raise USAJobsFailed("Could not reach the USAJOBS API. Try again.") from exc

        if response.status_code == 401:
            raise USAJobsUnavailable(
                "USAJOBS rejected the API key. Check USAJOBS_API_KEY and USAJOBS_USER_AGENT — "
                "the user agent must be the email the key was registered under."
            )
        if response.status_code >= 400:
            logger.warning(
                "usajobs api error",
                extra={"event": "usajobs.api_error", "status": response.status_code},
            )
            raise USAJobsFailed(
                f"The USAJOBS API returned {response.status_code}. Try again shortly."
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise USAJobsFailed("The USAJOBS API returned a response that was not JSON.") from exc

        items = payload.get("SearchResult", {}).get("SearchResultItems", [])
        descriptors = []
        for item in items:
            descriptor = item.get("MatchedObjectDescriptor")
            if not descriptor:
                continue
            # The id lives on the wrapper, not the descriptor, and it is the
            # only stable identity a listing has.
            descriptor = {**descriptor, "_MatchedObjectId": str(item.get("MatchedObjectId", ""))}
            descriptors.append(descriptor)
        return descriptors


__all__ = ["USAJobsClient", "USAJobsFailed", "USAJobsUnavailable"]
