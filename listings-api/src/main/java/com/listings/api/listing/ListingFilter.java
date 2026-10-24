package com.listings.api.listing;

import java.time.Instant;
import java.util.List;

/** Search criteria. Also persisted as-is inside saved searches. */
public record ListingFilter(
		List<String> sources,
		List<String> cities,
		List<String> neighborhoods,
		String region,
		String postalCodePrefix,
		ListingType listingType,
		List<String> propertyTypes,
		Double minPrice,
		Double maxPrice,
		Double minBedrooms,
		Double maxBedrooms,
		Double minBathrooms,
		Double minRoomsQc,
		Double maxRoomsQc,
		Double minAreaSqft,
		Double maxAreaSqft,
		Integer minYearBuilt,
		Integer minParkingSpots,
		Boolean furnished,
		Boolean petsAllowed,
		Boolean smokingAllowed,
		List<String> amenities,
		List<String> utilitiesIncluded,
		Boolean hasPhotos,
		String text,
		Instant firstSeenAfter,
		Instant firstSeenBefore,
		Instant lastSeenAfter,
		Boolean active,
		Boolean excludeDuplicates,
		GeoFilter near,
		BoundingBox within,
		Double maxMetroWalkMinutes,
		Double maxRemWalkMinutes,
		Double maxTransitWalkMinutes,
		List<String> nearbyCategories,
		Boolean excludeHidden) {
}
