"""Slug generation.

Slugs are derived server-side and never accepted from a client. Once a job is
published its slug is frozen: it is the URL every share, bookmark and search
result points at, so changing it silently breaks links that already exist.
"""

from __future__ import annotations

import re
import unicodedata

_DASHES = re.compile(r"[‐-―−]")  # hyphen, en/em dash, minus
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_EDGE_DASH = re.compile(r"^-+|-+$")

MAX_SLUG_LENGTH = 160


def slugify(value: str, *, max_length: int = MAX_SLUG_LENGTH) -> str:
    """Lowercase, ASCII, hyphen-separated.

    Handles the punctuation that actually appears in these listings — en-dashes
    in "Software Engineer – Backend" and parentheses in
    "Product Designer (UX/UI)".
    """
    normalised = unicodedata.normalize("NFKD", value)
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii")
    lowered = _DASHES.sub("-", ascii_only).lower()
    hyphenated = _NON_ALNUM.sub("-", lowered)
    trimmed = _EDGE_DASH.sub("", hyphenated)

    if len(trimmed) <= max_length:
        return trimmed
    # Cut on a word boundary rather than mid-word.
    cut = trimmed[:max_length].rsplit("-", 1)[0]
    return _EDGE_DASH.sub("", cut) or trimmed[:max_length]


def job_slug(title: str, company: str) -> str:
    """Namespaced by employer, so two companies may post the same title."""
    base = f"{slugify(title, max_length=100)}-at-{slugify(company, max_length=50)}"
    return _EDGE_DASH.sub("", base)[:MAX_SLUG_LENGTH]


def with_discriminator(base: str, attempt: int) -> str:
    """Append a numeric suffix when a slug is taken.

    Preferred over failing the request: a genuine duplicate posting is normal
    (the same role advertised twice), and an operator should not have to invent
    a different title to get past a uniqueness error.
    """
    suffix = f"-{attempt}"
    return f"{base[: MAX_SLUG_LENGTH - len(suffix)]}{suffix}"
