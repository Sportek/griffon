# listings-api

API GraphQL (Spring Boot 4 + MongoDB) qui stocke les annonces du scraper (`../scraper`).
Spécifications : [CAHIER_DES_CHARGES.md](CAHIER_DES_CHARGES.md). Schéma : [`schema.graphqls`](src/main/resources/graphql/schema.graphqls).

## Lancer

```bash
# Tout en conteneurs (Mongo + API)
docker compose up -d --build               # API_PORT=8085 si 8080 est déjà pris

# Dev : Mongo en conteneur, API en local (Java 17+)
docker compose up -d mongo
./mvnw spring-boot:run

# MongoDB distant
MONGODB_URI="mongodb+srv://user:pass@cluster.example.net/listings" ./mvnw spring-boot:run
```

- GraphQL : `http://localhost:8080/graphql` — GraphiQL : `http://localhost:8080/graphiql`
- Santé : `http://localhost:8080/actuator/health`
- Tests : `./mvnw test` (Docker requis, Testcontainers démarre un MongoDB)

| Variable                   | Défaut                               | Rôle                                                       |
|----------------------------|--------------------------------------|------------------------------------------------------------|
| `MONGODB_URI`              | `mongodb://localhost:27017/listings` | Base locale ou distante                                    |
| `PORT`                     | `8080`                               |                                                            |
| `API_KEY`                  | *(vide = API ouverte)*               | Exige l'en-tête `X-API-Key` sur les mutations              |
| `API_KEY_PROTECT_QUERIES`  | `false`                              | Exige aussi la clé pour les lectures                       |
| `INACTIVITY_STALE_AFTER`   | `3d`                                 | Annonce non revue depuis ce délai → inactive               |
| `INACTIVITY_SWEEP_ENABLED` | `true`                               | Balayage horaire des annonces inactives                    |
| `GRAPHIQL_ENABLED`         | `true`                               |                                                            |
| `CORS_ALLOWED_ORIGINS`     | `*`                                  |                                                            |
| `SCHEDULER_ENABLED`        | `true`                               | Met en file les plannings échus (chaque minute)            |
| `RUN_RUNNING_TIMEOUT`      | `30m`                                | Exécution sans signe de vie → `FAILED` (worker planté)     |
| `RUN_QUEUED_TIMEOUT`       | `6h`                                 | Exécution jamais réclamée → `FAILED` (aucun worker)        |
| `OPS_WEBHOOK_URL` / `OPS_WEBHOOK_FORMAT` | *(vide)* / `JSON`      | Prévenu à chaque scrape en échec (`SLACK`, `DISCORD`)      |

Seuil d'inactivité par source : `listings.inactivity.stale-after-by-source.<source>: 7d` dans `application.yaml`.
Avec `docker compose`, les mêmes variables (et `API_PORT` / `MONGO_PORT` pour les ports hôte) sont transmises.

## Production

```bash
cp .env.prod.example .env.prod          # mots de passe : openssl rand -hex 32
docker compose -f compose.prod.yaml --env-file .env.prod up -d --build                    # Mongo + sauvegardes + API
docker compose -f compose.prod.yaml --env-file .env.prod --profile worker up -d --build    # + worker sur la même machine
```

- MongoDB avec authentification, jamais publié sur l'hôte ; `mongodump` quotidien dans `BACKUP_DIR` (14 jours gardés).
- API sur `127.0.0.1` uniquement, clé obligatoire (lectures comprises), GraphiQL coupé : mettre un reverse proxy HTTPS devant pour l'exposer.
- Worker ailleurs (ex. API sur Wyvern, worker sur Gremlin) : `../scraper/compose.worker.yaml`, il n'a besoin que de l'URL et de la clé.

### Planifier les scrapes

Le backend décide, le worker exécute. Cron Spring à 6 champs (`seconde minute heure jour mois jour-semaine`), fuseau `America/Toronto` par défaut :

