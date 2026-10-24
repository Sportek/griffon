# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Next.js (SSR) en **BFF** : le navigateur ne parle jamais directement à `listings-api`, et la clé d'API reste côté serveur. Carte : MapLibre GL sur des tuiles OpenStreetMap servies par un fournisseur qui l'autorise (MapTiler ou Protomaps auto-hébergé), jamais les serveurs de tuiles publics d'OSM. Hébergement : Dokploy sur wyvern, derrière le tunnel Cloudflare existant. Domaine proposé : `griffon.gablandry.com`. L'app vit dans `web/`, à côté de `listings-api/` (GraphQL Spring Boot + MongoDB) et de `scraper/` (scraper et worker Python).

## Users

Un seul utilisateur au lancement : le propriétaire du projet, qui cherche un appartement à louer dans le Grand Montréal. Son but : trouver vite le bon logement dans un marché tendu. Il veut voir en un seul endroit toutes les annonces qui correspondent, de tous les sites et sans doublons, juger en quelques secondes si une annonce vaut un appel, suivre celles qu'il garde, et être le premier sur les nouveautés.

Les profils du §2 de `web/CAHIER_DES_CHARGES.md` (étudiant·e, jeune professionnel·le, famille, sans voiture, avec animal, nouvel arrivant, chasseur pressé, colocation/couple) décrivent les situations de recherche que le produit doit bien gérer. Ce ne sont pas des publics distincts au lancement.

## Product Purpose

Griffon remplace la surveillance, un par un, de six sites de location : DuProprio, Kijiji, Centris, Logis Québec, rentals.ca et realtor.ca. Chacun a ses propres filtres, ses doublons et ses alertes. Griffon les réunit en un seul ensemble d'annonces dédoublonné, filtrable et affichable sur une carte, avec un suivi personnel des démarches et des alertes.

Le produit réussit si aucune annonce pertinente n'est ratée, si chacune est vue peu après sa mise en ligne, et si le suivi (contacté, visite, candidature) tient en un seul endroit.

## Positioning

C'est la seule vue qui réunit les six sources de location québécoises et les dédoublonne entre elles. Sur chaque annonce, elle montre ce que les sites d'origine ne montrent pas : où elle est aussi publiée et à quel prix, l'historique et les baisses de prix, sa fraîcheur, et son retrait. Elle filtre sur les critères qui comptent au Québec : la taille « X ½ », le quartier, les minutes de marche jusqu'au métro ou au REM, le chauffage inclus, les animaux, le stationnement.

## Operating Context

- Usage surtout sur téléphone, souvent en déplacement ou juste après une alerte : la carte et les filtres doivent se manier au pouce. Usage aussi sur ordinateur, avec la carte et la liste côte à côte.
- Chercher un logement est un processus, pas une seule requête : garder → contacter → visite prévue (date) → visité → candidature → refusé / obtenu.
- Le contact se fait toujours sur le site d'origine. Griffon y renvoie et n'affiche jamais les coordonnées du propriétaire.
- Les données arrivent par les workers de scrape planifiés, via `listings-api`. Une annonce devient inactive quand elle n'est plus revue en ligne.

## Capabilities and Constraints

Déjà en place dans `listings-api` :
- ingestion ;
- recherche structurée : sources, ville, quartier, taille, prix, pièces, commodités, services, animaux/meublé/fumeur, plein texte, dates, rayon, minutes de marche jusqu'au métro ou au REM, commerces à proximité ;
- tris, dernières annonces, statistiques et options de filtres ;
- doublons inter-sources (`duplicateOf`), historique des prix, annonces inactives ;
- recherches sauvegardées avec alertes (livraison par webhook) ;
- planification des scrapes et clé d'API.

Contraintes :
- **Zone au lancement : le Grand Montréal** (Montréal, Laval, Longueuil et les couronnes).
- **Usage privé, pour un seul utilisateur.** Les photos et descriptions appartiennent aux sites d'origine et à leurs annonceurs : Griffon n'est pas republié publiquement.
- La couverture des données varie selon la source (§5 de `web/CAHIER_DES_CHARGES.md`). Une donnée absente s'affiche comme inconnue (« non précisé », ou « ≈ 4 ½ » quand la taille est déduite des chambres) ; elle n'est jamais exclue en silence. Une annonce à position approximative apparaît comme approximative sur la carte. Une annonce retirée n'est jamais présentée comme disponible.
- Français d'abord, avec le vocabulaire local : « 4 ½ », « chauffé », « semi-meublé », « 1er juillet ». L'anglais viendra plus tard.
- Les évolutions de l'API nécessaires au front sont listées au §7 de `web/CAHIER_DES_CHARGES.md` :
  - données par utilisateur, alertes par courriel ;
  - `bbox` et requête légère pour la carte ;
  - médianes par quartier ;
  - tris par prix au pi² et par distance ;
  - géocodage et rattachement aux quartiers ;
  - pagination par curseur, clé en lecture seule.

Décisions ouvertes :
- Comment réserver l'accès à un seul utilisateur : comptes par lien magique, comme dans le cahier, ou une couche d'accès devant l'app, par exemple Cloudflare Access. Les comptes ne sont pas indispensables au lancement.
- Où vivent les données personnelles (favoris, statuts, notes, annonces masquées) : dans `listings-api`, comme le recommande le cahier, ou dans le front.
- L'activation de l'enrichissement de proximité et du géocodage dans les plannings de scrape. La carte et les filtres métro/commerces en dépendent, et sans géocodage les annonces DuProprio n'ont pas de coordonnées.

## Brand Commitments

Nom : **Griffon**. Il n'existe encore ni logo, ni palette, ni identité visuelle.

## Evidence on Hand

- Annonces réelles issues des scrapes : `scraper/data/listings.jsonl` (34 annonces) et la base de production alimentée par les workers.
- Cahiers des charges : `web/CAHIER_DES_CHARGES.md` (cas d'usage UC1–UC12 avec priorités et critères d'acceptation) et `listings-api/CAHIER_DES_CHARGES.md`.
- Aucun témoignage, utilisateur, chiffre ou article de presse. Il ne faut pas en inventer.

## Product Principles

1. **Ne rien rater, ne jamais tromper.** Chaque annonce montre sa source et sa fraîcheur. Une annonce retirée ou périmée n'a jamais l'air disponible, et une donnée manquante se lit comme inconnue au lieu de disparaître.
2. **Décider en quelques secondes.** La carte d'annonce et la fiche mettent en tête ce qui décide un appel : le prix et ce qu'il inclut, la taille, le quartier, la disponibilité, les transports, la fraîcheur.
3. **Une annonce, toutes ses sources.** Les doublons sont regroupés et affichés, pas cachés : « aussi publiée sur », avec le prix de chaque site.
4. **L'étape suivante, c'est le site d'origine.** Griffon trouve et suit les annonces, et le contact se fait sur la source.
5. **Les mots du Québec, comme on les dit.** « 4 ½ », « chauffé », « 1er juillet », le métro et le REM sont des critères de premier plan, pas des traductions.

## Accessibility & Inclusion

WCAG 2.1 AA (contrastes, clavier, lecteurs d'écran). La carte a toujours une liste équivalente.
