# Griffon

Collecte et API des annonces de logements à louer au Québec.

| Dossier | Contenu |
|---|---|
| [`scraper/`](scraper/) | Scraper Python (DuProprio, Kijiji, Centris, Logis Québec, rentals.ca, realtor.ca), enrichissement de proximité, **worker** planifié |
| [`listings-api/`](listings-api/) | API GraphQL Spring Boot 4 + MongoDB : stockage, recherche, doublons, alertes, planification des scrapes |

```
           planifie (cron)          réclame / heartbeat / envoie
 listings-api  ──── QUEUED ────▶  worker (scraper)  ──── HTTP poli ───▶  sites d'annonces
   + MongoDB   ◀──── listings ───┘
```

## Démarrage rapide (dev)

```bash
cd listings-api && docker compose up -d --build          # API sur :8080 (+ MongoDB)
cd ../scraper && python -m pip install -r requirements.txt
LISTINGS_API_URL=http://localhost:8080/graphql python -m scraper.main duproprio --out api --limit 20
```

GraphiQL : http://localhost:8080/graphiql — exemples de requêtes dans [`listings-api/README.md`](listings-api/README.md).

## Tests

```bash
cd listings-api && ./mvnw verify               # Docker requis (Testcontainers)
cd scraper && pip install -r requirements-dev.txt && python -m pytest
```

La CI GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) lance les deux suites puis construit les images Docker.

## Production

- **Dokploy** : service Compose depuis ce repo, chemin `listings-api/compose.dokploy.yaml`, domaine sur le service `griffon-api` (port 8080). Variables : voir [`listings-api/.env.prod.example`](listings-api/.env.prod.example).
- **Sans Dokploy** : `listings-api/compose.prod.yaml`.
- **Worker sur une autre machine** (IP résidentielle conseillée) : `scraper/compose.worker.yaml`.

Détails : [`listings-api/README.md`](listings-api/README.md#production), [`scraper/README.md`](scraper/README.md), cahier des charges : [`listings-api/CAHIER_DES_CHARGES.md`](listings-api/CAHIER_DES_CHARGES.md).
