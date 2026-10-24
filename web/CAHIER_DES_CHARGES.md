# Cahier des charges — Interface web Griffon

> Objectif : permettre à une personne qui cherche un logement au Québec de **trouver vite l'appartement qui correspond à ses critères**, parmi les annonces de 6 sites réunies et dédoublonnées par Griffon, et de **ne rater aucune nouvelle annonce intéressante**.

## 1. Contexte et principe

Aujourd'hui, chercher un logement signifie surveiller DuProprio, Kijiji, Centris, Logis Québec, rentals.ca et realtor.ca séparément, avec des filtres différents, des doublons et aucune alerte commune. Griffon collecte déjà tout ça dans une seule base (`listings-api`). L'interface web en est la vitrine :

- **une seule recherche** sur toutes les sources, avec les critères qui comptent au Québec (le « 4 ½ », le quartier, le métro, les animaux, le stationnement…) ;
- **une carte et une liste** synchronisées ;
- **un suivi** des annonces retenues (favoris, statut, notes) ;
- **des alertes** dès qu'une nouvelle annonce correspond.

## 2. Profils d'utilisateurs

| Profil | Ce qu'il cherche | Critères typiques |
|---|---|---|
| **Étudiant·e** | Petit logement abordable près de son campus | 1 ½ à 3 ½, budget serré, métro/bus à pied, meublé, disponible au 1er juillet ou à la rentrée |
| **Jeune professionnel·le** | Bon emplacement, trajet court | 3 ½ – 4 ½, quartier précis, métro/REM < 10 min, commerces à proximité |
| **Famille** | De l'espace et un quartier pratique | 5 ½ et plus, 2-3 chambres, stationnement, école, parc et épicerie à pied |
| **Sans voiture** | Tout faire à pied ou en transport collectif | Métro ou REM proche, épicerie et pharmacie à distance de marche |
| **Avec animal** | Un propriétaire qui accepte chat ou chien | Animaux acceptés, cour ou balcon |
| **Nouvel arrivant** | Comprendre les quartiers et les prix avant de choisir | Comparaison des prix par quartier, carte, transports |
| **Chasseur pressé** | Être le premier à appeler (marché tendu) | Alerte immédiate, nouveautés du jour, baisses de prix |
| **Colocation / couple** | Chercher à deux, décider ensemble | Partage d'annonces et de listes, notes communes |

## 3. Cas d'usage

Priorité : **P1** = MVP, **P2** = deuxième version, **P3** = plus tard.

### UC1 — Rechercher avec ses critères (P1)
L'utilisateur indique ses critères et voit immédiatement les annonces correspondantes, **toutes sources confondues et sans doublons**.

- **Essentiels** (toujours visibles) : budget max (et min), taille « X ½ » et/ou nombre de chambres, quartiers ou villes, date d'emménagement souhaitée.
- **Avancés** (repliables) : type de bien, superficie min, salles de bain, stationnement, meublé, animaux acceptés, non-fumeur, services inclus (chauffage, eau chaude, électricité), commodités (balcon, laveuse-sécheuse, lave-vaisselle, climatisation…), année de construction, source.
- **Proximité** : métro ou REM à moins de N minutes de marche, commerces requis à pied (épicerie, pharmacie, école, parc, garderie…), rayon autour d'une adresse.
- **Texte libre** : « piscine », « terrasse », « rénové »…
- **Tri** : plus récentes, prix croissant/décroissant, plus grandes, prix au pi², plus proches du point de référence, baisses de prix récentes.
- L'URL reflète la recherche : on peut la mettre en favori ou la partager.
- Par défaut, seules les annonces **encore en ligne** et **sans doublons** sont affichées. Une option permet de voir les retirées.

**Critères d'acceptation** : un filtre modifié met les résultats à jour en moins d'une seconde ; le nombre de résultats est affiché ; une recherche sans résultat propose d'élargir le critère le plus restrictif (« 0 résultat à moins de 1 500 $, 14 à moins de 1 700 $ »).

### UC2 — Explorer sur une carte (P1)
- Carte et liste côte à côte (bureau) ou basculables (mobile), synchronisées : survoler une carte d'annonce la met en évidence sur la carte, et inversement.
- Regroupement des marqueurs quand on dézoome, avec le prix visible sur chaque marqueur.
- « Rechercher dans cette zone » quand on déplace la carte ; **dessiner une zone** à la main (P2).
- Couches optionnelles : stations de métro/REM (P1), limites de quartiers (P2).
- Les annonces à position **approximative** (adresse masquée sur Kijiji/realtor) sont signalées par un cercle plutôt qu'un point précis.

