from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import field_validator
from sqlmodel import Field, SQLModel


class FitLevel(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    LOW = "low"


class Job(SQLModel):
    """Transient job data fetched from a source — never persisted directly."""

    id: str
    title: str
    company: str
    location: str
    description: str
    url: str
    source: str
    posted_at: datetime | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    remote: bool = False
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        return list(v)  # type: ignore[arg-type]


class ScoredJob(SQLModel, table=True):
    """Persisted job with scoring results."""

    __tablename__ = "scored_jobs"

    pk: int | None = Field(default=None, primary_key=True)

    # Identity
    id: str = Field(index=True)
    title: str
    company: str
    location: str
    url: str
    source: str = Field(index=True)
    posted_at: datetime | None = Field(default=None, index=True)

    # Compensation
    salary_min: int | None = None
    salary_max: int | None = None

    # Location
    remote: bool = Field(default=False, index=True)

    # AI scoring
    fit_level: FitLevel = Field(index=True)
    fit_score: float  # 1.0 / 0.6 / 0.2 for strong / medium / low
    fit_reasoning: str

    # Component scores
    recency_score: float
    compensation_score: float
    location_score: float
    composite_score: float = Field(index=True)

    # Per-dimension scores (Jev only; None for Claude)
    score_skills: float | None = None
    score_seniority: float | None = None
    score_domain: float | None = None
    score_responsibilities: float | None = None
    seniority_direction: str | None = None  # overqualified | well_matched | underqualified
    scorer_details: str | None = None  # JSON blob of Jev probability distributions

    # Metadata
    tags: str = Field(default="")  # comma-separated
    scorer: str = Field(default="unknown")  # "claude" or "jev"
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    scored_at: datetime | None = None
