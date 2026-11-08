import type { BoundingBox, ListingFilter, ListingSort } from "./types";

/**
 * The search lives in the URL, in short French keys, so a search can be bookmarked or
 * shared. Every key is optional; an empty URL is "every rental still online, without
 * duplicates or hidden listings, newest first". `offre=vente` switches to properties for sale.
 */
export interface SearchState {
  /** Properties for sale instead of rentals (the default). */
  offre?: "vente";
  q?: string;
  /** A query in Griffon's filter language, on top of the other criteria. */
  requete?: string;
  prixMin?: number;
  prixMax?: number;
  tailleMin?: number;
  tailleMax?: number;
  chambres?: number;
  quartiers?: string[];
  villes?: string[];
  metro?: number;
  commerces?: string[];
  animaux?: boolean;
  meuble?: boolean;
  stationnement?: boolean;
  services?: string[];
  commodites?: string[];
  types?: string[];
  sources?: string[];
  superficie?: number;
  sdb?: number;
  /** For sale: built in this year or later. */
  annee?: number;
  /** For sale: minimum lot area, ft². */
  terrain?: number;
  /** For sale: maximum condo fees, $ a month. */
  frais?: number;
  /** For sale: minimum number of dwellings (plexes). */
  logements?: number;
  photos?: boolean;
  depuis?: "24h" | "3j" | "7j";
  retirees?: boolean;
  /** "Rechercher dans cette zone": the map viewport, south,west,north,east. */
  zone?: BoundingBox;
  /** One card per listing instead of one per building. */
  unites?: boolean;
  tri?: ListingSort;
}

export const SORTS: { value: ListingSort; label: string }[] = [
  { value: "NEWEST", label: "Plus récentes" },
  { value: "PRICE_ASC", label: "Prix croissant" },
  { value: "PRICE_DESC", label: "Prix décroissant" },
  { value: "AREA_DESC", label: "Plus grandes" },
  { value: "RECENTLY_UPDATED", label: "Mises à jour récemment" },
];

type Params = Record<string, string | string[] | undefined> | URLSearchParams;

function read(params: Params, key: string): string | undefined {
  if (params instanceof URLSearchParams) {
    return params.get(key) ?? undefined;
  }
  const value = params[key];
  return Array.isArray(value) ? value[0] : value;
}

function num(value: string | undefined): number | undefined {
  if (value === undefined || value === "") return undefined;
  const n = Number(value.replace(",", "."));
  return Number.isFinite(n) ? n : undefined;
}

function list(value: string | undefined): string[] | undefined {
  const items = value
    ?.split("|")
    .map((v) => v.trim())
    .filter(Boolean);
  return items?.length ? items : undefined;
}

function bool(value: string | undefined): boolean | undefined {
  return value === "1" ? true : undefined;
}

function box(value: string | undefined): BoundingBox | undefined {
  const parts = value?.split(",").map(Number);
  if (!parts || parts.length !== 4 || parts.some((n) => !Number.isFinite(n))) return undefined;
  const [south, west, north, east] = parts;
  return south < north && west < east ? { south, west, north, east } : undefined;
}

export function formatZone(zone: BoundingBox): string {
  return [zone.south, zone.west, zone.north, zone.east].map((n) => n.toFixed(4)).join(",");
}

