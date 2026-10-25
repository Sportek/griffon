import "server-only";

import type {
  Alert,
  FilterOptions,
  ListingDetail,
  ListingFilter,
  ListingGroupPage,
  ListingPage,
  ListingSort,
  MapPoint,
  SavedSearch,
  TrackedListing,
  Tracking,
  TrackingStatus,
} from "./types";

export class ApiError extends Error {}

const API_URL = process.env.LISTINGS_API_URL ?? "http://localhost:8080/graphql";

async function gql<T>(query: string, variables: Record<string, unknown> = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (process.env.LISTINGS_API_KEY) {
    headers["X-API-Key"] = process.env.LISTINGS_API_KEY;
  }
  let response: Response;
  try {
    response = await fetch(API_URL, {
      method: "POST",
      headers,
      body: JSON.stringify({ query, variables }),
      cache: "no-store",
      signal: AbortSignal.timeout(15_000),
    });
  } catch (error) {
    throw new ApiError(`L'API des annonces ne répond pas (${(error as Error).message}).`);
  }
  if (!response.ok) {
    throw new ApiError(`L'API des annonces a répondu ${response.status}.`);
  }
  const body = (await response.json()) as { data?: T; errors?: { message: string }[] };
  if (body.errors?.length) {
    throw new ApiError(body.errors.map((e) => e.message).join(" · "));
  }
  return body.data as T;
}

const TRACKING = `tracking { listingId favorite status notes visitAt hidden priceWhenTracked createdAt updatedAt }`;

const SUMMARY = `
  id source url title propertyType price pricePeriod address unit neighborhood city
  latitude longitude locationPrecision bedrooms bathrooms areaSqft roomsQc
  furnished petsAllowed parkingSpots availableDate utilitiesIncluded photos
  metroWalkMinutes remWalkMinutes firstSeenAt lastSeenAt active inactiveSince
  priceHistory { price observedAt }
  duplicates { id source price }
  ${TRACKING}
`;

export async function searchListings(filter: ListingFilter, sort: ListingSort, page: number, size = 30) {
  const data = await gql<{ listings: ListingPage }>(
    `query($filter: ListingFilter, $sort: ListingSort, $page: Int, $size: Int) {
      listings(filter: $filter, sort: $sort, page: $page, size: $size) {
        content { ${SUMMARY} } totalElements page totalPages hasNext
      }
    }`,
    { filter, sort, page, size },
  );
  return data.listings;
}

export async function searchGroups(filter: ListingFilter, sort: ListingSort, page: number, size = 30) {
  const data = await gql<{ listingGroups: ListingGroupPage }>(
    `query($filter: ListingFilter, $sort: ListingSort, $page: Int, $size: Int) {
      listingGroups(filter: $filter, sort: $sort, page: $page, size: $size) {
        content {
          key buildingKey address count totalInBuilding minPrice maxPrice minRoomsQc maxRoomsQc
          listings { ${SUMMARY} }
        }
        page totalGroups totalListings hasNext
      }
    }`,
    { filter, sort, page, size },
  );
  return data.listingGroups;
}

export async function countListings(filter: ListingFilter) {
  const data = await gql<{ listings: { totalElements: number } }>(
    `query($filter: ListingFilter) { listings(filter: $filter, size: 1) { totalElements } }`,
    { filter },
  );
  return data.listings.totalElements;
}

export async function mapListings(filter: ListingFilter, limit = 5000) {
  const data = await gql<{ mapListings: MapPoint[] }>(
    `query($filter: ListingFilter, $limit: Int) {
      mapListings(filter: $filter, limit: $limit) {
        id latitude longitude price roomsQc bedrooms locationPrecision firstSeenAt buildingKey
      }
    }`,
    { filter, limit },
  );
  return data.mapListings;
}

