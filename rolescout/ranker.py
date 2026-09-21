from __future__ import annotations

from datetime import UTC, datetime

from rolescout.config import settings
from rolescout.models import FitLevel, Job, ScoredJob
from rolescout.scorer import FitAssessment

_FIT_SCORE_MAP = {FitLevel.STRONG: 1.0, FitLevel.MEDIUM: 0.6, FitLevel.LOW: 0.2}

_W_FIT = 0.50
_W_RECENCY = 0.30
_W_COMPENSATION = 0.10
_W_LOCATION = 0.10


def _recency_score(posted_at: datetime | None) -> float:
    if posted_at is None:
        return 0.5
    now = datetime.now(tz=UTC)
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=UTC)
    age_days = max(0, (now - posted_at).days)
    return 1.0 - min(age_days, 30) / 30.0


def _compensation_score(salary_min: int | None, salary_max: int | None) -> float:
    t_min = settings.target_salary_min
    t_max = settings.target_salary_max

    if salary_min is None and salary_max is None:
        return 0.5
    if t_min is None and t_max is None:
        return 0.5

    j_min = salary_min or 0
    j_max = salary_max or salary_min or 0
    t_lo = t_min or 0
    t_hi = t_max or t_min or 0

    # Full containment or full overlap
    if j_min <= t_lo and j_max >= t_hi:
        return 1.0
    # Partial overlap
    overlap = min(j_max, t_hi) - max(j_min, t_lo)
    if overlap > 0:
        return 0.7
    # Near miss: job ceiling exceeds target floor
    if j_max > t_lo:
        return 0.3
    return 0.0


def _location_score(remote: bool, location: str) -> float:
    if remote:
        return 1.0

    loc_lower = location.lower()
    preferred = settings.preferred_locations
    acceptable = settings.acceptable_locations

    if preferred:
        # Fast path: substring match
        if any(p.lower() in loc_lower for p in preferred):
            return 1.0
        if acceptable and any(a.lower() in loc_lower for a in acceptable):
            return 0.6

        # Slow path: geocoded distance (results cached after first call)
        from rolescout.geocoder import location_tier

        tier = location_tier(location, preferred, acceptable, settings.location_radius_miles)
        if tier == "preferred":
            return 1.0
        if tier == "acceptable":
            return 0.6
        return 0.0

    # No tiers configured: fall back to target_location string match
    if settings.target_location.lower() in loc_lower:
        return 1.0
    return 0.0


def compute_scores(job: Job, assessment: FitAssessment) -> dict[str, float]:
    fit_score = _FIT_SCORE_MAP.get(assessment.fit_level, assessment.fit_score)
    recency = _recency_score(job.posted_at)
    compensation = _compensation_score(job.salary_min, job.salary_max)
    location = _location_score(job.remote, job.location)
    composite = (
        _W_FIT * fit_score
        + _W_RECENCY * recency
        + _W_COMPENSATION * compensation
        + _W_LOCATION * location
    )
    return {
        "fit_score": fit_score,
        "recency_score": recency,
        "compensation_score": compensation,
        "location_score": location,
        "composite_score": composite,
    }


def rank_jobs(pairs: list[tuple[Job, FitAssessment]]) -> list[ScoredJob]:
    scored: list[ScoredJob] = []
    now = datetime.now(tz=UTC)

    for job, assessment in pairs:
        scores = compute_scores(job, assessment)
        scored.append(
            ScoredJob(
                id=job.id,
                title=job.title,
                company=job.company,
                location=job.location,
                url=job.url,
                source=job.source,
                posted_at=job.posted_at,
                salary_min=job.salary_min,
                salary_max=job.salary_max,
                remote=job.remote,
                tags=",".join(job.tags),
                fit_level=assessment.fit_level,
                fit_score=scores["fit_score"],
                fit_reasoning=assessment.reasoning,
                recency_score=scores["recency_score"],
                compensation_score=scores["compensation_score"],
                location_score=scores["location_score"],
                composite_score=scores["composite_score"],
                scored_at=now,
            )
        )

    scored.sort(key=lambda j: j.composite_score, reverse=True)
    return scored