### UC3 — Consulter une annonce (P1)
Tout ce qu'il faut pour décider s'il vaut la peine d'appeler :
- photos, prix et ce qu'il inclut, taille (X ½, chambres, superficie), disponibilité, bail, animaux, stationnement, commodités ;
- **proximité** : métro/REM le plus proche et temps de marche, commerces et services à pied (épicerie, pharmacie, école, parc…) ;
- **historique du prix** (graphique) et badge « baisse de prix » ;
- **« Aussi publiée sur »** : les doublons des autres sites, avec leur prix — parfois moins cher ailleurs ;
- fraîcheur : « publiée il y a 3 jours », « vue en ligne pour la dernière fois hier », ou « retirée » ;
- **repère de prix** : comparaison avec le prix médian des logements similaires dans le quartier (« 8 % sous la médiane des 4 ½ de Rosemont ») ;
- bouton bien visible **« Voir l'annonce sur DuProprio »** (le contact se fait sur le site d'origine) ;
- actions : ajouter aux favoris, masquer, partager, comparer.

### UC4 — Garder un suivi de ses démarches (P1)
Chercher un logement, c'est un processus : on garde, on appelle, on visite, on décide.
- **Favoris** en un clic depuis la liste, la carte ou la fiche.
- **Statut** par annonce : *À contacter → Contacté → Visite prévue (date) → Visité → Candidature → Refusé / Obtenu*, présenté en liste ou en colonnes (kanban).
- **Notes** personnelles (« proprio sympa, bruit de rue »), date et heure de visite.
- **Masquer** une annonce (« pas intéressé ») : elle disparaît des résultats, y compris ses doublons.
- Une annonce suivie qui est **retirée** ou dont le **prix change** est signalée dans la liste de suivi.

