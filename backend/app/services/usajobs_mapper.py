"""A USAJOBS announcement, translated into a listing.

Pure functions. Nothing here touches the database or the network, which is what
makes the mapping testable against saved fixtures — and the mapping is where
this integration will actually go wrong, not the HTTP.

Three things learned from live responses, each of which the naive reading gets
wrong:

* **`MajorDuties` is a list whose shape varies.** Some agencies write five
  short bullets; others write one 1,300-character paragraph. Treating both as
  bullets produces a listing with a single enormous bullet, so the shape is
  measured rather than assumed.
* **Names are unreliable; codes are not.** A live `PositionSchedule` came back
  named `"M-F, Subject to irregular tour/On-Call"` with code `1` (Full-Time),
  and `PositionOfferingType.Name` was an empty string. Every classification
  here reads the code.
* **`Requirements` and `Benefits` are usually empty.** The substance lives in
  `Education`, `Evaluations` and `OtherInformation`. An empty list is the
  honest output — the listing page omits the section.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.enums import EmploymentType, ExperienceLevel, SalaryPeriod, WorkType

#: Occupational series -> category slug. Anything unlisted lands in
#: government-public-sector, which is true of every announcement here and is a
#: better default than guessing from the title.
SERIES_TO_CATEGORY: dict[str, str] = {
    "2210": "it-technology",
    "0854": "engineering",
    "0801": "engineering",
    "1560": "data-analytics",
    "0343": "data-analytics",
    "0501": "finance-accounting",
    "0510": "finance-accounting",
    "0201": "human-resources",
}
DEFAULT_CATEGORY = "government-public-sector"

#: PositionSchedule codes. 3-6 (shift work, intermittent, job sharing, multiple
#: schedules) have no counterpart in our four employment types and are all
#: still full-time commitments, so they map there rather than inventing a fifth.
SCHEDULE_TO_EMPLOYMENT = {
    "1": EmploymentType.FULL_TIME,
    "2": EmploymentType.PART_TIME,
    "3": EmploymentType.FULL_TIME,
    "4": EmploymentType.PART_TIME,
    "5": EmploymentType.PART_TIME,
    "6": EmploymentType.FULL_TIME,
}

#: RateIntervalCode. Biweekly and "per year" both describe an annual salary to
#: a reader, but only one of them is a period we store; BW is left out so a
#: biweekly figure is never presented as a monthly one.
RATE_TO_PERIOD = {
    "PA": SalaryPeriod.YEAR,
    "PH": SalaryPeriod.HOUR,
    "PM": SalaryPeriod.MONTH,
}

#: GS grade -> seniority. Federal grades are a real ladder, so this is a
#: mapping rather than a guess: 1-4 is entry, 13-14 is senior, 15 runs a
#: programme.
_GRADE_BANDS = (
    (4, ExperienceLevel.ENTRY),
    (8, ExperienceLevel.ENTRY),
    (12, ExperienceLevel.MID),
    (14, ExperienceLevel.SENIOR),
    (15, ExperienceLevel.LEAD),
)

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]+")


@dataclass(frozen=True)
class MappedJob:
    """What the importer hands to `JobService.create`, plus the identity the
    next run recognises this listing by."""

    source_ref: str
    city: str
    region: str
    #: ISO 3166-1 alpha-2, matching `locations.country`.
    country: str
    #: Pre-composed, because only the mapper knows whether the state or the
    #: country is the meaningful second half.
    display_name: str
    category_slug: str
    data: dict[str, Any]


def clean(text: str | None) -> str:
    """Tags out, whitespace normalised.

    Live responses have been plain text throughout, but the field is free-form
    and a single agency pasting HTML would otherwise put markup on the page.
    Stripping unconditionally costs nothing.
    """
    if not text:
        return ""
    without_tags = _TAG.sub(" ", text)
    collapsed = _WS.sub(" ", without_tags.replace("\r\n", "\n").replace("\r", "\n"))
    return "\n".join(line.strip() for line in collapsed.split("\n")).strip()


def _parse_datetime(value: str | None) -> datetime | None:
    """USAJOBS timestamps look like `2026-08-17T12:53:32.5770` — four
    fractional digits and no zone. Naive is correct to record; the caller
    attaches UTC where a timezone is required."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.rstrip("Z"))
    except ValueError:
        return None


def parse_date(value: str | None) -> date | None:
    parsed = _parse_datetime(value)
    return parsed.date() if parsed else None


