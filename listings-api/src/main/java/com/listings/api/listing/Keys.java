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
	 * Each source labels the same service its own way ("Heat", "Heated", "Chauffage"...):
	 * a few canonical keys, matched on the normalized label, let one filter cover them all.
	 * Both the labels' own keys and the canonical ones are stored.
	 */
	static final Map<String, List<String>> CANONICAL_UTILITIES = Map.of(
			"chauffage", List.of("heat", "chauff"),
			"eau chaude", List.of("hot water", "eau chaude"),
			"electricite", List.of("electric", "hydro"));

	static final Map<String, List<String>> CANONICAL_AMENITIES = Map.of(
			"balcon", List.of("balcon", "balcony", "terrace", "terrasse", "patio"),
			"laveuse secheuse", List.of("washer", "dryer", "laveuse", "secheuse", "laundry"),
			"lave vaisselle", List.of("dishwasher", "lave vaisselle"),
			"climatisation", List.of("air condition", "climatis"),
			"ascenseur", List.of("elevator", "ascenseur"),
			"stationnement", List.of("parking", "stationnement", "garage"),
			"cour", List.of("backyard", "yard", "cour"));

	static List<String> utilityKeys(List<String> labels) {
		return withCanonical(labels, CANONICAL_UTILITIES);
	}

	static List<String> amenityKeys(List<String> labels) {
		return withCanonical(labels, CANONICAL_AMENITIES);
	}

	private static List<String> withCanonical(List<String> labels, Map<String, List<String>> canonical) {
		if (labels == null) {
			return List.of();
		}
		List<String> keys = new java.util.ArrayList<>(normalize(labels));
		canonical.forEach((key, needles) -> {
			if (!keys.contains(key) && keys.stream().anyMatch(k -> needles.stream().anyMatch(k::contains))) {
				keys.add(key);
			}
		});
		return keys;
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
