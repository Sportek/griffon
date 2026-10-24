"""Montreal metro (STM) and REM stations, bundled offline.

Data comes from OpenStreetMap via scripts/build_transit_stations.py.
"""

import json
from functools import lru_cache
from pathlib import Path

from .walk import haversine_m

_DATA = Path(__file__).parent / "data" / "transit_stations.json"


@lru_cache(maxsize=1)
def stations() -> list[dict]:
    return json.loads(_DATA.read_text(encoding="utf-8"))


def nearest_stations(lat: float, lon: float, *, max_m: float) -> list[tuple[dict, float]]:
    """All stations within max_m straight-line metres, nearest first, as (station, distance_m)."""
    out = []
    for s in stations():
        d = haversine_m(lat, lon, s["latitude"], s["longitude"])
        if d <= max_m:
            out.append((s, d))
    out.sort(key=lambda x: x[1])
    return out
