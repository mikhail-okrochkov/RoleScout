from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from rolescout.models import FitLevel, Job
from rolescout.scorer import JobScorer


def _make_scorer(tmp_path) -> JobScorer:  # type: ignore[return]
    resume = tmp_path / "resume.md"
    resume.write_text("# Test Resume\nPython, FastAPI, 5 years experience.")
    with patch("rolescout.scorer.settings") as mock_settings:
        mock_settings.anthropic_api_key = "test-key"
        mock_settings.resume_path = resume
        mock_settings.batch_size = 5
        scorer = JobScorer.__new__(JobScorer)
        scorer._client = MagicMock()
        scorer._resume = resume.read_text()
    return scorer


def _sample_job(i: int = 0) -> Job:
    return Job(
        id=f"test-{i}", title="Python Engineer", company="Co",
        location="Remote", description="FastAPI and Python required.",
        url="https://example.com", source="test",
    )


def test_parse_valid_json(tmp_path) -> None:  # type: ignore[no-untyped-def]
    scorer = _make_scorer(tmp_path)
    raw = json.dumps([
        {"job_index": 0, "fit_level": "strong", "fit_score": 0.9, "reasoning": "Great match."},
        {"job_index": 1, "fit_level": "low", "fit_score": 0.1, "reasoning": "No match."},
    ])
    results = scorer._parse_response(raw, 2)
    assert results[0].fit_level == FitLevel.STRONG
    assert results[0].fit_score == pytest.approx(0.9)
    assert results[1].fit_level == FitLevel.LOW


def test_parse_invalid_json_returns_fallback(tmp_path) -> None:  # type: ignore[no-untyped-def]
    scorer = _make_scorer(tmp_path)
    results = scorer._parse_response("not json at all }{", 3)
    assert len(results) == 3
    assert all(r.fit_level == FitLevel.LOW for r in results)


def test_parse_clamps_fit_score(tmp_path) -> None:  # type: ignore[no-untyped-def]
    scorer = _make_scorer(tmp_path)
    raw = json.dumps([
        {"job_index": 0, "fit_level": "strong", "fit_score": 2.5, "reasoning": "Over 1."},
    ])
    results = scorer._parse_response(raw, 1)
    assert results[0].fit_score == pytest.approx(1.0)


def test_system_prompt_has_cache_control(tmp_path) -> None:  # type: ignore[no-untyped-def]
    scorer = _make_scorer(tmp_path)
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps([
        {"job_index": 0, "fit_level": "medium", "fit_score": 0.5, "reasoning": "OK."},
    ]))]
    scorer._client.messages.create.return_value = mock_response

    scorer._score_batch([_sample_job()])

    call_kwargs = scorer._client.messages.create.call_args[1]
    system_blocks = call_kwargs["system"]
    resume_block = system_blocks[1]
    assert resume_block.get("cache_control") == {"type": "ephemeral"}
