from __future__ import annotations

import logging
from datetime import datetime

import httpx

from rolescout.config import settings
from rolescout.fetchers.base import BaseFetcher
from rolescout.models import Job

logger = logging.getLogger(__name__)

_BASE_URL = "https://jsearch.p.rapidapi.com/search"


class JSearchFetcher(BaseFetcher):
    """Aggregates LinkedIn, Indeed, Glassdoor, and ZipRecruiter via RapidAPI JSearch."""

    source_name = "jsearch"

    def fetch(self) -> list[Job]:
        if not settings.rapidapi_key:
            logger.debug("JSearch skipped: RAPIDAPI_KEY not set")
            return []

        all_jobs: list[Job] = []
        for role in self.roles:
            all_jobs.extend(self._fetch_role(role))
        return self._dedup(all_jobs)

    def _fetch_role(self, role: str) -> list[Job]:
        query = f"{role} {settings.target_location}"
        headers = {
            "X-RapidAPI-Key": settings.rapidapi_key,  # type: ignore[arg-type]
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }

        jobs: list[Job] = []
        for page in range(1, settings.jsearch_pages_per_role + 1):
            try:
                resp = httpx.get(
                    _BASE_URL,
                    headers=headers,
                    params={
                        "query": query,
                        "page": str(page),
                        "num_pages": "1",
                        "date_posted": "week",
                    },
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning("JSearch fetch failed (role=%r, page=%d): %s", role, page, exc)
                break

            results = data.get("data", [])
            if not results:
                break

            for item in results:
                location_parts = filter(
                    None,
                    [item.get("job_city"), item.get("job_state"), item.get("job_country")],
                )
                location = ", ".join(location_parts) or "Unknown"

                try:
                    posted_at = datetime.fromisoformat(
                        item["job_posted_at_datetime_utc"].replace("Z", "+00:00")
                    )
                except (KeyError, ValueError, AttributeError):
                    posted_at = None

                raw_skills = item.get("job_required_skills") or []
                tags = [s for s in raw_skills if isinstance(s, str)]

                jobs.append(
                    Job(
                        id=f"jsearch-{item['job_id']}",
                        title=item.get("job_title", ""),
                        company=item.get("employer_name", ""),
                        location=location,
                        description=item.get("job_description", ""),
                        url=item.get("job_apply_link", ""),
                        source=self.source_name,
                        posted_at=posted_at,
                        salary_min=int(item["job_min_salary"])
                        if item.get("job_min_salary")
                        else None,
                        salary_max=int(item["job_max_salary"])
                        if item.get("job_max_salary")
                        else None,
                        remote=bool(item.get("job_is_remote", False)),
                        tags=tags,
                    )
                )

        return jobs
