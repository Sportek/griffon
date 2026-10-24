"""Points of interest around a location, from OpenStreetMap (Overpass API)."""

import hashlib
import math
import re

from . import overpass
from .cache import DiskCache
from .config import POI_CATEGORIES
from .walk import haversine_m

_POI_TTL_S = 30 * 24 * 3600  # shops don't move often; refresh monthly


# POIs are fetched per grid tile (plus a buffer of the search radius) rather than per
# listing, so every listing in the same ~1 km tile reuses one cached Overpass call.
_TILE_DEG = 0.01
_RADIUS_BUCKET_M = 250


def _build_query(bbox: tuple[float, float, float, float], categories: list[str], server_timeout_s: int = 90) -> str:
    # Merge filters per OSM key so the query has one clause per key.
    by_key: dict[str, set[str]] = {}
    for cat in categories:
        for key, values in POI_CATEGORIES[cat]:
            by_key.setdefault(key, set()).update(values.split("|"))
    s, w, n, e = bbox
    clauses = "".join(
        f'nwr["{key}"~"^({"|".join(sorted(values))})$"]({s:.5f},{w:.5f},{n:.5f},{e:.5f});'
        for key, values in sorted(by_key.items())
    )
    return f"[out:json][timeout:{server_timeout_s}];({clauses});out center tags;"


def _tile_bbox(lat: float, lon: float, buffer_m: float) -> tuple[str, tuple[float, float, float, float]]:
    ti, tj = math.floor(lat / _TILE_DEG), math.floor(lon / _TILE_DEG)
    dlat = buffer_m / 111_320
    dlon = buffer_m / (111_320 * math.cos(math.radians(lat)))
    s, w = ti * _TILE_DEG - dlat, tj * _TILE_DEG - dlon
    n, e = (ti + 1) * _TILE_DEG + dlat, (tj + 1) * _TILE_DEG + dlon
    return f"{ti},{tj}", (s, w, n, e)


def _categories_of(tags: dict, categories: list[str]) -> list[str]:
    out = []
    for cat in categories:
        for key, values in POI_CATEGORIES[cat]:
            if key in tags and re.fullmatch(values, tags[key]):
                out.append(cat)
                break
    return out


def _slim(result: dict) -> list[dict]:
    return [
        {
            "type": e["type"],
            "id": e["id"],
            "lat": e.get("lat") or (e.get("center") or {}).get("lat"),
            "lon": e.get("lon") or (e.get("center") or {}).get("lon"),
            "tags": e.get("tags", {}),
        }
        for e in result.get("elements", [])
    ]


def _cache_key(tile_key: str, buffer_m: int, categories: list[str]) -> str:
    cats_key = hashlib.sha1(",".join(sorted(categories)).encode()).hexdigest()[:10]
    return f"{tile_key}|{buffer_m}|{cats_key}"


def _buffer_for(radius_m: float) -> int:
    return math.ceil(radius_m / _RADIUS_BUCKET_M) * _RADIUS_BUCKET_M


def prefetch_area(
    bbox: tuple[float, float, float, float], *, radius_m: float, categories: list[str], cache: DiskCache
) -> int:
    """Fills the tile cache for every tile in bbox (south, west, north, east) with ONE Overpass query.

    Much faster than per-tile queries against the public servers when enriching
    thousands of listings in one city. Returns the number of tiles cached.
    """
    buffer_m = _buffer_for(radius_m)
    s, w, n, e = bbox
    mid_lat = (s + n) / 2
    dlat = buffer_m / 111_320
    dlon = buffer_m / (111_320 * math.cos(math.radians(mid_lat)))
    elements = _slim(overpass.query(_build_query((s - dlat, w - dlon, n + dlat, e + dlon), categories, server_timeout_s=540), timeout_s=600))

    tiles: dict[str, tuple[tuple[float, float, float, float], list[dict]]] = {}
    for ti in range(math.floor(s / _TILE_DEG), math.floor(n / _TILE_DEG) + 1):
        for tj in range(math.floor(w / _TILE_DEG), math.floor(e / _TILE_DEG) + 1):
            key, tb = _tile_bbox((ti + 0.5) * _TILE_DEG, (tj + 0.5) * _TILE_DEG, buffer_m)
            tiles[key] = (tb, [])
    for el in elements:
        if el["lat"] is None or el["lon"] is None:
            continue
        ti, tj = math.floor(el["lat"] / _TILE_DEG), math.floor(el["lon"] / _TILE_DEG)
        # An element belongs to its own tile and to neighbours whose buffer reaches it.
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                entry = tiles.get(f"{ti + di},{tj + dj}")
                if entry:
                    (ts, tw, tn, te), bucket = entry
                    if ts <= el["lat"] <= tn and tw <= el["lon"] <= te:
                        bucket.append(el)
    for key, (_, bucket) in tiles.items():
        cache.set("overpass_poi_tile", _cache_key(key, buffer_m, categories), bucket)
    return len(tiles)


def fetch_places(
    lat: float, lon: float, *, radius_m: float, categories: list[str], cache: DiskCache
) -> list[dict]:
    """Returns [{category, kind, name, brand, latitude, longitude, osm_id}] within radius_m (straight line).

    Results are cached per tile; the radius is rounded up to a 250 m bucket for the
    tile buffer, so changing --walk-minutes slightly still reuses the cache.
    """
    unknown = [c for c in categories if c not in POI_CATEGORIES]
    if unknown:
        raise ValueError(f"unknown POI categories: {unknown}; known: {sorted(POI_CATEGORIES)}")

    buffer_m = _buffer_for(radius_m)
    tile_key, bbox = _tile_bbox(lat, lon, buffer_m)
    cache_key = _cache_key(tile_key, buffer_m, categories)
    elements = cache.get("overpass_poi_tile", cache_key, ttl_s=_POI_TTL_S)
    if elements is None:
        elements = _slim(overpass.query(_build_query(bbox, categories), timeout_s=180))
        cache.set("overpass_poi_tile", cache_key, elements)

    places = []
    for e in elements:
        if e["lat"] is None or e["lon"] is None:
            continue
        if haversine_m(lat, lon, e["lat"], e["lon"]) > radius_m:
            continue
        tags = e["tags"]
        for cat in _categories_of(tags, categories):
            kind_key = next(k for k, _ in POI_CATEGORIES[cat] if k in tags)
            places.append(
                {
                    "category": cat,
                    "kind": tags.get(kind_key),
                    "name": tags.get("name") or tags.get("brand") or tags.get("operator"),
                    "brand": tags.get("brand"),
                    "latitude": e["lat"],
                    "longitude": e["lon"],
                    "osm_id": f"{e['type']}/{e['id']}",
                }
            )
    return places
