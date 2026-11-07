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
| Groupes Facebook | `facebook` | Playwright avec une session connectée, filtre par mots-clés puis LLM (OpenRouter) | **Désactivé dans `all`.** Logements entiers et sous-locations publiés dans `FACEBOOK_GROUPS`. Voir [Source Facebook](#source-facebook). |
| Realtor.ca | `realtor_ca` | Playwright, lecture passive de la réponse de recherche de la carte | **Désactivé dans `all`** (lançable explicitement). **Limité** : le site ne répond qu'au premier chargement de carte par session, donc environ 11 annonces par exécution en headless. Au Québec, ces annonces sont des syndications Centris (`extra.mls_number` = `external_id` Centris) : utiliser `centris` pour la couverture complète. |
| Centris (à vendre) | `centris_sale` | HTTP, pages serveur | Condos, maisons, plex (`--areas`, défaut montreal,laval,longueuil). Évaluation municipale, taxes, frais de copropriété, terrain, unités et revenus des plex. Une recherche plafonnée à 5000 est redécoupée par secteur ; si un secteur reste plafonné, l'exécution échoue à la fin (rien n'est désactivé). `external_id` = `sale-<n° Centris>`. **Hors `all`.** |
| DuProprio (à vendre) | `duproprio_sale` | HTTP, JSON-LD + HTML | Tout le Québec, du plus récent au plus ancien (~9000 annonces). Coordonnées publiées, évaluation, taxes, frais de copropriété, terrain. **Hors `all`.** |

Les sources `*_sale` envoient `listing_type = "sale"` et `price_period = "total"` sous la source
`centris` / `duproprio` : ce sont des sources d'exécution distinctes (planning, journal, désactivation
des annonces non revues) mais pas des sources d'annonces distinctes. Elles parcourent des milliers de
fiches (plusieurs heures) : leur plafond de requêtes est `SCRAPER_SALE_MAX_REQUESTS` (20000).
ubee.ca (ubee.com) n'est pas une source : ses conditions d'utilisation interdisent l'extraction
automatisée et la constitution de bases de données à partir de son contenu. Kijiji n'a pas de
catégorie « à vendre » structurée (annonces génériques sans attributs immobiliers).

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

## Source Facebook

Lit les publications récentes des groupes dont le compte de scraping est membre
(`FACEBOOK_GROUPS` : URL, identifiants ou alias séparés par des virgules). Par défaut :

```
FACEBOOK_GROUPS=https://www.facebook.com/groups/242242325809377,https://www.facebook.com/groups/232947036803405,https://www.facebook.com/groups/logementpmr.annonces
```

Gardé : logements entiers à louer et sous-locations (`extra.is_sublet`, `extra.sublet_end_date`,
`lease_term = "Sous-location"`). Écarté : colocations et chambres, « je cherche » / ISO, ventes, hors sujet.

**Déroulement d'une exécution** (`scraper/sources/facebook.py`) :

1. Pour chaque groupe, l'un après l'autre : fil trié par nouveautés (`?sorting_setting=CHRONOLOGICAL`),
   défilement lent à pas et pauses aléatoires, « Voir plus » déplié. Arrêt du groupe dès
   `FACEBOOK_STOP_AFTER_SEEN` (3) publications déjà vues, 3 publications de plus de `FACEBOOK_MAX_AGE_DAYS`
   (14) jours, `FACEBOOK_MAX_POSTS_PER_GROUP` (60) publications ou `FACEBOOK_MAX_SCROLLS` (25) défilements.
   Pause de 20 à 60 s entre deux groupes.
2. Déduplication par identifiant et par texte normalisé (republications d'un groupe à l'autre), puis
   règles par mots-clés FR/EN (`scraper/facebook/prefilter.py`, sans LLM).
