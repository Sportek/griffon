---
version: 1
slug: "web-src-app-page-tsx"
primary_target: "web/src/app/page.tsx"
related_targets: ["web/src/app"]
---

# Griffon web app (search, map, listing, follow-up, alerts)

Scope: the whole web app in `web/` (Next.js): search with list + map, listing page, follow-up board, alerts. Visitor mode: **Operate**. Single user (the owner), behind Cloudflare Access, no login.

Audience and job: the owner hunting a rental on the Island of Montréal, mostly on a phone right after an alert, also on desktop. Job: see every matching listing of six sites without duplicates, judge one in seconds, keep and follow up, never miss a new one.

Constraints: Vibe design system (monday.com) pinned by the user: its components, tokens, Figtree, light and dark themes. Data from the Java `listings-api` only, through the Next.js server (the key never reaches the browser). Contact happens on the source site. Unknown data reads "non précisé". A removed listing never looks available.

## Direction contract

THESIS: one list and one map over six sites, where every listing says up front its price and what it includes, its size, its area, its freshness and where else it is posted. Refuses the real-estate portal default: a photo grid with a hero search bar and sponsored cards.

OWN-WORLD: Vibe as shipped: white ground (#ffffff) on the light grey app frame (#f6f7fb), Figtree, `--primary-color` #0073ea for actions and selection, Vibe buttons, dropdowns, chips, tabs, modals, toasts. Signature move: monday's status column. The follow-up pipeline (À contacter → Obtenu) is set as monday's full-colour status pills, and the same colour language marks freshness on cards and map pins (new = green, price drop = orange, removed = grey).

STORY: the owner opens Griffon, sees today's new listings on the island first, narrows with essentials (budget, X ½, neighbourhood), scans list and map together, opens one, checks price vs the neighbourhood median and duplicates, stars it, moves it through the pipeline, and saves the search as an alert.

FIRST VIEWPORT: desktop: top bar (Griffon, Recherche / Suivi / Alertes), a filter row of essentials (budget, size, neighbourhoods, metro, more filters, save as alert) with the result count, then a split: listing cards column (≈ 420px) on the left, the map filling the right with price pins. Phone: same top bar, filter row scrolls horizontally, list by default with a floating Liste/Carte toggle at the bottom, map full screen.

FORM: monday-style work tool, assigned by the user's pinned design system (no roll). seed: none (unavailable)

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
