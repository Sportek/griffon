"""A kept Facebook post (+ its LLM classification, if any) -> Listing.

Privacy: the poster's name, profile link and picture are never extracted (see extract.py),
so contact_name stays empty. The post text goes to `description` as is: phone numbers and
emails in it are how the user reaches the poster, but they are not parsed into fields.

Sublets are rentals (listing_type="rent") flagged with extra["is_sublet"] = True, plus
extra["sublet_end_date"] when known.
"""

import re

from ..models import Listing
from ..normalize import iso_date, parse_qc_rooms
from .extract import Post
from .prefilter import is_sublet, regex_price

SOURCE = "facebook"
DEFAULT_CITY = "Montréal"


def _title(text: str) -> str | None:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    first = re.sub(r"\s+", " ", first)
    return (first[:117] + "…" if len(first) > 120 else first) or None


def _property_type(rooms_qc: float | None, bedrooms: float | None, text: str) -> str:
    if (rooms_qc is not None and rooms_qc <= 1) or bedrooms == 0 or re.search(r"\bstudio\b", text, re.I):
        return "studio"
    if re.search(r"\bloft\b", text, re.I):
        return "loft"
    return "apartment"


def to_listing(post: Post, classification: dict | None, *, group: str) -> Listing:
    c = classification or {}
    text = post.text
    sublet = c.get("kind") == "sublet" if classification else is_sublet(text)
    rooms_qc = c.get("rooms_qc") if classification else parse_qc_rooms(text)
    price = c.get("price") if classification else regex_price(text)
    period = c.get("price_period") if classification else "monthly"

    utilities = []
    if c.get("heating_included"):
        utilities.append("Heat")
    if c.get("electricity_included"):
        utilities.append("Electricity")
    amenities = []
    if c.get("laundry") == "in_unit":
        amenities.append("Laundry (in unit)")
    elif c.get("laundry") == "building":
        amenities.append("Laundry (in building)")
    elif c.get("laundry") == "hookups":
        amenities.append("Laundry hookups")

    extra: dict = {"group": post.group or group, "classifier": c.get("_model") or ("llm" if classification else "rules")}
    if sublet:
        extra["is_sublet"] = True
        if end := iso_date(c.get("sublet_end_date")):
            extra["sublet_end_date"] = end
    if period not in (None, "monthly"):
        extra["price_period_raw"] = period  # weekly / daily / total for the stay
    if c.get("parking") is not None:
        extra["parking"] = c["parking"]

    return Listing(
        source=SOURCE,
        external_id=post.post_id,
        url=post.url or f"https://www.facebook.com/groups/{group}/posts/{post.post_id}/",
        title=_title(text),
        listing_type="rent",
        property_type=_property_type(rooms_qc, c.get("bedrooms"), text),
        price=price,
        price_period="monthly" if period in (None, "monthly") else "unknown",
        address=c.get("address"),
        neighborhood=c.get("neighborhood"),
        city=c.get("city") or DEFAULT_CITY,
        region="QC",
        bedrooms=c.get("bedrooms"),
        bathrooms=c.get("bathrooms"),
        rooms_qc=rooms_qc,
        parking_spots=1 if c.get("parking") else None,
        furnished=c.get("furnished"),
        pets_allowed=c.get("pets_allowed"),
        available_date=iso_date(c.get("available_date")),
        lease_term="Sous-location" if sublet else None,
        amenities=amenities,
        utilities_included=utilities,
        photos=post.photos,
        description=text,
        published_at=post.published_at,
        extra=extra,
    )
