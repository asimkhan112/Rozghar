"""Share captions, per platform.

Each network rewards a different shape. LinkedIn reads as a post and tolerates
structure; WhatsApp is a message someone forwards, so it stays short and puts
the link where a thumb lands; X has a hard character budget; Facebook sits
between them.

Writing one caption and truncating it for the others is how you get a LinkedIn
post that reads like an SMS and a tweet that ends mid-word.

Every caption also carries the WhatsApp channel, because a post is read once
and a channel follower is read every time: the whole point of sharing a listing
to four networks is to bring people somewhere they stay.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import settings

#: X's limit. A URL counts as 23 regardless of its real length (t.co wrapping),
#: which is why the budget is computed against a constant rather than len(url).
TWEET_LIMIT = 280
TWEET_URL_COST = 23

#: Always present, in this order — the broad tags a Pakistani job seeker
#: actually follows.
BASE_HASHTAGS = ("Hiring", "Jobs", "PakistanJobs")

#: Skill or title fragment → the hashtag people actually search. Without this
#: map, "Node.js" becomes "#Nodejs" and "C++" becomes "#C", which is a
#: different and very busy tag.
SKILL_HASHTAGS: dict[str, str] = {
    "react": "ReactJobs",
    "react.js": "ReactJobs",
    "next.js": "NextJS",
    "node": "NodeJS",
    "node.js": "NodeJS",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "python": "PythonJobs",
    "django": "Django",
    "fastapi": "FastAPI",
    "java": "JavaJobs",
    "php": "PHPJobs",
    "laravel": "Laravel",
    "flutter": "Flutter",
    "android": "AndroidDev",
    "ios": "iOSDev",
    "aws": "AWS",
    "azure": "Azure",
    "docker": "DevOps",
    "kubernetes": "DevOps",
    "terraform": "DevOps",
    "sql": "SQL",
    "postgresql": "PostgreSQL",
    "figma": "UIUX",
    "ui/ux": "UIUX",
    "seo": "SEO",
    "excel": "Excel",
}

#: Title keyword → role hashtag.
ROLE_HASHTAGS: tuple[tuple[str, str], ...] = (
    ("frontend", "FrontendDeveloper"),
    ("front end", "FrontendDeveloper"),
    ("backend", "BackendDeveloper"),
    ("full stack", "FullStackDeveloper"),
    ("fullstack", "FullStackDeveloper"),
    ("devops", "DevOps"),
    ("data analyst", "DataAnalyst"),
    ("data scientist", "DataScience"),
    ("designer", "DesignJobs"),
    ("marketing", "MarketingJobs"),
    ("accountant", "AccountingJobs"),
    ("finance", "FinanceJobs"),
    ("hr ", "HRJobs"),
    ("human resources", "HRJobs"),
    ("sales", "SalesJobs"),
    ("intern", "Internship"),
    ("teacher", "TeachingJobs"),
    ("nurse", "HealthcareJobs"),
    ("engineer", "EngineeringJobs"),
)


@dataclass(frozen=True)
class CaptionInput:
    title: str
    company: str
    location: str
    employment_type: str
    slug: str
    salary: str | None = None
    experience: str | None = None
    skills: tuple[str, ...] = ()

    @property
    def job_url(self) -> str:
        return f"{settings.site_url.rstrip('/')}/jobs/{self.slug}"


@dataclass(frozen=True)
class Captions:
    linkedin: str
    whatsapp: str
    facebook: str
    twitter: str
    hashtags: tuple[str, ...]


def _hashtags(data: CaptionInput, limit: int = 6) -> tuple[str, ...]:
    """Broad tags first, then role, then skills.

    Ordered by reach so that a caption truncated for X keeps the tags that
    actually surface it.
    """
    tags: list[str] = list(BASE_HASHTAGS)
    haystack = data.title.lower()

    for needle, tag in ROLE_HASHTAGS:
        if needle in haystack and tag not in tags:
            tags.append(tag)
            break

    for skill in data.skills:
        tag = SKILL_HASHTAGS.get(skill.strip().lower())
        if tag and tag not in tags:
            tags.append(tag)
        if len(tags) >= limit:
            break

    if data.employment_type.lower().startswith("intern") and "Internship" not in tags:
        tags.append("Internship")

    return tuple(tags[:limit])


def _channel_lines(prompt: str) -> list[str]:
    """The channel call-to-action, or nothing when no channel is configured.

    Returned as caption lines rather than a string so a caller can splice it
    into a list without leaving a blank paragraph behind when it is empty.
    """
    channel = settings.whatsapp_channel_url.strip()
    if not channel:
        return []
    return ["", prompt, channel]


def _hashtag_line(tags: tuple[str, ...]) -> str:
    return " ".join(f"#{tag}" for tag in tags)


def _skill_bullets(skills: tuple[str, ...], limit: int = 5) -> str:
    return "\n".join(f"• {skill}" for skill in skills[:limit])


def build_captions(data: CaptionInput) -> Captions:
    tags = _hashtags(data)
    url = data.job_url

    # --- LinkedIn --------------------------------------------------------
    # Structured and scannable. Emoji are used as row markers rather than
    # decoration, which is the convention on the platform and what makes the
    # post readable in a dense feed.
    lines = [
        f"🚀 Hiring: {data.title}",
        "",
        f"🏢 Company: {data.company}",
        f"📍 Location: {data.location}",
    ]
    if data.salary:
        lines.append(f"💰 Salary: {data.salary}")
    lines.append(f"🕒 {data.employment_type}")
    if data.experience:
        lines.append(f"📈 Experience: {data.experience}")
    if data.skills:
        lines += ["", "Required Skills:", _skill_bullets(data.skills)]
    lines += ["", "Apply here:", url]
    lines += _channel_lines("📢 Daily jobs on our WhatsApp channel:")
    lines += ["", _hashtag_line(tags)]
    linkedin = "\n".join(lines)

    # --- WhatsApp --------------------------------------------------------
    # A forwarded message, not a post. No hashtags — they are inert here and
    # read as spam — and the link sits near the end where a thumb reaches.
    whatsapp_lines = [
        f"*{data.title}*",
        f"{data.company}",
        "",
        f"📍 {data.location}",
        f"🕒 {data.employment_type}",
    ]
    if data.salary:
        whatsapp_lines.append(f"💰 {data.salary}")
    whatsapp_lines += ["", "Apply here:", url]
    whatsapp_lines += _channel_lines("📢 Join our channel for daily jobs:")
    whatsapp_lines += ["", "Found on Plenilo.com"]
    whatsapp = "\n".join(whatsapp_lines)

    # --- Facebook --------------------------------------------------------
    facebook_lines = [
        f"🚀 We're hiring: {data.title} at {data.company}",
        "",
        f"📍 {data.location}  ·  🕒 {data.employment_type}",
    ]
    if data.salary:
        facebook_lines.append(f"💰 {data.salary}")
    facebook_lines += ["", f"Apply now: {url}"]
    facebook_lines += _channel_lines("📢 Daily jobs on our WhatsApp channel:")
    facebook_lines += ["", _hashtag_line(tags[:4])]
    facebook = "\n".join(facebook_lines)

    # --- X ---------------------------------------------------------------
    twitter = _build_tweet(data, tags, url)

    return Captions(
        linkedin=linkedin, whatsapp=whatsapp, facebook=facebook, twitter=twitter, hashtags=tags
    )


def _build_tweet(data: CaptionInput, tags: tuple[str, ...], url: str) -> str:
    """Fit the post to 280, dropping the least valuable parts first.

    Order of sacrifice: salary, then location, then the channel line, then the
    title is truncated. The job link and the company are never dropped —
    without them the post is not actionable — and the channel outlives the
    listing, so it goes late rather than first.
    """
    tag_line = _hashtag_line(tags[:3])
    channel = settings.whatsapp_channel_url.strip()

    def compose(
        title: str, include_salary: bool, include_location: bool, with_channel: bool
    ) -> str:
        head = f"🚀 {title} @ {data.company}"
        bits = []
        if include_location:
            bits.append(f"📍 {data.location}")
        if include_salary and data.salary:
            bits.append(f"💰 {data.salary}")
        detail = ("\n" + "  ·  ".join(bits)) if bits else ""
        channel_line = f"\n\n📢 {channel}" if with_channel and channel else ""
        return f"{head}{detail}\n\n{url}{channel_line}\n\n{tag_line}"

    def cost(text: str, with_channel: bool) -> int:
        # Every link is wrapped to a fixed width by t.co, however long it is,
        # so each one is counted at that width rather than at its own length.
        links = [url] + ([channel] if with_channel and channel else [])
        return len(text) - sum(map(len, links)) + TWEET_URL_COST * len(links)

    for salary, location, with_channel in (
        (True, True, True),
        (False, True, True),
        (False, False, True),
        (False, False, False),
    ):
        candidate = compose(data.title, salary, location, with_channel)
        if cost(candidate, with_channel) <= TWEET_LIMIT:
            return candidate

    # Still too long: shorten the title itself, keeping whole words.
    fixed = TWEET_URL_COST + len("\n\n") + len(tag_line) + len("\n\n")
    budget = TWEET_LIMIT - fixed - len(f"🚀  @ {data.company}") - 2
    title = data.title
    while len(title) > budget and " " in title:
        title = title.rsplit(" ", 1)[0]
    return compose(f"{title}…", False, False, False)


def share_urls(job_url: str, captions: Captions) -> dict[str, str]:
    """Intent URLs for each platform.

    LinkedIn takes only a URL — it dropped prefilled text years ago and scrapes
    the page's own metadata instead, which is why the flow copies the caption to
    the clipboard for the user to paste. WhatsApp and X do accept text.
    """
    from urllib.parse import quote

    encoded = quote(job_url, safe="")
    return {
        "linkedin": f"https://www.linkedin.com/sharing/share-offsite/?url={encoded}",
        "facebook": f"https://www.facebook.com/sharer/sharer.php?u={encoded}",
        "twitter": f"https://twitter.com/intent/tweet?text={quote(captions.twitter, safe='')}",
        "whatsapp": f"https://wa.me/?text={quote(captions.whatsapp, safe='')}",
    }


def strip_markup(text: str) -> str:
    """WhatsApp's asterisks, removed — for a plain-text copy button."""
    return re.sub(r"[*_~]", "", text)


__all__ = ["CaptionInput", "Captions", "build_captions", "share_urls", "strip_markup"]
