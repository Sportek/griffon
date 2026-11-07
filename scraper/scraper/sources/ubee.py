"""ubee.com (ubee.ca redirects there): rentals (`scrape`) and properties for sale (`scrape_sale`).

Its terms of use forbid automated extraction: this source is for private use only, runs from
a schedule (never in "all"), and keeps a very small footprint. robots.txt allows the listing
pages and the API host has none.

No browser needed -- plain HTTP, JSON throughout:

1. Discovery: the site's own search endpoint
   `api.ubee.ca/api/anonymous/Search/offered-properties?forSale=…&pageIndex=…&pageSize=500`
   returns every listing of a kind as cards (price, bedrooms, bathrooms, areas, coordinates,
   street address, photos, online-since date). 468 rentals fit in one request, ~1830
   properties for sale in four. (The listings sitemap has the same URLs without any data.)
2. Detail: the listing page is Angular server-rendered; its `<script id="ng-state">`
   TransferState holds the full record under `listingDetails:<slug>`: description, rooms,
   parking, features, assessments, taxes, plex units, the listing broker, and where it
   comes from. (`/api/anonymous/Search/Details/{id}` only returns the card again.)
3. Many ubee listings are Centris syndications: those carry an `mlsNumber`, descriptions
   whose `source` is "Centris" and a passerelle.centris.ca link. We scrape Centris directly,
   so they are skipped (counted in the log). Only listings published on ubee itself, mostly
   by owners, are kept.

To keep requests down, `.cache/ubee.json` (UBEE_CACHE) remembers which listing ids are
Centris syndications (never fetched again) and the detail record of the others (fetched
again when the card changes or after UBEE_DETAIL_MAX_AGE_DAYS, 7 by default). Without the
cache a run just fetches every detail page. Terrains, commercial premises and other
non-homes are dropped from the cards, before any detail request.

Politeness: 3 to 7 s between requests, a per-run request budget, and the first 403/429 (or
a Cloudflare challenge) stops the source at once (SourceBlocked) instead of retrying.
"""

import json
import os
import re
import sys
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from ..models import Listing
from ..normalize import format_postal_code, html_to_text, iso_date, parse_qc_rooms, split_city_neighborhood
from ..polite import CrawlHealth, PoliteClient, SourceBlocked

SITE_URL = "https://ubee.com"
API_URL = "https://api.ubee.ca"
SEARCH_PATH = "/api/anonymous/Search/offered-properties"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-CA,fr;q=0.9",
}
API_HEADERS = {"Accept": "text/json", "Origin": SITE_URL, "Referer": SITE_URL + "/"}

PAGE_SIZE = 500
MIN_DELAY, MAX_DELAY = 3.0, 7.0
# A full run with an empty cache: one detail page per home (~470 rentals, ~1500 for sale).
RENT_MAX_REQUESTS = 800
SALE_MAX_REQUESTS = 2500
# Below this share of the announced total, the listing is not complete: no deactivation.
_MIN_COVERAGE = 0.98
_SQFT_PER_M2 = 10.7639
_STATE_RE = re.compile(r'<script id="ng-state" type="application/json">(.*?)</script>', re.S)
_DWELLINGS_RE = re.compile(r"\b(\d{1,3})\s+(?:logements|appartements|unités|portes)\b", re.I)
_LD_RE = re.compile(r'<script type="application/ld\+json" data-jsonld-source="listing">(.*?)</script>', re.S)

# (inscriptionType, propertyType) -> canonical property type. Plexes are "Commercial" on ubee.
_PROPERTY_STYLES = {"PlainPied": "plain-pied", "Etages": "à étages", "EtageEtDemi": "à un étage et demi",
                    "Paliers": "à paliers", "Mobile": "maison mobile"}
_UNIT_COUNTS = {
    "oneAndHalfCount": "1 ½", "twoAndHalfCount": "2 ½", "threeAndHalfCount": "3 ½", "fourAndHalfCount": "4 ½",
    "fiveAndHalfCount": "5 ½", "sixAndHalfCount": "6 ½", "sevenAndHalfCount": "7 ½",
}


