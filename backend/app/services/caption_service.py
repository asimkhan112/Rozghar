"""Share captions, per platform.

Each network rewards a different shape. LinkedIn reads as a post and tolerates
structure; WhatsApp is a message someone forwards, so it stays short and puts
the link where a thumb lands; X has a hard character budget; Facebook sits
between them.

Writing one caption and truncating it for the others is how you get a LinkedIn
post that reads like an SMS and a tweet that ends mid-word.
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
    lines += ["", "Apply here:", url, "", _hashtag_line(tags)]
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
    whatsapp_lines += ["", "Apply here:", url, "", "Found on Rozgar.pk"]
    whatsapp = "\n".join(whatsapp_lines)

    # --- Facebook --------------------------------------------------------
    facebook_lines = [
        f"🚀 We're hiring: {data.title} at {data.company}",
        "",
        f"📍 {data.location}  ·  🕒 {data.employment_type}",
    ]
    if data.salary:
        facebook_lines.append(f"💰 {data.salary}")
    facebook_lines += ["", f"Apply now: {url}", "", _hashtag_line(tags[:4])]
    facebook = "\n".join(facebook_lines)

    # --- X ---------------------------------------------------------------
    twitter = _build_tweet(data, tags, url)

    return Captions(
        linkedin=linkedin, whatsapp=whatsapp, facebook=facebook, twitter=twitter, hashtags=tags
    )


def _build_tweet(data: CaptionInput, tags: tuple[str, ...], url: str) -> str:
    """Fit the post to 280, dropping the least valuable parts first.

    Order of sacrifice: salary, then location, then hashtags, then the title is
    truncated. The link and the company are never dropped — without them the
    post is not actionable.
    """
    tag_line = _hashtag_line(tags[:3])
    # The URL is counted at its wrapped cost, not its literal length.
    fixed = TWEET_URL_COST + len("\n\n") + len(tag_line) + len("\n\n")

    def compose(title: str, include_salary: bool, include_location: bool) -> str:
        head = f"🚀 {title} @ {data.company}"
        bits = []
        if include_location:
            bits.append(f"📍 {data.location}")
        if include_salary and data.salary:
            bits.append(f"💰 {data.salary}")
        detail = ("\n" + "  ·  ".join(bits)) if bits else ""
        return f"{head}{detail}\n\n{url}\n\n{tag_line}"

    def cost(text: str) -> int:
        return len(text) - len(url) + TWEET_URL_COST

    for salary, location in ((True, True), (False, True), (False, False)):
        candidate = compose(data.title, salary, location)
        if cost(candidate) <= TWEET_LIMIT:
            return candidate

    # Still too long: shorten the title itself, keeping whole words.
    budget = TWEET_LIMIT - fixed - len(f"🚀  @ {data.company}") - 2
    title = data.title
    while len(title) > budget and " " in title:
        title = title.rsplit(" ", 1)[0]
    return compose(f"{title}…", False, False)


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
