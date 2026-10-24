"""Optional walking distances from an OSRM server with a foot profile.

Default server is the FOSSGIS demo (routing.openstreetmap.de/routed-foot),
which is fine for light use; self-host OSRM with the foot profile for bulk.
Uses the `table` service so one request covers all destinations of a listing.
"""

import httpx

from .cache import DiskCache
from .overpass import user_agent

_MAX_DESTINATIONS = 90


def walking_distances_m(
    origin: tuple[float, float],
    destinations: list[tuple[float, float]],
    *,
    osrm_url: str,
    cache: DiskCache,
) -> list[float | None]:
    """Routed walking distance (m) from origin to each destination; None where unroutable."""
    out: list[float | None] = []
    for start in range(0, len(destinations), _MAX_DESTINATIONS):
        chunk = destinations[start : start + _MAX_DESTINATIONS]
        coords = ";".join(f"{lon:.6f},{lat:.6f}" for lat, lon in [origin, *chunk])
        key = f"{osrm_url}|{coords}"
        cached = cache.get("osrm_table", key)
        if cached is None:
            # FOSSGIS routes every profile under the "driving" path segment; the profile is the server.
            resp = httpx.get(
                f"{osrm_url.rstrip('/')}/table/v1/driving/{coords}",
                params={"sources": "0", "annotations": "distance"},
                headers={"User-Agent": user_agent()},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != "Ok":
                raise RuntimeError(f"OSRM error: {data.get('code')} {data.get('message')}")
            cached = data["distances"][0][1:]
            cache.set("osrm_table", key, cached)
        out.extend(cached)
    return out
