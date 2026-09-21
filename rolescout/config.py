from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Anthropic
    anthropic_api_key: str = ""

    # JSearch via RapidAPI (optional — fetcher skipped if absent)
    rapidapi_key: str | None = None

    # Adzuna (optional — fetcher skipped if absent)
    adzuna_app_id: str | None = None
    adzuna_api_key: str | None = None

    # Job search parameters
    target_role: str = "Software Engineer"  # fallback when target_roles is empty
    target_roles: list[str] = []            # multi-role search; overrides target_role when set
    target_location: str = "Remote"         # used as API search query only
    target_salary_min: int | None = None
    target_salary_max: int | None = None

    # Location scoring tiers (used for ranking, not API queries)
    # Tier 1 — full score: remote jobs OR jobs in these cities
    preferred_locations: list[str] = []
    # Tier 2 — partial score: acceptable but not ideal (e.g. requires substantial comp)
    acceptable_locations: list[str] = []

    # Pre-score filters — jobs matching any keyword (title or description) are dropped
    exclude_keywords: list[str] = []

    # Distance radius (miles) around each preferred/acceptable location
    location_radius_miles: float = 50.0

    # Storage
    db_path: Path = Path("rolescout.db")

    # Per-source pagination limits
    adzuna_pages: int = 3          # pages × 50 results each
    jsearch_pages_per_role: int = 1  # keep at 1 for RapidAPI free tier (10 req/day)

    # Scoring
    batch_size: int = 10
    resume_path: Path = Path("resume.md")


settings = Settings()
