# Scraper de logements à louer (Québec)

Récupère les annonces de location et les normalise dans un seul schéma (`scraper/models.py:Listing`).
Un champ absent de la source vaut `null`. On peut aussi enrichir chaque annonce avec le métro
le plus proche et les commerces essentiels accessibles à pied.

## Sources

| Source | Commande | Méthode | Couverture / limites |
|---|---|---|---|
| Centris | `centris` | HTTP, pages serveur | Description, photos, caractéristiques, courtier. Au plus ~5000 résultats par recherche, d'où le découpage par ville (`--areas`). |
| Kijiji | `kijiji` | HTTP, état Apollo `__NEXT_DATA__` | Coordonnées, inclusions, commodités, date de disponibilité. `--no-details` évite la page de chaque annonce (description tronquée). |
| Logis Québec | `logis_quebec` | HTTP, JSON-LD | Prix, coordonnées, superficie, photos, charges (incluses ou montant). |
| DuProprio | `duproprio` | HTTP, JSON-LD | Pas de coordonnées publiées : elles sont géocodées par `--enrich`. |
| Rentals.ca | `rentals_ca` | Playwright (Cloudflare) | Une ligne par plan d'unité. |
| Realtor.ca | `realtor_ca` | Playwright, lecture passive de la réponse de recherche de la carte | **Désactivé dans `all`** (lançable explicitement). **Limité** : le site ne répond qu'au premier chargement de carte par session, donc environ 11 annonces par exécution en headless. Au Québec, ces annonces sont des syndications Centris (`extra.mls_number` = `external_id` Centris) : utiliser `centris` pour la couverture complète. |

## Utilisation

```bash
pip install -r requirements.txt && playwright install chromium

python -m scraper.main kijiji --areas montreal --out -              # JSONL sur stdout
python -m scraper.main centris --areas montreal,laval --out data/centris.jsonl
python -m scraper.main logis_quebec --areas ile-de-montreal --enrich --walk-minutes 10
python -m scraper.main all --enrich --prefetch-pois montreal --out api   # vers listings-api
```

`--out` accepte un fichier JSONL (dédupliqué par `source:external_id`), `-` pour stdout, ou `api`
(voir `scraper/api_sink.py`). `--limit N` arrête chaque source après N annonces.

Utilisation en bibliothèque :

```python
from scraper.sources import kijiji
from scraper.geo.enrich import Enricher
from scraper.geo.config import ProximityConfig

enricher = Enricher(ProximityConfig(max_walk_minutes=10, categories=["grocery", "pharmacy"]))
for listing in kijiji.scrape(location="montreal"):
    doc = enricher.enrich(listing).model_dump(mode="json")   # prêt pour MongoDB
```

## Enrichissement de proximité (`--enrich`)

