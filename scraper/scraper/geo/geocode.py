"""Nominatim (OpenStreetMap) geocoding for listings that don't publish coordinates.

The public instance allows at most 1 request/second and asks for an
identifying User-Agent (set GEOCODER_EMAIL); results are cached on disk so
repeated runs don't re-query. Point NOMINATIM_URL at your own instance for
bulk use.
"""

import os
import re
import threading
import time

import httpx

from .cache import DiskCache
from .overpass import user_agent

_lock = threading.Lock()
_last_call = 0.0


def _base_url() -> str:
    return os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org").rstrip("/")


def _throttled_get(params: dict) -> list[dict]:
    global _last_call
    with _lock:
        wait = 1.05 - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            resp = httpx.get(
                f"{_base_url()}/search",
                params={**params, "format": "jsonv2", "limit": 1, "countrycodes": "ca"},
                headers={"User-Agent": user_agent(), "Accept-Language": "fr-CA,fr"},
                timeout=20,
            )
        finally:
            _last_call = time.monotonic()
    resp.raise_for_status()
    return resp.json()


def clean_street(street: str | None) -> str | None:
    """Drops unit numbers and placeholders Nominatim can't use: '401-962 rue X' -> '962 rue X'."""
    if not street:
        return None
    s = street.strip().lstrip(".,- ")
    s = re.sub(r"\b(app\.?|apt\.?|appartement|unit|suite|#)\s*\w+", "", s, flags=re.I)
    s = re.sub(r"^\d+[A-Za-z]?\s*-\s*(\d+)", r"\1", s)  # "401-962 rue" -> "962 rue"
    s = re.sub(r"\s*,\s*,", ",", s)
    return re.sub(r"\s+", " ", s).strip(" ,") or None


def geocode(
    *,
    street: str | None,
    city: str | None,
    postal_code: str | None,
    cache: DiskCache,
) -> tuple[float, float, str] | None:
    """Returns (lat, lon, precision) using the most specific query that resolves.

    precision is one of "geocoded_address", "geocoded_postal_code", "geocoded_city".
    """
    street = clean_street(street)
    attempts: list[tuple[str, dict]] = []
    if street and (city or postal_code):
        attempts.append(("geocoded_address", {"street": street, "city": city or "", "postalcode": postal_code or "", "state": "Québec"}))
        attempts.append(("geocoded_address", {"q": ", ".join(p for p in (street, city, postal_code, "Québec") if p)}))
    if postal_code:
        attempts.append(("geocoded_postal_code", {"postalcode": postal_code, "country": "Canada"}))
    if city:
        attempts.append(("geocoded_city", {"city": city, "state": "Québec", "country": "Canada"}))

    for precision, params in attempts:
        params = {k: v for k, v in params.items() if v}
        key = repr(sorted(params.items()))
        cached = cache.get("nominatim", key)
        if cached is None:
            try:
                cached = _throttled_get(params)
            except httpx.HTTPError:
                continue
            cache.set("nominatim", key, cached)
        if cached:
            hit = cached[0]
            return float(hit["lat"]), float(hit["lon"]), precision
    return None
