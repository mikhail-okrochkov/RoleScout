from __future__ import annotations

import logging
import re
from datetime import datetime

import httpx

from rolescout.fetchers.base import BaseFetcher
from rolescout.models import Job

logger = logging.getLogger(__name__)

_HTML_TAG = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    return _HTML_TAG.sub(" ", html).strip()


class TheMuseFetcher(BaseFetcher):
    source_name = "themuse"

    def fetch(self) -> list[Job]:
        all_jobs: list[Job] = []
        for role in self.roles:
            all_jobs.extend(self._fetch_role(role))
        return self._dedup(all_jobs)

    def _fetch_role(self, role: str) -> list[Job]:
        jobs: list[Job] = []
        for page in range(3):
            try:
                resp = httpx.get(
                    "https://www.themuse.com/api/public/jobs",
                    params={"page": page, "descending": "true", "query": role},
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning("The Muse fetch failed (role=%r, page=%d): %s", role, page, exc)
                break

            for item in data.get("results", []):
                locations = [loc.get("name", "") for loc in item.get("locations", [])]
                is_remote = any(
                    kw in loc.lower() for loc in locations for kw in ("remote", "flexible")
                )
                location_str = ", ".join(locations) if locations else "Unknown"

                try:
                    posted_at = datetime.fromisoformat(item["publication_date"])
                except (KeyError, ValueError):
                    posted_at = None

                jobs.append(
                    Job(
                        id=f"themuse-{item['id']}",
                        title=item.get("name", ""),
                        company=item.get("company", {}).get("name", ""),
                        location=location_str,
                        description=_strip_html(item.get("contents", "")),
                        url=item.get("refs", {}).get("landing_page", ""),
                        source=self.source_name,
                        posted_at=posted_at,
                        remote=is_remote,
                    )
                )

            if page >= data.get("page_count", 1) - 1:
                break

        return jobs
