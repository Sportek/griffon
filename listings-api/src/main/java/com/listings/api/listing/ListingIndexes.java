package com.listings.api.listing;

import java.util.ArrayList;
import java.util.List;

import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.IndexModel;
import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;
import org.bson.Document;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Component;

/** Creates the listings indexes at startup (no-op when they already exist). */
@Component
class ListingIndexes implements ApplicationRunner {

	static final String TEXT_INDEX = "listing_text_v2";

	private final MongoTemplate mongo;

	ListingIndexes(MongoTemplate mongo) {
		this.mongo = mongo;
	}

	@Override
	public void run(ApplicationArguments args) {
		MongoCollection<Document> listings = mongo.getCollection(Listing.COLLECTION);
		dropOutdatedTextIndexes(listings);
		listings.createIndexes(List.of(
				new IndexModel(Indexes.ascending("source", "externalId"),
						new IndexOptions().unique(true).name("source_externalId_unique")),
				new IndexModel(Indexes.descending("firstSeenAt")),
				new IndexModel(Indexes.descending("lastSeenAt")),
				new IndexModel(Indexes.descending("updatedAt")),
				new IndexModel(Indexes.ascending("price")),
				new IndexModel(Indexes.ascending(Keys.CITY)),
				new IndexModel(Indexes.ascending(Keys.NEIGHBORHOOD)),
				new IndexModel(Indexes.ascending(Keys.AMENITIES)),
				new IndexModel(Indexes.ascending("source", "active", "lastSeenAt")),
				new IndexModel(Indexes.ascending(DuplicateDetector.KEY), new IndexOptions().sparse(true)),
				new IndexModel(Indexes.ascending("duplicateOf"), new IndexOptions().sparse(true)),
				new IndexModel(Indexes.ascending(ProximityFacts.TRANSIT), new IndexOptions().sparse(true)),
				new IndexModel(Indexes.geo2dsphere("location")),
				// Listings mix French and English, so no language-specific stemming.
				new IndexModel(
						Indexes.compoundIndex(Indexes.text("title"), Indexes.text("address"),
								Indexes.text("neighborhood"), Indexes.text("city"), Indexes.text("description")),
						new IndexOptions().name(TEXT_INDEX)
							.defaultLanguage("none")
							.weights(new Document("title", 5).append("address", 3)
								.append("neighborhood", 3)
								.append("city", 3)))));
	}

	/** MongoDB allows a single text index per collection: replace older definitions. */
	private static void dropOutdatedTextIndexes(MongoCollection<Document> listings) {
		List<String> outdated = new ArrayList<>();
		for (Document index : listings.listIndexes()) {
			Object textField = index.get("key", Document.class).get("_fts");
			if (textField != null && !TEXT_INDEX.equals(index.getString("name"))) {
				outdated.add(index.getString("name"));
			}
		}
		outdated.forEach(listings::dropIndex);
	}

}
