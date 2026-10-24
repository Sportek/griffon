package com.listings.api.listing;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/** What the scraper sends. Mirrors the Python {@code Listing} model. */
public record ListingInput(
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
		Instant scrapedAt) {

	public ListingInput {
		amenities = (amenities == null) ? List.of() : amenities;
		utilitiesIncluded = (utilitiesIncluded == null) ? List.of() : utilitiesIncluded;
		photos = (photos == null) ? List.of() : photos;
		listingType = (listingType == null) ? ListingType.RENT : listingType;
		pricePeriod = (pricePeriod == null) ? PricePeriod.MONTHLY : pricePeriod;
	}

	String key() {
		return source + ":" + externalId;
	}

}
