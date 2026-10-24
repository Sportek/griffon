package com.listings.api.listing;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

/**
 * Read model of a stored listing. Writes go through {@link ListingIngestionService},
 * which also maintains the bookkeeping fields (firstSeenAt, lastSeenAt, priceHistory...).
 */
@Document(Listing.COLLECTION)
public record Listing(
		@Id String id,
		String source,
		String externalId,
		String url,
		String title,
		ListingType listingType,
		String propertyType,
		Double price,
		String priceCurrency,
		PricePeriod pricePeriod,
		String address,
		String neighborhood,
		String city,
		String region,
		String postalCode,
		String country,
		Double latitude,
		Double longitude,
		String locationPrecision,
		Double bedrooms,
		Double bathrooms,
		Double areaSqft,
		Double roomsQc,
		Integer yearBuilt,
		Integer parkingSpots,
		Boolean furnished,
		Boolean petsAllowed,
		Boolean smokingAllowed,
		String availableDate,
		String leaseTerm,
		List<String> amenities,
		List<String> utilitiesIncluded,
		List<String> photos,
		String description,
		String contactName,
		String agencyName,
		String publishedAt,
		Map<String, Object> extra,
		Map<String, Object> proximity,
		Double metroWalkMinutes,
		Double remWalkMinutes,
		Instant scrapedAt,
		Instant firstSeenAt,
		Instant lastSeenAt,
		Instant updatedAt,
		Integer seenCount,
		List<PricePoint> priceHistory,
		Boolean active,
		Instant inactiveSince,
		String duplicateOf) {

	public static final String COLLECTION = "listings";

	public Listing {
		amenities = (amenities == null) ? List.of() : amenities;
		utilitiesIncluded = (utilitiesIncluded == null) ? List.of() : utilitiesIncluded;
		photos = (photos == null) ? List.of() : photos;
		priceHistory = (priceHistory == null) ? List.of() : priceHistory;
		listingType = (listingType == null) ? ListingType.UNKNOWN : listingType;
		pricePeriod = (pricePeriod == null) ? PricePeriod.UNKNOWN : pricePeriod;
		seenCount = (seenCount == null) ? 0 : seenCount;
		// Documents stored before the "active" flag existed are still live.
		active = (active == null) || active;
	}

	/** Id of the canonical listing of this listing's duplicate group (itself when canonical). */
	String duplicateGroupId() {
		return (duplicateOf != null) ? duplicateOf : id;
	}

}
