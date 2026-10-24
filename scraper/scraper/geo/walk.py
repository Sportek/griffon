import math

from .config import ProximityConfig

_EARTH_RADIUS_M = 6_371_000


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


def estimate_walk_m(straight_m: float, config: ProximityConfig) -> float:
    return straight_m * config.detour_factor


def walk_minutes(walk_m: float, config: ProximityConfig) -> float:
    return round(walk_m / config.meters_per_minute, 1)