3. Classement par lots de 25 avec OpenRouter (`scraper/facebook/llm.py`) : schéma JSON strict à clés
   courtes, 600 caractères par publication, résultat mis en cache par empreinte du texte (jamais deux fois
   le même texte). Réponse illisible : un nouvel essai, puis le lot est coupé en deux. Consommation de
   jetons journalisée, plafond par exécution `FACEBOOK_LLM_TOKEN_BUDGET` (150 000) : au-delà, les
   publications restantes attendent l'exécution suivante. Sans `OPENROUTER_API_KEY` : avertissement,
   règles par mots-clés seules et prix extrait par expression régulière.
4. Envoi comme `Listing` (`source = "facebook"`, URL = lien permanent de la publication).

Modèle par défaut : `google/gemini-2.5-flash-lite` (0,10 $ US / M jetons en entrée, 0,40 $ / M en sortie,
sorties structurées). Environ 210 jetons d'entrée et 80 de sortie par publication, soit **environ 0,06 $ US
pour 1 000 publications classées**.

**Vie privée.** Ni le nom, ni le profil, ni la photo de l'auteur ne sont extraits (`contact_name` reste vide),
ni les commentaires. Le texte est gardé tel quel dans `description` : les téléphones et courriels qu'il
contient servent à joindre l'annonceur, mais ne sont pas extraits dans des champs.

**Expiration.** Les publications ne disparaissent pas d'une façon visible au défilement : jamais de
`markUnseenInactive` pour cette source (le worker l'ignore). L'API les retire 30 jours après leur
première apparition (`listings.inactivity.stale-after-by-source.facebook`, `INACTIVITY_STALE_AFTER_FACEBOOK`).

### Mise en place

1. **Session**, sur son propre PC, avec le compte secondaire dédié :

   ```bash
   pip install -r requirements.txt && playwright install chromium
   python -m scraper.facebook_login --b64        # Chromium visible : se connecter à la main (2FA compris)
   ```

   Le fichier `facebook_state.json` est le compte lui-même : ne jamais le versionner ni le partager.
2. **Le mettre sur Gremlin**, au choix :
   - Dokploy, onglet Environment : coller la ligne base64 affichée dans `FACEBOOK_STORAGE_STATE_B64`, puis
     redéployer. Le worker l'écrit dans le volume `facebook-data` au démarrage de la première exécution
     (et de nouveau seulement si la valeur change, après une nouvelle connexion) ;
   - ou copier le fichier dans le volume :

     ```bash
     scp facebook_state.json gremlin:/tmp/
     ssh gremlin 'docker cp /tmp/facebook_state.json $(docker ps -qf name=worker):/data/facebook/storage_state.json && rm /tmp/facebook_state.json'
     ```

   Les cookies sont réécrits à la fin de chaque exécution pour rester frais. Page de connexion ou de
   vérification : l'exécution échoue tout de suite avec `facebook: session expired, re-run facebook_login`
   (refaire les étapes 1 et 2).
3. **Clé OpenRouter** : `OPENROUTER_API_KEY` dans l'onglet Environment (optionnel, voir plus haut).
4. **Planifier** quelques passages par jour, avec `enrich` pour le géocodage (adresse ou intersection +
   ville) : voir `listings-api/README.md`, « Planifier les scrapes ».

En local : `FACEBOOK_STORAGE_STATE=facebook_state.json python -m scraper.main facebook --headed --out -` (`--areas` remplace `FACEBOOK_GROUPS`,
`--max-pages` limite les défilements par groupe). L'état (publications vues, cache du LLM) est dans
`cache.json` à côté du fichier de session (`FACEBOOK_CACHE` pour le déplacer).

**Quand Facebook change son balisage**, seul `scraper/facebook/extract.py` est à adapter (ancres utilisées :
`role="article"`, liens permanents `/groups/<id ou alias>/posts|permalink/<id>`, `data-ad-preview="message"`).
Les tests s'appuient sur `tests/fixtures/facebook/group_feed.html`, à remplacer par une page réelle
enregistrée (données personnelles retirées).
