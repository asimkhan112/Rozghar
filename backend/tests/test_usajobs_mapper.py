"""Mapping tests, run against a real captured response.

No network. The fixture is an actual `GET /api/search?...&Fields=Full` body,
which matters: every bug this integration is likely to have lives in the gap
between what the documentation describes and what the API sends, and a
hand-written fixture would encode the documentation rather than the reality.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.enums import EmploymentType, ExperienceLevel, SalaryPeriod, WorkType
from app.services.usajobs_mapper import (
    DEFAULT_CATEGORY,
    apply_url,
    category_slug,
    clean,
    experience_level,
    map_announcement,
    split_location,
)

FIXTURE = Path(__file__).parent / "fixtures" / "usajobs_search.json"


def descriptors() -> list[dict]:
    payload = json.loads(FIXTURE.read_text())
    return [
        {**item["MatchedObjectDescriptor"], "_MatchedObjectId": str(item["MatchedObjectId"])}
        for item in payload["SearchResult"]["SearchResultItems"]
    ]


@pytest.fixture
def hourly() -> dict:
    """A wage-grade post: pay per hour, one long duties paragraph."""
    return descriptors()[0]


@pytest.fixture
def salaried() -> dict:
    """An overseas GS post: annual salary, five real duty bullets."""
    return descriptors()[1]


def test_every_fixture_row_maps(hourly: dict, salaried: dict) -> None:
    for descriptor in (hourly, salaried):
        assert map_announcement(descriptor) is not None


def test_hourly_pay_is_not_read_as_monthly(hourly: dict) -> None:
    mapped = map_announcement(hourly)
    assert mapped is not None
    assert mapped.data["salary_period"] is SalaryPeriod.HOUR
    assert mapped.data["salary_currency"] == "USD"
    assert mapped.data["salary_is_disclosed"] is True


def test_annual_salary_keeps_its_range(salaried: dict) -> None:
    mapped = map_announcement(salaried)
    assert mapped is not None
    assert mapped.data["salary_period"] is SalaryPeriod.YEAR
    assert mapped.data["salary_min"] < mapped.data["salary_max"]


def test_one_long_duty_becomes_prose_not_a_single_bullet(hourly: dict) -> None:
    """The failure this guards against is a listing whose Responsibilities
    section is one 1,300-character bullet."""
    mapped = map_announcement(hourly)
    assert mapped is not None
    assert mapped.data["responsibilities"] == []
    assert "Duties:" in mapped.data["description"]


def test_several_short_duties_become_bullets(salaried: dict) -> None:
    mapped = map_announcement(salaried)
    assert mapped is not None
    assert len(mapped.data["responsibilities"]) > 1
    assert all(len(item) <= 400 for item in mapped.data["responsibilities"])


def test_domestic_location_splits_city_from_state(hourly: dict) -> None:
    city, region, country, display = split_location(hourly)
    assert city == "Norfolk"
    assert region == "Virginia"
    assert country == "US"
    assert display == "Norfolk, Virginia, United States"


def test_overseas_posting_is_not_filed_as_american(salaried: dict) -> None:
    """`CityName` is "Stuttgart, Germany" and there is no state — reading the
    whole string as a city and defaulting to US gets both fields wrong."""
    city, _region, country, display = split_location(salaried)
    assert city == "Stuttgart"
    assert country == "DE"
    assert display == "Stuttgart, Germany"


def test_schedule_is_read_from_the_code_not_the_name(hourly: dict) -> None:
    """A live record named its schedule "M-F, Subject to irregular tour/On-Call"
    while carrying code 1 — the name is unusable."""
    mapped = map_announcement(hourly)
    assert mapped is not None
    assert mapped.data["employment_type"] is EmploymentType.FULL_TIME


def test_grade_drives_seniority(hourly: dict, salaried: dict) -> None:
    assert experience_level({"HighGrade": "4"}) is ExperienceLevel.ENTRY
    assert experience_level({"HighGrade": "12"}) is ExperienceLevel.MID
    assert experience_level({"HighGrade": "14"}) is ExperienceLevel.SENIOR
    assert experience_level({}) is ExperienceLevel.MID
    assert map_announcement(hourly).data["experience_level"] is ExperienceLevel.ENTRY
    assert map_announcement(salaried).data["experience_level"] is ExperienceLevel.MID


def test_telework_is_hybrid_not_remote(hourly: dict) -> None:
    """Telework-eligible still has a duty station. Calling it remote would put
    it in front of readers who cannot take it."""
    mapped = map_announcement(hourly)
    assert mapped is not None
    assert mapped.data["work_type"] is WorkType.HYBRID


def test_apply_url_loses_the_explicit_port(hourly: dict) -> None:
    assert apply_url(hourly) == "https://www.usajobs.gov/job/865220800"


def test_series_maps_to_a_category(hourly: dict) -> None:
    assert category_slug(hourly) == "it-technology"
    assert category_slug({"JobCategory": [{"Code": "9999"}]}) == DEFAULT_CATEGORY
    assert category_slug({}) == DEFAULT_CATEGORY


def test_description_clears_the_column_minimum(hourly: dict, salaried: dict) -> None:
    for descriptor in (hourly, salaried):
        body = map_announcement(descriptor).data["description"]
        assert 50 <= len(body) <= 20_000


def test_a_row_without_an_id_is_dropped_not_raised(hourly: dict) -> None:
    assert map_announcement({**hourly, "_MatchedObjectId": ""}) is None


def test_markup_is_stripped() -> None:
    assert clean("<p>Hello <b>there</b></p>") == "Hello there"
    assert clean(None) == ""