class ParseError(ValueError):
    """The page has no listing record (redesign, error page...)."""


# --- Parsing -------------------------------------------------------------------------------


def is_home(card: dict) -> bool:
    """Condos/apartments, houses and plexes; not land, offices, industrial or farm premises."""
    kind = card.get("inscriptionType")
    return kind in ("Condo", "Unifamiliale") or (kind == "Commercial" and card.get("propertyType") == "Plex")


def detail_record(page: str) -> dict:
    """The `listingDetails:<slug>` record of a listing page's ng-state."""
    m = _STATE_RE.search(page)
    if not m:
        raise ParseError("no ng-state in the page")
    state = json.loads(m.group(1))
    for key, value in state.items():
        if key.startswith("listingDetails:") and isinstance(value, dict):
            return value
    raise ParseError("no listingDetails in ng-state")


def page_title(page: str) -> str | None:
    """'Condo à 104-7995 Av Shelley, 104, Montréal, H1Z 3H5' from the listing JSON-LD."""
    if m := _LD_RE.search(page):
        try:
            return json.loads(m.group(1)).get("name")
        except ValueError:
            return None
    return None


def centris_number(detail: dict) -> str | None:
    """The Centris (MLS) number of a syndicated listing, "" when it is Centris without one,
    None for a listing published on ubee itself."""
    if mls := (detail.get("mlsNumber") or "").strip():
        return mls
    link = ((detail.get("additionalLinks") or {}).get("listingLink") or "").lower()
    if "centris.ca" in link:
        m = re.search(r"nomls=(\d+)", link)
        return m.group(1) if m else ""
    if any((t.get("source") or "").lower() == "centris" for t in detail.get("descriptionTexts") or []):
        return ""
    return None