def _decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError):
        return None
    return amount if amount > 0 else None


#: Country names -> ISO 3166-1 alpha-2. USAJOBS sends a country *name* in
#: `CountryCode`, and federal announcements include real overseas duty stations.
#: Territories map to US because that is what they are to a job seeker. An
#: unrecognised country falls back to US — rare, and the display name still
#: reads "Stuttgart, Germany", so the listing never misleads a reader.
COUNTRY_CODES: dict[str, str] = {
    "united states": "US", "germany": "DE", "japan": "JP", "south korea": "KR",
    "korea, south": "KR", "italy": "IT", "united kingdom": "GB", "spain": "ES",
    "belgium": "BE", "netherlands": "NL", "turkey": "TR", "bahrain": "BH",
    "kuwait": "KW", "qatar": "QA", "united arab emirates": "AE", "poland": "PL",
    "philippines": "PH", "australia": "AU", "greece": "GR", "portugal": "PT",
    "djibouti": "DJ", "honduras": "HN", "cuba": "CU", "guam": "US",
    "puerto rico": "US",
}


def split_location(descriptor: dict[str, Any]) -> tuple[str, str, str, str]:
    """First duty station only.

    An announcement can list a dozen; a listing holds one. The full set stays
    readable in the description, and fanning out into a dozen near-identical
    rows sharing one apply URL would be worse than naming the first.

    Returns `(city, region, country_iso, display_name)`.

    `CityName` arrives as the whole display string — `"Norfolk, Virginia"` at
    home, `"Stuttgart, Germany"` abroad — so the trailing state or country is
    trimmed rather than trusted to be absent.
    """
    locations = descriptor.get("PositionLocation") or []
    first = locations[0] if locations else {}
    region = clean(first.get("CountrySubDivisionCode"))
    country_name = clean(first.get("CountryCode")) or "United States"
    country = COUNTRY_CODES.get(country_name.lower(), "US")

    city = clean(first.get("CityName")) or clean(descriptor.get("PositionLocationDisplay"))
    for suffix in (region, country_name):
        if suffix and city.endswith(f", {suffix}"):
            city = city[: -len(f", {suffix}")].strip()
            break
    city = city or "United States"

    # "Norfolk, Virginia, United States" at home; "Stuttgart, Germany" abroad,
    # where the state is absent and repeating the country would be noise.
    parts = [city, region, country_name] if country == "US" else [city, country_name]
    display = ", ".join(part for part in parts if part)
    return city, region, country, display


def category_slug(descriptor: dict[str, Any]) -> str:
    for entry in descriptor.get("JobCategory") or []:
        mapped = SERIES_TO_CATEGORY.get(str(entry.get("Code", "")).strip())
        if mapped:
            return mapped
    return DEFAULT_CATEGORY


def employment_type(descriptor: dict[str, Any]) -> EmploymentType:
    for entry in descriptor.get("PositionSchedule") or []:
        mapped = SCHEDULE_TO_EMPLOYMENT.get(str(entry.get("Code", "")).strip())
        if mapped:
            return mapped
    return EmploymentType.FULL_TIME


def work_type(details: dict[str, Any]) -> WorkType:
    if details.get("RemoteIndicator"):
        return WorkType.REMOTE
    # Telework-eligible is a real hybrid arrangement, not a remote job: the
    # duty station still exists and the holder reports to it.
    if details.get("TeleworkEligible"):
        return WorkType.HYBRID
    return WorkType.ON_SITE


def experience_level(details: dict[str, Any]) -> ExperienceLevel:
    raw = str(details.get("HighGrade") or details.get("LowGrade") or "").strip()
    if not raw.isdigit():
        return ExperienceLevel.MID
    grade = int(raw)
    for ceiling, level in _GRADE_BANDS:
        if grade <= ceiling:
            return level
    return ExperienceLevel.EXECUTIVE


def salary(descriptor: dict[str, Any]) -> dict[str, Any]:
    entries = descriptor.get("PositionRemuneration") or []
    first = entries[0] if entries else {}
    minimum = _decimal(first.get("MinimumRange"))
    maximum = _decimal(first.get("MaximumRange"))
    period = RATE_TO_PERIOD.get(str(first.get("RateIntervalCode", "")).strip())
    if not (minimum or maximum) or period is None:
        # Undisclosed rather than zero, and the period left at its default:
        # a listing with no figure must not read as "$0".
        return {"salary_is_disclosed": False}
    return {
        "salary_min": minimum,
        "salary_max": maximum,
        "salary_currency": "USD",
        "salary_period": period,
        "salary_is_disclosed": True,
    }