export async function getListing(id: string) {
  const data = await gql<{ listing: ListingDetail | null }>(
    `query($id: ID!) {
      listing(id: $id) {
        ${SUMMARY.replace("duplicates { id source price }", "")}
        externalId listingType region postalCode yearBuilt smokingAllowed leaseTerm amenities
        description agencyName publishedAt updatedAt proximity
        priceBenchmark { scope area median sampleSize deltaPercent }
        sameBuilding { ${SUMMARY} }
        duplicates { id source url price active lastSeenAt }
      }
    }`,
    { id },
  );
  return data.listing;
}

export async function getFilterOptions() {
  const data = await gql<{ filterOptions: FilterOptions }>(
    `{ filterOptions { sources cities neighborhoods propertyTypes amenities utilitiesIncluded } }`,
  );
  return data.filterOptions;
}

export async function trackedListings(hidden = false) {
  const data = await gql<{ trackedListings: TrackedListing[] }>(
    `query($hidden: Boolean) { trackedListings(hidden: $hidden) { tracking { listingId favorite status notes visitAt hidden priceWhenTracked createdAt updatedAt } listing { ${SUMMARY} } } }`,
    { hidden },
  );
  return data.trackedListings;
}

export interface TrackingInput {
  favorite?: boolean;
  status?: TrackingStatus;
  clearStatus?: boolean;
  notes?: string;
  visitAt?: string;
  clearVisitAt?: boolean;
  hidden?: boolean;
}

export async function updateTracking(listingId: string, input: TrackingInput) {
  const data = await gql<{ updateTracking: Tracking }>(
    `mutation($id: ID!, $input: TrackingInput!) {
      updateTracking(listingId: $id, input: $input) { listingId favorite status notes visitAt hidden priceWhenTracked createdAt updatedAt }
    }`,
    { id: listingId, input },
  );
  return data.updateTracking;
}

const SAVED_SEARCH = `
  id name webhookUrl webhookFormat notifyOnPriceDrop enabled createdAt lastAlertAt
  matches(size: 1) { totalElements }
  filter {
    sources cities neighborhoods propertyTypes minPrice maxPrice minBedrooms minRoomsQc maxRoomsQc
    minAreaSqft minBathrooms minParkingSpots furnished petsAllowed smokingAllowed amenities
    utilitiesIncluded hasPhotos text active excludeDuplicates excludeHidden maxTransitWalkMinutes buildingKeys
    nearbyCategories within { south west north east }
  }
`;

export async function savedSearches() {
  const data = await gql<{ savedSearches: SavedSearch[] }>(`{ savedSearches { ${SAVED_SEARCH} } }`);
  return data.savedSearches;
}

export interface SavedSearchInput {
  name: string;
  filter: ListingFilter;
  webhookUrl?: string | null;
  webhookFormat?: "JSON" | "SLACK" | "DISCORD";
  notifyOnPriceDrop?: boolean;
  enabled?: boolean;
}

export async function createSavedSearch(input: SavedSearchInput) {
  const data = await gql<{ createSavedSearch: SavedSearch }>(
    `mutation($input: SavedSearchInput!) { createSavedSearch(input: $input) { ${SAVED_SEARCH} } }`,
    { input },
  );
  return data.createSavedSearch;
}

export async function updateSavedSearch(id: string, input: SavedSearchInput) {
  const data = await gql<{ updateSavedSearch: SavedSearch }>(
    `mutation($id: ID!, $input: SavedSearchInput!) { updateSavedSearch(id: $id, input: $input) { ${SAVED_SEARCH} } }`,
    { id, input },
  );
  return data.updateSavedSearch;
}

export async function deleteSavedSearch(id: string) {
  const data = await gql<{ deleteSavedSearch: boolean }>(
    `mutation($id: ID!) { deleteSavedSearch(id: $id) }`,
    { id },
  );
  return data.deleteSavedSearch;
}

export async function recentAlerts(limit = 60) {
  const data = await gql<{ alerts: Alert[] }>(
    `query($limit: Int) { alerts(limit: $limit) { id reason previousPrice price createdAt savedSearch { id name } listing { ${SUMMARY} } } }`,
    { limit },
  );
  return data.alerts;
}
