package com.listings.api.listing;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.WriteModel;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Component;

/**
 * Recomputes the amenity and utility lookup keys of stored listings at startup, so a
 * change to the canonical keys in {@link Keys} reaches listings the scraper has not
 * resent since. Only documents whose keys differ are written.
 */
@Component
@Order(10)
class KeysBackfill implements ApplicationRunner {

	private static final Logger log = LoggerFactory.getLogger(KeysBackfill.class);

	private final MongoTemplate mongo;

	KeysBackfill(MongoTemplate mongo) {
		this.mongo = mongo;
	}

	@Override
	public void run(ApplicationArguments args) {
		Document projection = new Document("amenities", 1).append("utilitiesIncluded", 1)
			.append(Keys.AMENITIES, 1)
			.append(Keys.UTILITIES, 1);
		List<WriteModel<Document>> writes = new ArrayList<>();
		for (Document doc : mongo.getCollection(Listing.COLLECTION).find().projection(projection)) {
			List<String> amenityKeys = Keys.amenityKeys(doc.getList("amenities", String.class));
			List<String> utilityKeys = Keys.utilityKeys(doc.getList("utilitiesIncluded", String.class));
			if (!Objects.equals(amenityKeys, doc.get(Keys.AMENITIES)) || !Objects.equals(utilityKeys, doc.get(Keys.UTILITIES))) {
				writes.add(new UpdateOneModel<>(new Document("_id", doc.get("_id")), new Document("$set",
						new Document(Keys.AMENITIES, amenityKeys).append(Keys.UTILITIES, utilityKeys))));
			}
		}
		if (!writes.isEmpty()) {
			mongo.getCollection(Listing.COLLECTION).bulkWrite(writes);
			log.info("Recomputed amenity and utility keys of {} listings", writes.size());
		}
	}

}
