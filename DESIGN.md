---
name: Griffon
description: Toutes les annonces de location du Grand Montréal, en une liste et une carte, suivies comme un tableau monday.
colors:
  primary: "#0073ea"
  primary-hover: "#0060b9"
  primary-selected: "#cce5ff"
  surface: "#ffffff"
  app-frame: "#f6f7fb"
  text-primary: "#323338"
  text-secondary: "#676879"
  ui-border: "#c3c6d4"
  layout-border: "#d0d4e4"
  dark-surface: "#181b34"
  dark-frame: "#30324e"
  dark-text-primary: "#d5d8df"
  dark-text-secondary: "#9699a6"
  dark-ui-border: "#797e93"
  dark-layout-border: "#4b4e69"
  status-to-contact: "#579bfc"
  status-contacted: "#fdab3d"
  status-visit-planned: "#784bd1"
  status-visited: "#007eb5"
  status-applied: "#ffcb00"
  status-refused: "#df2f4a"
  status-obtained: "#00c875"
  status-ink: "#1f2029"
  signal-new: "#00854d"
  signal-drop: "#c2410c"
  signal-gone: "#676879"
typography:
  display:
    fontFamily: "Figtree, Roboto, Noto Sans, sans-serif"
    fontSize: "32px"
    fontWeight: 700
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Figtree, Roboto, Noto Sans, sans-serif"
    fontSize: "24px"
    fontWeight: 700
  title:
    fontFamily: "Figtree, Roboto, Noto Sans, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    letterSpacing: "-0.01em"
  title-sm:
    fontFamily: "Figtree, Roboto, Noto Sans, sans-serif"
    fontSize: "15px"
    fontWeight: 600
  body:
    fontFamily: "Figtree, Roboto, Noto Sans, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    fontFeature: "\"tnum\" 1"
  label:
    fontFamily: "Figtree, Roboto, Noto Sans, sans-serif"
    fontSize: "13px"
    fontWeight: 500
  caption:
    fontFamily: "Figtree, Roboto, Noto Sans, sans-serif"
    fontSize: "12px"
    fontWeight: 600
rounded:
  sm: "4px"
  md: "8px"
  full: "9999px"
spacing:
  "4": "4px"
  "8": "8px"
  "12": "12px"
  "16": "16px"
  "24": "24px"
  gutter: "16px"
  header-height: "56px"
  header-height-phone: "52px"
  filters-height: "64px"
  list-width: "clamp(360px, 34vw, 480px)"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    height: "32px"
    padding: "0 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
  nav-link:
    textColor: "{colors.text-secondary}"
    typography: "{typography.body}"
    padding: "0 12px"
    height: "{spacing.header-height}"
  nav-link-active:
    textColor: "{colors.primary}"
  listing-card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "12px"
  status-pill-to-contact:
    backgroundColor: "{colors.status-to-contact}"
    textColor: "{colors.status-ink}"
    rounded: "{rounded.sm}"
    typography: "{typography.body}"
    height: "32px"
    padding: "0 12px"
  status-pill-contacted:
    backgroundColor: "{colors.status-contacted}"
    textColor: "{colors.status-ink}"
    rounded: "{rounded.sm}"
    height: "32px"
  status-pill-visit-planned:
    backgroundColor: "{colors.status-visit-planned}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    height: "32px"
  status-pill-visited:
    backgroundColor: "{colors.status-visited}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    height: "32px"
  status-pill-applied:
    backgroundColor: "{colors.status-applied}"
    textColor: "{colors.status-ink}"
    rounded: "{rounded.sm}"
    height: "32px"
  status-pill-refused:
    backgroundColor: "{colors.status-refused}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    height: "32px"
  status-pill-obtained:
    backgroundColor: "{colors.status-obtained}"
    textColor: "{colors.status-ink}"
    rounded: "{rounded.sm}"
    height: "32px"
  status-select-cell:
    rounded: "{rounded.sm}"
    height: "40px"
    width: "100%"
  signal-new:
    backgroundColor: "{colors.signal-new}"
    textColor: "{colors.surface}"
    typography: "{typography.caption}"
    rounded: "{rounded.sm}"
    height: "20px"
    padding: "0 6px"
  signal-drop:
    backgroundColor: "{colors.signal-drop}"
    textColor: "{colors.surface}"
    typography: "{typography.caption}"
    rounded: "{rounded.sm}"
    height: "20px"
    padding: "0 6px"
  signal-gone:
    backgroundColor: "{colors.signal-gone}"
    textColor: "{colors.surface}"
    typography: "{typography.caption}"
    rounded: "{rounded.sm}"
    height: "20px"
    padding: "0 6px"
  map-pin:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.full}"
    height: "24px"
  map-pin-new:
    backgroundColor: "{colors.signal-new}"
    textColor: "{colors.surface}"
    rounded: "{rounded.full}"
    height: "24px"
  map-pin-active:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.full}"
    height: "24px"
  map-cluster:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.full}"
    size: "32px"