def _positive(value) -> float | None:
    """ubee writes 0 for "not filled in"."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _sqft(m2) -> float | None:
    n = _positive(m2)
    return round(n * _SQFT_PER_M2, 1) if n else None


def _words(code: str) -> str:
    """'ClimatiseurCentral' -> 'Climatiseur central', 'EchangeurDAir' -> 'Echangeur d air'."""
    parts = re.findall(r"[A-ZÀ-Ý][a-zà-ÿ]*|[a-zà-ÿ]+|\d+", code) or [code]
    return " ".join([parts[0]] + [p.lower() for p in parts[1:]])


def _description(detail: dict) -> str | None:
    """The French text as written by the lister (HTML kept as line breaks), else any text."""
    texts = detail.get("descriptionTexts") or []
    ordered = sorted(texts, key=lambda t: (t.get("language") != "Fr", (t.get("source") or "") == "Llm"))
    for t in ordered:
        if body := t.get("text") or t.get("plainText"):
            return html_to_text(re.sub(r"</div>", "\n", body, flags=re.I))
    raw = detail.get("description") or detail.get("plainTextDescription")
    return html_to_text(re.sub(r"</div>", "\n", raw, flags=re.I)) if raw else None


def _photos(card: dict, detail: dict) -> list[str]:
    images = detail.get("images") or card.get("images") or []
    images = sorted(images, key=lambda i: i.get("index") or 0)
    return [u for i in images if (u := (i.get("publicUrls") or {}).get("default_size"))]


def _expenses(detail: dict) -> dict:
    """Taxes (yearly), condo fees (monthly) and the other expenses (yearly), by ubee code."""
    out: dict = {}
    other: dict[str, float] = {}
    for e in detail.get("expenses") or []:
        amount = _positive(e.get("amount"))
        code = e.get("expenseType") or ""
        if amount is None or not code:
            continue
        frequency = (e.get("paymentFrequency") or "Annual").lower()
        yearly = amount * 12 if frequency.startswith("month") else amount
        low = code.lower()
        if low == "taxmun":
            out["municipal_taxes_yearly"] = yearly
        elif low == "taxsco":
            out["school_taxes_yearly"] = yearly
        elif "copro" in low or "condo" in low:
            out["condo_fees_monthly"] = round(yearly / 12, 2)
        else:
            other[code] = yearly
    if other:
        out["expenses_yearly"] = other
    return out


def _units(detail: dict) -> tuple[int | None, str | None]:
    """Dwellings of a plex and their mix ('1 x 5 ½, 1 x 6 ½')."""
    counts = [(label, int(n)) for key, label in _UNIT_COUNTS.items() if (n := _positive(detail.get(key)))]
    total = sum(n for _, n in counts) or len(detail.get("plexUnits") or []) or None
    mix = ", ".join(f"{n} x {label}" for label, n in counts) or None
    return total, mix


def _pets(codes: list[str]) -> bool | None:
    if not codes:
        return None
    folded = " ".join(codes).lower()
    if "nonpermis" in folded or "interdit" in folded or "refuse" in folded:
        return False
    return True if "permis" in folded or "accept" in folded else None


def _smoking(policy: str | None) -> bool | None:
    if not policy:
        return None
    low = policy.lower()
    if low.startswith(("non", "no")):
        return False
    return True if "smok" in low or "fum" in low else None


def _available(detail: dict) -> str | None:
    for raw in (detail.get("moveInDate"), detail.get("moveInDelay")):
        if raw and raw.strip().upper() != "TODO":  # "TODO" is a placeholder the site ships
            return iso_date(raw)
    for t in detail.get("moveInDelayTexts") or []:
        if isinstance(t, dict) and (text := t.get("text")):
            return iso_date(text)
    return None


def _path(card: dict, sale: bool) -> str:
    """'a-louer/montreal/condo-104-7995-av-shelley-d3cb9f'."""
    return f"{'a-vendre' if sale else 'a-louer'}/{card.get('citySlug')}/{card.get('slugFr')}"


def _property_type(card: dict, sale: bool) -> str:
    kind = card.get("inscriptionType")
    if kind == "Commercial":
        return "duplex-triplex"
    if kind == "Unifamiliale":
        return "house"
    # ubee files every rental apartment as "Condo" (like Centris' "Condo / Appartement").
    return "condo" if sale else "apartment"


def to_listing(card: dict, detail: dict, *, sale: bool, title: str | None = None) -> Listing:
    """One ubee listing from its search card and its detail record. The card wins when both
    have a field: it comes from this run's search, the detail may come from the cache."""

    def pick(key):
        value = card.get(key)
        return value if value not in (None, "", 0) else detail.get(key)

    city, neighborhood = split_city_neighborhood(pick("city"), city_first=True)
    url = f"{SITE_URL}/{detail.get('sharedUrl') or _path(card, sale)}"

    bathrooms = _positive(pick("nbBathrooms"))
    if half := _positive(pick("nbHalfBaths")):
        bathrooms = (bathrooms or 0) + 0.5 * half

    parking = _positive(detail.get("numberOfParkings"))
    if parking is None and detail.get("parkings"):
        parking = sum(_positive(p.get("count")) or 0 for p in detail["parkings"]) or None

    conveniences = detail.get("convenienceType") or []
    furnished = True if ("Meuble" in conveniences or "SemiMeuble" in conveniences) else None
    amenities = [_words(c) for c in conveniences if c not in ("Meuble", "SemiMeuble")]
    if detail.get("hasGarage") and not any(a.lower().startswith("garage") for a in amenities):
        amenities.append("Garage")

    price = _positive(pick("askPrice"))
    extra: dict = {
        "ubee_id": card.get("id") or detail.get("id"),
        "listed_by": "professional" if detail.get("isListedByProfessional") else "owner",
        "property_type_raw": " / ".join(x for x in (card.get("inscriptionType"), card.get("propertyType")) if x),
        "property_style": _PROPERTY_STYLES.get(card.get("propertyType") or ""),
        "building_type": card.get("buildingType") or detail.get("buildingType"),
        "rooms_total": _positive(detail.get("nbRooms")),
        "heating": [_words(c) for c in (detail.get("heatingType") or []) + (detail.get("heatingEnergyType") or [])] or None,
        "proximity": [_words(c) for c in detail.get("proximityType") or []] or None,
        "view": [_words(c) for c in detail.get("viewType") or []] or None,
        "pets_policy": ", ".join(_words(c) for c in detail.get("animalPermissionType") or []) or None,
        "furnishing": "semi-meublé" if "SemiMeuble" in conveniences else ("meublé" if furnished else None),
        "co_ownership": detail.get("coOwnershipKind") if detail.get("coOwnershipKind") not in (None, "None") else None,
        "floors": _positive(detail.get("numberOfFloors")),
        "lease_end_date": detail.get("leaseEndDate"),
        "virtual_tour": (detail.get("additionalLinks") or {}).get("virtualTourFrLink"),
    }
    if mls := centris_number(detail):
        extra["mls_number"] = mls
    if detail.get("pricedPerUnitSquared"):
        # A commercial rate per square foot, not a rent: keep it out of the price.
        extra["price_per_unit_squared"] = price
        price = None

    if sale:
        period = "total"
    else:
        frequency = (pick("rentalPriceFrequency") or "Monthly").lower()
        period = {"monthly": "monthly", "annual": "yearly", "yearly": "yearly"}.get(frequency, "unknown")
        if period == "unknown":
            extra["price_frequency"] = pick("rentalPriceFrequency")

    data: dict = {}
    description = _description(detail)
    if sale:
        fin = _expenses(detail)
        if fin.get("expenses_yearly"):
            extra["expenses_yearly"] = fin["expenses_yearly"]
        plex = card.get("inscriptionType") == "Commercial"
        units, mix = _units(detail) if plex else (None, None)
        if plex and units is None and (m := _DWELLINGS_RE.search(description or "")):
            units = int(m.group(1))  # owners often only write it: "Immeuble de 7 logements"
        if mix:
            extra["residential_units"] = mix
        lot, building = _positive(detail.get("lotMunicipalAssessment")), _positive(detail.get("buildingMunicipalAssessment"))
        data = {
            "lot_area_sqft": _sqft(pick("landSurfaceInMeters")),
            "municipal_assessment": (lot or 0) + (building or 0) or None,
            "municipal_assessment_year": int(y) if (y := _positive(detail.get("municipalAssessmentYear"))) else None,
            "municipal_taxes_yearly": fin.get("municipal_taxes_yearly"),
            "school_taxes_yearly": fin.get("school_taxes_yearly"),
            "condo_fees_monthly": fin.get("condo_fees_monthly"),
            "units": units,
            "gross_revenue_yearly": _positive(detail.get("potentialCommercialRevenue")) if plex else None,
        }
        # The "X 1/2" in a plex's text is one of its units, not the property.
        rooms_qc = None if plex else parse_qc_rooms(" ".join(filter(None, (title, description))))
    else:
        rooms_qc = parse_qc_rooms(" ".join(filter(None, (title, description))))

    professional = detail.get("professional") or {}
    lat, lng = card.get("latitude"), card.get("longitude")
    if not lat or not lng:  # 0 = no position
        lat = lng = None
    year = _positive(pick("yearBuilt"))
    return Listing(
        source="ubee",
        external_id=str(card.get("id") or detail.get("id")),
        url=url,
        title=title,
        listing_type="sale" if sale else "rent",
        property_type=_property_type(card, sale),
        price=price,
        price_period=period,
        address=card.get("address") or None,
        city=city,
        neighborhood=neighborhood,
        region=pick("province"),
        postal_code=format_postal_code(pick("zipCode")),
        latitude=lat,
        longitude=lng,
        location_precision="exact" if lat is not None else None,
        bedrooms=_positive(pick("nbBedrooms")),
        bathrooms=bathrooms,
        area_sqft=_sqft(pick("livingSurfaceInMeters")),
        rooms_qc=rooms_qc,
        year_built=int(year) if year else None,
        parking_spots=int(parking) if parking else None,
        furnished=furnished,
        pets_allowed=_pets(detail.get("animalPermissionType") or []),
        smoking_allowed=_smoking(detail.get("smokingPolicy")),
        available_date=None if sale else _available(detail),
        amenities=amenities,
        photos=_photos(card, detail),
        description=description,
        # Only the agency: the broker's own name, phone and email stay out of the data.
        agency_name=professional.get("agenceName") or professional.get("realtorBrokerageName") or None,
        published_at=card.get("isOnlineSince"),
        extra={k: v for k, v in extra.items() if v not in (None, "", [])},
        **data,
    )


