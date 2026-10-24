package com.listings.api.listing;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Comparator;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.WriteModel;
import org.bson.Document;
import org.bson.types.ObjectId;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Component;

/**
 * Groups listings that look like the same unit published on several sites.
 * <p>
 * Candidates share a {@code duplicateKey} (normalized civic address + bedrooms). Within a
 * group the canonical listing is the active one seen first; another listing is flagged
 * {@code duplicateOf} the canonical only if it comes from a <em>different</em> source and its
 * price is within {@link #MAX_PRICE_GAP} (same-source rows sharing an address are usually
 * distinct units of one building). This is a heuristic: common street names in different
 * towns can collide.
 */
@Component
class DuplicateDetector {

	static final String KEY = "duplicateKey";

	static final double MAX_PRICE_GAP = 0.10;

	static final String UNIT = "duplicateUnit";

	private static final Pattern UNIT_PREFIX = Pattern.compile("^\\s*(\\w+)\\s*-\\s*(?=\\d)");

	private static final Pattern CIVIC_NUMBER = Pattern.compile("\\d+[a-d]?");

	private static final Pattern UNIT_SUFFIX = Pattern.compile(
			"(?i)\\s*,?\\s*(?:#|\\b(?:app|apt|appartement|unit|unite|unité|suite|logement)\\b\\.?)\\s*([\\w-]+)");

	/** Street types and articles, dropped so "962 rue Verdier" matches "962 Verdier Street". */
	private static final Set<String> NOISE = Set.of("rue", "street", "st", "avenue", "ave", "av", "boulevard",
			"boul", "blvd", "bd", "chemin", "ch", "road", "rd", "place", "pl", "montee", "rang", "route", "rte",
			"drive", "dr", "cote", "croissant", "crescent", "cres", "terrasse", "impasse", "allee", "square", "carre",
			"promenade", "prom", "de", "du", "des", "la", "le", "les", "l", "d", "of", "the");

	private static final Map<String, String> DIRECTIONS = Map.of("ouest", "w", "west", "w", "o", "w", "est", "e",
			"east", "e", "nord", "n", "north", "n", "sud", "s", "south", "s");

	private final MongoTemplate mongo;

	DuplicateDetector(MongoTemplate mongo) {
		this.mongo = mongo;
	}

	/** Null when the listing has no civic address or no bedroom count to compare on. */
	static String key(String address, Double bedrooms) {
		if (address == null || bedrooms == null) {
			return null;
		}
		String street = UNIT_PREFIX.matcher(streetPart(address)).replaceFirst("");
		String stripped = UNIT_SUFFIX.matcher(street).replaceAll(" ");
		String normalized = Keys.normalize(stripped);
		if (normalized == null) {
			return null;
		}
		List<String> tokens = Arrays.stream(normalized.split(" "))
			.filter(t -> !NOISE.contains(t))
			.map(t -> DIRECTIONS.getOrDefault(t, t))
			.toList();
		// A civic number ("962", "962a"), not an ordinal street name ("36e avenue"), then a street name.
		boolean hasStreetName = tokens.stream().skip(1).anyMatch(t -> !DIRECTIONS.containsValue(t));
		if (tokens.isEmpty() || !CIVIC_NUMBER.matcher(tokens.get(0)).matches() || !hasStreetName) {
			return null;
		}
		String beds = (bedrooms == Math.rint(bedrooms)) ? String.valueOf(bedrooms.longValue()) : bedrooms.toString();
		return String.join(" ", tokens) + "|" + beds;
	}

	/** Unit / apartment number ("401-962 rue X", "app. 5516", "#3201"), lower-cased; null if none. */
	static String unit(String address) {
		if (address == null) {
			return null;
		}
		Matcher prefix = UNIT_PREFIX.matcher(address);
		if (prefix.find()) {
			return prefix.group(1).toLowerCase(Locale.ROOT);
		}
		Matcher suffix = UNIT_SUFFIX.matcher(address);
		return suffix.find() ? suffix.group(1).toLowerCase(Locale.ROOT) : null;
	}

	/**
	 * Number and street only: sources append the unit, city, province or postal code after
	 * commas ("36 rue de l'Aqueduc, Varennes, QC, J3X 1P4"), and some put a comma after the
	 * civic number ("1245, Rue De Bleury, app. 5516").
	 */
	private static String streetPart(String address) {
		String[] segments = address.split(",");
		String first = segments[0].trim();
		if (segments.length > 1 && CIVIC_NUMBER.matcher(first.toLowerCase(Locale.ROOT)).matches()) {
			return first + " " + segments[1].trim();
		}
		return first;
	}

	/** Recomputes canonical / duplicateOf for every listing sharing one of these keys. */
	void regroup(Collection<String> keys) {
		List<String> nonNull = keys.stream().filter(Objects::nonNull).distinct().toList();
		if (nonNull.isEmpty()) {
			return;
		}
		Document projection = new Document("source", 1).append(KEY, 1)
			.append("price", 1)
			.append("active", 1)
			.append("firstSeenAt", 1)
			.append("duplicateOf", 1)
			.append(UNIT, 1);
		Map<String, List<Document>> groups = mongo.getCollection(Listing.COLLECTION)
			.find(new Document(KEY, new Document("$in", nonNull)))
			.projection(projection)
			.into(new ArrayList<>())
			.stream()
			.collect(Collectors.groupingBy(d -> d.getString(KEY)));

		List<WriteModel<Document>> writes = new ArrayList<>();
		for (List<Document> group : groups.values()) {
			Document canonical = group.stream().min(CANONICAL_ORDER).orElseThrow();
			for (Document doc : group) {
				String target = (doc != canonical && isDuplicate(doc, canonical))
						? canonical.getObjectId("_id").toHexString() : null;
				if (!Objects.equals(target, doc.getString("duplicateOf"))) {
					writes.add(new UpdateOneModel<>(new Document("_id", doc.getObjectId("_id")),
							new Document("$set", new Document("duplicateOf", target))));
				}
			}
		}
		if (!writes.isEmpty()) {
			mongo.getCollection(Listing.COLLECTION).bulkWrite(writes);
		}
	}

	private static boolean isDuplicate(Document doc, Document canonical) {
		if (doc.getString("source").equals(canonical.getString("source"))) {
			return false;
		}
		// Two known, different unit numbers are two apartments of the same building.
		String unit = doc.getString(UNIT);
		String canonicalUnit = canonical.getString(UNIT);
		if (unit != null && canonicalUnit != null && !unit.equals(canonicalUnit)) {
			return false;
		}
		Double a = doc.getDouble("price");
		Double b = canonical.getDouble("price");
		return a == null || b == null || Math.abs(a - b) <= MAX_PRICE_GAP * Math.max(a, b);
	}

	/** Active first, then the earliest discovered, then by id for determinism. */
	private static final Comparator<Document> CANONICAL_ORDER = Comparator
		.comparing((Document d) -> Boolean.FALSE.equals(d.getBoolean("active")))
		.thenComparing(d -> d.getDate("firstSeenAt"), Comparator.nullsLast(Comparator.<Date>naturalOrder()))
		.thenComparing(d -> d.getObjectId("_id"), Comparator.<ObjectId>naturalOrder());

}
