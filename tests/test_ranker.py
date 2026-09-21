from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from rolescout.models import FitLevel, Job
from rolescout.ranker import _compensation_score, _location_score, _recency_score, compute_scores
from rolescout.scorer import FitAssessment


def _job(**kwargs) -> Job:  # type: ignore[return]
    defaults: dict = dict(
        id="j1", title="T", company="C", location="Remote",
        description="D", url="U", source="s", remote=True,
    )
    defaults.update(kwargs)
    return Job(**defaults)


# ── recency ──────────────────────────────────────────────────────────────────

def test_recency_today() -> None:
    score = _recency_score(datetime.now(tz=UTC))
    assert score == pytest.approx(1.0, abs=0.05)


def test_recency_30_days() -> None:
    old = datetime.now(tz=UTC) - timedelta(days=30)
    assert _recency_score(old) == pytest.approx(0.0)


def test_recency_none() -> None:
    assert _recency_score(None) == 0.5


def test_recency_15_days() -> None:
    mid = datetime.now(tz=UTC) - timedelta(days=15)
    assert _recency_score(mid) == pytest.approx(0.5, abs=0.05)


# ── compensation ─────────────────────────────────────────────────────────────

def test_comp_both_none() -> None:
    assert _compensation_score(None, None) == 0.5


def test_comp_no_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rolescout.ranker.settings.target_salary_min", None)
    monkeypatch.setattr("rolescout.ranker.settings.target_salary_max", None)
    assert _compensation_score(100_000, 150_000) == 0.5


def test_comp_full_overlap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rolescout.ranker.settings.target_salary_min", 130_000)
    monkeypatch.setattr("rolescout.ranker.settings.target_salary_max", 160_000)
    assert _compensation_score(120_000, 180_000) == 1.0


def test_comp_partial_overlap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rolescout.ranker.settings.target_salary_min", 150_000)
    monkeypatch.setattr("rolescout.ranker.settings.target_salary_max", 180_000)
    assert _compensation_score(130_000, 160_000) == 0.7


def test_comp_no_overlap_below(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rolescout.ranker.settings.target_salary_min", 150_000)
    monkeypatch.setattr("rolescout.ranker.settings.target_salary_max", 200_000)
    assert _compensation_score(80_000, 110_000) == 0.0


# ── location ─────────────────────────────────────────────────────────────────

def test_location_remote_always_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rolescout.ranker.settings.preferred_locations", ["Seattle"])
    monkeypatch.setattr("rolescout.ranker.settings.acceptable_locations", [])
    assert _location_score(True, "New York") == 1.0


def test_location_preferred_city_onsite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rolescout.ranker.settings.preferred_locations", ["Seattle", "San Francisco"])
    monkeypatch.setattr("rolescout.ranker.settings.acceptable_locations", [])
    assert _location_score(False, "Seattle, WA") == 1.0


def test_location_acceptable_city_scores_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rolescout.ranker.settings.preferred_locations", ["Seattle"])
    monkeypatch.setattr("rolescout.ranker.settings.acceptable_locations", ["Boston"])
    assert _location_score(False, "Boston, MA") == 0.6


def test_location_unlisted_city_scores_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rolescout.ranker.settings.preferred_locations", ["Seattle"])
    monkeypatch.setattr("rolescout.ranker.settings.acceptable_locations", ["Boston"])
    assert _location_score(False, "Chicago, IL") == 0.0


def test_location_fallback_when_no_tiers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rolescout.ranker.settings.preferred_locations", [])
    monkeypatch.setattr("rolescout.ranker.settings.acceptable_locations", [])
    monkeypatch.setattr("rolescout.ranker.settings.target_location", "Seattle")
    assert _location_score(False, "Seattle, WA") == 1.0


# ── composite ────────────────────────────────────────────────────────────────

def test_composite_weights(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rolescout.ranker.settings.preferred_locations", ["Seattle"])
    monkeypatch.setattr("rolescout.ranker.settings.acceptable_locations", [])
    monkeypatch.setattr("rolescout.ranker.settings.target_salary_min", None)
    monkeypatch.setattr("rolescout.ranker.settings.target_salary_max", None)

    job = _job(posted_at=datetime.now(tz=UTC), remote=True)
    assessment = FitAssessment(fit_level=FitLevel.STRONG, fit_score=1.0, reasoning="great")
    scores = compute_scores(job, assessment)

    expected = 0.50 * 1.0 + 0.30 * 1.0 + 0.10 * 0.5 + 0.10 * 1.0
    assert scores["composite_score"] == pytest.approx(expected, abs=0.01)
