import type { ListingSummary, TrackingStatus } from "./types";

export const SOURCE_NAMES: Record<string, string> = {
  duproprio: "DuProprio",
  kijiji: "Kijiji",
  centris: "Centris",
  logis_quebec: "Logis Québec",
  rentals_ca: "rentals.ca",
  realtor_ca: "realtor.ca",
};

export function sourceName(source: string): string {
  return SOURCE_NAMES[source] ?? source;
}

const money = new Intl.NumberFormat("fr-CA", { style: "currency", currency: "CAD", maximumFractionDigits: 0 });

export function formatPrice(price: number | null | undefined): string {
  return price == null ? "Prix non précisé" : money.format(price);
}

/** "1 450 $/mois", the period omitted when unknown. */
export function formatRent(listing: Pick<ListingSummary, "price" | "pricePeriod">): string {
  if (listing.price == null) return "Prix non précisé";
  const suffix = listing.pricePeriod === "MONTHLY" ? "/mois" : listing.pricePeriod === "YEARLY" ? "/an" : "";
  return money.format(listing.price) + suffix;
}

/** Short marker label: "1,4 k" past a thousand, so a map pin stays narrow. */
export function shortPrice(price: number | null): string {
  if (price == null) return "?";
  if (price < 1000) return `${Math.round(price)} $`;
  return `${(price / 1000).toLocaleString("fr-CA", { maximumFractionDigits: 1 })} k$`;
}

function half(rooms: number): string {
  const whole = Math.floor(rooms);
  return `${whole} ½`;
}

/**
 * The Québec size: "4 ½" as published, or "≈ 4 ½" inferred from the bedrooms (a 4 ½
 * has two bedrooms) when the source does not give it.
 */
export function formatSize(listing: Pick<ListingSummary, "roomsQc" | "bedrooms">): string | null {
  if (listing.roomsQc != null) return half(listing.roomsQc);
  if (listing.bedrooms != null) {
    return listing.bedrooms === 0 ? "≈ 1 ½" : `≈ ${half(listing.bedrooms + 2)}`;
  }
  return null;
}

export function formatBedrooms(bedrooms: number | null): string | null {
  if (bedrooms == null) return null;
  if (bedrooms === 0) return "Studio";
  return `${bedrooms} ch.`;
}

export function formatArea(areaSqft: number | null): string | null {
  return areaSqft == null ? null : `${Math.round(areaSqft).toLocaleString("fr-CA")} pi²`;
}

const relative = new Intl.RelativeTimeFormat("fr-CA", { numeric: "auto" });

/** "aujourd'hui", "hier", "il y a 3 jours", "il y a 2 semaines". */
export function ago(iso: string, now = Date.now()): string {
  const days = Math.round((new Date(iso).getTime() - now) / 86_400_000);
  if (days === 0) {
    const hours = Math.round((new Date(iso).getTime() - now) / 3_600_000);
    return hours === 0 ? "à l'instant" : relative.format(hours, "hour");
  }
  if (Math.abs(days) < 14) return relative.format(days, "day");
  if (Math.abs(days) < 60) return relative.format(Math.round(days / 7), "week");
  return relative.format(Math.round(days / 30), "month");
}

