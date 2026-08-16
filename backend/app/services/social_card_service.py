"""Branded share-card rendering.

Composed programmatically rather than stamped onto a fixed background. Every
element is measured and placed at render time, which is what lets one template
absorb a two-word job title and a sixty-character one, a disclosed salary and a
withheld one, six skills and none.

**Why Pillow and not a headless browser.** A browser would give CSS layout and
pixel-perfect fidelity, at the cost of a 400MB runtime dependency on the
publish path and a cold start measured in seconds. For a card with a dozen text
runs and no reflow, the layout logic here is smaller than the deployment
problem a browser creates.

**Fonts are bundled, not looked up.** A container has no fonts. Resolving by
family name works on a developer's laptop and renders empty boxes in
production, which is the kind of failure nobody sees until a customer does.
Noto Naskh Arabic is included so Urdu company names render as words.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

from app.core.config import settings
from app.core.enums import SocialVariant

logger = logging.getLogger(__name__)

FONT_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts"

# --- brand -----------------------------------------------------------------
# Taken from the frontend design system so a card is recognisably the same
# product as the site it links to.
BRAND = "#33A4BB"
BRAND_DEEP = "#0E7490"
INK = "#111827"
INK_SOFT = "#6B7280"
SURFACE = "#FFFFFF"
CANVAS = "#F8FAFB"
BORDER = "#E5EAF0"
SUCCESS = "#22C55E"

#: Arabic, Arabic Supplement, Arabic Extended-A and the Presentation Forms.
#: Urdu is written in Arabic script, so a company name containing any of these
#: needs the Naskh face rather than the Latin one.
_ARABIC = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")


@dataclass(frozen=True)
class CardSpec:
    """The geometry of one variant."""

    width: int
    height: int
    padding: int
    title_max: int
    title_min: int
    #: How many skill chips fit before the row is truncated.
    chip_limit: int
    qr_size: int


SPECS: dict[SocialVariant, CardSpec] = {
    SocialVariant.SQUARE: CardSpec(
        width=1080, height=1080, padding=72, title_max=86, title_min=44, chip_limit=6, qr_size=168
    ),
    # Shorter, so the title gets less room and fewer chips fit. A variant is a
    # design, not a crop.
    SocialVariant.LANDSCAPE: CardSpec(
        width=1200, height=627, padding=56, title_max=64, title_min=34, chip_limit=4, qr_size=132
    ),
}


@dataclass
class JobCardData:
    """Exactly what appears on a card — and therefore exactly what the content
    hash covers. Anything not on this object cannot change the image."""

    title: str
    company: str
    location: str
    employment_type: str
    slug: str
    salary: str | None = None
    experience: str | None = None
    skills: list[str] = field(default_factory=list)

    def content_hash(self) -> str:
        """Digest of the rendered fields.

        Order and separator are fixed so the digest is stable across processes.
        A field added to the card must be added here, or stale images survive
        an edit — which is the one bug this whole mechanism exists to prevent.
        """
        parts = [
            self.title,
            self.company,
            self.location,
            self.employment_type,
            self.slug,
            self.salary or "",
            self.experience or "",
            "|".join(self.skills),
        ]
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()

    @property
    def job_url(self) -> str:
        return f"{settings.site_url.rstrip('/')}/jobs/{self.slug}"


@lru_cache(maxsize=64)
def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a bundled face. Cached — building a face is not free and a card
    uses the same handful of sizes repeatedly."""
    path = FONT_DIR / name
    if not path.is_file():
        # Loud rather than silent: the alternative is every card rendering in
        # a default bitmap face that looks like a bug report.
        raise FileNotFoundError(f"bundled font missing: {path}")
    return ImageFont.truetype(str(path), size)


def _face(text: str, *, bold: bool) -> str:
    """Pick the face that can actually draw this string."""
    if _ARABIC.search(text):
        return "NotoNaskhArabic-Bold.ttf" if bold else "NotoNaskhArabic-Regular.ttf"
    return "NotoSans-Bold.ttf" if bold else "NotoSans-Regular.ttf"