### UC5 — Être alerté des nouvelles annonces (P1)
- Enregistrer la recherche en cours en un clic (« M'alerter »), avec un nom.
- Canal : **courriel** (P1), notification push navigateur ou mobile (P2), Discord/Telegram (P3).
- Fréquence : **immédiate** (marché tendu) ou **résumé quotidien**.
- Option « m'alerter aussi des baisses de prix ».
- Chaque alerte renvoie vers la fiche, avec un lien « ne plus recevoir ».
- Page « Mes alertes » : modifier, mettre en pause, supprimer ; voir les dernières annonces trouvées par chaque alerte.

### UC6 — Voir ce qui est nouveau (P1)
- Badge **« Nouveau »** sur les annonces apparues depuis la dernière visite.
- Vue « Nouveautés du jour » pour ses recherches sauvegardées.

### UC7 — Comparer des annonces (P2)
Deux à quatre annonces côte à côte : prix, prix au pi², taille, ce qui est inclus, transports, commerces, disponibilité. Les meilleures valeurs sont mises en évidence.

### UC8 — Comprendre le marché (P2)
Pour savoir si un prix est raisonnable et où chercher :
- prix médian par quartier et par taille (tableau et carte de chaleur) ;
- évolution des prix et du nombre d'annonces dans le temps ;
- « avec ton budget, voici où tu peux trouver un 4 ½ ».

### UC9 — Temps de trajet vers ses lieux importants (P2)
L'utilisateur enregistre 1 à 3 adresses (travail, école, garderie) et voit, pour chaque annonce, le temps de trajet à pied, en vélo ou en transport collectif. Il peut aussi filtrer : « moins de 30 min du travail ».

### UC10 — Chercher à plusieurs (P2)
Partager une liste de favoris ou une recherche avec un·e colocataire ou un·e conjoint·e, avec des notes et des votes (👍 / 👎) communs.

### UC11 — Compte et confidentialité (P1)
- Connexion sans mot de passe (lien magique par courriel) ou via Google.
- Les favoris, statuts, notes, recherches et alertes sont **privés** et propres à chaque compte.
- Export et suppression de ses données (Loi 25).

### UC12 — Administration (P2)
Réservée à l'administrateur : santé des scrapers (exécutions, échecs, volume par source), plannings, lancement manuel, statistiques d'usage.

## 4. Exigences non fonctionnelles

- **Mobile d'abord** : la plupart des recherches se font sur téléphone ; la carte et les filtres doivent être confortables au pouce.
- **Langue** : français d'abord, anglais ensuite (P2). Vocabulaire local : « 4 ½ », « chauffé », « semi-meublé », « 1er juillet ».
- **Performance** : premier affichage < 2 s sur mobile, filtres < 1 s, carte fluide avec quelques milliers d'annonces.
- **Accessibilité** : WCAG 2.1 AA (contrastes, clavier, lecteurs d'écran), la carte ayant toujours une alternative en liste.
- **Fiabilité de l'information** : afficher la source et la fraîcheur de chaque annonce ; ne jamais présenter une annonce retirée comme disponible.
- **Sécurité** : la clé de l'API n'est jamais envoyée au navigateur (voir §6).

## 5. Ce que les données permettent déjà, et leurs limites

D'après les scrapes réels, la couverture varie selon la source. L'interface doit le gérer avec élégance (critère « inconnu » plutôt qu'exclusion silencieuse) :

| Donnée | Couverture | Conséquence pour l'interface |
|---|---|---|
| Prix, chambres, photos | Toutes les sources | Fiables pour filtrer et trier |
| Taille « X ½ » | DuProprio, Kijiji, Logis Québec ; souvent absente ailleurs | La déduire des chambres quand elle manque (« ≈ 4 ½ ») |
| Coordonnées GPS | Toutes sauf DuProprio | Activer le **géocodage** des annonces DuProprio, sinon elles n'apparaissent pas sur la carte ni dans les filtres de proximité |
| Proximité (métro, commerces) | Seulement avec l'enrichissement `--enrich`, désactivé pour l'instant | À activer dans les plannings avant de proposer ces filtres (UC1, UC3) |
| Quartier | Centris, Logis Québec, realtor.ca | Pour les autres, déduire le quartier des coordonnées (polygones de quartiers) |
| Animaux, meublé, stationnement | Partielle | Proposer « oui / non / peu importe », et afficher « non précisé » |
| Disponibilité | Date ISO, « immédiatement » ou texte libre | Filtrer sur les dates connues, afficher le texte sinon |
| Contact du propriétaire | Parfois présent | **Ne pas l'afficher** : renvoyer vers l'annonce d'origine |

## 6. Architecture proposée

```
Navigateur ──HTTPS──▶ Front web (Next.js, SSR) ──GraphQL + X-API-Key──▶ listings-api ──▶ MongoDB
                         │  (la clé reste côté serveur)
                         └── comptes, favoris, suivi, alertes (base du front ou nouvelle partie de l'API)
```

- **Front** : Next.js (React) ou SvelteKit, avec rendu serveur pour la vitesse et le partage de liens. Il joue le rôle de **BFF** : c'est lui qui appelle l'API avec la clé, jamais le navigateur.
- **Carte** : MapLibre GL avec des tuiles OpenStreetMap via un fournisseur gratuit (MapTiler, Protomaps auto-hébergé) ; les serveurs de tuiles publics d'OSM interdisent l'usage intensif.
- **Hébergement** : Dokploy sur Wyvern, par exemple sur `griffon.gablandry.com`, derrière le même tunnel Cloudflare.

## 7. Évolutions nécessaires côté API

L'API actuelle couvre la recherche, la fiche, les doublons, l'historique des prix et les statistiques. Pour une interface grand public, il manque :

| Besoin (cas d'usage) | Évolution |
|---|---|
| Comptes et données privées (UC4, UC5, UC10, UC11) | Notion d'utilisateur : favoris, statuts, notes, annonces masquées, recherches sauvegardées par utilisateur (les recherches actuelles sont globales) |
| Alertes par courriel (UC5) | Canal courriel (SMTP ou service type Resend), résumé quotidien, lien de désabonnement |
| Carte (UC2) | Filtre par rectangle de carte (`bbox`) et requête légère dédiée à la carte (id, position, prix) pour afficher des milliers de marqueurs |
| Repère de prix (UC3, UC8) | Médiane par quartier et par taille, exposée sur la fiche et dans les statistiques |
| Tri par prix au pi² et par distance (UC1) | Nouveaux tris |
| Quartier et position manquants (§5) | Géocodage systématique, rattachement au quartier par polygones |
| Temps de trajet (UC9) | Calcul de trajets (OSRM pour la marche et le vélo, GTFS de la STM pour le transport collectif) |
| Grand volume (UC1, UC2) | Pagination par curseur |
| Clé d'API (§6) | Une clé « lecture seule » pour le front, distincte de la clé d'administration |

## 8. Proposition de découpage

| Version | Contenu | Pour qui |
|---|---|---|
| **MVP (P1)** | Recherche + filtres essentiels et avancés, carte/liste, fiche complète, favoris et statuts, alertes par courriel, badge « nouveau », compte par lien magique | Toi et tes proches, en usage privé |
| **V2 (P2)** | Comparateur, marché par quartier, trajets vers ses lieux, recherche à plusieurs, notifications push, zone dessinée, anglais, admin | Un cercle plus large |
| **V3 (P3)** | Application mobile installable (PWA), Discord/Telegram, recommandations (« ressemble à tes favoris ») | Ouverture éventuelle |

## 9. Points à trancher

1. **Usage privé ou public ?** Les photos et descriptions appartiennent aux sites d'origine et à leurs annonceurs, et republier ce contenu publiquement pose des questions de droits d'auteur et de conditions d'utilisation. **Recommandation : un MVP privé** (accès sur invitation), qui renvoie toujours vers l'annonce d'origine pour le contact.
2. **Combien d'utilisateurs ?** Toi seul, quelques proches, ou du public ? Ça décide si les comptes sont indispensables dès le MVP.
3. **Le front a-t-il sa propre base** (comptes, favoris) ou l'API gère-t-elle les utilisateurs ? Recommandation : dans l'API, pour que les alertes, qui sont côté serveur, connaissent les recherches de chaque utilisateur.
4. **Quelles villes ?** Grand Montréal seulement au départ, ou tout le Québec ? Ça influe sur la carte des quartiers et sur les plannings des scrapers.
5. **Activer l'enrichissement de proximité et le géocodage** : indispensable pour la carte et les filtres « métro à 10 min », mais ça rallonge chaque scrape et sollicite les serveurs d'OpenStreetMap. À valider.
