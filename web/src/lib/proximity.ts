import type { CategorySummary, NearbyPlace, Proximity } from "./types";

/** Categories in the order someone choosing a home looks for them. */
export const CATEGORY_ORDER = [
  "grocery",
  "pharmacy",
  "convenience",
  "bakery",
  "butcher",
  "park",
  "school",
  "daycare",
  "clinic",
  "hospital",
  "dentist",
  "bank",
  "alcohol",
  "laundry",
  "gym",
  "library",
  "post_office",
  "hardware",
  "cafe",
  "restaurant",
  "bike_share",
  "bus_stop",
];

export const CATEGORY_LABELS: Record<string, { one: string; many: string }> = {
  grocery: { one: "Épicerie", many: "Épiceries" },
  pharmacy: { one: "Pharmacie", many: "Pharmacies" },
  convenience: { one: "Dépanneur", many: "Dépanneurs" },
  bakery: { one: "Boulangerie", many: "Boulangeries" },
  butcher: { one: "Boucherie, fromagerie", many: "Boucheries, fromageries" },
  park: { one: "Parc", many: "Parcs" },
  school: { one: "École", many: "Écoles" },
  daycare: { one: "Garderie", many: "Garderies" },
  clinic: { one: "Clinique", many: "Cliniques" },
  hospital: { one: "Hôpital", many: "Hôpitaux" },
  dentist: { one: "Dentiste", many: "Dentistes" },
  bank: { one: "Banque", many: "Banques" },
  alcohol: { one: "SAQ", many: "SAQ et cavistes" },
  laundry: { one: "Buanderie", many: "Buanderies" },
  gym: { one: "Gym", many: "Gyms" },
  library: { one: "Bibliothèque", many: "Bibliothèques" },
  post_office: { one: "Bureau de poste", many: "Bureaux de poste" },
  hardware: { one: "Quincaillerie", many: "Quincailleries" },
  cafe: { one: "Café", many: "Cafés" },
  restaurant: { one: "Restaurant", many: "Restaurants" },
  bike_share: { one: "Station BIXI", many: "Stations BIXI" },
  bus_stop: { one: "Arrêt de bus", many: "Arrêts de bus" },
};

/** OpenStreetMap tag values, as a French reader names them. */
const KIND_LABELS: Record<string, string> = {
  supermarket: "Supermarché",
  greengrocer: "Fruiterie",
  grocery: "Épicerie",
  wholesale: "Grande surface",
  convenience: "Dépanneur",
  pharmacy: "Pharmacie",
  chemist: "Produits de santé",
  bakery: "Boulangerie",
  pastry: "Pâtisserie",
  butcher: "Boucherie",
  seafood: "Poissonnerie",
  cheese: "Fromagerie",
  deli: "Épicerie fine",
  alcohol: "Alcool",
  wine: "Vins",
  bank: "Banque",
  atm: "Guichet",
  laundry: "Buanderie",
  dry_cleaning: "Nettoyeur",
  hardware: "Quincaillerie",
  doityourself: "Rénovation",
  clinic: "Clinique",
  doctors: "Médecin",
  centre: "Centre de santé",
  hospital: "Hôpital",
  dentist: "Dentiste",
  post_office: "Bureau de poste",
  school: "École",
  childcare: "Garderie",
  kindergarten: "Garderie, maternelle",
  park: "Parc",
  fitness_centre: "Gym",
  library: "Bibliothèque",
  bus_stop: "Arrêt de bus",
  bicycle_rental: "Vélo en libre-service",
  restaurant: "Restaurant",
  fast_food: "Restauration rapide",
  cafe: "Café",
};

export function kindLabel(kind: string | null): string | null {
  if (!kind) return null;
  return KIND_LABELS[kind] ?? kind.replace(/_/g, " ");
}

export function categoryLabel(category: string, count = 1): string {
  const label = CATEGORY_LABELS[category];
  if (!label) return category.replace(/_/g, " ");
  return count > 1 ? label.many : label.one;
}

/** Shown when OpenStreetMap has no name, so each row still says what it is. */
export function placeName(place: NearbyPlace): string {
  return place.name?.trim() || place.brand || kindLabel(place.kind) || "Sans nom";
}

export function formatWalk(minutes: number): string {
  return `${Math.max(1, Math.round(minutes))} min`;
}

export function formatDistance(meters: number): string {
  return meters < 1000 ? `${Math.round(meters / 10) * 10} m` : `${(meters / 1000).toLocaleString("fr-CA", { maximumFractionDigits: 1 })} km`;
}

export interface CategoryEntry {
  key: string;
  summary: CategorySummary;
  places: NearbyPlace[];
}

/** Categories with at least one place, in reading order, unknown ones last. */
export function categories(proximity: Proximity | null): CategoryEntry[] {
  const essentials = proximity?.essentials ?? {};
  return Object.entries(essentials)
    .filter(([, summary]) => summary.count > 0)
    .map(([key, summary]) => ({
      key,
      summary,
      places: summary.places?.length ? summary.places : summary.nearest ? [summary.nearest] : [],
    }))
    .sort((a, b) => rank(a.key) - rank(b.key));
}

function rank(category: string) {
  const index = CATEGORY_ORDER.indexOf(category);
  return index === -1 ? CATEGORY_ORDER.length : index;
}

/** Kinds present in a category, most common first: offered as a sub-filter when there are several. */
export function kindsOf(places: NearbyPlace[]): { kind: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const p of places) {
    if (p.kind) counts.set(p.kind, (counts.get(p.kind) ?? 0) + 1);
  }
  return [...counts.entries()].map(([kind, count]) => ({ kind, count })).sort((a, b) => b.count - a.count);
}