```graphql
mutation {
  a: saveScrapeSchedule(input: { source: "duproprio",    cron: "0 0 2 * * *",  params: { markUnseenInactive: true } }) { nextRunAt }
  b: saveScrapeSchedule(input: { source: "kijiji",       cron: "0 0 4 * * *",  params: { markUnseenInactive: true } }) { nextRunAt }
  c: saveScrapeSchedule(input: { source: "centris",      cron: "0 0 6 * * *" }) { nextRunAt }
  d: saveScrapeSchedule(input: { source: "logis_quebec", cron: "0 0 8 * * *" }) { nextRunAt }
  e: saveScrapeSchedule(input: { source: "rentals_ca",   cron: "0 0 10 * * *", params: { areas: ["montreal", "laval"] } }) { nextRunAt }
}
mutation { triggerScrape(source: "kijiji", params: { limit: 50 }) { id status } }   # lancer maintenant
{ ingestionRuns(limit: 10) { source status trigger worker queuedAt startedAt finishedAt received created error } }
```

Une source n'a jamais deux exécutions en même temps : un créneau qui tombe pendant une exécution est sauté.

## Alimenter depuis le scraper

```bash
cd ../scraper
export LISTINGS_API_URL=http://localhost:8080/graphql   # défaut
export LISTINGS_API_KEY=...                              # si l'API a une API_KEY
python -m scraper.main duproprio --out api               # chaque source = une exécution journalisée
python -m scraper.main all --out api --mark-unseen-inactive   # scrape complet : désactive ce qui a disparu
```

`ApiSink` envoie **chaque** annonce vue (pas seulement les nouvelles) pour que l'API mette à
jour `lastSeenAt`, l'historique des prix et l'état actif. En Python :

```python
from scraper.api_sink import ApiSink

with ApiSink() as sink, sink.run("duproprio"):   # run() est optionnel
    sink.write(listing)                          # True si l'annonce est nouvelle pour l'API
```

Importer un JSONL existant :

```bash
cd ../scraper
python -m scraper.api_sink data/listings.jsonl [--url http://localhost:8080/graphql]
```

## Exemples de requêtes

```graphql
# Les 10 dernières annonces découvertes à Montréal
{ latestListings(limit: 10, filter: { cities: ["montreal"] }) { title price city url firstSeenAt } }

# 4 1/2 et plus, max 1800 $, avec stationnement, dans un rayon de 5 km
{
  listings(
    filter: { minRoomsQc: 4, maxPrice: 1800, amenities: ["Parking"],
              near: { latitude: 45.52, longitude: -73.58, radiusKm: 5 } }
    sort: PRICE_ASC, page: 0, size: 20
  ) {
    totalElements hasNext
    content { title price roomsQc address city priceHistory { price observedAt } }
  }
}

# Prix moyen par taille de logement
{ listingStats(filter: { sources: ["duproprio"] }) { count avgPrice byRoomsQc { key count avgPrice } } }

# Encore en ligne, sans doublons inter-sources, métro ou REM à 10 min, épicerie à distance de marche
{
  listings(filter: { active: true, excludeDuplicates: true, maxTransitWalkMinutes: 10,
                     nearbyCategories: ["grocery"], neighborhoods: ["Villeray/Saint-Michel/Parc-Extension"] }) {
    totalElements
    content { title price metroWalkMinutes url duplicates { source url price } }
  }
}

# Santé du scraper
{ ingestionRuns(limit: 10) { source status startedAt finishedAt received created rejected deactivated error } }
```

### Alertes

```graphql
mutation {
  createSavedSearch(input: {
    name: "4 1/2 Plateau < 1800 $"
    filter: { neighborhoods: ["Le Plateau-Mont-Royal"], minRoomsQc: 4, maxPrice: 1800, active: true }
    webhookUrl: "https://discord.com/api/webhooks/..."   # optionnel
    webhookFormat: DISCORD                                # JSON (défaut), SLACK ou DISCORD
    notifyOnPriceDrop: true
  }) { id }
}

# Sans webhook, consulter les alertes (nouvelles annonces et baisses de prix) :
{ alerts(since: "2026-10-24T00:00:00Z") { reason previousPrice price createdAt delivery listing { title url } } }
```

Avec `API_KEY`, ajouter l'en-tête `X-API-Key` (dans GraphiQL : onglet *Headers*, `{"X-API-Key": "..."}`).

Ingestion (ce que fait `ApiSink`) :

```graphql
mutation($listings: [ListingInput!]!) {
  upsertListings(listings: $listings) {
    received created updated unchanged rejected
    results { source externalId status error }
  }
}
```