export function parseSearch(params: Params): SearchState {
  const depuis = read(params, "depuis");
  const tri = read(params, "tri") as ListingSort | undefined;
  return {
    offre: read(params, "offre") === "vente" ? "vente" : undefined,
    q: read(params, "q")?.trim() || undefined,
    requete: read(params, "requete")?.trim() || undefined,
    prixMin: num(read(params, "prix_min")),
    prixMax: num(read(params, "prix_max")),
    tailleMin: num(read(params, "taille_min")),
    tailleMax: num(read(params, "taille_max")),
    chambres: num(read(params, "chambres")),
    quartiers: list(read(params, "quartiers")),
    villes: list(read(params, "villes")),
    metro: num(read(params, "metro")),
    commerces: list(read(params, "commerces")),
    animaux: bool(read(params, "animaux")),
    meuble: bool(read(params, "meuble")),
    stationnement: bool(read(params, "stationnement")),
    services: list(read(params, "services")),
    commodites: list(read(params, "commodites")),
    types: list(read(params, "types")),
    sources: list(read(params, "sources")),
    superficie: num(read(params, "superficie")),
    sdb: num(read(params, "sdb")),
    annee: num(read(params, "annee")),
    terrain: num(read(params, "terrain")),
    frais: num(read(params, "frais")),
    logements: num(read(params, "logements")),
    photos: bool(read(params, "photos")),
    depuis: depuis === "24h" || depuis === "3j" || depuis === "7j" ? depuis : undefined,
    retirees: bool(read(params, "retirees")),
    zone: box(read(params, "zone")),
    unites: bool(read(params, "unites")),
    tri: SORTS.some((s) => s.value === tri) ? tri : undefined,
  };
}

const KEYS: Record<keyof SearchState, string> = {
  offre: "offre",
  q: "q",
  requete: "requete",
  prixMin: "prix_min",
  prixMax: "prix_max",
  tailleMin: "taille_min",
  tailleMax: "taille_max",
  chambres: "chambres",
  quartiers: "quartiers",
  villes: "villes",
  metro: "metro",
  commerces: "commerces",
  animaux: "animaux",
  meuble: "meuble",
  stationnement: "stationnement",
  services: "services",
  commodites: "commodites",
  types: "types",
  sources: "sources",
  superficie: "superficie",
  sdb: "sdb",
  annee: "annee",
  terrain: "terrain",
  frais: "frais",
  logements: "logements",
  photos: "photos",
  depuis: "depuis",
  retirees: "retirees",
  zone: "zone",
  unites: "unites",
  tri: "tri",
};

