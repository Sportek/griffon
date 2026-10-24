from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .normalize import property_type

# How trustworthy latitude/longitude are:
# - "exact": the source published coordinates for the building itself
# - "approximate": the source published coordinates but blurs them (e.g. Kijiji/realtor hidden addresses)
# - "geocoded_address" / "geocoded_postal_code" / "geocoded_city": we geocoded it ourselves at that granularity
LocationPrecision = Literal[
    "exact", "approximate", "geocoded_address", "geocoded_postal_code", "geocoded_city"
]


class NearbyPlace(BaseModel):
    name: str | None = None
    category: str
    kind: str | None = None  # raw OSM tag value, e.g. "supermarket", "convenience", "pharmacy"
    brand: str | None = None
    latitude: float
    longitude: float
    distance_m: float  # straight line
    walk_distance_m: float  # routed (osrm) or estimated (straight line x detour factor)
    walk_minutes: float
    osm_id: str | None = None


class NearbyStation(BaseModel):
    name: str
    network: Literal["metro", "rem"]
    lines: list[str] = Field(default_factory=list)
    latitude: float
    longitude: float
    distance_m: float
    walk_distance_m: float
    walk_minutes: float


class CategorySummary(BaseModel):
    count: int = 0
    nearest: NearbyPlace | None = None
    places: list[NearbyPlace] = Field(default_factory=list)  # sorted by walk time, capped


class Proximity(BaseModel):
    method: Literal["estimate", "osrm"] = "estimate"
    walk_speed_kmh: float
    max_walk_minutes: float
    nearest_metro: NearbyStation | None = None
    nearest_rem: NearbyStation | None = None
    stations_within_walk: list[NearbyStation] = Field(default_factory=list)
    # Keyed by category name ("grocery", "pharmacy", ...). Only places within max_walk_minutes.
    essentials: dict[str, CategorySummary] = Field(default_factory=dict)
    computed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Listing(BaseModel):
    source: str
    external_id: str
    url: str

    title: str | None = None
    listing_type: Literal["rent", "sale", "unknown"] = "rent"
    property_type: str | None = None  # apartment, condo, house, studio, room, duplex-triplex, ...

    price: float | None = None
    price_currency: str = "CAD"
    price_period: Literal["monthly", "yearly", "unknown"] = "monthly"

    address: str | None = None
    neighborhood: str | None = None  # e.g. "Villeray/Saint-Michel/Parc-Extension"
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str = "CA"
    latitude: float | None = None
    longitude: float | None = None
    location_precision: LocationPrecision | None = None

    bedrooms: float | None = None
    bathrooms: float | None = None
    area_sqft: float | None = None
    rooms_qc: float | None = None  # Quebec convention: the "X" in "X 1/2" (e.g. 3 1/2, 4 1/2)
    year_built: int | None = None
    parking_spots: int | None = None

    furnished: bool | None = None
    pets_allowed: bool | None = None
    smoking_allowed: bool | None = None
    available_date: str | None = None  # ISO date when parseable, else the source's raw text
    lease_term: str | None = None

    amenities: list[str] = Field(default_factory=list)
    utilities_included: list[str] = Field(default_factory=list)

    photos: list[str] = Field(default_factory=list)
    description: str | None = None

    contact_name: str | None = None
    agency_name: str | None = None
    published_at: str | None = None

    # Source-specific fields that don't map onto the common schema.
    extra: dict[str, Any] = Field(default_factory=dict)

    proximity: Proximity | None = None

    scraped_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @model_validator(mode="after")
    def _normalize_property_type(self) -> "Listing":
        """One vocabulary across sources (see normalize.PROPERTY_TYPES); the source's own
        label is kept in extra["property_type_raw"] when it differs."""
        raw = self.property_type
        canonical = property_type(raw)
        if raw is not None and canonical != raw:
            self.extra.setdefault("property_type_raw", raw)
        self.property_type = canonical
        return self

    @property
    def dedupe_key(self) -> str:
        return f"{self.source}:{self.external_id}"
