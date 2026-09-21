from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from rolescout.fetchers.remotive import RemotiveFetcher

_SAMPLE = {
    "jobs": [
        {
            "id": 12345,
            "title": "Senior Python Engineer",
            "company_name": "TestCo",
            "candidate_required_location": "Worldwide",
            "description": "<p>Python and FastAPI required.</p>",
            "url": "https://remotive.com/jobs/12345",
            "publication_date": "2026-09-15T00:00:00",
            "salary": "$130,000 - $160,000",
            "tags": ["python", "fastapi"],
        }
    ]
}


def _pin_single_role(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rolescout.fetchers.base.settings.target_roles", [])
    monkeypatch.setattr("rolescout.fetchers.base.settings.target_role", "Staff Data Scientist")


def test_fetch_returns_jobs(httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_single_role(monkeypatch)
    httpx_mock.add_response(json=_SAMPLE)
    jobs = RemotiveFetcher().fetch()
    assert len(jobs) == 1
    assert jobs[0].id == "remotive-12345"
    assert jobs[0].remote is True
    assert jobs[0].salary_min == 130000
    assert jobs[0].salary_max == 160000


def test_id_prefix(httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_single_role(monkeypatch)
    httpx_mock.add_response(json=_SAMPLE)
    jobs = RemotiveFetcher().fetch()
    assert all(j.id.startswith("remotive-") for j in jobs)


def test_fetch_empty_response(httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch) -> None:
    _pin_single_role(monkeypatch)
    httpx_mock.add_response(json={"jobs": []})
    assert RemotiveFetcher().fetch() == []


def test_fetch_http_error_returns_empty(
    httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_single_role(monkeypatch)
    httpx_mock.add_response(status_code=500)
    assert RemotiveFetcher().fetch() == []


def test_html_stripped_from_description(
    httpx_mock: HTTPXMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pin_single_role(monkeypatch)
    httpx_mock.add_response(json=_SAMPLE)
    jobs = RemotiveFetcher().fetch()
    assert "<p>" not in jobs[0].description
