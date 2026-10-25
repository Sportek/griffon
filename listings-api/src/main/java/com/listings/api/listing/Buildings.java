package com.listings.api.listing;

import java.util.Locale;

/**
 * Which building a listing is in, so the units of one building can be shown together.
 * <p>
 * The key is the civic address without the unit, plus the city: two "100 rue Principale"
 * in different towns are different buildings. A listing without a usable address falls
 * back to its coordinates, but only when they are exact: a source that hides addresses
 * publishes a shared approximate point, which would merge unrelated buildings.
 */
final class Buildings {

	static final String KEY = "buildingKey";

	private Buildings() {
	}

	static String key(String address, String city, Double latitude, Double longitude, String locationPrecision) {
		String street = DuplicateDetector.streetKey(address);
		if (street != null) {
			String cityKey = Keys.normalize(city);
			return (cityKey != null) ? street + "|" + cityKey : street;
		}
		if (latitude != null && longitude != null && "exact".equals(locationPrecision)) {
			// ~10 m: the same building entrance, not the same block.
			return String.format(Locale.ROOT, "geo:%.4f,%.4f", latitude, longitude);
		}
		return null;
	}

}
