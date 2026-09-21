from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from rolescout.fetchers.jsearch import JSearchFetcher

_SAMPLE_ITEM = {
    "job_id": "abc123",
    "job_title": "Senior Python Engineer",
    "employer_name": "TestCorp",
    "job_city": "New York",
    "job_state": "NY",
    "job_country": "US",
    "job_description": "Python and FastAPI required.",
    "job_apply_link": "https://example.com/apply",
    "job_posted_at_datetime_utc": "2026-09-15T00:00:00Z",
    "job_min_salary": 130000.0,
    "job_max_salary": 160000.0,
    "job_is_remote": True,
    "job_required_skills": ["Python", "FastAPI"],
}


def test_fetch_skipped_when_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rolescout.fetchers.jsearch.settings.rapidapi_key", None)
    jobs = JSearchFetcher().fetch()
    assert jobs == []


def test_fetch_returns_jobs(httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rolescout.fetchers.jsearch.settings.rapidapi_key", "test-key")
    monkeypatch.setattr("rolescout.fetchers.base.settings.target_roles", [])
    monkeypatch.setattr("rolescout.fetchers.base.settings.target_role", "Python Engineer")
    monkeypatch.setattr("rolescout.fetchers.jsearch.settings.target_location", "Remote")

    httpx_mock.add_response(json={"status": "OK", "data": [_SAMPLE_ITEM]})

    jobs = JSearchFetcher().fetch()
    assert len(jobs) == 1
    assert jobs[0].id == "jsearch-abc123"
    assert jobs[0].remote is True
    assert jobs[0].salary_min == 130000
    assert jobs[0].tags == ["Python", "FastAPI"]


def test_id_prefix(httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rolescout.fetchers.jsearch.settings.rapidapi_key", "test-key")
    monkeypatch.setattr("rolescout.fetchers.base.settings.target_roles", [])
    monkeypatch.setattr("rolescout.fetchers.base.settings.target_role", "Engineer")
    monkeypatch.setattr("rolescout.fetchers.jsearch.settings.target_location", "Remote")

    httpx_mock.add_response(json={"status": "OK", "data": [_SAMPLE_ITEM]})

    jobs = JSearchFetcher().fetch()
    assert all(j.id.startswith("jsearch-") for j in jobs)


def test_fetch_http_error_returns_empty(
    httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("rolescout.fetchers.jsearch.settings.rapidapi_key", "test-key")
    monkeypatch.setattr("rolescout.fetchers.base.settings.target_roles", [])
    monkeypatch.setattr("rolescout.fetchers.base.settings.target_role", "Engineer")
    monkeypatch.setattr("rolescout.fetchers.jsearch.settings.target_location", "Remote")

    httpx_mock.add_response(status_code=429)
    jobs = JSearchFetcher().fetch()
    assert jobs == []
