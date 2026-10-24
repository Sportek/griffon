"""Adds location-based info to a Listing: geocoding, nearest metro/REM, nearby essentials."""

from ..models import CategorySummary, Listing, NearbyPlace, NearbyStation, Proximity
from . import geocode as geocoder
from . import poi, routing, transit
from .cache import DiskCache
from .config import ProximityConfig
from .walk import estimate_walk_m, haversine_m, walk_minutes

# A city centroid says nothing about what's walkable from the unit.
_TOO_COARSE = {"geocoded_city"}


class Enricher:
    def __init__(self, config: ProximityConfig | None = None, cache: DiskCache | None = None):
        self.config = config or ProximityConfig()
        self.cache = cache or DiskCache(self.config.cache_path)

    # --- public -----------------------------------------------------------------

    def prefetch(self, bbox: tuple[float, float, float, float]) -> int:
        """Warms the POI cache for a whole area with one Overpass query; returns tiles cached."""
        return poi.prefetch_area(bbox, radius_m=self._search_radius(), categories=self.config.categories, cache=self.cache)

    def enrich(self, listing: Listing) -> Listing:
        """Fills coordinates (if missing) and `proximity` in place; returns the listing.

        Network failures (Overpass/OSRM/Nominatim) leave the affected part empty
        rather than failing the listing.
        """
        if listing.latitude is None or listing.longitude is None:
            if self.config.geocode_missing:
                self._geocode(listing)
        if listing.latitude is None or listing.longitude is None:
            return listing
        if listing.location_precision in _TOO_COARSE:
            return listing

        lat, lon = listing.latitude, listing.longitude
        proximity = Proximity(
            method=self.config.routing,
            walk_speed_kmh=self.config.walk_speed_kmh,
            max_walk_minutes=self.config.max_walk_minutes,
        )
        self._add_transit(proximity, lat, lon)
        try:
            proximity.essentials = self._essentials(lat, lon)
        except Exception as e:  # noqa: BLE001 -- keep the listing, flag the gap
            listing.extra["proximity_error"] = f"essentials: {e}"
        listing.proximity = proximity
        return listing

    # --- steps ------------------------------------------------------------------

    def _geocode(self, listing: Listing) -> None:
        hit = geocoder.geocode(
            street=listing.address,
            city=listing.city,
            postal_code=listing.postal_code,
            cache=self.cache,
        )
        if hit:
            listing.latitude, listing.longitude, listing.location_precision = hit

    def _walk_distances(self, lat: float, lon: float, points: list[tuple[float, float]], straight: list[float]) -> list[float]:
        if self.config.routing == "osrm" and points:
            try:
                routed = routing.walking_distances_m((lat, lon), points, osrm_url=self.config.osrm_url, cache=self.cache)
                return [r if r is not None else estimate_walk_m(s, self.config) for r, s in zip(routed, straight)]
            except Exception:  # noqa: BLE001 -- fall back to the estimate
                pass
        return [estimate_walk_m(s, self.config) for s in straight]

    def _add_transit(self, proximity: Proximity, lat: float, lon: float) -> None:
        candidates = transit.nearest_stations(lat, lon, max_m=self.config.max_station_km * 1000)
        if not candidates:
            return
        # Route only the closest few: straight-line order is a good proxy at this scale.
        candidates = candidates[:8]
        walks = self._walk_distances(
            lat, lon, [(s["latitude"], s["longitude"]) for s, _ in candidates], [d for _, d in candidates]
        )
        stations = sorted(
            (
                NearbyStation(
                    name=s["name"],
                    network=s["network"],
                    lines=s["lines"],
                    latitude=s["latitude"],
                    longitude=s["longitude"],
                    distance_m=round(d),
                    walk_distance_m=round(w),
                    walk_minutes=walk_minutes(w, self.config),
                )
                for (s, d), w in zip(candidates, walks)
            ),
            key=lambda st: st.walk_distance_m,
        )
        proximity.nearest_metro = next((s for s in stations if s.network == "metro"), None)
        proximity.nearest_rem = next((s for s in stations if s.network == "rem"), None)
        proximity.stations_within_walk = [s for s in stations if s.walk_minutes <= self.config.max_walk_minutes]

    def _search_radius(self) -> float:
        # Straight-line search radius: nothing farther can be within the walk limit.
        cfg = self.config
        return cfg.max_walk_m if cfg.routing == "osrm" else cfg.max_walk_m / cfg.detour_factor

    def _essentials(self, lat: float, lon: float) -> dict[str, CategorySummary]:
        cfg = self.config
        raw = poi.fetch_places(lat, lon, radius_m=self._search_radius(), categories=cfg.categories, cache=self.cache)

        straight = [haversine_m(lat, lon, p["latitude"], p["longitude"]) for p in raw]
        # Dedupe coordinates before routing: one place can be in several categories.
        unique_points = list(dict.fromkeys((p["latitude"], p["longitude"]) for p in raw))
        unique_straight = [haversine_m(lat, lon, a, b) for a, b in unique_points]
        unique_walk = dict(zip(unique_points, self._walk_distances(lat, lon, unique_points, unique_straight)))

        by_cat: dict[str, list[NearbyPlace]] = {c: [] for c in cfg.categories}
        for p, d in zip(raw, straight):
            w = unique_walk[(p["latitude"], p["longitude"])]
            minutes = walk_minutes(w, cfg)
            if minutes > cfg.max_walk_minutes:
                continue
            by_cat[p["category"]].append(
                NearbyPlace(**p, distance_m=round(d), walk_distance_m=round(w), walk_minutes=minutes)
            )

        out: dict[str, CategorySummary] = {}
        for cat, places in by_cat.items():
            places.sort(key=lambda pl: pl.walk_distance_m)
            out[cat] = CategorySummary(
                count=len(places),
                nearest=places[0] if places else None,
                places=places[: cfg.max_places_per_category],
            )
        return out
