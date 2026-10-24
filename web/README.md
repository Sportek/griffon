# Griffon — interface web

Next.js (App Router) avec le design system [Vibe](https://vibe.monday.com) de monday.com.
Cahier des charges : [`CAHIER_DES_CHARGES.md`](CAHIER_DES_CHARGES.md).

| Page | Contenu |
|---|---|
| `/` | Recherche : critères essentiels, filtres avancés, liste et carte synchronisées, « M'alerter » |
| `/annonces/[id]` | Fiche : photos, essentiel, inclus, proximité métro/REM et commerces, historique du prix, repère de prix du quartier, doublons des autres sites, suivi |
| `/suivi` | Tableau des démarches par statut (À contacter → Obtenu), liste, annonces masquées |
| `/alertes` | Recherches sauvegardées (pause, Discord) et dernières annonces trouvées |

## Fonctionnement

- **Le navigateur ne parle jamais à `listings-api`.** Les pages serveur et les server actions
  (`src/app/actions.ts`) appellent l'API avec la clé (`src/lib/api.ts`, `server-only`).
- **La recherche vit dans l'URL** (`src/lib/search-params.ts`) : une recherche se partage ou se
  met en favori. Changer un critère navigue vers la nouvelle URL, rendue côté serveur.
- **Carte** : MapLibre sur les tuiles [OpenFreeMap](https://openfreemap.org) (gratuites, sans
  clé). Les étiquettes de prix sont dessinées par MapLibre (couche de symboles), pas en DOM, pour
  rester fluides avec des milliers d'annonces. Les stations de métro et du REM viennent de
  `src/data/transit_stations.json`, copie de celle du scraper.
- **Pas de compte** : l'application n'a qu'un utilisateur et doit être servie derrière
  Cloudflare Access.

Deux scripts tournent avant `dev` et `build` :

- `scripts/extract-vibe-css.mjs` : Vibe injecte ses styles depuis JavaScript, dans le navigateur
  seulement. Le script les écrit dans une feuille statique, pour que le rendu serveur arrive déjà
  stylé, et y ajoute le thème sombre sous `prefers-color-scheme`.
- `scripts/copy-maplibre-worker.mjs` : copie le worker de MapLibre dans `public/maplibre/`, que
  le bundler n'émet pas.

Certains composants Vibe (menus déroulants, onglets, modales) ne se rendent pas côté serveur :
ils sont montés dans le navigateur (`src/components/ClientOnly.tsx`), derrière un gabarit de même
taille.

## Développement

```bash
cp .env.example .env.local      # LISTINGS_API_URL (+ LISTINGS_API_KEY si l'API en exige une)
npm install
npm run dev                      # http://localhost:3000
npm run typecheck && npm run lint && npm run build
```

## Production

Image `Dockerfile` (sortie `standalone`), servie par le service `griffon-web` de
`../listings-api/compose.dokploy.yaml`, qui lui passe `LISTINGS_API_URL` et la clé de l'API.
