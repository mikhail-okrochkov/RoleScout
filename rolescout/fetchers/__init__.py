from __future__ import annotations

from rolescout.fetchers.adzuna import AdzunaFetcher
from rolescout.fetchers.base import BaseFetcher
from rolescout.fetchers.jsearch import JSearchFetcher
from rolescout.fetchers.remotive import RemotiveFetcher
from rolescout.fetchers.themuse import TheMuseFetcher


def get_all_fetchers() -> list[BaseFetcher]:
    return [RemotiveFetcher(), TheMuseFetcher(), AdzunaFetcher(), JSearchFetcher()]
