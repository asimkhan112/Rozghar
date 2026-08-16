"""Share-asset schemas."""

from __future__ import annotations

from uuid import UUID

from app.schemas.common import ORMModel


class ShareUrls(ORMModel):
    linkedin: str
    facebook: str
    twitter: str
    whatsapp: str


class ShareAssets(ORMModel):
    """Everything the share modal renders, in one response.

    Captions are generated server-side rather than in the browser so that the
    wording is identical wherever it is produced — the modal today, an email
    digest or a scheduled repost later.
    """

    job_id: UUID
    job_url: str
    job_title: str
    #: The square card. Generated on first request, then served from storage.
    image_url: str
    #: Every variant, keyed by name. Phase 7 points `og:image` at the landscape
    #: entry without this endpoint changing.
    image_urls: dict[str, str]
    linkedin_caption: str
    whatsapp_message: str
    facebook_caption: str
    twitter_caption: str
    hashtags: list[str]
    share_urls: ShareUrls
