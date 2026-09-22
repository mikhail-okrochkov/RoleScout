from __future__ import annotations

import logging
from dataclasses import dataclass

from typesafe_sdk import Choice, Score, TypeSafeClient  # type: ignore[import-untyped]

from rolescout.config import settings
from rolescout.models import FitLevel, Job
from rolescout.scorer import FitAssessment

logger = logging.getLogger(__name__)

# Score criteria: 4 levels each (indices 0–3), normalized to 0.0–1.0 by dividing by 3

_Q_SKILLS = Score(
    instructions=(
        "How well do the job's required technical skills and tools match "
        "the candidate's demonstrated skills?"
    ),
    criteria=[
        "Candidate lacks most required skills; significant reskilling needed",
        "Candidate has some relevant skills but notable gaps exist in core requirements",
        "Candidate meets most requirements; minor gaps that are quickly closable",
        "Candidate's skills strongly match requirements and exceed several criteria",
    ],
)

_Q_SENIORITY = Score(
    instructions=(
        "How well does the role's seniority and scope align with "
        "the candidate's experience level and career stage?"
    ),
    criteria=[
        "Clear mismatch — role is significantly above or below the candidate's level",
        "Partial match — candidate would be a stretch or a notable step down",
        "Good alignment — experience and scope match the expected seniority",
        "Excellent alignment — role fits perfectly and matches growth trajectory",
    ],
)

_Q_DOMAIN = Score(
    instructions=(
        "How relevant is the company's domain, industry, and problem space "
        "to the candidate's background and interests?"
    ),
    criteria=[
        "Unrelated domain with little transferable context",
        "Adjacent domain; some concepts transfer but most is new territory",
        "Related domain where most experience applies directly",
        "Strong match — deep domain expertise transfers with high impact",
    ],
)

_Q_RESPONSIBILITIES = Score(
    instructions=(
        "How closely do the day-to-day responsibilities and deliverables "
        "match what the candidate has done and wants to do next?"
    ),
    criteria=[
        "Responsibilities largely unfamiliar or undesirable based on background",
        "Some overlap but significant new or unwanted responsibilities",
        "Most responsibilities align with candidate's experience and goals",
        "Responsibilities are an excellent match and build on candidate's strengths",
    ],
)

_Q_SENIORITY_DIR = Choice(
    instructions=(
        "Considering the candidate's total years of experience, scope of past roles, "
        "and depth of expertise, how does their seniority compare to what this role requires?"
    ),
    criteria={
        "underqualified": (
            "The candidate lacks the experience, scope, or depth required — "
            "this role would be a significant stretch"
        ),
        "well_matched": (
            "The candidate's seniority aligns well with the role's expectations "
            "and typical career stage for this position"
        ),
        "overqualified": (
            "The candidate significantly exceeds the seniority this role is targeting — "
            "they may find the scope limiting"
        ),
    },
)

# Short labels for probability display in UI (one per criterion level)
_CRITERIA_SHORT: dict[str, list[str]] = {
    "skills": ["Lacking", "Some gaps", "Mostly match", "Strong match"],
    "seniority": ["Mismatch", "Stretch", "Good fit", "Excellent"],
    "domain": ["Unrelated", "Adjacent", "Related", "Strong"],
    "responsibilities": ["Unfamiliar", "Some overlap", "Mostly align", "Excellent"],
}

# Weights for the composite fit score (must sum to 1.0)
_W_SKILLS = 0.40
_W_SENIORITY = 0.30
_W_DOMAIN = 0.15
_W_RESPONSIBILITIES = 0.15

_MAX_LEVEL = 3.0  # 4 criteria → levels 0–3


def _to_fit_level(score: float) -> FitLevel:
    if score >= 0.75:
        return FitLevel.STRONG
    if score >= 0.40:
        return FitLevel.MEDIUM
    return FitLevel.LOW


@dataclass
class _ScoreBreakdown:
    skills: float
    seniority: float
    domain: float
    responsibilities: float


class JevScorer:
    def __init__(self, resume: str) -> None:
        self._client = TypeSafeClient(api_key=settings.typesafe_api_key)
        self._resume = resume

    def score_jobs(
        self,
        jobs: list[Job],
        on_batch: object = None,
    ) -> list[tuple[Job, FitAssessment]]:
        results: list[tuple[Job, FitAssessment]] = []
        for i, job in enumerate(jobs):
            assessment = self._score_one(job)
            results.append((job, assessment))
            if callable(on_batch):
                on_batch(i + 1, len(jobs))
        return results

    def _score_one(self, job: Job) -> FitAssessment:
        state = {
            "resume": self._resume,
            "job": {
                "title": job.title,
                "company": job.company,
                "location": job.location,
                "description": job.description[:3000],
            },
        }
        questions = {
            "skills": _Q_SKILLS,
            "seniority": _Q_SENIORITY,
            "domain": _Q_DOMAIN,
            "responsibilities": _Q_RESPONSIBILITIES,
            "seniority_direction": _Q_SENIORITY_DIR,
        }

        try:
            resp = self._client.system_one(state, questions)
            breakdown = _ScoreBreakdown(
                skills=resp.scores["skills"].score / _MAX_LEVEL,
                seniority=resp.scores["seniority"].score / _MAX_LEVEL,
                domain=resp.scores["domain"].score / _MAX_LEVEL,
                responsibilities=resp.scores["responsibilities"].score / _MAX_LEVEL,
            )
            seniority_direction: str = resp.choices["seniority_direction"].choice
        except Exception as exc:
            logger.error("Jev scoring failed for %r: %s", job.title, exc)
            return FitAssessment(
                fit_level=FitLevel.LOW,
                fit_score=0.2,
                reasoning="Jev scoring unavailable.",
            )

        fit_score = (
            _W_SKILLS * breakdown.skills
            + _W_SENIORITY * breakdown.seniority
            + _W_DOMAIN * breakdown.domain
            + _W_RESPONSIBILITIES * breakdown.responsibilities
        )
        fit_level = _to_fit_level(fit_score)

        # Build probability distributions for UI display
        scorer_details: dict = {}
        for dim_key in ("skills", "seniority", "domain", "responsibilities"):
            score_resp = resp.scores[dim_key]
            probs = score_resp.probabilities  # dict[int, float] keyed by score level
            scorer_details[dim_key] = {
                "score": score_resp.score,
                # Sort by level index so probabilities align with short_labels order
                "probabilities": [
                    probs[k] for k in sorted(probs.keys())
                ] if probs else [],
                "short_labels": _CRITERIA_SHORT[dim_key],
            }
        dir_resp = resp.choices["seniority_direction"]
        scorer_details["seniority_direction"] = {
            "choice": dir_resp.choice,
            "probabilities": dict(dir_resp.probabilities) if dir_resp.probabilities else {},
        }

        return FitAssessment(
            fit_level=fit_level,
            fit_score=fit_score,
            reasoning="",
            score_skills=breakdown.skills,
            score_seniority=breakdown.seniority,
            score_domain=breakdown.domain,
            score_responsibilities=breakdown.responsibilities,
            seniority_direction=seniority_direction,
            scorer_details=scorer_details,
        )
