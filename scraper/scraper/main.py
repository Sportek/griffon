import argparse
import sys
from contextlib import nullcontext

from dotenv import load_dotenv

from .api_sink import ApiSink
from .geo.config import DEFAULT_CATEGORIES, POI_CATEGORIES, PREFETCH_AREAS, ProximityConfig
from .geo.enrich import Enricher
from .polite import SourceBlocked
from .sinks import JsonlSink, StdoutSink
from .sources import centris, duproprio, kijiji, logis_quebec, realtor_ca, rentals_ca


def _csv(value: str | None) -> list[str] | None:
    return [v.strip() for v in value.split(",") if v.strip()] if value else None


SOURCES = {
    "duproprio": lambda args: duproprio.scrape(max_pages=args.max_pages or 200),
    "rentals_ca": lambda args: rentals_ca.scrape(
        cities=_csv(args.areas),
        max_pages_per_city=args.max_pages or 3,
        headless=not args.headed,
    ),
    "kijiji": lambda args: kijiji.scrape(
        location=args.areas or "quebec",
        max_pages=args.max_pages or 100,
        fetch_details=not args.no_details,
    ),
    "centris": lambda args: centris.scrape(
        areas=_csv(args.areas),
        max_pages_per_area=args.max_pages or 250,
    ),
    "logis_quebec": lambda args: logis_quebec.scrape(
        regions=_csv(args.areas),
        max_pages_per_region=args.max_pages or 500,
    ),
    # Disabled from "all": realtor.ca only answers the first map load per session (~11 listings),
    # and its Quebec rentals are Centris syndications already covered by "centris".
    # Still runnable explicitly: `python -m scraper.main realtor_ca`.
    "realtor_ca": lambda args: realtor_ca.scrape(
        areas=_csv(args.areas),
        headless=not args.headed,
        max_tiles=args.max_pages or 400,
    ),
}

DISABLED_FROM_ALL = {"realtor_ca"}


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Quebec rental listings scraper")
    parser.add_argument("source", choices=[*SOURCES.keys(), "all"])
    parser.add_argument(
        "--out",
        default="data/listings.jsonl",
        help="JSONL file, '-' for stdout, or 'api' to send to listings-api ($LISTINGS_API_URL)",
    )
    parser.add_argument("--max-pages", type=int, default=None, help="per area/city (tiles for realtor_ca)")
    parser.add_argument(
        "--areas",
        default=None,
        help="comma-separated areas; meaning depends on the source "
        "(centris: montreal,laval; logis_quebec: ile-de-montreal; kijiji: montreal or slug:locationId; "
        "rentals_ca: montreal,laval; realtor_ca: montreal,laval)",
    )
    parser.add_argument("--headed", action="store_true", help="show the browser (rentals_ca, realtor_ca)")
    parser.add_argument("--no-details", action="store_true", help="kijiji: skip detail pages (truncated descriptions)")
    parser.add_argument("--limit", type=int, default=None, help="stop each source after N listings")
    parser.add_argument(
        "--mark-unseen-inactive",
        action="store_true",
        help="--out api: after a successful source, flag its listings not seen in this run as inactive "
        "(only for complete scrapes)",
    )

    geo = parser.add_argument_group("proximity enrichment")
    geo.add_argument("--enrich", action="store_true", help="add nearest metro/REM and nearby essentials")
    geo.add_argument("--walk-minutes", type=float, default=15.0, help="max walk time for 'nearby' (default 15)")
    geo.add_argument("--walk-speed", type=float, default=4.8, help="walking speed in km/h (default 4.8)")
    geo.add_argument(
        "--categories",
        default=None,
        help=f"comma-separated POI categories (default: {','.join(DEFAULT_CATEGORIES)}; "
        f"all: {','.join(POI_CATEGORIES)})",
    )
    geo.add_argument("--max-places", type=int, default=10, help="places listed per category (default 10)")
    geo.add_argument(
        "--routing",
        choices=["estimate", "osrm"],
        default="estimate",
        help="estimate = straight line x detour factor (offline, fast); osrm = routed walking distance",
    )
    geo.add_argument("--osrm-url", default=None, help="OSRM foot-profile server (default: FOSSGIS demo)")
    geo.add_argument("--no-geocode", action="store_true", help="don't geocode listings without coordinates")
    geo.add_argument(
        "--prefetch-pois",
        default=None,
        help=f"warm the POI cache for whole areas with one big query each before scraping "
        f"(comma-separated: {','.join(PREFETCH_AREAS)})",
    )
    args = parser.parse_args()

    enricher = None
    if args.enrich:
        config = ProximityConfig(
            max_walk_minutes=args.walk_minutes,
            walk_speed_kmh=args.walk_speed,
            routing=args.routing,
            max_places_per_category=args.max_places,
            geocode_missing=not args.no_geocode,
        )
        if args.categories:
            config.categories = _csv(args.categories)
            unknown = set(config.categories) - set(POI_CATEGORIES)
            if unknown:
                parser.error(f"unknown categories {sorted(unknown)}; known: {', '.join(POI_CATEGORIES)}")
        if args.osrm_url:
            config.osrm_url = args.osrm_url
        enricher = Enricher(config)
        for area in _csv(args.prefetch_pois) or []:
            if area not in PREFETCH_AREAS:
                parser.error(f"unknown prefetch area {area!r}; known: {', '.join(PREFETCH_AREAS)}")
            print(f"[geo] prefetching POIs for {area}...", file=sys.stderr)
            print(f"[geo] {area}: {enricher.prefetch(PREFETCH_AREAS[area])} tiles cached", file=sys.stderr)

    # A truncated scrape would flag every listing past the cut-off as gone.
    if args.mark_unseen_inactive and (args.out != "api" or args.limit or args.max_pages):
        parser.error("--mark-unseen-inactive needs --out api and a complete scrape (no --limit / --max-pages)")

    if args.out == "api":
        sink = ApiSink()
    else:
        sink = StdoutSink() if args.out == "-" else JsonlSink(args.out)
    log = sys.stderr
    targets = [s for s in SOURCES if s not in DISABLED_FROM_ALL] if args.source == "all" else [args.source]

    for name in targets:
        print(f"[{name}] starting...", file=log)
        written = 0
        seen = 0
        # With the API, each source is journaled as an ingestion run (FAILED if it raises).
        run = (
            sink.run(name, mark_unseen_inactive=args.mark_unseen_inactive)
            if isinstance(sink, ApiSink)
            else nullcontext()
        )
        try:
            with run:
                for listing in SOURCES[name](args):
                    seen += 1
                    if enricher:
                        enricher.enrich(listing)
                    if sink.write(listing):
                        written += 1
                    if seen % 25 == 0:
                        print(f"[{name}] {seen} seen, {written} new", file=log)
                    if args.limit and seen >= args.limit:
                        break
        except SourceBlocked as e:
            # The site is refusing us: stop this source (its run is FAILED) and move on.
            print(f"[{name}] stopped: {e}", file=log)
        except Exception as e:  # noqa: BLE001 -- one broken source shouldn't stop "all"
            print(f"[{name}] failed: {e!r}", file=log)
        print(f"[{name}] done: {seen} seen, {written} new. Total in sink: {len(sink)}", file=log)


if __name__ == "__main__":
    main()
