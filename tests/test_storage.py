from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from rolescout.models import FitLevel, ScoredJob


def _make_job(id: str = "j1", fit: FitLevel = FitLevel.STRONG, score: float = 0.9) -> ScoredJob:
    return ScoredJob(
        id=id, title="Engineer", company="Co", location="Remote",
        url="https://example.com", source="remotive",
        posted_at=datetime(2026, 9, 18, tzinfo=UTC),
        remote=True, tags="python",
        fit_level=fit, fit_score=score, fit_reasoning="Good.",
        recency_score=0.9, compensation_score=0.5, location_score=1.0,
        composite_score=score,
    )


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rolescout.storage.settings.db_path", tmp_path / "test.db")
    monkeypatch.setattr("rolescout.storage._engine", None)
    from rolescout.storage import init_db
    init_db()


def test_save_and_load_roundtrip() -> None:
    from rolescout.storage import load_jobs, save_jobs
    job = _make_job()
    save_jobs([job])
    results = load_jobs()
    assert len(results) == 1
    assert results[0].id == "j1"


def test_upsert_updates_existing() -> None:
    from rolescout.storage import load_jobs, save_jobs
    save_jobs([_make_job(score=0.9)])
    save_jobs([_make_job(score=0.5)])  # same id
    results = load_jobs()
    assert len(results) == 1
    assert results[0].composite_score == pytest.approx(0.5)


def test_filter_by_fit_level() -> None:
    from rolescout.storage import load_jobs, save_jobs
    save_jobs([_make_job("j1", FitLevel.STRONG), _make_job("j2", FitLevel.LOW)])
    results = load_jobs(fit_levels=[FitLevel.STRONG])
    assert len(results) == 1
    assert results[0].id == "j1"


def test_filter_remote_only() -> None:
    from rolescout.storage import load_jobs, save_jobs
    onsite = _make_job("j2")
    onsite.remote = False
    save_jobs([_make_job("j1"), onsite])
    results = load_jobs(remote_only=True)
    assert all(j.remote for j in results)
    assert len(results) == 1
