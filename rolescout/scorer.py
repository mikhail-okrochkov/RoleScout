from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass

import anthropic

from rolescout.config import settings
from rolescout.models import FitLevel, Job

logger = logging.getLogger(__name__)

_SYSTEM_INSTRUCTIONS = """\
You are an expert technical recruiter evaluating job postings against a candidate's resume.
Respond with valid JSON only — no prose, no markdown fences, just the raw JSON array.\
"""


@dataclass
class FitAssessment:
    fit_level: FitLevel
    fit_score: float
    reasoning: str
    # Per-dimension scores (populated by JevScorer; None for Claude)
    score_skills: float | None = None
    score_seniority: float | None = None
    score_domain: float | None = None
    score_responsibilities: float | None = None
    seniority_direction: str | None = None  # "overqualified" | "well_matched" | "underqualified"
    # Full probability distributions from Jev (serialized as JSON in ScoredJob)
    scorer_details: dict | None = None


_FALLBACK = FitAssessment(fit_level=FitLevel.LOW, fit_score=0.2, reasoning="Scoring unavailable.")


class JobScorer:
    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=120.0)
        resume_path = settings.resume_path
        if not resume_path.exists():
            raise FileNotFoundError(
                f"Resume not found at {resume_path}. "
                "Copy resume.md.template to resume.md and fill it in."
            )
        self._resume = resume_path.read_text(encoding="utf-8")

    def score_jobs(
        self,
        jobs: list[Job],
        on_batch: Callable[[int, int], None] | None = None,
    ) -> list[tuple[Job, FitAssessment]]:
        results: list[tuple[Job, FitAssessment]] = []
        batch_size = settings.batch_size
        total = len(jobs)
        for i in range(0, total, batch_size):
            batch = jobs[i : i + batch_size]
            assessments = self._score_batch(batch)
            results.extend(zip(batch, assessments, strict=True))
            if on_batch:
                on_batch(min(i + batch_size, total), total)
        return results

    def _score_batch(self, batch: list[Job]) -> list[FitAssessment]:
        system: list[anthropic.types.TextBlockParam] = [
            {"type": "text", "text": _SYSTEM_INSTRUCTIONS},
            {
                "type": "text",
                "text": f"## Candidate Resume\n\n{self._resume}",
                "cache_control": {"type": "ephemeral"},
            },
        ]

        user_content = self._build_user_prompt(batch)

        try:
            response = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2048,
                system=system,
                messages=[{"role": "user", "content": user_content}],
            )
            raw = response.content[0].text
        except Exception as exc:
            logger.error("Claude API error: %s", exc)
            return [_FALLBACK] * len(batch)

        return self._parse_response(raw, len(batch))

    def _build_user_prompt(self, batch: list[Job]) -> str:
        n = len(batch)
        lines = [
            f"Evaluate these {n} job postings against the candidate resume above.",
            f"Return ONLY a JSON array with exactly {n} objects in the same order.",
            "Each object must have:",
            '  "job_index": integer (0-based)',
            '  "fit_level": "strong" | "medium" | "low"',
            '  "fit_score": float 0.0–1.0  (strong>=0.75, medium 0.4–0.74, low<0.4)',
            '  "reasoning": 2–4 sentences citing specific skill matches or gaps',
            "",
            "Evaluation criteria: technical skills match, seniority alignment, "
            "domain fit, role responsibilities.",
            "",
        ]
        for i, job in enumerate(batch):
            salary_line = ""
            if job.salary_min and job.salary_max:
                salary_line = f"Salary: ${job.salary_min:,}–${job.salary_max:,}\n"
            elif job.salary_min:
                salary_line = f"Salary: ${job.salary_min:,}+\n"

            lines.append(f"### Job {i}: {job.title} at {job.company}")
            lines.append(f"Location: {job.location}")
            if salary_line:
                lines.append(salary_line.strip())
            lines.append("")
            lines.append(job.description[:2000])
            lines.append("---")

        return "\n".join(lines)

    def _parse_response(self, raw: str, expected: int) -> list[FitAssessment]:
        # Strip markdown code fences if Claude wraps the response despite instructions
        stripped = raw.strip()
        if stripped.startswith("```"):
            stripped = stripped.split("\n", 1)[-1]  # drop opening fence line
            stripped = stripped.rsplit("```", 1)[0]  # drop closing fence
        try:
            data = json.loads(stripped)
            if not isinstance(data, list):
                raise ValueError("Expected a JSON array")
        except Exception as exc:
            logger.error("Failed to parse scorer response: %s\nRaw: %.200s", exc, stripped)
            return [_FALLBACK] * expected

        results: list[FitAssessment] = []
        for i in range(expected):
            item = next((d for d in data if d.get("job_index") == i), None)
            if item is None:
                results.append(_FALLBACK)
                continue
            try:
                fit_level = FitLevel(item["fit_level"])
                fit_score = max(0.0, min(1.0, float(item["fit_score"])))
                reasoning = str(item.get("reasoning", ""))
                results.append(
                    FitAssessment(fit_level=fit_level, fit_score=fit_score, reasoning=reasoning)
                )
            except Exception as exc:
                logger.warning("Bad assessment for job %d: %s", i, exc)
                results.append(_FALLBACK)

        return results
