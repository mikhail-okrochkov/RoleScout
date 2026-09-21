from __future__ import annotations

import logging
from datetime import datetime

import httpx

from rolescout.config import settings
from rolescout.fetchers.base import BaseFetcher
from rolescout.models import Job

logger = logging.getLogger(__name__)

_LEVEL_PREFIXES = ("staff ", "principal ", "lead ", "senior ", "junior ", "head of ")


def _strip_prefix(role: str) -> str:
    """Remove seniority prefix — Adzuna's index uses 'Data Scientist' not 'Staff Data Scientist'."""
    lower = role.lower()
    for prefix in _LEVEL_PREFIXES:
        if lower.startswith(prefix):
            return role[len(prefix):]
    return role


class AdzunaFetcher(BaseFetcher):
    source_name = "adzuna"

    def fetch(self) -> list[Job]:
        if not settings.adzuna_app_id or not settings.adzuna_api_key:
            logger.debug("Adzuna skipped: ADZUNA_APP_ID/ADZUNA_API_KEY not set")
            return []

        all_jobs: list[Job] = []
        for role in self.roles:
            all_jobs.extend(self._fetch_role(role))
        return self._dedup(all_jobs)

    def _fetch_role(self, role: str) -> list[Job]:
        search_role = _strip_prefix(role)

        # Adzuna's `where` param expects a real city/region — "Remote" returns 0 results
        base_params: dict[str, str | int] = {
            "app_id": settings.adzuna_app_id,  # type: ignore[assignment]
            "app_key": settings.adzuna_api_key,  # type: ignore[assignment]
            "results_per_page": 50,
            "what": search_role,
            "content-type": "application/json",
        }
        if settings.target_location.lower() not in ("remote", ""):
            base_params["where"] = settings.target_location

        jobs: list[Job] = []
        for page in range(1, settings.adzuna_pages + 1):
            try:
                resp = httpx.get(
                    f"https://api.adzuna.com/v1/api/jobs/us/search/{page}",
                    params=base_params,
                    timeout=15,
                )
                resp.raise_for_status()
                results = resp.json().get("results", [])
            except Exception as exc:
                logger.warning("Adzuna fetch failed (role=%r, page=%d): %s", role, page, exc)
                break

            if not results:
                break

            for item in results:
                location_name = item.get("location", {}).get("display_name", "")
                description = item.get("description", "")
                is_remote = "remote" in location_name.lower() or "remote" in description.lower()

                try:
                    posted_at = datetime.fromisoformat(item["created"])
                except (KeyError, ValueError):
                    posted_at = None

                jobs.append(
                    Job(
                        id=f"adzuna-{item['id']}",
                        title=item.get("title", ""),
                        company=item.get("company", {}).get("display_name", ""),
                        location=location_name,
                        description=description,
                        url=item.get("redirect_url", ""),
                        source=self.source_name,
                        posted_at=posted_at,
                        salary_min=int(item["salary_min"]) if item.get("salary_min") else None,
                        salary_max=int(item["salary_max"]) if item.get("salary_max") else None,
                        remote=is_remote,
                    )
                )

        return jobs
