package com.listings.api.listing;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

import org.bson.Document;

import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.BasicQuery;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class ListingQueryService {

	static final int MAX_PAGE_SIZE = 100;

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

	public ListingPage search(ListingFilter filter, ListingSort sort, int page, int size) {
		if (page < 0) {
			throw new IllegalArgumentException("page must be >= 0");
		}
		if (size < 1 || size > MAX_PAGE_SIZE) {
			throw new IllegalArgumentException("size must be between 1 and " + MAX_PAGE_SIZE);
		}
		Document filterDoc = ListingFilterMapper.toQuery(filter);
		long total = mongo.count(new BasicQuery(filterDoc), Listing.class);
		Query query = new BasicQuery(filterDoc).with(sort.toSort()).skip((long) page * size).limit(size);
		return new ListingPage(mongo.find(query, Listing.class), page, size, total);
	}

	public List<Listing> latest(int limit, Instant since, ListingFilter filter) {
		if (limit < 1 || limit > MAX_PAGE_SIZE) {
			throw new IllegalArgumentException("limit must be between 1 and " + MAX_PAGE_SIZE);
		}
		Document filterDoc = ListingFilterMapper.toQuery(filter);
		if (since != null) {
			// "since" wins over filter.firstSeenAfter: it is the more specific intent.
			Document range = filterDoc.get("firstSeenAt", new Document());
			range.put("$gte", since);
			filterDoc.put("firstSeenAt", range);
		}
		Query query = new BasicQuery(filterDoc).with(ListingSort.NEWEST.toSort()).limit(limit);
		return mongo.find(query, Listing.class);
	}

	public boolean delete(String id) {
		return mongo.remove(Query.query(Criteria.where("_id").is(id)), Listing.class).getDeletedCount() > 0;
	}

	public ListingStats stats(ListingFilter filter) {
		Document match = new Document("$match", ListingFilterMapper.toQuery(filter));
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
