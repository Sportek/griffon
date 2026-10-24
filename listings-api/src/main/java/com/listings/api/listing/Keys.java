package com.listings.api.listing;

import java.text.Normalizer;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

/**
 * Normalized lookup keys stored next to the display values, so filters match
 * "Montréal", "MONTREAL" and "montreal" alike (and "Ste-Foy" / "Ste Foy").
 */
final class Keys {

	static final String CITY = "cityKey";

	static final String NEIGHBORHOOD = "neighborhoodKey";

	static final String AMENITIES = "amenityKeys";

	static final String UTILITIES = "utilityKeys";

	private Keys() {
	}

	static String normalize(String value) {
		if (value == null) {
			return null;
		}
		String stripped = Normalizer.normalize(value, Normalizer.Form.NFD).replaceAll("\\p{M}", "");
		String key = stripped.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9]+", " ").trim();
		return key.isEmpty() ? null : key;
	}

	static List<String> normalize(List<String> values) {
		return values.stream().map(Keys::normalize).filter(Objects::nonNull).distinct().toList();
	}

	/**
	 * Copy of a free-form JSON object whose keys are safe as MongoDB field names: scrapers
	 * build {@code extra} keys from page labels, which may contain "." or start with "$".
	 */
	@SuppressWarnings("unchecked")
	static Map<String, Object> safeFieldNames(Map<String, Object> map) {
		return (map == null) ? null : (Map<String, Object>) safeValue(map);
	}

	private static Object safeValue(Object value) {
		if (value instanceof Map<?, ?> map) {
			Map<String, Object> safe = new LinkedHashMap<>();
			map.forEach((k, v) -> safe.put(String.valueOf(k).replace('.', '_').replaceFirst("^\\$", "_"), safeValue(v)));
			return safe;
		}
		if (value instanceof List<?> list) {
			return list.stream().map(Keys::safeValue).toList();
		}
		return value;
	}

}