# --- Cache ---------------------------------------------------------------------------------


def _card_signature(card: dict) -> str:
    """What the card shows of a listing: a change means the detail may have changed too."""
    images = [i.get("publicUrls", {}).get("default_size") for i in card.get("images") or []]
    keys = ("askPrice", "nbBedrooms", "nbBathrooms", "nbHalfBaths", "livingSurfaceInMeters", "address")
    return json.dumps([card.get(k) for k in keys] + [len(images), images[:1]], ensure_ascii=False)


class DetailCache:
    """{listing id: {"mls": ...} for Centris syndications, {"sig", "at", "detail"} for the others}."""

    def __init__(self, path: str | None, max_age_days: float):
        self.path = Path(path) if path else None
        self.max_age = timedelta(days=max_age_days)
        self.entries: dict[str, dict] = {}
        if self.path and self.path.exists():
            try:
                self.entries = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                print(f"[ubee] cache {self.path} unreadable, starting over: {e!r}", file=sys.stderr)

    def centris(self, listing_id: str) -> str | None:
        entry = self.entries.get(listing_id) or {}
        return entry.get("mls") if "mls" in entry else None

    def fresh_detail(self, listing_id: str, card: dict) -> dict | None:
        entry = self.entries.get(listing_id) or {}
        if "detail" not in entry or entry.get("sig") != _card_signature(card):
            return None
        try:
            at = datetime.fromisoformat(entry["at"])
        except (KeyError, ValueError):
            return None
        return entry["detail"] if datetime.now(timezone.utc) - at < self.max_age else None

    def remember(self, listing_id: str, card: dict, detail: dict, title: str | None) -> None:
        mls = centris_number(detail)
        if mls is not None:
            self.entries[listing_id] = {"mls": mls}
        else:
            slim = {k: v for k, v in detail.items() if k not in ("images", "draftImages", "plainTextDescription", "description")}
            slim["_title"] = title
            self.entries[listing_id] = {
                "sig": _card_signature(card), "at": datetime.now(timezone.utc).isoformat(), "detail": slim
            }

    def save(self, keep: set[str]) -> None:
        """Writes the cache, forgetting listings that are no longer online."""
        if not self.path:
            return
        self.entries = {k: v for k, v in self.entries.items() if k in keep}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.entries, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as e:
            print(f"[ubee] cannot write cache {self.path}: {e!r}", file=sys.stderr)