const dateFormat = new Intl.DateTimeFormat("fr-CA", { day: "numeric", month: "long", year: "numeric" });
const dateTimeFormat = new Intl.DateTimeFormat("fr-CA", {
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatDate(iso: string): string {
  return dateFormat.format(new Date(iso));
}

export function formatDateTime(iso: string): string {
  return dateTimeFormat.format(new Date(iso));
}

/** Availability as the source gives it: an ISO date, "immédiatement" or free text. */
export function formatAvailability(value: string | null): string | null {
  if (!value) return null;
  if (/^\d{4}-\d{2}-\d{2}/.test(value)) {
    const date = new Date(`${value.slice(0, 10)}T12:00:00`);
    return date.getTime() <= Date.now() ? "Disponible maintenant" : `Dès le ${dateFormat.format(date)}`;
  }
  return value;
}

export const NEW_LISTING_HOURS = 48;

export function isNew(firstSeenAt: string, now = Date.now()): boolean {
  return now - new Date(firstSeenAt).getTime() < NEW_LISTING_HOURS * 3_600_000;
}

/** The latest price drop, when the last observed price is below the one before it. */
export function priceDrop(listing: Pick<ListingSummary, "priceHistory" | "price">): number | null {
  const history = listing.priceHistory.filter((p) => p.price != null);
  if (history.length < 2 || listing.price == null) return null;
  const previous = history[history.length - 2].price as number;
  return listing.price < previous ? previous - listing.price : null;
}

export function walkLabel(minutes: number | null | undefined): string | null {
  return minutes == null ? null : `${Math.round(minutes)} min à pied`;
}

export const STATUSES: { value: TrackingStatus; label: string; color: string }[] = [
  { value: "TO_CONTACT", label: "À contacter", color: "var(--status-to-contact)" },
  { value: "CONTACTED", label: "Contacté", color: "var(--status-contacted)" },
  { value: "VISIT_PLANNED", label: "Visite prévue", color: "var(--status-visit-planned)" },
  { value: "VISITED", label: "Visité", color: "var(--status-visited)" },
  { value: "APPLIED", label: "Candidature", color: "var(--status-applied)" },
  { value: "REFUSED", label: "Refusé", color: "var(--status-refused)" },
  { value: "OBTAINED", label: "Obtenu", color: "var(--status-obtained)" },
];

export function statusMeta(status: TrackingStatus) {
  return STATUSES.find((s) => s.value === status) ?? STATUSES[0];
}

export const PROPERTY_TYPES: Record<string, string> = {
  apartment: "Appartement",
  condo: "Condo",
  house: "Maison",
  studio: "Studio",
  room: "Chambre",
  "duplex-triplex": "Plex",
  townhouse: "Maison de ville",
  loft: "Loft",
};

export function propertyTypeName(type: string | null): string | null {
  if (!type) return null;
  return PROPERTY_TYPES[type] ?? type.charAt(0).toUpperCase() + type.slice(1);
}

/** Canonical keys of listings-api (Keys.CANONICAL_UTILITIES / CANONICAL_AMENITIES). */
export const SERVICES = [
  { key: "chauffage", label: "Chauffé" },
  { key: "eau chaude", label: "Eau chaude incluse" },
  { key: "electricite", label: "Électricité incluse" },
];

export const AMENITIES = [
  { key: "balcon", label: "Balcon ou terrasse" },
  { key: "cour", label: "Cour" },
  { key: "laveuse secheuse", label: "Laveuse-sécheuse" },
  { key: "lave vaisselle", label: "Lave-vaisselle" },
  { key: "climatisation", label: "Climatisation" },
  { key: "ascenseur", label: "Ascenseur" },
];

/** Proximity categories of the scraper's enrichment, as the filter offers them. */
export const NEARBY = [
  { key: "grocery", label: "Épicerie" },
  { key: "pharmacy", label: "Pharmacie" },
  { key: "park", label: "Parc" },
  { key: "school", label: "École" },
  { key: "daycare", label: "Garderie" },
  { key: "convenience", label: "Dépanneur" },
  { key: "bakery", label: "Boulangerie" },
  { key: "gym", label: "Gym" },
  { key: "cafe", label: "Café" },
  { key: "bike_share", label: "BIXI" },
];

export const NEARBY_NAMES: Record<string, string> = {
  ...Object.fromEntries(NEARBY.map((n) => [n.key, n.label])),
  butcher: "Boucherie, fromagerie",
  alcohol: "SAQ",
  bank: "Banque",
  laundry: "Buanderie",
  hardware: "Quincaillerie",
  clinic: "Clinique",
  hospital: "Hôpital",
  dentist: "Dentiste",
  post_office: "Bureau de poste",
  library: "Bibliothèque",
  bus_stop: "Arrêt de bus",
  restaurant: "Restaurant",
};
