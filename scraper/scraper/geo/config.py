from dataclasses import dataclass, field
from typing import Literal

# name -> list of (OSM key, regex on the value). A place lands in every category it matches.
POI_CATEGORIES: dict[str, list[tuple[str, str]]] = {
    "grocery": [("shop", "supermarket|greengrocer|grocery|wholesale")],
    "convenience": [("shop", "convenience")],  # dépanneurs
    "pharmacy": [("amenity", "pharmacy"), ("shop", "chemist")],
    "bakery": [("shop", "bakery|pastry")],
    "butcher": [("shop", "butcher|seafood|cheese|deli")],
    "alcohol": [("shop", "alcohol|wine")],  # SAQ
    "bank": [("amenity", "bank|atm")],
    "laundry": [("shop", "laundry|dry_cleaning")],
    "hardware": [("shop", "hardware|doityourself")],
    "clinic": [("amenity", "clinic|doctors"), ("healthcare", "clinic|doctor|centre")],
    "hospital": [("amenity", "hospital")],
    "dentist": [("amenity", "dentist")],
    "post_office": [("amenity", "post_office")],
    "school": [("amenity", "school")],
    "daycare": [("amenity", "childcare|kindergarten")],
    "park": [("leisure", "park")],
    "gym": [("leisure", "fitness_centre")],
    "library": [("amenity", "library")],
    "bus_stop": [("highway", "bus_stop")],
    "bike_share": [("amenity", "bicycle_rental")],  # BIXI
    "restaurant": [("amenity", "restaurant|fast_food")],
    "cafe": [("amenity", "cafe")],
}

# What "essentials" means by default; restaurants/cafes are opt-in.
DEFAULT_CATEGORIES = [
    "grocery", "convenience", "pharmacy", "bakery", "butcher", "alcohol", "bank", "laundry",
    "hardware", "clinic", "hospital", "post_office", "school", "daycare", "park", "gym",
    "library", "bus_stop", "bike_share",
]


# (south, west, north, east) for --prefetch-pois.
PREFETCH_AREAS: dict[str, tuple[float, float, float, float]] = {
    "montreal": (45.40, -73.98, 45.71, -73.47),
    "laval": (45.51, -73.89, 45.70, -73.52),
    "longueuil": (45.42, -73.56, 45.62, -73.36),
    "quebec-city": (46.72, -71.48, 46.94, -71.13),
    "gatineau": (45.40, -75.95, 45.56, -75.50),
    "sherbrooke": (45.33, -72.03, 45.48, -71.80),
}


@dataclass
class ProximityConfig:
    max_walk_minutes: float = 15.0
    walk_speed_kmh: float = 4.8
    # Street networks make walks longer than the crow flies; ~1.3 is typical for
    # Montreal's grid. Only used by the "estimate" routing mode.
    detour_factor: float = 1.3
    routing: Literal["estimate", "osrm"] = "estimate"
    osrm_url: str = "https://routing.openstreetmap.de/routed-foot"
    categories: list[str] = field(default_factory=lambda: list(DEFAULT_CATEGORIES))
    max_places_per_category: int = 10
    # Report the nearest metro/REM station only if it's within this straight-line distance;
    # beyond that (Quebec City, Sherbrooke, ...) it's null.
    max_station_km: float = 5.0
    geocode_missing: bool = True
    cache_path: str = ".cache/geo.sqlite"

    @property
    def meters_per_minute(self) -> float:
        return self.walk_speed_kmh * 1000 / 60

    @property
    def max_walk_m(self) -> float:
        return self.max_walk_minutes * self.meters_per_minute
