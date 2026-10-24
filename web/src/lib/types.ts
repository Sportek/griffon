export type TrackingStatus =
  | "TO_CONTACT"
  | "CONTACTED"
  | "VISIT_PLANNED"
  | "VISITED"
  | "APPLIED"
  | "REFUSED"
  | "OBTAINED";

export type ListingSort =
  | "NEWEST"
  | "PRICE_ASC"
  | "PRICE_DESC"
  | "AREA_DESC"
  | "RECENTLY_UPDATED";

export interface BoundingBox {
  south: number;
  west: number;
  north: number;
  east: number;
}

/** Mirrors the API's ListingFilter input (only the fields the app uses). */
export interface ListingFilter {
  sources?: string[];
  cities?: string[];
  neighborhoods?: string[];
  propertyTypes?: string[];
  minPrice?: number;
  maxPrice?: number;
  minBedrooms?: number;
  minRoomsQc?: number;
  maxRoomsQc?: number;
  minAreaSqft?: number;
  minBathrooms?: number;
  minParkingSpots?: number;
  furnished?: boolean;
  petsAllowed?: boolean;
  smokingAllowed?: boolean;
  amenities?: string[];
  utilitiesIncluded?: string[];
  hasPhotos?: boolean;
  text?: string;
  firstSeenAfter?: string;
  active?: boolean;
  excludeDuplicates?: boolean;
  excludeHidden?: boolean;
  within?: BoundingBox;
  maxTransitWalkMinutes?: number;
  nearbyCategories?: string[];
}

export interface Tracking {
  listingId: string;
  favorite: boolean;
  status: TrackingStatus | null;
  notes: string | null;
  visitAt: string | null;
  hidden: boolean;
  priceWhenTracked: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface PricePoint {
  price: number | null;
  observedAt: string;
}

export interface ListingSummary {
  id: string;
  source: string;
  url: string;
  title: string | null;
  propertyType: string | null;
  price: number | null;
  pricePeriod: "MONTHLY" | "YEARLY" | "UNKNOWN";
  address: string | null;
  neighborhood: string | null;
  city: string | null;
  latitude: number | null;
  longitude: number | null;
  locationPrecision: string | null;
  bedrooms: number | null;
  bathrooms: number | null;
  areaSqft: number | null;
  roomsQc: number | null;
  furnished: boolean | null;
  petsAllowed: boolean | null;
  parkingSpots: number | null;
  availableDate: string | null;
  utilitiesIncluded: string[];
  photos: string[];
  metroWalkMinutes: number | null;
  remWalkMinutes: number | null;
  firstSeenAt: string;
  lastSeenAt: string;
  active: boolean;
  inactiveSince: string | null;
  priceHistory: PricePoint[];
  duplicates: { id: string; source: string; price: number | null }[];
  tracking: Tracking | null;
}

export interface NearbyStation {
  name: string;
  network: "metro" | "rem";
  lines: string[];
  walk_minutes: number;
}

export interface NearbyPlace {
  name: string | null;
  category: string;
  walk_minutes: number;
}

export interface Proximity {
  nearest_metro?: NearbyStation | null;
  nearest_rem?: NearbyStation | null;
  stations_within_walk?: NearbyStation[];
  essentials?: Record<string, { count: number; nearest?: NearbyPlace | null }>;
}

export interface PriceBenchmark {
  scope: "NEIGHBORHOOD" | "CITY";
  area: string;
  median: number;
  sampleSize: number;
  deltaPercent: number;
}

export interface ListingDetail extends Omit<ListingSummary, "duplicates"> {
  externalId: string;
  listingType: string;
  region: string | null;
  postalCode: string | null;
  yearBuilt: number | null;
  smokingAllowed: boolean | null;
  leaseTerm: string | null;
  amenities: string[];
  description: string | null;
  agencyName: string | null;
  publishedAt: string | null;
  updatedAt: string;
  proximity: Proximity | null;
  priceBenchmark: PriceBenchmark | null;
  duplicates: {
    id: string;
    source: string;
    url: string;
    price: number | null;
    active: boolean;
    lastSeenAt: string;
  }[];
}

export interface ListingPage {
  content: ListingSummary[];
  totalElements: number;
  page: number;
  totalPages: number;
  hasNext: boolean;
}

export interface MapPoint {
  id: string;
  latitude: number;
  longitude: number;
  price: number | null;
  roomsQc: number | null;
  bedrooms: number | null;
  locationPrecision: string | null;
  firstSeenAt: string;
}

export interface FilterOptions {
  sources: string[];
  cities: string[];
  neighborhoods: string[];
  propertyTypes: string[];
  amenities: string[];
  utilitiesIncluded: string[];
}

export interface SavedSearch {
  id: string;
  name: string;
  filter: ListingFilter;
  webhookUrl: string | null;
  webhookFormat: "JSON" | "SLACK" | "DISCORD";
  notifyOnPriceDrop: boolean;
  enabled: boolean;
  createdAt: string;
  lastAlertAt: string | null;
  matches: { totalElements: number };
}

export interface Alert {
  id: string;
  reason: "NEW_LISTING" | "PRICE_DROP";
  previousPrice: number | null;
  price: number | null;
  createdAt: string;
  savedSearch: { id: string; name: string } | null;
  listing: ListingSummary | null;
}

export interface TrackedListing {
  tracking: Tracking;
  listing: ListingSummary | null;
}
