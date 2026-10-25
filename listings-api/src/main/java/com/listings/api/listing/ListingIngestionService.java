package com.listings.api.listing;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.stream.Collectors;

import com.mongodb.bulk.BulkWriteResult;
import com.mongodb.bulk.BulkWriteUpsert;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.BulkWriteOptions;
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.UpdateOptions;
import com.mongodb.client.model.WriteModel;
import org.bson.Document;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

/**
 * Upserts scraped listings keyed by (source, externalId).
 * <p>
 * A content hash (every stored field except timestamps) decides between UPDATED and
 * UNCHANGED, so re-sending the same listing only refreshes lastSeenAt / seenCount and
 * reactivates it. Price changes are appended to priceHistory. Once written, duplicate
 * groups are recomputed and a {@link ListingsIngested} event is published (alerts).
 */
@Service
public class ListingIngestionService {

	private final MongoTemplate mongo;

	private final DuplicateDetector duplicates;

	private final ApplicationEventPublisher events;

	private final Clock clock;

	private final int maxBatchSize;

	public ListingIngestionService(MongoTemplate mongo, DuplicateDetector duplicates,
			ApplicationEventPublisher events, Clock clock,
			@Value("${listings.ingest.max-batch-size:1000}") int maxBatchSize) {
		this.mongo = mongo;
		this.duplicates = duplicates;
		this.events = events;
		this.clock = clock;
		this.maxBatchSize = maxBatchSize;
	}

	public IngestReport upsert(List<ListingInput> inputs) {
		return upsert(inputs, null);
	}

	/**
	 * @param expectedSource when non-null, listings from another source are rejected
	 * (used for ingestion runs, which belong to one source)
	 */
	public IngestReport upsert(List<ListingInput> inputs, String expectedSource) {
		if (inputs.size() > maxBatchSize) {
			throw new IllegalArgumentException(
					"Batch too large: " + inputs.size() + " listings (max " + maxBatchSize + "), split it");
		}
		String[] errors = new String[inputs.size()];
		// Last occurrence wins when the same listing appears twice in one batch.
		Map<String, ListingInput> valid = new LinkedHashMap<>();
		for (int i = 0; i < inputs.size(); i++) {
			ListingInput input = inputs.get(i);
			errors[i] = validate(input, expectedSource);
			if (errors[i] == null) {
				valid.put(input.key(), input);
			}
		}
		Map<String, IngestStatus> statuses = new HashMap<>();
		if (!valid.isEmpty()) {
			write(List.copyOf(valid.values()), statuses);
		}

		// Results mirror the input order so callers can zip them with what they sent.
		List<IngestResult> results = new ArrayList<>(inputs.size());
		for (int i = 0; i < inputs.size(); i++) {
			ListingInput input = inputs.get(i);
			IngestStatus status = (errors[i] != null) ? IngestStatus.REJECTED : statuses.get(input.key());
			results.add(new IngestResult(input.source(), input.externalId(), status, errors[i]));
		}
		return new IngestReport(inputs.size(), results);
	}

	private void write(List<ListingInput> inputs, Map<String, IngestStatus> statuses) {
		Map<String, Document> existing = loadExisting(inputs);
		Instant now = clock.instant();
		List<WriteModel<Document>> writes = new ArrayList<>();
		List<PriceDrop> priceDrops = new ArrayList<>();
		Set<String> duplicateKeys = new HashSet<>();

		for (ListingInput input : inputs) {
			Document current = existing.get(input.key());
			Document fields = fields(input);
			if (current != null) {
				keepEnrichment(fields, current);
			}
			String hash = contentHash(fields);
			String duplicateKey = fields.getString(DuplicateDetector.KEY);
			duplicateKeys.add(duplicateKey);
			if (current != null) {
				duplicateKeys.add(current.getString(DuplicateDetector.KEY));
			}

			Document set = new Document("lastSeenAt", now)
				.append("scrapedAt", (input.scrapedAt() != null) ? input.scrapedAt() : now)
				.append("active", true);
			// Derived fields are refreshed even when the content is unchanged, so a change to
			// how they are computed reaches every listing on its next scrape.
			DERIVED.stream().filter(fields::containsKey).forEach(key -> set.append(key, fields.get(key)));
			Document unset = new Document("inactiveSince", "");
			Document update = new Document("$inc", new Document("seenCount", 1));
			IngestStatus status;

			if (current == null || !hash.equals(current.getString("contentHash"))) {
				status = (current == null) ? IngestStatus.CREATED : IngestStatus.UPDATED;
				set.putAll(fields);
				set.append("contentHash", hash).append("updatedAt", now);
				if (!fields.containsKey("location")) {
					unset.append("location", "");
				}
				Double previousPrice = (current == null) ? null : current.getDouble("price");
				boolean priceChanged = input.price() != null && !Objects.equals(input.price(), previousPrice);
				Document onInsert = new Document("firstSeenAt", now);
				if (current == null) {
					onInsert.append("priceHistory", priceChanged ? List.of(pricePoint(input.price(), now)) : List.of());
				}
				else if (priceChanged) {
					update.append("$push", new Document("priceHistory", pricePoint(input.price(), now)));
					if (previousPrice != null && input.price() < previousPrice) {
						priceDrops.add(new PriceDrop(current.getObjectId("_id").toHexString(), previousPrice,
								input.price()));
					}
				}
				update.append("$setOnInsert", onInsert);
			}
			else {
				status = IngestStatus.UNCHANGED;
			}
			if (duplicateKey == null) {
				set.append("duplicateOf", null);
			}
			update.append("$set", set).append("$unset", unset);

			Document key = new Document("source", input.source()).append("externalId", input.externalId());
			writes.add(new UpdateOneModel<>(key, update, new UpdateOptions().upsert(true)));
			statuses.put(input.key(), status);
		}

		BulkWriteResult result = collection().bulkWrite(writes, new BulkWriteOptions().ordered(false));
		duplicates.regroup(duplicateKeys);

		List<String> createdIds = result.getUpserts()
			.stream()
			.map(BulkWriteUpsert::getId)
			.map(id -> id.asObjectId().getValue().toHexString())
			.toList();
		if (!createdIds.isEmpty() || !priceDrops.isEmpty()) {
			events.publishEvent(new ListingsIngested(createdIds, priceDrops));
		}
	}

