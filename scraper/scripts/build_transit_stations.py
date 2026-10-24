"""Regenerates scraper/geo/data/transit_stations.json from OpenStreetMap.

Run when the network changes (new REM branch, Blue line extension, ...):

    python scripts/build_transit_stations.py

STM line membership isn't reliably tagged on OSM station nodes, so it comes
from the table below (keyed by normalized station name).
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scraper.geo import overpass  # noqa: E402

BBOX = (45.30, -74.10, 45.75, -73.35)  # south, west, north, east
OUT = Path(__file__).resolve().parents[1] / "scraper" / "geo" / "data" / "transit_stations.json"

STM_LINES = {
    "green": [
        "Angrignon", "Monk", "Jolicoeur", "Verdun", "De l'Église", "LaSalle", "Charlevoix",
        "Lionel-Groulx", "Atwater", "Guy-Concordia", "Peel", "McGill", "Place-des-Arts",
        "Saint-Laurent", "Berri-UQAM", "Beaudry", "Papineau", "Frontenac", "Préfontaine",
        "Joliette", "Pie-IX", "Viau", "Assomption", "Cadillac", "Langelier", "Radisson",
        "Honoré-Beaugrand",
    ],
    "orange": [
        "Côte-Vertu", "Du Collège", "De La Savane", "Namur", "Plamondon", "Côte-Sainte-Catherine",
        "Snowdon", "Villa-Maria", "Vendôme", "Place-Saint-Henri", "Lionel-Groulx", "Georges-Vanier",
        "Lucien-L'Allier", "Bonaventure", "Square-Victoria-OACI", "Place-d'Armes", "Champ-de-Mars",
        "Berri-UQAM", "Sherbrooke", "Mont-Royal", "Laurier", "Rosemont", "Beaubien", "Jean-Talon",
        "Jarry", "Crémazie", "Sauvé", "Henri-Bourassa", "Cartier", "De la Concorde", "Montmorency",
    ],
    "yellow": ["Berri-UQAM", "Jean-Drapeau", "Longueuil–Université-de-Sherbrooke"],
    "blue": [
        "Snowdon", "Côte-des-Neiges", "Université-de-Montréal", "Édouard-Montpetit", "Outremont",
        "Acadie", "Parc", "De Castelnau", "Jean-Talon", "Fabre", "D'Iberville", "Saint-Michel",
    ],
}


def normalize(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    name = re.sub(r"^station\s+", "", name)
    return re.sub(r"[^a-z0-9]", "", name)


def main() -> None:
    lines_by_station: dict[str, list[str]] = {}
    canonical_name: dict[str, str] = {}
    for line, names in STM_LINES.items():
        for n in names:
            lines_by_station.setdefault(normalize(n), []).append(line)
            canonical_name[normalize(n)] = n

    s, w, n, e = BBOX
    query = f'[out:json][timeout:60];node["railway"="station"]["station"~"subway|light_rail"]({s},{w},{n},{e});out body;'
    result = overpass.query(query, timeout_s=120)

    stations: dict[tuple[str, str], dict] = {}
    for el in result["elements"]:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        is_rem = tags.get("network") == "REM" or "pulsar" in (tags.get("operator") or "").lower()
        is_stm = "transport de montréal" in (tags.get("operator") or "").lower()
        if not (is_rem or is_stm):
            continue
        key = normalize(name)
        network = "rem" if is_rem else "metro"
        if network == "metro" and key not in lines_by_station:
            print(f"warning: STM station without line mapping: {name!r}", file=sys.stderr)
        stations[(network, key)] = {
            "name": canonical_name.get(key, name) if network == "metro" else re.sub(r"^Station\s+", "", name),
            "network": network,
            "lines": lines_by_station.get(key, []) if network == "metro" else ["REM"],
            "latitude": el["lat"],
            "longitude": el["lon"],
        }

    metro = [s for (net, _), s in stations.items() if net == "metro"]
    missing = set(lines_by_station) - {k for (net, k) in stations if net == "metro"}
    if missing:
        # Overpass mirrors occasionally serve stale/partial data; don't overwrite a good file with it.
        sys.exit(f"STM stations missing from OSM result, not writing (retry): {sorted(missing)}")

    rows = sorted(stations.values(), key=lambda s: (s["network"], s["name"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {len(metro)} metro + {len(rows) - len(metro)} REM stations to {OUT}")


if __name__ == "__main__":
    main()