---

# Design System: Griffon

## Overview

**Creative North Star: "Le tableau de bord de la chasse"**

Griffon n'invente pas son monde visuel : c'est le design system Vibe de monday.com (`@vibe/core` 4.5.38, épinglé par l'utilisateur), utilisé tel qu'il est livré. Fond blanc sur le cadre gris clair de l'application, Figtree, le bleu monday pour les actions et la sélection, et les composants Vibe (boutons, dropdowns, chips, onglets, modales, toasts) sans restylage. L'outil se lit comme un outil de travail : dense, calme, chiffres alignés, aucune décoration.

Le geste signature vient de monday lui-même : la colonne de statut. Le pipeline de suivi (À contacter → Obtenu) s'affiche en blocs de statut pleine couleur, et la même grammaire de pastilles pleines marque la fraîcheur et le mouvement des prix sur les cartes (nouveau en vert, baisse de prix en orange, retirée en gris). Sur la carte, seul le signal « nouveau » colore les épingles ; la baisse de prix n'y apparaît pas dans la version livrée. Une couleur pleine veut toujours dire un état ; le reste de l'interface reste neutre pour que ces états se voient.

Le thème suit le système : clair par défaut, sombre Vibe (`.dark-app-theme`) quand l'appareil le demande, sans script ni flash, parce que les variables sombres sont recopiées sous une requête `prefers-color-scheme` dans la feuille Vibe générée.

**Key Characteristics:**
- Vibe tel que livré : ses variables CSS sont la source de vérité, jamais de valeurs codées en dur pour l'interface.
- Couleur pleine = état (statut de suivi ou signal d'annonce) ; tout le reste est neutre.
- Densité d'outil de travail : 14px par défaut, chiffres tabulaires, cartes compactes.
- Liste + carte côte à côte sur grand écran, une seule des deux à la fois sur téléphone.
- Thème clair et sombre suivant le système, sans flash.

## Colors

La palette est celle de Vibe : un bleu d'action unique sur des neutres gris-bleu, plus deux familles d'états empruntées à la colonne de statut de monday.

### Primary
- **Bleu monday** (`primary`) : actions principales (bouton « M'alerter »), lien de navigation actif et son soulignement, contour de focus (2px, décalage 2px), bordure de survol des cartes, épingle de l'annonce survolée, grappes de la carte, cercle de position approximative (à 8 % d'opacité, contour à 35 %). Survol en `primary-hover`, sélection de texte en `primary-selected`. Identique dans les deux thèmes.

### Secondary
- **Statuts de suivi** (`status-to-contact` bleu ciel, `status-contacted` orange, `status-visit-planned` violet, `status-visited` bleu pétrole, `status-applied` jaune, `status-refused` rouge, `status-obtained` vert) : la colonne de statut de monday appliquée au pipeline de location. Uniquement en remplissage plein (pastilles, cellules de sélection, en-têtes de colonnes du tableau Suivi). Mêmes valeurs dans les deux thèmes.

### Tertiary
- **Signaux d'annonce** (`signal-new` vert, `signal-drop` orange brûlé, `signal-gone` gris) : fraîcheur (« Nouveau », 48 h ou non vu depuis la dernière visite), baisse de prix (« −120 $ »), annonce retirée. Plus sombres que les statuts pour porter du texte blanc. Utilisée comme couleur de texte (« Moins cher sur… », changement de prix dans le suivi), la baisse passe par `--signal-drop-ink` : `#c2410c` en clair (5,2:1), `#ff9a5c` en sombre (8:1), parce que `#c2410c` tombe à 3,3:1 sur la surface sombre. `signal-new` remplit aussi les épingles des nouvelles annonces et la pastille de légende.

### Neutral
- **Surface** (`surface` / `dark-surface`) : cartes, barre du haut, barre de filtres, menus. `--primary-background-color`.
- **Cadre de l'app** (`app-frame` / `dark-frame`) : fond du `body`, colonne de liste, fond de carte en chargement. `--allgrey-background-color`.
- **Encre** (`text-primary` / `dark-text-primary`) : prix, titres, quartier. **Encre secondaire** (`text-secondary` / `dark-text-secondary`) : détails, méta, onglets inactifs.
- **Bordures** : `layout-border` pour les séparations de structure (sous la barre du haut, autour des cartes, entre liste et carte) ; `ui-border` pour les contrôles, les bordures pointillées des états vides et les barres de défilement (8px, arrondies).
- **Encre de statut** (`status-ink`) : le texte foncé posé sur les statuts clairs.

**Couleurs de données de la carte (hors système).** Les stations sont colorées selon les lignes réelles (verte `#00a650`, orange `#f08123`, jaune `#ffd100`, bleue `#0083ca`, REM `#7ac143`, repli gris `#676879`). Ce sont des couleurs d'identité du transport, pas des rôles d'interface : ne pas les réutiliser ailleurs.

### Named Rules
**The Full-Colour State Rule.** Une couleur saturée pleine signifie un état, rien d'autre : statut de suivi ou signal d'annonce. Aucun bouton, fond ou ornement n'emprunte ces teintes.

**The Status Ink Rule.** Sur les statuts clairs (`status-to-contact`, `status-contacted`, `status-applied`, `status-obtained`), le texte est `status-ink` ; sur les statuts foncés (`status-visit-planned`, `status-visited`, `status-refused`) et sur les trois signaux, il est blanc. Le blanc sur un statut clair tombe sous 4,5:1 ; toute nouvelle couleur d'état doit être classée d'un côté ou de l'autre par son contraste mesuré.

**The Vibe Variable Rule.** Les surfaces, textes et bordures passent par les variables Vibe (`--primary-background-color`, `--allgrey-background-color`, `--primary-text-color`, `--secondary-text-color`, `--layout-border-color`, `--ui-border-color`, `--primary-color`) pour que le thème sombre suive seul. Seuls les états (statuts, signaux) ont des valeurs fixes, déclarées dans `globals.css`.

## Typography

**Display Font:** Figtree (avec Roboto, Noto Sans, sans-serif)
**Body Font:** Figtree (même pile)

**Character:** Une seule famille, la grotesque arrondie de Vibe, servie par `next/font` sous `--font-figtree` et injectée dans `--font-family` et `--title-font-family`. La hiérarchie se fait par la graisse (400 / 500 / 600 / 700) et la taille, jamais par une deuxième famille. Tous les chiffres sont tabulaires (`font-variant-numeric: tabular-nums` sur le `body`) pour que les prix s'alignent.

### Hierarchy
- **Display** (700, 32px, −0,02em ; 26px sous 767px) : le prix en tête de la page d'annonce, seul élément de cette taille.
- **Headline** (700, 24px) : titre de page (Suivi, Alertes).
- **Title** (700, 18px, −0,01em ; 17px sous 767px) : prix sur la carte d'annonce, compte de résultats, nom « Griffon ». Faits clés de la page d'annonce en 600.
- **Title-sm** (600, 15px) : titre d'annonce sur la carte.
- **Body** (400, 14px) : quartier, détails, liens de navigation (en 500), fil d'Ariane. C'est la taille la plus employée.
- **Label** (500, 13px) : portée des résultats, petites pastilles de statut, liens de navigation sur téléphone.
- **Caption** (600, 12px) : signaux, méta des cartes (en 400), légende de la carte. 11px réservé au compteur de photos et à l'attribution de la carte.

Les étiquettes de la carte sont rendues par MapLibre en Noto Sans (Regular 11px pour les stations, Bold 12–13px pour les prix et les grappes) : contrainte des glyphes de tuiles, pas une seconde voix typographique.

### Named Rules
**The Weight Not Family Rule.** Figtree partout ; on hiérarchise par la graisse et la taille. Pas de capitales espacées, pas de surtitre au-dessus des titres.

## Layout

- **Barre du haut** : `header-height` (56px, 52px sous 767px), collante, fond surface, filet `layout-border` en bas, marges latérales `gutter` (16px) respectant `safe-area-inset`.
- **Barre de filtres** : hauteur minimale `filters-height` (64px), champs de largeur fixe (132 / 168 / 224px, réduits à 152 / 196px sous 1279px), écart 8px. Sous 1023px elle défile horizontalement avec accroche (`scroll-snap`) au lieu de passer à la ligne.
- **Recherche** : grille `list-width` + carte. La colonne de liste (fond `app-frame`, cartes espacées de 8px, en-tête de résultats collant) et la carte remplissent la hauteur restante. Sous 1023px : une seule colonne, liste ou carte, avec un sélecteur flottant Liste/Carte centré en bas (ombre large).
- **Page d'annonce** : conteneur centré de 1200px max, `gutter` latéral.
- **Suivi** : tableau à colonnes de 280px défilant horizontalement, écart 12px.
- **Rythme** : l'échelle `--space-*` de Vibe (4, 8, 12, 16, 24 en usage courant, 32–64 pour les respirations d'états vides).
- **Points de rupture** : 767px (téléphone), 1023px (tablette : la grille se replie), 1279px (resserrement des filtres) ; 599px ponctuellement dans les filtres avancés.

## Elevation & Depth

Le système est plat au repos : la profondeur vient des filets (`layout-border`) et de l'alternance surface / cadre. Les ombres Vibe n'apparaissent que sur ce qui flotte au-dessus d'autre chose ou en réponse à un état. En sombre, Vibe remplace ces ombres par sa propre version (`rgba(9, 11, 25, 0.5)`), automatiquement.

### Shadow Vocabulary
- **Petite** (`--box-shadow-small`) : survol ou mise en évidence d'une carte d'annonce, contrôles posés sur la carte (outils, zoom, légende).
- **Moyenne** (`--box-shadow-medium`) : menus déroulants (sélecteur de statut), bouton « Rechercher dans cette zone », aperçu d'annonce sur la carte.
- **Grande** (`--box-shadow-large`) : le sélecteur flottant Liste/Carte sur téléphone.

### Named Rules
**The Float-Only Shadow Rule.** Une ombre signifie « posé au-dessus » (sur la carte, en menu, en flottant) ou « survolé ». Une surface dans le flux n'a qu'un filet.

## Shapes

Deux rayons Vibe : `sm` (`--border-radius-small`) pour tout ce qui est petit ou en ligne (pastilles de statut, signaux, vignette photo, boutons, marque « G », contrôles de carte) et `md` (`--border-radius-medium`) pour les conteneurs (cartes d'annonce, menus, aperçu sur la carte, sélecteur flottant). Le plein arrondi est réservé à la carte : épingles de prix en gélule, grappes et stations en cercles. Les états vides utilisent une bordure pointillée `ui-border` d'1px. Le soulignement de l'onglet actif est une barre de 2px arrondie en haut.

## Components

### Buttons
- **Shape :** coins légèrement arrondis (4px).
- **Primary :** bouton Vibe primaire, `primary` sur texte blanc, hauteur 32px dans la barre de filtres (« M'alerter » avec icône cloche).
- **Hover / Focus :** `primary-hover` ; focus visible en contour `primary` de 2px décalé de 2px (global).
- **Secondary / Tertiary :** boutons Vibe secondaires (bordure `ui-border`, ex. « Filtres ») et tertiaires (outils de carte, sur fond surface avec petite ombre).

### Chips
- Chips et onglets Vibe tels que livrés (onglets Tableau / Liste / Masquées du Suivi, souligné `primary`).

### Cards / Containers
- **Corner Style :** 8px.
- **Background :** surface sur le cadre de l'app.
- **Shadow Strategy :** aucune au repos ; petite ombre et bordure `primary` au survol ou quand l'épingle correspondante est survolée.
- **Border :** 1px `layout-border`.
- **Internal Padding :** 12px (10px sous 767px), grille vignette carrée 128px (104px sur téléphone) + texte, écart 12px. Un lien étiré couvre toute la carte ; le favori (cœur) est en haut à droite au-dessus de lui. Une annonce retirée a sa photo en niveaux de gris à 60 % d'opacité.

### Inputs / Fields
- **Style :** dropdowns et champs Vibe (32px, bordure `ui-border`, 4px), curseur de saisie `primary`.
- **Focus :** bordure et contour `primary` de Vibe.

### Navigation
- Barre du haut : marque « G » (carré `primary` 28px, 4px) + « Griffon » en Title, puis Recherche / Suivi / Alertes avec icônes Vibe. Liens en Body 500 `text-secondary`, survol `text-primary`, actif en `primary` avec barre de 2px sous le lien. Sous 767px le nom disparaît et les liens passent à 13px.

### Status Pill / Status Select (signature)
Le bloc de statut monday : couleur pleine, libellé centré en 500, 4px de rayon. Pastille de 32px (min. 112px) ou 24px en petite taille (min. 96px, 13px). La cellule de sélection fait 40px (32px en petit) et s'assombrit au survol (`brightness(0.94)`, 70ms) ; son menu empile les sept statuts en blocs de 32px sur surface, bordure `layout-border`, 8px de rayon, ombre moyenne ; l'option choisie porte un contour de 2px couleur encre. « Sans statut » est une cellule pointillée neutre. Le texte suit la Status Ink Rule.

### Signals
Pastilles de 20px, 12px en 600, texte blanc, 4px de rayon, écart 4px : « Nouveau », « −montant », « Retirée ». Une annonce retirée n'affiche que « Retirée ».

### Map Pins
Épingles de prix dessinées par MapLibre (couche de symboles sur image étirable, pas de DOM) : gélule de 24px de haut, prix abrégé (« 1,7 k$ ») en Noto Sans Bold. Par défaut fond surface, contour `ui-border` (en sombre : `dark-frame` / `dark-ui-border`), texte encre ; nouvelle annonce en `signal-new` plein, texte blanc ; annonce survolée en `primary` plein. Les grappes sont des cercles `primary` à 92 % d'opacité, contour surface de 2px, rayon croissant avec le nombre (16 → 32px), compte blanc. Les stations sont des points couleur de ligne (3 → 6px selon le zoom), contour surface, plus épais aux correspondances, nom en 11px avec halo surface. Les icônes de contrôle MapLibre sont inversées en thème sombre.

## Do's and Don'ts

### Do:
- **Do** utiliser les composants et variables Vibe tels que livrés ; régénérer `vibe.generated.css` avec `scripts/extract-vibe-css.mjs` après toute montée de version.
- **Do** réserver les couleurs pleines aux états, et classer le texte de toute nouvelle couleur d'état par contraste mesuré (`status-ink` ou blanc, 4,5:1 minimum).
- **Do** garder une seule famille (Figtree) et des chiffres tabulaires.
- **Do** n'ajouter une ombre qu'à ce qui flotte ou répond à un survol.
- **Do** vérifier chaque écran dans les deux thèmes ; une couleur fixe posée en texte doit tenir 4,5:1 sur `surface` comme sur `dark-surface`.

### Don't:
- **Don't** restyler les composants Vibe ni coder des valeurs hexadécimales pour les surfaces, textes ou bordures.
- **Don't** utiliser une teinte de statut ou de signal comme couleur décorative, de bouton ou de fond de section.
- **Don't** mettre du texte blanc sur `status-to-contact`, `status-contacted`, `status-applied` ou `status-obtained`.
- **Don't** faire apparaître une annonce retirée comme disponible : signal `signal-gone`, photo désaturée.
- **Don't** ajouter de surtitres, de capitales espacées ou une seconde famille typographique.
