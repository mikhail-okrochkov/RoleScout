from __future__ import annotations

import logging
import re
from datetime import datetime

import httpx

from rolescout.fetchers.base import BaseFetcher
from rolescout.models import Job

logger = logging.getLogger(__name__)

_HTML_TAG = re.compile(r"<[^>]+>")
_SALARY_NUM = re.compile(r"\d[\d,]*")


def _strip_html(html: str) -> str:
    return _HTML_TAG.sub(" ", html).strip()


def _parse_salary(salary_str: str) -> tuple[int | None, int | None]:
    nums = [int(n.replace(",", "")) for n in _SALARY_NUM.findall(salary_str)]
    if not nums:
        return None, None
    if len(nums) == 1:
        return nums[0], None
    return nums[0], nums[-1]


class RemotiveFetcher(BaseFetcher):
    source_name = "remotive"

    def fetch(self) -> list[Job]:
        all_jobs: list[Job] = []
        for role in self.roles:
            all_jobs.extend(self._fetch_role(role))
        return self._dedup(all_jobs)

    def _fetch_role(self, role: str) -> list[Job]:
        try:
            resp = httpx.get(
                "https://remotive.com/api/remote-jobs",
                params={"search": role, "limit": 100},
                timeout=15,
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("Remotive fetch failed (role=%r): %s", role, exc)
            return []

        jobs: list[Job] = []
        for item in resp.json().get("jobs", []):
            salary_min, salary_max = _parse_salary(item.get("salary") or "")
            try:
                posted_at = datetime.fromisoformat(item["publication_date"])
            except (KeyError, ValueError):
                posted_at = None

            jobs.append(
                Job(
                    id=f"remotive-{item['id']}",
                    title=item.get("title", ""),
                    company=item.get("company_name", ""),
                    location=item.get("candidate_required_location", "Remote"),
                    description=_strip_html(item.get("description", "")),
                    url=item.get("url", ""),
                    source=self.source_name,
                    posted_at=posted_at,
                    salary_min=salary_min,
                    salary_max=salary_max,
                    remote=True,
                    tags=item.get("tags", []),
                )
            )
        return jobs
