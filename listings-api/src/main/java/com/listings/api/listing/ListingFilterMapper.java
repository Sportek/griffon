package com.listings.api.listing;

import java.util.List;
import java.util.regex.Pattern;

import org.bson.Document;

/**
 * Translates a {@link ListingFilter} into a raw MongoDB query document. Raw documents
 * (rather than Spring Criteria) let the same filter feed find, count and aggregations.
 */
public final class ListingFilterMapper {

	private static final double EARTH_RADIUS_KM = 6378.1;

	private ListingFilterMapper() {
	}

	public static Document toQuery(ListingFilter filter) {
		Document query = new Document();
		if (filter == null) {
			return query;
		}
		if (notEmpty(filter.sources())) {
			query.append("source", new Document("$in", filter.sources()));
		}
		if (notEmpty(filter.cities())) {
			query.append(Keys.CITY, new Document("$in", Keys.normalize(filter.cities())));
		}
		if (notEmpty(filter.neighborhoods())) {
			query.append(Keys.NEIGHBORHOOD, new Document("$in", Keys.normalize(filter.neighborhoods())));
		}
		if (notEmpty(filter.propertyTypes())) {
			query.append("propertyType", new Document("$in", filter.propertyTypes()));
		}
		if (filter.region() != null) {
			query.append("region", Pattern.compile("^" + Pattern.quote(filter.region()) + "$", Pattern.CASE_INSENSITIVE));
		}
		if (filter.postalCodePrefix() != null) {
			String prefix = filter.postalCodePrefix().replace(" ", "");
			// Postal codes are stored as "G1W 4X8"; allow an optional space after the FSA.
			String regex = prefix.length() > 3 ? prefix.substring(0, 3) + " ?" + prefix.substring(3) : prefix;
			query.append("postalCode", Pattern.compile("^" + regex, Pattern.CASE_INSENSITIVE));
		}
		if (filter.listingType() != null) {
			query.append("listingType", filter.listingType().name());
		}

		range(query, "price", filter.minPrice(), filter.maxPrice());
		range(query, "bedrooms", filter.minBedrooms(), filter.maxBedrooms());
		range(query, "bathrooms", filter.minBathrooms(), null);
		range(query, "roomsQc", filter.minRoomsQc(), filter.maxRoomsQc());
		range(query, "areaSqft", filter.minAreaSqft(), filter.maxAreaSqft());
		range(query, "firstSeenAt", filter.firstSeenAfter(), filter.firstSeenBefore());
		range(query, "lastSeenAt", filter.lastSeenAfter(), null);
		range(query, "yearBuilt", filter.minYearBuilt(), null);
		range(query, "parkingSpots", filter.minParkingSpots(), null);
		range(query, "metroWalkMinutes", null, filter.maxMetroWalkMinutes());
		range(query, "remWalkMinutes", null, filter.maxRemWalkMinutes());
		range(query, ProximityFacts.TRANSIT, null, filter.maxTransitWalkMinutes());

		if (filter.furnished() != null) {
			query.append("furnished", filter.furnished());
		}
		if (filter.petsAllowed() != null) {
			query.append("petsAllowed", filter.petsAllowed());
		}
		if (filter.smokingAllowed() != null) {
			query.append("smokingAllowed", filter.smokingAllowed());
		}
		if (filter.active() != null) {
			// Documents without the flag predate it and count as active.
			query.append("active", filter.active() ? new Document("$ne", false) : false);
		}
		if (Boolean.TRUE.equals(filter.excludeDuplicates())) {
			query.append("duplicateOf", null);
		}
		if (notEmpty(filter.nearbyCategories())) {
			query.append(ProximityFacts.CATEGORIES, new Document("$all", filter.nearbyCategories()));
		}
		if (notEmpty(filter.amenities())) {
			query.append(Keys.AMENITIES, new Document("$all", Keys.normalize(filter.amenities())));
		}
		if (notEmpty(filter.utilitiesIncluded())) {
			query.append(Keys.UTILITIES, new Document("$all", Keys.normalize(filter.utilitiesIncluded())));
		}
		if (filter.hasPhotos() != null) {
			query.append("photos.0", new Document("$exists", filter.hasPhotos()));
		}
		if (filter.text() != null && !filter.text().isBlank()) {
			query.append("$text", new Document("$search", filter.text()));
		}
		if (filter.near() != null) {
			GeoFilter near = filter.near();
			if (near.radiusKm() <= 0) {
				throw new IllegalArgumentException("near.radiusKm must be > 0");
			}
			List<Object> center = List.of(List.of(near.longitude(), near.latitude()), near.radiusKm() / EARTH_RADIUS_KM);
			query.append("location", new Document("$geoWithin", new Document("$centerSphere", center)));
		}

		return query;
	}

	private static void range(Document query, String field, Object min, Object max) {
		if (min == null && max == null) {
			return;
		}
		Document range = new Document();
		if (min != null) {
			range.append("$gte", min);
		}
		if (max != null) {
			range.append("$lte", max);
		}
		query.append(field, range);
	}

	private static boolean notEmpty(List<?> list) {
		return list != null && !list.isEmpty();
	}

}
