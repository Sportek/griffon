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
 * Recomputes the amenity, utility and building lookup keys of stored listings at startup,
 * so a change to {@link Keys} or {@link Buildings} reaches listings the scraper has not
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
			.append(Keys.UTILITIES, 1)
			.append("address", 1)
			.append("city", 1)
			.append("latitude", 1)
			.append("longitude", 1)
			.append("locationPrecision", 1)
			.append(Buildings.KEY, 1);
		List<WriteModel<Document>> writes = new ArrayList<>();
		for (Document doc : mongo.getCollection(Listing.COLLECTION).find().projection(projection)) {
			List<String> amenityKeys = Keys.amenityKeys(doc.getList("amenities", String.class));
			List<String> utilityKeys = Keys.utilityKeys(doc.getList("utilitiesIncluded", String.class));
			String buildingKey = Buildings.key(doc.getString("address"), doc.getString("city"),
					asDouble(doc.get("latitude")), asDouble(doc.get("longitude")), doc.getString("locationPrecision"));
			if (!Objects.equals(amenityKeys, doc.get(Keys.AMENITIES)) || !Objects.equals(utilityKeys, doc.get(Keys.UTILITIES))
					|| !Objects.equals(buildingKey, doc.get(Buildings.KEY))) {
				writes.add(new UpdateOneModel<>(new Document("_id", doc.get("_id")),
						new Document("$set", new Document(Keys.AMENITIES, amenityKeys).append(Keys.UTILITIES, utilityKeys)
							.append(Buildings.KEY, buildingKey))));
			}
		}
		if (!writes.isEmpty()) {
			mongo.getCollection(Listing.COLLECTION).bulkWrite(writes);
			log.info("Recomputed amenity, utility and building keys of {} listings", writes.size());
		}
	}

	private static Double asDouble(Object value) {
		return (value instanceof Number n) ? n.doubleValue() : null;
	}

}
