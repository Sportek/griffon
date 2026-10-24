package com.listings.api.listing;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import com.listings.api.tracking.Tracking;

import org.bson.Document;
import org.bson.types.ObjectId;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.BasicQuery;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ListingQueryService {

	static final int MAX_PAGE_SIZE = 100;

	static final int MAX_MAP_POINTS = 10_000;

	/** Fewer comparable listings than this in a neighbourhood falls back to the city. */
	static final int MIN_BENCHMARK_SAMPLE = 5;

	private final MongoTemplate mongo;

	public ListingQueryService(MongoTemplate mongo) {
		this.mongo = mongo;
	}

	public Optional<Listing> findById(String id) {
		return Optional.ofNullable(mongo.findById(id, Listing.class));
	}

	public Optional<Listing> findByKey(String source, String externalId) {
		Query query = Query.query(Criteria.where("source").is(source).and("externalId").is(externalId));
		return Optional.ofNullable(mongo.findOne(query, Listing.class));
	}

	public Map<String, Listing> findByIds(Collection<String> ids) {
		return mongo.find(Query.query(Criteria.where("_id").in(ids)), Listing.class)
			.stream()
			.collect(Collectors.toMap(Listing::id, Function.identity()));
	}

	public ListingPage search(ListingFilter filter, ListingSort sort, int page, int size) {
		if (page < 0) {
			throw new IllegalArgumentException("page must be >= 0");
		}
		if (size < 1 || size > MAX_PAGE_SIZE) {
			throw new IllegalArgumentException("size must be between 1 and " + MAX_PAGE_SIZE);
		}
		Document filterDoc = query(filter);
		long total = mongo.count(new BasicQuery(filterDoc), Listing.class);
		Query query = new BasicQuery(filterDoc).with(sort.toSort()).skip((long) page * size).limit(size);
		return new ListingPage(mongo.find(query, Listing.class), page, size, total);
	}

	public List<Listing> latest(int limit, Instant since, ListingFilter filter) {
		if (limit < 1 || limit > MAX_PAGE_SIZE) {
			throw new IllegalArgumentException("limit must be between 1 and " + MAX_PAGE_SIZE);
		}
		Document filterDoc = query(filter);
		if (since != null) {
			// "since" wins over filter.firstSeenAfter: it is the more specific intent.
			Document range = filterDoc.get("firstSeenAt", new Document());
			range.put("$gte", since);
			filterDoc.put("firstSeenAt", range);
		}
		Query query = new BasicQuery(filterDoc).with(ListingSort.NEWEST.toSort()).limit(limit);
		return mongo.find(query, Listing.class);
	}

	/** Marker data for every located listing matching the filter, newest first. */
	public List<MapPoint> mapPoints(ListingFilter filter, int limit) {
		if (limit < 1 || limit > MAX_MAP_POINTS) {
			throw new IllegalArgumentException("limit must be between 1 and " + MAX_MAP_POINTS);
		}
		Document filterDoc = query(filter);
		if (!filterDoc.containsKey("location")) {
			filterDoc.put("location", new Document("$exists", true));
		}
		Query query = new BasicQuery(filterDoc).with(ListingSort.NEWEST.toSort()).limit(limit);
		query.fields()
			.include("latitude", "longitude", "price", "roomsQc", "bedrooms", "locationPrecision", "firstSeenAt");
		return mongo.find(query, MapPoint.class, Listing.COLLECTION);
	}

	/**
	 * Median price of active, non-duplicate listings of the same size as this one, in its
	 * neighbourhood or, failing enough of them, its city. Null when there is nothing to compare.
	 */
	public PriceBenchmark priceBenchmark(Listing listing) {
		if (listing.price() == null || listing.price() <= 0) {
			return null;
		}
		Document base = new Document("_id", new Document("$ne", new ObjectId(listing.id()))).append("active", new Document("$ne", false))
			.append("duplicateOf", null)
			.append("listingType", listing.listingType().name())
			.append("pricePeriod", listing.pricePeriod().name())
			.append("price", new Document("$gt", 0));
		if (listing.roomsQc() != null) {
			base.append("roomsQc", listing.roomsQc());
		}
		else if (listing.bedrooms() != null) {
			base.append("bedrooms", listing.bedrooms());
		}
		else {
			return null;
		}
		String neighborhood = Keys.normalize(listing.neighborhood());
		if (neighborhood != null) {
			PriceBenchmark benchmark = benchmark(listing, new Document(base).append(Keys.NEIGHBORHOOD, neighborhood),
					"NEIGHBORHOOD", listing.neighborhood());
			if (benchmark != null) {
				return benchmark;
			}
		}
		String city = Keys.normalize(listing.city());
		return (city != null) ? benchmark(listing, base.append(Keys.CITY, city), "CITY", listing.city()) : null;
	}

	private PriceBenchmark benchmark(Listing listing, Document match, String scope, String area) {
		Document group = new Document("_id", null).append("count", new Document("$sum", 1))
			.append("median", new Document("$median", new Document("input", "$price").append("method", "approximate")));
		Document result = mongo.getCollection(Listing.COLLECTION)
			.aggregate(List.of(new Document("$match", match), new Document("$group", group)))
			.first();
		if (result == null || result.getInteger("count") < MIN_BENCHMARK_SAMPLE) {
			return null;
		}
		double median = ((Number) result.get("median")).doubleValue();
		double delta = (listing.price() - median) / median * 100;
		return new PriceBenchmark(scope, area, listing.roomsQc(), listing.bedrooms(), median, result.getInteger("count"),
				Math.round(delta * 10) / 10.0);
	}

	public boolean delete(String id) {
		return mongo.remove(Query.query(Criteria.where("_id").is(id)), Listing.class).getDeletedCount() > 0;
	}

	public ListingStats stats(ListingFilter filter) {
		Document match = new Document("$match", query(filter));
		Document facet = new Document("$facet", new Document()
			.append("overall", List.of(group(null)))
			.append("bySource", List.of(group("$source"), sortByCount()))
			.append("byCity", List.of(group("$city"), sortByCount(), new Document("$limit", 50)))
			.append("byRoomsQc", List.of(group("$roomsQc"), new Document("$sort", new Document("_id", 1)))));

		Document result = mongo.getCollection(Listing.COLLECTION)
			.aggregate(List.of(match, facet))
			.first();
		Objects.requireNonNull(result, "$facet always returns one document");

		List<StatsBucket> overall = buckets(result, "overall");
		StatsBucket all = overall.isEmpty() ? new StatsBucket(null, 0, null, null, null) : overall.get(0);
		return new ListingStats(all.count(), all.avgPrice(), all.minPrice(), all.maxPrice(),
				buckets(result, "bySource"), buckets(result, "byCity"), buckets(result, "byRoomsQc"));
	}

	public FilterOptions filterOptions() {
		return new FilterOptions(distinct("source"), distinct("city"), distinct("neighborhood"), distinct("region"),
				distinct("propertyType"), distinct("amenities"), distinct("utilitiesIncluded"));
	}

	/** The other members of the listing's duplicate group (canonical included), empty if none. */
	public List<Listing> duplicateGroup(Listing listing) {
		String groupId = listing.duplicateGroupId();
		Query query = Query.query(new Criteria().orOperator(Criteria.where("_id").is(groupId),
				Criteria.where("duplicateOf").is(groupId)))
			.addCriteria(Criteria.where("_id").ne(listing.id()))
			.with(ListingSort.OLDEST.toSort());
		return mongo.find(query, Listing.class);
	}

	/**
	 * The filter as a query document, plus what the mapper cannot know on its own: with
	 * {@code excludeHidden}, a hidden listing takes its whole duplicate group with it.
	 */
	private Document query(ListingFilter filter) {
		Document doc = ListingFilterMapper.toQuery(filter);
		if (filter == null || !Boolean.TRUE.equals(filter.excludeHidden())) {
			return doc;
		}
		Set<String> groups = hiddenGroups();
		if (groups.isEmpty()) {
			return doc;
		}
		// _id is an ObjectId while duplicateOf holds its hex string.
		List<ObjectId> ids = groups.stream().filter(ObjectId::isValid).map(ObjectId::new).toList();
		return new Document("$and", List.of(doc, new Document("_id", new Document("$nin", ids)),
				new Document("duplicateOf", new Document("$nin", groups))));
	}

	private Set<String> hiddenGroups() {
		List<String> hidden = mongo.find(Query.query(Criteria.where("hidden").is(true)), Tracking.class)
			.stream()
			.map(Tracking::listingId)
			.toList();
		Set<String> groups = new HashSet<>(hidden);
		Query duplicates = Query.query(Criteria.where("_id").in(hidden).and("duplicateOf").ne(null));
		duplicates.fields().include("duplicateOf");
		mongo.find(duplicates, Listing.class).forEach(l -> groups.add(l.duplicateOf()));
		return groups;
	}

	private List<String> distinct(String field) {
		return mongo.findDistinct(new Query(), field, Listing.class, String.class)
			.stream()
			.filter(Objects::nonNull)
			.sorted(String.CASE_INSENSITIVE_ORDER)
			.toList();
	}

	private static Document group(String key) {
		return new Document("$group", new Document("_id", key).append("count", new Document("$sum", 1))
			.append("avgPrice", new Document("$avg", "$price"))
			.append("minPrice", new Document("$min", "$price"))
			.append("maxPrice", new Document("$max", "$price")));
	}

	private static Document sortByCount() {
		return new Document("$sort", new Document("count", -1).append("_id", 1));
	}

	private static List<StatsBucket> buckets(Document facetResult, String name) {
		List<StatsBucket> out = new ArrayList<>();
		for (Document d : facetResult.getList(name, Document.class)) {
			Object key = d.get("_id");
			out.add(new StatsBucket(key == null ? null : formatKey(key), d.getInteger("count"),
					asDouble(d.get("avgPrice")), asDouble(d.get("minPrice")), asDouble(d.get("maxPrice"))));
		}
		return out;
	}

	private static String formatKey(Object key) {
		// roomsQc is stored as a double: show 4.0 as "4" but keep "4.5".
		if (key instanceof Double d && d == Math.rint(d)) {
			return String.valueOf(d.longValue());
		}
		return key.toString();
	}

	private static Double asDouble(Object value) {
		return (value instanceof Number n) ? n.doubleValue() : null;
	}

}