def _duties(details: dict[str, Any]) -> tuple[list[str], str]:
    """Splits `MajorDuties` into bullets and leftover prose.

    Several short entries are the bullets the agency wrote. One long entry is a
    paragraph that happens to sit in a list, and belongs in the description
    where the body text renderer can parse it.
    """
    entries = [clean(entry) for entry in details.get("MajorDuties") or []]
    entries = [entry for entry in entries if entry]
    if not entries:
        return [], ""
    if len(entries) == 1 and len(entries[0]) > 400:
        return [], entries[0]
    bullets = [entry for entry in entries if len(entry) <= 400]
    prose = "\n\n".join(entry for entry in entries if len(entry) > 400)
    return bullets, prose


def apply_url(descriptor: dict[str, Any]) -> str:
    """`ApplyURI` arrives with an explicit `:443` — valid, and ugly in a link
    a reader hovers over."""
    candidates = descriptor.get("ApplyURI") or []
    url = (candidates[0] if candidates else "") or descriptor.get("PositionURI") or ""
    return url.replace(":443/", "/", 1).strip()


def build_description(descriptor: dict[str, Any], details: dict[str, Any], prose: str) -> str:
    """Assembles the body, labelled section by section.

    Written with `Heading:` lines and `- ` bullets deliberately: that is the
    shape the listing page's text parser reads, so an imported description
    renders with the same structure as one an editor typed.
    """
    parts: list[str] = []
    summary = clean(details.get("JobSummary"))
    if summary:
        parts.append(summary)
    if prose:
        parts.append(f"Duties:\n{prose}")

    where = clean(descriptor.get("PositionLocationDisplay"))
    extra = len(descriptor.get("PositionLocation") or [])
    if where:
        suffix = f" (and {extra - 1} other locations)" if extra > 1 else ""
        parts.append(f"Location: {where}{suffix}")

    for label, key in (
        ("Education", "Education"),
        ("How you will be evaluated", "Evaluations"),
        ("Other information", "OtherInformation"),
        ("How to apply", "HowToApply"),
    ):
        value = clean(details.get(key))
        if value:
            parts.append(f"{label}:\n{value}")

    body = "\n\n".join(parts).strip()
    # The column caps at 20,000 and the check constraint rejects under 50.
    # Truncating on a paragraph boundary keeps the tail from ending mid-word.
    if len(body) > 19_500:
        body = body[:19_500].rsplit("\n\n", 1)[0] + "\n\n(Continued on the USAJOBS announcement.)"
    return body


def map_announcement(descriptor: dict[str, Any]) -> MappedJob | None:
    """One announcement to one listing, or None when it cannot make a valid one.

    Returning None rather than raising: an import run over 250 announcements
    should not be lost because one of them has no description.
    """
    source_ref = str(descriptor.get("_MatchedObjectId") or "").strip()
    title = clean(descriptor.get("PositionTitle"))[:200]
    url = apply_url(descriptor)
    if not (source_ref and title and url.startswith("http")):
        return None

    details = (descriptor.get("UserArea") or {}).get("Details") or {}
    bullets, prose = _duties(details)
    description = build_description(descriptor, details, prose)
    if len(description) < 50:
        return None

    city, region, country, display_name = split_location(descriptor)
    employer = clean(descriptor.get("OrganizationName")) or clean(
        descriptor.get("DepartmentName")
    )

    requirements = [clean(item) for item in details.get("KeyRequirements") or []]
    data: dict[str, Any] = {
        "title": title,
        "company_name": (employer or "U.S. Federal Government")[:160],
        "company_website": None,
        "work_type": work_type(details),
        "employment_type": employment_type(descriptor),
        "experience_level": experience_level(details),
        "description": description,
        "responsibilities": bullets,
        "requirements": [item for item in requirements if item][:20],
        "benefits": [],
        "apply_url": url,
        "expiry_date": parse_date(descriptor.get("ApplicationCloseDate")),
        **salary(descriptor),
    }
    return MappedJob(
        source_ref=source_ref,
        city=city,
        region=region,
        country=country,
        display_name=display_name,
        category_slug=category_slug(descriptor),
        data=data,
    )


__all__ = [
    "DEFAULT_CATEGORY",
    "SERIES_TO_CATEGORY",
    "MappedJob",
    "clean",
    "map_announcement",
]