def _measure(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return right - left, bottom - top


def _wrap(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int
) -> list[str]:
    """Greedy word wrap.

    A word longer than the line — a URL, an unbroken German compound — is left
    to overflow rather than hyphenated at an arbitrary point; the caller shrinks
    the face instead.
    """
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _measure(draw, candidate, font)[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fit_title(
    draw: ImageDraw.ImageDraw, text: str, spec: CardSpec, max_width: int, max_lines: int
) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Largest size at which the title fits in `max_lines`.

    Steps down rather than solving directly because wrapping is discrete: the
    line count changes in jumps as the face shrinks, so there is no closed form.
    Six-point steps keep it to a handful of iterations.
    """
    face = _face(text, bold=True)
    size = spec.title_max
    while size >= spec.title_min:
        font = _font(face, size)
        lines = _wrap(draw, text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines
        size -= 6

    # Even at the floor it does not fit: keep the floor and ellipsize, so a
    # pathological title degrades to something readable instead of overflowing
    # the canvas.
    font = _font(face, spec.title_min)
    lines = _wrap(draw, text, font, max_width)[:max_lines]
    if lines:
        lines[-1] = lines[-1].rstrip(" .,") + "…"
    return font, lines


def _rounded(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    radius: int,
    fill: str | None = None,
    outline: str | None = None,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def _icon(draw: ImageDraw.ImageDraw, kind: str, x: int, y: int, size: int, colour: str) -> None:
    """Draw a fact icon as vector primitives.

    Not emoji. Noto Sans carries no emoji glyphs, so `📍` renders as a tofu box
    — and bundling Noto Color Emoji would add ~10MB and a CBDT rendering path
    for four small marks. Drawn shapes are a few lines each, scale cleanly, and
    read as deliberate design rather than as pasted characters.
    """
    r = size / 2
    cx, cy = x + r, y + r

    if kind == "location":
        # Pin: a ring with a tapered point.
        head = size * 0.62
        draw.ellipse(
            (cx - head / 2, y, cx + head / 2, y + head), outline=colour, width=max(2, size // 9)
        )
        draw.polygon(
            [
                (cx - head * 0.30, y + head * 0.74),
                (cx + head * 0.30, y + head * 0.74),
                (cx, y + size),
            ],
            fill=colour,
        )
    elif kind == "clock":
        draw.ellipse((x, y, x + size, y + size), outline=colour, width=max(2, size // 9))
        draw.line((cx, cy, cx, cy - r * 0.52), fill=colour, width=max(2, size // 10))
        draw.line((cx, cy, cx + r * 0.40, cy), fill=colour, width=max(2, size // 10))
    elif kind == "experience":
        # Three ascending bars.
        bar = size * 0.22
        for i, height in enumerate((0.42, 0.68, 1.0)):
            left = x + i * (bar + size * 0.11)
            draw.rounded_rectangle(
                (left, y + size - size * height, left + bar, y + size), radius=2, fill=colour
            )
    elif kind == "salary":
        # Coin with a slot, which reads as money without a currency symbol —
        # the amount beside it already names its currency.
        draw.ellipse((x, y, x + size, y + size), outline=colour, width=max(2, size // 9))
        draw.line((cx, y + size * 0.24, cx, y + size * 0.76), fill=colour, width=max(2, size // 10))
        draw.line(
            (cx - r * 0.42, y + size * 0.40, cx + r * 0.42, y + size * 0.40),
            fill=colour,
            width=max(2, size // 11),
        )


def _qr(url: str, size: int) -> Image.Image:
    """QR for the listing URL.

    Error correction M rather than L: a phone photographing a laptop screen at
    an angle is the normal case, and the extra redundancy costs a few modules.
    """
    code = qrcode.QRCode(
        version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=1
    )
    code.add_data(url)
    code.make(fit=True)
    image = code.make_image(fill_color=INK, back_color=SURFACE).convert("RGB")
    return image.resize((size, size), Image.Resampling.LANCZOS)


def _draw_body(
    draw: ImageDraw.ImageDraw,
    data: JobCardData,
    spec: CardSpec,
    variant: SocialVariant,
    *,
    card_top: int,
    content_left: int,
    content_width: int,
    measure_only: bool,
) -> int:
    """Lay the card's contents out top-down, returning the final Y.

    Run twice per render: once to measure, once to draw. The card panel has to
    be painted *before* the text that sits on it, but its height depends on how
    much text there turns out to be — a title that wraps to three lines and six
    skill chips need a taller panel than a two-word title and none.

    Pinning the panel to a fixed height instead is what produced a landscape
    card with the call-to-action printed across the middle of the facts.
    `measure_only` suppresses the ink; the arithmetic is identical either way,
    so the two passes cannot disagree.
    """
    ink = (lambda *a, **k: None) if measure_only else draw.text
    shape = None if measure_only else draw

    cursor = card_top + (44 if variant is SocialVariant.SQUARE else 34)

    # Company, above the title and quieter than it — the role is what a reader
    # scans for first.
    company_font = _font(
        _face(data.company, bold=False), 30 if variant is SocialVariant.SQUARE else 24
    )
    company_lines = _wrap(draw, data.company, company_font, content_width)
    ink(
        (content_left, cursor),
        company_lines[0] if company_lines else data.company,
        font=company_font,
        fill=INK_SOFT,
    )
    cursor += _measure(draw, "Ag", company_font)[1] + 22

    # Title: the largest thing on the card.
    max_title_lines = 3 if variant is SocialVariant.SQUARE else 2
    title_font, title_lines = _fit_title(draw, data.title, spec, content_width, max_title_lines)
    line_height = int(title_font.size * 1.18)
    for line in title_lines:
        ink((content_left, cursor), line, font=title_font, fill=INK)
        cursor += line_height
    cursor += 16

    # --- facts -----------------------------------------------------------
    fact_font = _font("NotoSans-Regular.ttf", 27 if variant is SocialVariant.SQUARE else 21)
    facts = [("location", data.location), ("clock", data.employment_type)]
    if data.experience:
        facts.append(("experience", data.experience))
    # Salary is omitted entirely when undisclosed. A "Salary: not specified"
    # line spends the most valuable row on the card saying nothing.
    if data.salary:
        facts.append(("salary", data.salary))

    icon_size = int(fact_font.size * 0.92)
    for kind, value in facts:
        if shape is not None:
            _icon(shape, kind, content_left, cursor + 2, icon_size, BRAND_DEEP)
        ink((content_left + icon_size + 18, cursor), value, font=fact_font, fill=INK)
        cursor += int(fact_font.size * 1.6)

    # --- skill chips -----------------------------------------------------
    if data.skills:
        cursor += 8
        chip_font = _font("NotoSans-Bold.ttf", 22 if variant is SocialVariant.SQUARE else 18)
        chip_x = content_left
        chip_height = int(chip_font.size * 2.0)
        for skill in data.skills[: spec.chip_limit]:
            label = skill if len(skill) <= 22 else f"{skill[:21]}…"
            chip_width = _measure(draw, label, chip_font)[0] + 34
            # Wrap to a second row rather than running off the card.
            if chip_x + chip_width > content_left + content_width:
                chip_x = content_left
                cursor += chip_height + 12
            if shape is not None:
                _rounded(
                    shape,
                    (chip_x, cursor, chip_x + chip_width, cursor + chip_height),
                    radius=chip_height // 2,
                    fill="#EEF7F9",
                    outline="#CDE8EE",
                )
            ink(
                (chip_x + 17, cursor + chip_height // 2 - chip_font.size // 2 - 2),
                label,
                font=chip_font,
                fill=BRAND_DEEP,
            )
            chip_x += chip_width + 12
        cursor += chip_height

    # --- call to action --------------------------------------------------
    cursor += 30
    cta_font = _font("NotoSans-Bold.ttf", 30 if variant is SocialVariant.SQUARE else 24)
    cta_height = 72 if variant is SocialVariant.SQUARE else 58
    cta_width = 280 if variant is SocialVariant.SQUARE else 230
    if shape is not None:
        _rounded(
            shape,
            (content_left, cursor, content_left + cta_width, cursor + cta_height),
            radius=cta_height // 2,
            fill=BRAND,
        )
    cta_text_width = _measure(draw, "Apply Now", cta_font)[0]
    ink(
        (
            content_left + (cta_width - cta_text_width) // 2,
            cursor + cta_height // 2 - cta_font.size // 2 - 3,
        ),
        "Apply Now",
        font=cta_font,
        fill=SURFACE,
    )

    # A green dot beside the CTA reads as "this listing is live" without
    # spending a line of text on it.
    live_font = _font("NotoSans-Regular.ttf", 22 if variant is SocialVariant.SQUARE else 18)
    dot_x = content_left + cta_width + 28
    dot_y = cursor + cta_height // 2
    if shape is not None:
        shape.ellipse((dot_x, dot_y - 7, dot_x + 14, dot_y + 7), fill=SUCCESS)
    ink(
        (dot_x + 24, dot_y - live_font.size // 2 - 2),
        "Now accepting applications",
        font=live_font,
        fill=INK_SOFT,
    )

    return cursor + cta_height


def render_card(data: JobCardData, variant: SocialVariant = SocialVariant.SQUARE) -> bytes:
    """Compose one card and return PNG bytes."""
    spec = SPECS[variant]
    canvas = Image.new("RGB", (spec.width, spec.height), CANVAS)
    draw = ImageDraw.Draw(canvas)

    pad = spec.padding
    square = variant is SocialVariant.SQUARE

    # The landscape card is short and wide, so the QR sits in a right-hand
    # column beside the content instead of below it; stacking them would leave
    # the text roughly 250px of height, which nothing legible fits into.
    qr_beside = not square

    # --- brand band ------------------------------------------------------
    draw.rectangle((0, 0, spec.width, 12), fill=BRAND)

    # --- header ----------------------------------------------------------
    y = 12 + pad - 20
    logo_font = _font("NotoSans-Bold.ttf", 38 if square else 30)
    draw.text((pad, y), "Rozgar", font=logo_font, fill=INK)
    draw.text((pad + _measure(draw, "Rozgar", logo_font)[0], y), ".pk", font=logo_font, fill=BRAND)

    tag_font = _font("NotoSans-Regular.ttf", 20 if square else 17)
    tag = "WE ARE HIRING"
    tag_width = _measure(draw, tag, tag_font)[0]
    tag_box = (spec.width - pad - tag_width - 32, y + 2, spec.width - pad, y + 40)
    _rounded(draw, tag_box, radius=19, fill="#E6F4F7")
    draw.text((tag_box[0] + 16, y + 10), tag, font=tag_font, fill=BRAND_DEEP)

    # --- geometry --------------------------------------------------------
    card_top = y + (72 if square else 58)
    card_right = spec.width - pad
    content_left = pad + 40
    content_width = (spec.width - pad * 2) - 80
    if qr_beside:
        content_width -= spec.qr_size + 60

    # Measure, then paint the panel to fit, then draw for real.
    content_bottom = _draw_body(
        draw,
        data,
        spec,
        variant,
        card_top=card_top,
        content_left=content_left,
        content_width=content_width,
        measure_only=True,
    )

    card_bottom = content_bottom + (44 if square else 34)
    if qr_beside:
        # Never shorter than the QR block it has to contain.
        card_bottom = max(card_bottom, card_top + spec.qr_size + 68)
    card_bottom = min(card_bottom, spec.height - pad - (spec.qr_size + 56 if not qr_beside else 0))

    _rounded(
        draw, (pad, card_top, card_right, card_bottom), radius=32, fill=SURFACE, outline=BORDER
    )
    _draw_body(
        draw,
        data,
        spec,
        variant,
        card_top=card_top,
        content_left=content_left,
        content_width=content_width,
        measure_only=False,
    )

    # --- QR and URL ------------------------------------------------------
    qr_image = _qr(data.job_url, spec.qr_size)
    if qr_beside:
        qr_x = card_right - spec.qr_size - 44
        qr_y = card_top + 44
    else:
        qr_x = spec.width - pad - spec.qr_size
        qr_y = spec.height - pad - spec.qr_size
        _rounded(
            draw,
            (qr_x - 12, qr_y - 12, qr_x + spec.qr_size + 12, qr_y + spec.qr_size + 12),
            radius=18,
            fill=SURFACE,
            outline=BORDER,
        )
    canvas.paste(qr_image, (qr_x, qr_y))

    url_font = _font("NotoSans-Bold.ttf", 26 if square else 20)
    hint_font = _font("NotoSans-Regular.ttf", 21 if square else 17)

    if qr_beside:
        # Under the QR, inside the card, centred on the column.
        label_y = qr_y + spec.qr_size + 10
        scan = "Scan to apply"
        scan_width = _measure(draw, scan, hint_font)[0]
        draw.text(
            (qr_x + (spec.qr_size - scan_width) // 2, label_y), scan, font=hint_font, fill=INK_SOFT
        )
        footer_y = card_bottom + 22
        draw.text(
            (pad, footer_y),
            _display_url(draw, data.job_url, url_font, spec.width - pad * 2),
            font=url_font,
            fill=BRAND_DEEP,
        )
    else:
        footer_y = qr_y + spec.qr_size // 2 - 34
        draw.text((pad, footer_y), "Scan or visit", font=hint_font, fill=INK_SOFT)
        available = spec.width - pad * 2 - spec.qr_size - 40
        draw.text(
            (pad, footer_y + 34),
            _display_url(draw, data.job_url, url_font, available),
            font=url_font,
            fill=BRAND_DEEP,
        )

    buffer = io.BytesIO()
    # `optimize` costs a few milliseconds and takes roughly a fifth off the
    # file, which matters because these are served to social crawlers.
    canvas.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _display_url(
    draw: ImageDraw.ImageDraw, url: str, font: ImageFont.FreeTypeFont, available: int
) -> str:
    """The URL as printed: no scheme, truncated from the right if it must be.

    The scheme is noise on a poster, and the readable part of a job URL is the
    slug — so what gets dropped is the tail, with an ellipsis to say so.
    """
    display = url.replace("https://", "").replace("http://", "")
    if _measure(draw, display, font)[0] <= available:
        return display
    while _measure(draw, f"{display}…", font)[0] > available and len(display) > 24:
        display = display[:-2]
    return f"{display}…"


def storage_key(job_id: str, variant: SocialVariant) -> str:
    return f"social-assets/job_{job_id}_{variant.value}.png"


__all__ = ["BRAND", "JobCardData", "SPECS", "CardSpec", "render_card", "storage_key"]
