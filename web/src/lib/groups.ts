import type { ListingGroup, ListingGroupPage, ListingPage, ListingSummary } from "./types";

/** A listing on its own, shaped as a group, so the list renders one kind of item. */
export function single(listing: ListingSummary): ListingGroup {
  return {
    key: listing.id,
    buildingKey: null,
    address: listing.address,
    count: 1,
    totalInBuilding: 1,
    minPrice: listing.price,
    maxPrice: listing.price,
    minRoomsQc: listing.roomsQc,
    maxRoomsQc: listing.roomsQc,
    listings: [listing],
  };
}

export function asGroups(page: ListingPage): ListingGroupPage {
  return {
    content: page.content.map(single),
    page: page.page,
    totalGroups: page.totalElements,
    totalListings: page.totalElements,
    hasNext: page.hasNext,
  };
}