1. **Coordonnées.** Celles de la source si elle en publie. Sinon, géocodage Nominatim de
   l'adresse, puis du code postal, puis de la ville. `location_precision` indique d'où elles viennent :
   `exact`, `approximate` (adresse masquée par l'annonceur), `geocoded_address`,
   `geocoded_postal_code` ou `geocoded_city`. À l'échelle de la ville, on ne calcule pas la proximité.
2. **Métro / REM** (`proximity.nearest_metro`, `nearest_rem`, `stations_within_walk`). Les 68 stations STM
   et celles du REM sont embarquées hors ligne (`scraper/geo/data/transit_stations.json`, régénérable avec
   `python scripts/build_transit_stations.py`). Vaut `null` si aucune station n'est à moins de 5 km :
   Québec, Sherbrooke, etc.
3. **Commerces essentiels** (`proximity.essentials`). Pour chaque catégorie : `count` à moins de
   `--walk-minutes` (15 par défaut), `nearest`, et `places` triés par temps de marche
   (`--max-places`). Les données viennent d'OpenStreetMap (Overpass). Catégories par défaut :
   épicerie, dépanneur, pharmacie, boulangerie, boucherie/fromagerie, SAQ, banque/guichet, buanderie,
   quincaillerie, clinique, hôpital, poste, école, garderie, parc, gym, bibliothèque, arrêt de bus et BIXI.
   `restaurant` et `cafe` sont disponibles sur demande (`--categories grocery,pharmacy,cafe`).

**Temps de marche.** Par défaut (`--routing estimate`), distance à vol d'oiseau × 1,3 (facteur de
détour typique d'une grille urbaine) à 4,8 km/h (`--walk-speed`). C'est hors ligne et instantané.
`--routing osrm` utilise à la place la distance réellement routée par un serveur OSRM à profil piéton
(`--osrm-url`, démo FOSSGIS par défaut).

**Performance.** Les commerces sont mis en cache par tuile d'environ 1 km pendant 30 jours
(`.cache/geo.sqlite`). Le serveur Overpass public peut prendre de 30 s à plusieurs minutes par tuile.
Avant un gros lot, `--prefetch-pois montreal` remplit le cache de toute l'île en une seule requête
(environ 8 min). Ensuite, l'enrichissement prend environ 10 ms par annonce. Pour un usage intensif, utiliser
ses propres instances (`OVERPASS_URL`, `NOMINATIM_URL`) et définir `GEOCODER_EMAIL` (voir `.env.example`).

Exemple de bloc `proximity` (abrégé) :

```json
{
  "method": "estimate", "walk_speed_kmh": 4.8, "max_walk_minutes": 15,
  "nearest_metro": {"name": "Place-des-Arts", "network": "metro", "lines": ["green"],
                    "distance_m": 345, "walk_distance_m": 449, "walk_minutes": 5.6},
  "nearest_rem": {"name": "McGill", "network": "rem", "walk_minutes": 13.3},
  "essentials": {
    "grocery":  {"count": 12, "nearest": {"name": "Provigo", "kind": "supermarket", "walk_minutes": 1.9}},
    "pharmacy": {"count": 8,  "nearest": {"name": "Jean Coutu", "walk_minutes": 2.3}}
  }
}
```

## Politesse (anti-blocage)

Toutes les sources HTTP passent par `scraper/polite.py` (`PoliteClient`) :

- pause aléatoire entre deux requêtes au même site (`SCRAPER_MIN_DELAY`..`SCRAPER_MAX_DELAY`, 2 à 5 s par défaut ; 3 à 7 s pour les sources navigateur via `SCRAPER_BROWSER_*`) ;
- sur 429 / 5xx : respect de `Retry-After`, sinon attente exponentielle (30 s, 60 s, 120 s…) ;
- après `SCRAPER_BLOCK_THRESHOLD` (3) réponses 403/429 consécutives, la source s'arrête (`SourceBlocked`) au lieu d'insister : son exécution est marquée `FAILED` avec la raison ;
- plafond de requêtes par exécution (`SCRAPER_MAX_REQUESTS`, 6000).

Ordre de grandeur : ~3,5 s par requête, soit 1 000 requêtes/heure par source. Un scrape complet prend plusieurs heures : à planifier une fois par jour, sources décalées.

## Worker planifié (production)

En production, le scraper tourne comme **worker** : c'est l'API qui décide quand scraper
(`saveScrapeSchedule`, `triggerScrape`), le worker réclame les exécutions en attente,
les exécute et envoie un heartbeat. Il ne fait que des appels sortants vers l'API : il peut
tourner derrière une box (IP résidentielle, beaucoup moins bloquée qu'une IP de datacenter).

```bash
cp .env.worker.example .env.worker      # URL + clé de l'API, nom du worker
docker compose -f compose.worker.yaml --env-file .env.worker up -d --build
# ou sans Docker :
LISTINGS_API_URL=... LISTINGS_API_KEY=... python -m scraper.worker
```

`WORKER_SOURCES` permet de répartir les sources entre plusieurs workers.
