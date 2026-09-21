from __future__ import annotations

from datetime import UTC, datetime

import pytest

from rolescout.models import FitLevel, Job, ScoredJob


@pytest.fixture
def sample_job() -> Job:
    return Job(
        id="test-001",
        title="Senior Python Engineer",
        company="TestCo",
        location="Remote",
        description="We need a Python expert with FastAPI and PostgreSQL experience.",
        url="https://example.com/jobs/1",
        source="remotive",
        posted_at=datetime(2026, 9, 18, tzinfo=UTC),
        salary_min=130000,
        salary_max=170000,
        remote=True,
        tags=["python", "fastapi"],
    )


@pytest.fixture
def sample_scored_job(sample_job: Job) -> ScoredJob:
    return ScoredJob(
        id=sample_job.id,
        title=sample_job.title,
        company=sample_job.company,
        location=sample_job.location,
        url=sample_job.url,
        source=sample_job.source,
        posted_at=sample_job.posted_at,
        salary_min=sample_job.salary_min,
        salary_max=sample_job.salary_max,
        remote=sample_job.remote,
        tags=",".join(sample_job.tags),
        fit_level=FitLevel.STRONG,
        fit_score=1.0,
        fit_reasoning="Strong Python and FastAPI match.",
        recency_score=0.93,
        compensation_score=1.0,
        location_score=1.0,
        composite_score=0.97,
    )
