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
		Boolean excludeHidden,
		List<String> buildingKeys,
		Integer maxYearBuilt,
		Double minLotAreaSqft,
		Double maxCondoFeesMonthly,
		Integer minUnits) {

	/** This filter restricted to one listing type (the other criteria unchanged). */
	public ListingFilter withListingType(ListingType type) {
		return new ListingFilter(sources, cities, neighborhoods, region, postalCodePrefix, type, propertyTypes, minPrice,
				maxPrice, minBedrooms, maxBedrooms, minBathrooms, minRoomsQc, maxRoomsQc, minAreaSqft, maxAreaSqft,
				minYearBuilt, minParkingSpots, furnished, petsAllowed, smokingAllowed, amenities, utilitiesIncluded,
				hasPhotos, text, firstSeenAfter, firstSeenBefore, lastSeenAfter, active, excludeDuplicates, near, within,
				maxMetroWalkMinutes, maxRemWalkMinutes, maxTransitWalkMinutes, nearbyCategories, excludeHidden,
				buildingKeys, maxYearBuilt, minLotAreaSqft, maxCondoFeesMonthly, minUnits);
	}

	/**
	 * Saved searches predate properties for sale: one without a listing type was a rental
	 * search, and must not start alerting on houses for sale.
	 */
	public static ListingFilter rentalsUnlessTyped(ListingFilter filter) {
		if (filter == null || filter.listingType() != null) {
			return filter;
		}
		return filter.withListingType(ListingType.RENT);
	}

}
