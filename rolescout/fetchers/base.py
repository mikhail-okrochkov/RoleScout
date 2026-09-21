from __future__ import annotations

import abc

from rolescout.config import settings
from rolescout.models import Job


class BaseFetcher(abc.ABC):
    source_name: str

    @property
    def roles(self) -> list[str]:
        """All role titles to search. Falls back to single target_role if list not set."""
        return settings.target_roles if settings.target_roles else [settings.target_role]

    @staticmethod
    def _dedup(jobs: list[Job]) -> list[Job]:
        seen: set[str] = set()
        result: list[Job] = []
        for job in jobs:
            if job.id not in seen:
                seen.add(job.id)
                result.append(job)
        return result

    @abc.abstractmethod
    def fetch(self) -> list[Job]:
        """Fetch jobs from this source. Returns [] on any error."""
        ...