# --- Crawl ---------------------------------------------------------------------------------


def _stop_on_block(response: httpx.Response) -> None:
    """The first 403/429 ends the run: no retry, no second try at a refusing site."""
    if response.status_code in (403, 429):
        raise SourceBlocked(f"ubee: HTTP {response.status_code} on {response.request.url}, stopping at once")


def _search(client: httpx.Client, *, sale: bool, health: CrawlHealth) -> dict[str, dict]:
    """Every card of one kind, by listing id."""
    cards: dict[str, dict] = {}
    total = None
    page = 0
    while True:
        resp = client.get(
            API_URL + SEARCH_PATH,
            params={"forSale": str(sale).lower(), "pageIndex": page, "pageSize": PAGE_SIZE},
            headers=API_HEADERS,
        )
        resp.raise_for_status()
        body = resp.json()
        health.ok("search page")
        items = body.get("items") or []
        total = body.get("totalCount") if total is None else total
        for card in items:
            if card.get("id"):
                cards.setdefault(card["id"], card)
        page += 1
        if not items or page >= (body.get("totalPages") or 0):
            break
    if total and len(cards) < _MIN_COVERAGE * total:
        health.gap(f"search listed {len(cards)} of {total} listings")
    print(f"[ubee] {'sale' if sale else 'rent'}: {len(cards)} listings online (announced {total})", file=sys.stderr)
    return cards


