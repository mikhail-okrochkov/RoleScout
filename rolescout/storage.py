from __future__ import annotations

from datetime import datetime

from sqlmodel import Session, SQLModel, create_engine, select

from rolescout.config import settings
from rolescout.models import FitLevel, ScoredJob

_engine = None


def get_engine():  # type: ignore[return]
    global _engine
    if _engine is None:
        _engine = create_engine(f"sqlite:///{settings.db_path}", echo=False)
    return _engine


def init_db() -> None:
    from sqlalchemy import text

    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    # Add columns introduced after initial schema — safe to run repeatedly
    new_columns = [
        "ALTER TABLE scored_jobs ADD COLUMN scorer TEXT NOT NULL DEFAULT 'unknown'",
        "ALTER TABLE scored_jobs ADD COLUMN score_skills REAL",
        "ALTER TABLE scored_jobs ADD COLUMN score_seniority REAL",
        "ALTER TABLE scored_jobs ADD COLUMN score_domain REAL",
        "ALTER TABLE scored_jobs ADD COLUMN score_responsibilities REAL",
        "ALTER TABLE scored_jobs ADD COLUMN seniority_direction TEXT",
        "ALTER TABLE scored_jobs ADD COLUMN scorer_details TEXT",
    ]
    with engine.connect() as conn:
        for stmt in new_columns:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists


def save_jobs(jobs: list[ScoredJob]) -> None:
    engine = get_engine()
    with Session(engine) as session:
        for job in jobs:
            existing = session.exec(
                select(ScoredJob).where(ScoredJob.id == job.id)
            ).first()
            if existing:
                for field in ScoredJob.model_fields:
                    if field != "pk":
                        setattr(existing, field, getattr(job, field))
                session.add(existing)
            else:
                session.add(job)
        session.commit()


def load_jobs(
    fit_levels: list[FitLevel] | None = None,
    sources: list[str] | None = None,
    remote_only: bool = False,
    min_location_score: float | None = None,
    min_date: datetime | None = None,
    max_date: datetime | None = None,
    limit: int = 500,
) -> list[ScoredJob]:
    engine = get_engine()
    with Session(engine) as session:
        stmt = select(ScoredJob).order_by(ScoredJob.composite_score.desc())  # type: ignore[arg-type]
        if fit_levels:
            stmt = stmt.where(ScoredJob.fit_level.in_(fit_levels))  # type: ignore[attr-defined]
        if sources:
            stmt = stmt.where(ScoredJob.source.in_(sources))  # type: ignore[attr-defined]
        if remote_only:
            stmt = stmt.where(ScoredJob.remote == True)  # noqa: E712
        if min_location_score is not None:
            stmt = stmt.where(ScoredJob.location_score >= min_location_score)  # type: ignore[operator]
        if min_date:
            stmt = stmt.where(ScoredJob.posted_at >= min_date)  # type: ignore[operator]
        if max_date:
            stmt = stmt.where(ScoredJob.posted_at <= max_date)  # type: ignore[operator]
        stmt = stmt.limit(limit)
        return list(session.exec(stmt).all())


def get_sources() -> list[str]:
    engine = get_engine()
    with Session(engine) as session:
        results = session.exec(select(ScoredJob.source).distinct()).all()
        return sorted(set(results))