	private static String validate(ListingInput input, String expectedSource) {
		if (isBlank(input.source()) || isBlank(input.externalId()) || isBlank(input.url())) {
			return "source, externalId and url must not be blank";
		}
		if (expectedSource != null && !expectedSource.equals(input.source())) {
			return "source " + input.source() + " does not match the ingestion run source " + expectedSource;
		}
		if (input.latitude() != null && Math.abs(input.latitude()) > 90) {
			return "latitude out of range: " + input.latitude();
		}
		if (input.longitude() != null && Math.abs(input.longitude()) > 180) {
			return "longitude out of range: " + input.longitude();
		}
		if (input.price() != null && input.price() < 0) {
			return "price must not be negative: " + input.price();
		}
		return null;
	}

	private Map<String, Document> loadExisting(List<ListingInput> inputs) {
		Map<String, List<String>> idsBySource = new HashMap<>();
		for (ListingInput input : inputs) {
			idsBySource.computeIfAbsent(input.source(), s -> new ArrayList<>()).add(input.externalId());
		}
		List<Document> or = idsBySource.entrySet()
			.stream()
			.map(e -> new Document("source", e.getKey()).append("externalId", new Document("$in", e.getValue())))
			.toList();
		Document projection = new Document("source", 1).append("externalId", 1)
			.append("contentHash", 1)
			.append("price", 1)
			.append(DuplicateDetector.KEY, 1)
			.append("proximity", 1)
			.append("latitude", 1)
			.append("longitude", 1)
			.append("locationPrecision", 1);
		return collection().find(new Document("$or", or))
			.projection(projection)
			.into(new ArrayList<>())
			.stream()
			.collect(Collectors.toMap(d -> d.getString("source") + ":" + d.getString("externalId"), d -> d));
	}

	/**
	 * A scrape run without enrichment sends neither proximity nor, for sources that publish
	 * no coordinates (DuProprio), a position: what an enriched run computed earlier is kept
	 * instead of being erased. A scrape that does send them replaces them as usual.
	 */
	static void keepEnrichment(Document fields, Document current) {
		boolean keepPosition = fields.get("latitude") == null && fields.get("longitude") == null
				&& current.get("latitude") != null && current.get("longitude") != null;
		if (keepPosition) {
			Double latitude = ((Number) current.get("latitude")).doubleValue();
			Double longitude = ((Number) current.get("longitude")).doubleValue();
			fields.append("latitude", latitude)
				.append("longitude", longitude)
				.append("locationPrecision", current.getString("locationPrecision"))
				.append("location", new Document("type", "Point").append("coordinates", List.of(longitude, latitude)))
				.append(Buildings.KEY, Buildings.key(fields.getString("address"), fields.getString("city"), latitude,
						longitude, current.getString("locationPrecision")));
		}
		if (fields.get("proximity") == null && current.get("proximity") instanceof Document proximity) {
			fields.append("proximity", proximity);
			ProximityFacts.appendTo(fields, proximity);
		}
	}