def _crawl(
    *, sale: bool, run_source: str, default_budget: int, skip_centris: bool, cache_path: str | None
) -> Iterator[Listing]:
    health = CrawlHealth(run_source)
    cache = DetailCache(cache_path, float(os.getenv("UBEE_DETAIL_MAX_AGE_DAYS", 7)))
    skipped_centris = skipped_not_home = from_cache = gone = 0
    with PoliteClient(
        headers=HEADERS,
        timeout=30,
        follow_redirects=True,
        source=run_source,
        min_delay=MIN_DELAY,
        max_delay=MAX_DELAY,
        default_max_requests=default_budget,
        event_hooks={"response": [_stop_on_block]},
    ) as client:
        try:
            cards = _search(client, sale=sale, health=health)
        except (httpx.HTTPError, ValueError) as e:
            health.failed("search page", "offered-properties", e)
            health.gap("search failed: nothing listed")
            cards = {}
        try:
            for listing_id, card in cards.items():
                if not is_home(card):
                    skipped_not_home += 1
                    continue
                if skip_centris and cache.centris(listing_id) is not None:
                    skipped_centris += 1
                    continue
                detail = cache.fresh_detail(listing_id, card)
                title = detail.get("_title") if detail else None
                if detail is not None:
                    from_cache += 1
                else:
                    url = f"{SITE_URL}/{_path(card, sale)}"
                    try:
                        resp = client.get(url)
                        if resp.status_code in (404, 410):  # taken down since the search
                            gone += 1
                            health.ok("detail")
                            continue
                        resp.raise_for_status()
                        detail, title = detail_record(resp.text), page_title(resp.text)
                    except Exception as e:  # noqa: BLE001 -- counted; SourceBlocked is not an Exception
                        health.failed("detail", url, e)
                        continue
                    health.ok("detail")
                    cache.remember(listing_id, card, detail, title)
                if skip_centris and centris_number(detail) is not None:
                    skipped_centris += 1
                    continue
                try:
                    listing = to_listing(card, detail, sale=sale, title=title)
                except Exception as e:  # noqa: BLE001
                    health.failed("detail", f"parse {listing_id}", e)
                    continue
                yield listing
        finally:
            # Also on a block or a stopped run: what was learnt saves requests next time.
            cache.save(set(cards))
            print(
                f"[ubee] {run_source}: skipped {skipped_centris} Centris syndications, {skipped_not_home} non-homes; "
                f"{from_cache} details from cache, {gone} gone, {client.requests_sent} requests",
                file=sys.stderr,
            )
    health.finish()


def _cache_path(cache_path: str | None) -> str | None:
    if cache_path is not None:
        return cache_path or None
    return os.getenv("UBEE_CACHE", ".cache/ubee.json") or None


def scrape(*, skip_centris: bool = True, cache_path: str | None = None) -> Iterator[Listing]:
    """Yields ubee rentals published on ubee itself (Centris syndications skipped)."""
    yield from _crawl(
        sale=False, run_source="ubee", default_budget=RENT_MAX_REQUESTS, skip_centris=skip_centris,
        cache_path=_cache_path(cache_path),
    )


def scrape_sale(*, skip_centris: bool = True, cache_path: str | None = None) -> Iterator[Listing]:
    """Yields ubee properties for sale (houses, condos, plexes) published on ubee itself.

    Listings keep source "ubee" with listing_type "sale" and price_period "total"; the run
    source is "ubee_sale", so a sale run only ever deactivates ubee properties for sale."""
    yield from _crawl(
        sale=True, run_source="ubee_sale", default_budget=SALE_MAX_REQUESTS, skip_centris=skip_centris,
        cache_path=_cache_path(cache_path),
    )