export function toQueryString(state: SearchState): string {
  const params = new URLSearchParams();
  for (const [field, key] of Object.entries(KEYS) as [keyof SearchState, string][]) {
    const value = state[field];
    if (value === undefined || value === "" || (Array.isArray(value) && value.length === 0)) continue;
    if (value === false) continue;
    const text =
      field === "zone"
        ? formatZone(value as BoundingBox)
        : Array.isArray(value)
          ? value.join("|")
          : value === true
            ? "1"
            : String(value);
    params.set(key, text);
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

const SINCE_HOURS = { "24h": 24, "3j": 72, "7j": 168 } as const;

export function isSale(state: SearchState): boolean {
  return state.offre === "vente";
}

/** Criteria that only mean something for one kind of offer. */
const RENT_ONLY: (keyof SearchState)[] = ["tailleMin", "tailleMax", "animaux", "meuble", "services"];
const SALE_ONLY: (keyof SearchState)[] = ["annee", "terrain", "frais", "logements"];

/**
 * Switching between rentals and properties for sale: a rent budget means nothing for a house,
 * so the price range goes, with the criteria of the kind left behind. Places, transit, dates
 * and the map zone stay.
 */
export function switchOffer(state: SearchState, sale: boolean): SearchState {
  if (sale === isSale(state)) return state;
  const cleared = Object.fromEntries([...(sale ? RENT_ONLY : SALE_ONLY), "prixMin", "prixMax"].map((k) => [k, undefined]));
  return { ...state, ...cleared, offre: sale ? "vente" : undefined };
}

export function toFilter(state: SearchState, now = Date.now()): ListingFilter {
  const sale = isSale(state);
  return {
    listingType: sale ? "SALE" : "RENT",
    text: state.q,
    query: state.requete,
    minPrice: state.prixMin,
    maxPrice: state.prixMax,
    minRoomsQc: sale ? undefined : state.tailleMin,
    maxRoomsQc: sale ? undefined : state.tailleMax,
    minBedrooms: state.chambres,
    neighborhoods: state.quartiers,
    cities: state.villes,
    maxTransitWalkMinutes: state.metro,
    nearbyCategories: state.commerces,
    petsAllowed: sale ? undefined : state.animaux,
    furnished: sale ? undefined : state.meuble,
    minParkingSpots: state.stationnement ? 1 : undefined,
    utilitiesIncluded: sale ? undefined : state.services,
    minYearBuilt: sale ? state.annee : undefined,
    minLotAreaSqft: sale ? state.terrain : undefined,
    maxCondoFeesMonthly: sale ? state.frais : undefined,
    minUnits: sale ? state.logements : undefined,
    amenities: state.commodites,
    propertyTypes: state.types,
    sources: state.sources,
    minAreaSqft: state.superficie,
    minBathrooms: state.sdb,
    hasPhotos: state.photos,
    firstSeenAfter: state.depuis
      ? new Date(now - SINCE_HOURS[state.depuis] * 3_600_000).toISOString()
      : undefined,
    active: state.retirees ? undefined : true,
    within: state.zone,
    excludeDuplicates: true,
    excludeHidden: true,
  };
}

/** The saved-search filter keeps no date window: "new since" is what an alert is about. */
export function toAlertFilter(state: SearchState): ListingFilter {
  const filter = toFilter({ ...state, depuis: undefined });
  return Object.fromEntries(Object.entries(filter).filter(([, v]) => v !== undefined)) as ListingFilter;
}

/** Back from a saved search's filter to the URL state, to open the alert as a search. */
export function fromFilter(filter: ListingFilter): SearchState {
  return {
    offre: filter.listingType === "SALE" ? "vente" : undefined,
    q: filter.text ?? undefined,
    requete: filter.query ?? undefined,
    prixMin: filter.minPrice ?? undefined,
    prixMax: filter.maxPrice ?? undefined,
    tailleMin: filter.minRoomsQc ?? undefined,
    tailleMax: filter.maxRoomsQc ?? undefined,
    chambres: filter.minBedrooms ?? undefined,
    quartiers: filter.neighborhoods ?? undefined,
    villes: filter.cities ?? undefined,
    metro: filter.maxTransitWalkMinutes ?? undefined,
    commerces: filter.nearbyCategories ?? undefined,
    animaux: filter.petsAllowed ?? undefined,
    meuble: filter.furnished ?? undefined,
    stationnement: (filter.minParkingSpots ?? 0) > 0 || undefined,
    services: filter.utilitiesIncluded ?? undefined,
    commodites: filter.amenities ?? undefined,
    types: filter.propertyTypes ?? undefined,
    sources: filter.sources ?? undefined,
    superficie: filter.minAreaSqft ?? undefined,
    sdb: filter.minBathrooms ?? undefined,
    annee: filter.minYearBuilt ?? undefined,
    terrain: filter.minLotAreaSqft ?? undefined,
    frais: filter.maxCondoFeesMonthly ?? undefined,
    logements: filter.minUnits ?? undefined,
    photos: filter.hasPhotos ?? undefined,
    retirees: filter.active === true ? undefined : true,
    zone: filter.within ?? undefined,
  };
}

/** Number of criteria set beyond the defaults, for the "Filtres (3)" button. */
export function countAdvanced(state: SearchState): number {
  const advanced: (keyof SearchState)[] = [
    "commerces",
    "animaux",
    "meuble",
    "stationnement",
    "services",
    "commodites",
    "types",
    "sources",
    "superficie",
    "sdb",
    "annee",
    "terrain",
    "frais",
    "logements",
    "photos",
    "retirees",
    "villes",
  ];
  // For sale, bedrooms sit in the bar (where the Québec size is for rentals).
  if (!isSale(state)) advanced.push("chambres");
  return advanced.filter((key) => {
    const value = state[key];
    return value !== undefined && !(Array.isArray(value) && value.length === 0);
  }).length;
}
