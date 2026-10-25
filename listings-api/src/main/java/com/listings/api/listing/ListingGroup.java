package com.listings.api.listing;

import java.util.List;

/**
 * The matching listings of one building. A listing without a known building is a group of
 * its own, so a grouped result keeps every listing the flat one has.
 *
 * @param count matching listings in the group
 * @param totalInBuilding active listings of the building, matching or not (the count for a
 * listing alone)
 */
public record ListingGroup(
		String key,
		String buildingKey,
		String address,
		int count,
		int totalInBuilding,
		Double minPrice,
		Double maxPrice,
		Double minRoomsQc,
		Double maxRoomsQc,
		List<Listing> listings) {
}
