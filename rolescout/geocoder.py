from __future__ import annotations

import json
import logging
import time
from math import asin, cos, radians, sin, sqrt

import httpx

from rolescout.config import settings as _settings

logger = logging.getLogger(__name__)

_CACHE_PATH = _settings.db_path.parent / "geocode_cache.json"
_cache: dict[str, tuple[float, float] | None] = {}
_cache_dirty = False
_cache_loaded = False
_last_request: float = 0.0


def _load() -> None:
    global _cache_loaded
    if _cache_loaded:
        return
    _cache_loaded = True
    if not _CACHE_PATH.exists():
        return
    try:
        raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        for k, v in raw.items():
            _cache[k] = (float(v[0]), float(v[1])) if v else None
    except Exception as exc:
        logger.warning("Could not load geocode cache: %s", exc)


def _save() -> None:
    global _cache_dirty
    if not _cache_dirty:
        return
    try:
        out = {k: list(v) if v else None for k, v in _cache.items()}
        _CACHE_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
        _cache_dirty = False
    except Exception as exc:
        logger.warning("Could not save geocode cache: %s", exc)


def geocode(location: str) -> tuple[float, float] | None:
    """Return (lat, lon) for a location string, using a local cache + Nominatim."""
    global _last_request, _cache_dirty
    _load()

    key = location.strip().lower()
    if key in _cache:
        return _cache[key]

    # Nominatim requires ≤ 1 req/sec
    gap = 1.05 - (time.monotonic() - _last_request)
    if gap > 0:
        time.sleep(gap)

    result: tuple[float, float] | None = None
    try:
        resp = httpx.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": location, "format": "json", "limit": 1},
            headers={"User-Agent": "RoleScout/1.0 (open-source job matcher)"},
            timeout=10,
        )
        _last_request = time.monotonic()
        data = resp.json()
        if data:
            result = (float(data[0]["lat"]), float(data[0]["lon"]))
    except Exception as exc:
        logger.warning("Geocoding failed for %r: %s", location, exc)
        _last_request = time.monotonic()

    _cache[key] = result
    _cache_dirty = True
    _save()
    return result


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 3958.8 * 2 * asin(sqrt(a))


def location_tier(
    job_location: str,
    preferred: list[str],
    acceptable: list[str],
    radius_miles: float,
) -> str | None:
    """
    Returns 'preferred', 'acceptable', or None based on geocoded distance.
    Falls back gracefully if geocoding fails for either side.
    """
    job_coords = geocode(job_location)
    if job_coords is None:
        return None

    for target in preferred:
        tc = geocode(target)
        if tc and haversine_miles(*job_coords, *tc) <= radius_miles:
            return "preferred"

    for target in acceptable:
        tc = geocode(target)
        if tc and haversine_miles(*job_coords, *tc) <= radius_miles:
            return "acceptable"

    return None
