package com.listings.api.listing;

import java.util.List;
import java.util.Map;

import org.bson.Document;

/**
 * Pulls the filterable bits out of the scraper's free-form {@code proximity} blob
 * (Python {@code Proximity} model, snake_case keys). The blob itself is stored untouched,
 * so a change in its shape only degrades these derived fields to null.
 */
final class ProximityFacts {

	static final String TRANSIT = "transitWalkMinutes";

	static final String CATEGORIES = "nearbyCategories";

	private ProximityFacts() {
	}

	static void appendTo(Document doc, Map<String, Object> proximity) {
		Double metro = walkMinutes(proximity, "nearest_metro");
		Double rem = walkMinutes(proximity, "nearest_rem");
		Double transit = metro;
		if (transit == null || (rem != null && rem < transit)) {
			transit = rem;
		}
		doc.append("metroWalkMinutes", metro)
			.append("remWalkMinutes", rem)
			.append(TRANSIT, transit)
			.append(CATEGORIES, nearbyCategories(proximity));
	}

	private static Double walkMinutes(Map<String, Object> proximity, String station) {
		if (proximity != null && proximity.get(station) instanceof Map<?, ?> s
				&& s.get("walk_minutes") instanceof Number n) {
			return n.doubleValue();
		}
		return null;
	}

	/** Essentials categories with at least one place within walking distance. */
	private static List<String> nearbyCategories(Map<String, Object> proximity) {
		if (proximity == null || !(proximity.get("essentials") instanceof Map<?, ?> essentials)) {
			return List.of();
		}
		return essentials.entrySet()
			.stream()
			.filter(e -> e.getValue() instanceof Map<?, ?> summary && summary.get("count") instanceof Number n
					&& n.intValue() > 0)
			.map(e -> String.valueOf(e.getKey()))
			.sorted()
			.toList();
	}

}