	private static Document fields(ListingInput in) {
		Document doc = new Document("url", in.url()).append("title", in.title())
			.append("listingType", in.listingType().name())
			.append("propertyType", in.propertyType())
			.append("price", in.price())
			.append("priceCurrency", in.priceCurrency())
			.append("pricePeriod", in.pricePeriod().name())
			.append("address", in.address())
			.append("neighborhood", in.neighborhood())
			.append(Keys.NEIGHBORHOOD, Keys.normalize(in.neighborhood()))
			.append("city", in.city())
			.append(Keys.CITY, Keys.normalize(in.city()))
			.append("region", in.region())
			.append("postalCode", in.postalCode())
			.append("country", in.country())
			.append("latitude", in.latitude())
			.append("longitude", in.longitude())
			.append("locationPrecision", in.locationPrecision())
			.append("bedrooms", in.bedrooms())
			.append("bathrooms", in.bathrooms())
			.append("areaSqft", in.areaSqft())
			.append("roomsQc", in.roomsQc())
			.append("yearBuilt", in.yearBuilt())
			.append("parkingSpots", in.parkingSpots())
			.append("furnished", in.furnished())
			.append("petsAllowed", in.petsAllowed())
			.append("smokingAllowed", in.smokingAllowed())
			.append("availableDate", in.availableDate())
			.append("leaseTerm", in.leaseTerm())
			.append("amenities", in.amenities())
			.append(Keys.AMENITIES, Keys.amenityKeys(in.amenities()))
			.append("utilitiesIncluded", in.utilitiesIncluded())
			.append(Keys.UTILITIES, Keys.utilityKeys(in.utilitiesIncluded()))
			.append("photos", in.photos())
			.append("description", in.description())
			.append("contactName", in.contactName())
			.append("agencyName", in.agencyName())
			.append("publishedAt", in.publishedAt())
			.append("extra", Keys.safeFieldNames(in.extra()))
			.append("proximity", Keys.safeFieldNames(in.proximity()))
			.append(DuplicateDetector.KEY, DuplicateDetector.key(in.address(), in.bedrooms()))
			.append(DuplicateDetector.UNIT, DuplicateDetector.unit(in.address()))
			.append(Buildings.KEY,
					Buildings.key(in.address(), in.city(), in.latitude(), in.longitude(), in.locationPrecision()));
		ProximityFacts.appendTo(doc, in.proximity());
		if (in.latitude() != null && in.longitude() != null) {
			doc.append("location",
					new Document("type", "Point").append("coordinates", List.of(in.longitude(), in.latitude())));
		}
		return doc;
	}

	private static Document pricePoint(Double price, Instant at) {
		return new Document("price", price).append("observedAt", at);
	}

	/**
	 * Fields computed from the scraped ones. They stay out of the content hash: changing how
	 * they are derived must not flag every listing as modified.
	 */
	private static final Set<String> DERIVED = Set.of(Keys.CITY, Keys.NEIGHBORHOOD, Keys.AMENITIES, Keys.UTILITIES,
			DuplicateDetector.KEY, DuplicateDetector.UNIT, Buildings.KEY, "location", "metroWalkMinutes",
			"remWalkMinutes", ProximityFacts.TRANSIT, ProximityFacts.CATEGORIES);

	private static String contentHash(Document fields) {
		@SuppressWarnings("unchecked")
		Map<String, Object> hashed = (Map<String, Object>) canonical(fields);
		hashed.keySet().removeAll(DERIVED);
		if (hashed.get("proximity") instanceof Map<?, ?> proximity) {
			// The enrichment timestamp changes on every run without the content changing.
			proximity.remove("computed_at");
		}
		try {
			byte[] digest = MessageDigest.getInstance("SHA-256")
				.digest(new Document(hashed).toJson().getBytes(StandardCharsets.UTF_8));
			return HexFormat.of().formatHex(digest);
		}
		catch (NoSuchAlgorithmException ex) {
			throw new IllegalStateException(ex);
		}
	}

	/** Deep copy with map keys sorted, so the hash does not depend on JSON key order. */
	private static Object canonical(Object value) {
		if (value instanceof Map<?, ?> map) {
			Map<String, Object> sorted = new TreeMap<>();
			map.forEach((k, v) -> sorted.put(String.valueOf(k), canonical(v)));
			return sorted;
		}
		if (value instanceof List<?> list) {
			return list.stream().map(ListingIngestionService::canonical).toList();
		}
		return value;
	}

	private static boolean isBlank(String s) {
		return s == null || s.isBlank();
	}

	private MongoCollection<Document> collection() {
		return mongo.getCollection(Listing.COLLECTION);
	}

	/** A price decrease observed on an already known listing. */
	public record PriceDrop(String listingId, double previousPrice, double price) {
	}

	/** Published after each write: what the alerting needs to know. */
	public record ListingsIngested(List<String> createdIds, List<PriceDrop> priceDrops) {
	}

}
