# Cahier des charges — listings-api

## 1. Contexte

Le scraper Python (`../scraper`) collecte des annonces de logements au Québec
(DuProprio, rentals.ca, d'autres sources à venir) et les écrit aujourd'hui dans un
fichier JSONL. **listings-api** devient le point de stockage central : le scraper
l'alimente, et les clients (front, scripts d'analyse, alertes…) l'interrogent.

## 2. Périmètre technique

| Élément        | Choix                                                                     |
|----------------|---------------------------------------------------------------------------|
| Langage        | Java 17+ (image Docker en Java 21)                                        |
| Framework      | Spring Boot 4.1, Spring for GraphQL, Spring Data MongoDB                  |
| Base           | MongoDB 7.0 (la 8.x ne démarre pas sur les noyaux Linux ≥ 6.19, SERVER-121912), en conteneur (`compose.yaml`) **ou** distante via `MONGODB_URI` |
| API            | GraphQL unique sur `/graphql`, GraphiQL sur `/graphiql`                   |
| Auth           | Aucune pour l'instant (voir §7)                                           |
| Supervision    | `/actuator/health`                                                        |

## 3. Modèle de données

### `listings` : une annonce, clé naturelle **unique** `(source, externalId)`
- **Champs scrapés** : miroir du modèle Python `Listing` : identité, type d'annonce et de bien,
  prix (devise, période), adresse, quartier, ville, région, code postal, pays, coordonnées et
  leur précision, chambres, salles de bain, superficie, `roomsQc` (« 4 1/2 »), année de
  construction, stationnements, meublé/animaux/fumeur, disponibilité, bail, commodités, services
  inclus, photos, description, contact/agence, date de publication, `extra` (JSON libre propre à
  la source), `proximity` (JSON de l'enrichissement métro/REM/commerces), `scrapedAt`.
- **Champs gérés par l'API** :
  - `firstSeenAt` / `lastSeenAt` / `updatedAt` / `seenCount` / `priceHistory[]` ;
  - `active` / `inactiveSince` : l'annonce est-elle encore en ligne ;
  - `duplicateOf` : id de l'annonce de référence si c'est un doublon inter-sources ;
  - extraits de `proximity` pour filtrer : `metroWalkMinutes`, `remWalkMinutes`,
    `transitWalkMinutes`, `nearbyCategories` ;
  - champs techniques : `contentHash`, `location` (GeoJSON), `duplicateKey`, `cityKey`,
    `neighborhoodKey`, `amenityKeys`, `utilityKeys` (valeurs normalisées).

### Autres collections
- `ingestionRuns` : une exécution du scraper pour une source (statut, dates, compteurs).
- `savedSearches` : filtre enregistré + webhook optionnel.
- `alerts` : une alerte (nouvelle annonce ou baisse de prix) par recherche et par annonce, avec statut de livraison.

## 4. Exigences fonctionnelles

### F1 — Ingestion par le scraper ✅
- Mutation `upsertListings(listings, runId?)`, lots de 1 à 1000 annonces, upsert **idempotent** par `(source, externalId)`.
- Rapport `received / created / updated / unchanged / rejected` + un résultat par annonce, dans l'ordre d'envoi.
- Une annonce invalide est **rejetée seule** ; le reste du lot est enregistré.
- Le hash de contenu ignore l'ordre des clés JSON et `proximity.computed_at` : ré-enrichir une annonce ne la marque pas « modifiée ».
- Client Python : `scraper/scraper/api_sink.py` (`ApiSink`), branché dans `main.py` via `--out api`.

### F2 — Consultation structurée ✅
- `listing(id)`, `listingByKey(source, externalId)`, `listings(filter, sort, page, size)` (offset, max 100).
- Filtres combinables (ET logique) :
  - source(s), ville(s), quartier(s) (insensibles aux accents et à la casse), région, préfixe de code postal, type d'annonce, type(s) de bien ;
  - bornes : prix, chambres, `roomsQc`, superficie, salles de bain, année de construction, stationnements ;
  - meublé, animaux, fumeur, photos, commodités et services (tous requis) ;
  - plein texte (titre, adresse, quartier, ville, description) ;
  - dates (découverte, dernière vue) ; `active` ; `excludeDuplicates` ;
  - géographie : rayon (`near`), minutes de marche max. jusqu'au métro / REM / l'un des deux, catégories de commerces à distance de marche.
- Tris : `NEWEST`, `OLDEST`, `PRICE_ASC`, `PRICE_DESC`, `AREA_DESC`, `RECENTLY_UPDATED`, `RECENTLY_SEEN`.

### F3 — Les plus récents ✅
- `latestListings(limit, since, filter)` par `firstSeenAt` décroissant ; une annonce revue ne remonte pas.

### F4 — Statistiques et aide aux filtres ✅
- `listingStats(filter)` (par source, ville, `roomsQc`) et `filterOptions` (sources, villes, quartiers, régions, types de bien, commodités, services).

### F5 — Administration ✅
- `deleteListing(id)`.

### F6 — Annonces inactives ✅
- **Balayage planifié** (toutes les heures par défaut) : une annonce non revue depuis `stale-after`
  (3 jours par défaut, surchargeable par source) passe `active=false` avec `inactiveSince`.
- **Fin d'exécution complète** : `finishIngestionRun(..., markUnseenInactive: true)` désactive les
  annonces de la source non revues pendant l'exécution (uniquement si `SUCCEEDED`).
- Une annonce revue est réactivée automatiquement. Déclenchement manuel : `sweepInactiveListings`.

### F7 — Journal d'ingestion ✅
- `startIngestionRun(source)` → `upsertListings(..., runId)` (compteurs cumulés, `lastBatchAt`) → `finishIngestionRun(id, status, error)`.
- Une exécution n'accepte que les annonces de sa source, et plus aucun lot une fois terminée.
- `ingestionRuns(source, status, limit)` pour suivre la santé du scraper (exécutions `FAILED`, `RUNNING` sans activité récente…).
- Côté Python, chaque source lancée avec `--out api` est journalisée automatiquement (`FAILED` si elle lève une exception).

### F8 — Doublons inter-sources ✅ (heuristique)
- Clé candidate : adresse civique normalisée (unité, type de voie, accents, langue et points cardinaux neutralisés) + nombre de chambres.
- Dans un groupe, l'annonce de référence est l'active découverte en premier ; une autre annonce est
  marquée `duplicateOf` seulement si elle vient d'une **autre source** et que son prix est à ±10 %.
- Recalcul à chaque ingestion et à chaque désactivation (une référence inactive passe la main).
- Exposé via `duplicateOf`, `duplicates` et le filtre `excludeDuplicates`.
- Limites connues : les rues homonymes dans des villes différentes peuvent se confondre ; les annonces sans numéro civique ou sans chambres ne sont jamais regroupées.

### F9 — Recherches sauvegardées et alertes ✅
- CRUD : `createSavedSearch`, `updateSavedSearch`, `deleteSavedSearch`, `savedSearch(es)` (avec le filtre et les `matches` actuels).
- À chaque ingestion, chaque recherche active est évaluée sur les **nouvelles** annonces (et sur les
  **baisses de prix** si `notifyOnPriceDrop`) → enregistrement dans `alerts`.
- Livraison asynchrone optionnelle par webhook (`JSON`, `SLACK`, `DISCORD`), statut `PENDING → SENT/FAILED` ;
  sans webhook, les alertes se consultent via `alerts(savedSearchId, since)`.
- Une recherche en erreur ne fait jamais échouer le lot du scraper.

### F10 — Clé d'API ✅
- Si `API_KEY` est défini, les mutations exigent l'en-tête `X-API-Key` (comparaison en temps constant) ;
  `API_KEY_PROTECT_QUERIES=true` protège aussi les lectures. Sans clé, l'API reste ouverte.

### F11 — Planification des scrapes par le backend ✅
- Plannings par source (`saveScrapeSchedule` : cron 6 champs, fuseau, paramètres `maxPages / areas / limit / enrich / markUnseenInactive`), stockés dans `scrapeSchedules`.
- Chaque minute, les plannings échus deviennent des exécutions `QUEUED` ; `triggerScrape` en crée une à la demande. Jamais deux exécutions actives pour une source (créneau sauté).
- Un ou plusieurs **workers** (`python -m scraper.worker`, image Docker dédiée) réclament les exécutions (`claimIngestionRun`, filtrable par source), envoient un heartbeat et les terminent. Ils ne font que des appels sortants vers l'API.
- Une exécution sans signe de vie depuis 30 min, ou jamais réclamée en 6 h, passe `FAILED` ; tout échec est notifié au webhook « ops » (optionnel).
- Un worker arrêté (SIGTERM) termine son exécution en `FAILED` avec la raison.

### F12 — Scraping poli ✅
- Pause aléatoire de 2 à 5 s entre deux requêtes HTTP (3 à 7 s pour les sources navigateur), respect de `Retry-After` et attente exponentielle sur 429/5xx.
- Arrêt de la source après 3 réponses 403/429 consécutives, plafond de requêtes par exécution ; l'exécution est `FAILED` avec la raison au lieu d'insister.

## 5. Exigences non fonctionnelles

- **Configuration** par variables d'environnement : `MONGODB_URI`, `PORT`, `GRAPHIQL_ENABLED`,
  `CORS_ALLOWED_ORIGINS`, `API_KEY`, `API_KEY_PROTECT_QUERIES`, `INACTIVITY_SWEEP_ENABLED`, `INACTIVITY_STALE_AFTER`.
- **Index** créés au démarrage (dont remplacement automatique de l'ancien index texte).
- **Erreurs** : validation → `BAD_REQUEST`, clé absente ou invalide → `UNAUTHORIZED`.
- **Tests** : 21 tests d'intégration sur un vrai MongoDB (Testcontainers) ; Docker requis pour `./mvnw test`.
- **Déploiement** : `compose.yaml` pour le dev ; `compose.prod.yaml` pour la production (MongoDB authentifié et non publié, sauvegardes quotidiennes, API sur 127.0.0.1 derrière un reverse proxy, clé obligatoire, GraphiQL coupé, worker optionnel) ; `../scraper/compose.worker.yaml` pour un worker sur une autre machine.
- **Hébergement recommandé** : worker sur une IP résidentielle (Gremlin) ; API + MongoDB sur Gremlin ou Wyvern.

## 6. Pistes restantes

1. **Normalisation des villes** : rattacher quartier → municipalité (« Le Plateau-Mont-Royal » → Montréal) quand la source ne fournit pas `neighborhood`.
2. **Pagination par curseur** pour les gros volumes.
3. **Sécurité avancée** : limiter la complexité/profondeur des requêtes ; vraie authentification si un front public est ajouté ; filtrer les webhooks vers des adresses internes (SSRF) si l'API devient multi-utilisateurs.
4. **Alertes temps réel** via `subscription` GraphQL (WebSocket) et/ou e-mail.
5. **Dédoublonnage plus fin** : coordonnées proches et superficie en plus de l'adresse, révision manuelle des groupes.
6. **Alerte de santé avancée** : notifier aussi quand une source réussit mais ne renvoie presque plus rien (changement de structure du site).
