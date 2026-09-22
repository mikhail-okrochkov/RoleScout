from __future__ import annotations

from pathlib import Path

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        yaml_file="config.yaml",
        yaml_file_encoding="utf-8",
        case_sensitive=False,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Priority (highest → lowest): env vars → .env → config.yaml → defaults
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
        )

    # ── Secrets (live in .env) ────────────────────────────────────────────────
    anthropic_api_key: str = ""
    typesafe_api_key: str | None = None
    rapidapi_key: str | None = None
    adzuna_app_id: str | None = None
    adzuna_api_key: str | None = None

    db_path: Path = Path("rolescout.db")
    resume_path: Path = Path("resume.md")

    # ── Preferences (live in config.yaml) ────────────────────────────────────
    target_role: str = "Software Engineer"  # fallback when target_roles is empty
    target_roles: list[str] = []
    target_location: str = "Remote"
    target_salary_min: int | None = None
    target_salary_max: int | None = None

    preferred_locations: list[str] = []
    acceptable_locations: list[str] = []
    location_radius_miles: float = 50.0

    exclude_keywords: list[str] = []

    adzuna_pages: int = 3
    jsearch_pages_per_role: int = 1
    batch_size: int = 10


settings = Settings()
