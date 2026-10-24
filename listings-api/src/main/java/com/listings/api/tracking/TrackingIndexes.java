package com.listings.api.tracking;

import java.util.List;

import com.mongodb.client.model.IndexModel;
import com.mongodb.client.model.Indexes;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Component;

/** Creates the trackings indexes at startup (no-op when they already exist). */
@Component
class TrackingIndexes implements ApplicationRunner {

	private final MongoTemplate mongo;

	TrackingIndexes(MongoTemplate mongo) {
		this.mongo = mongo;
	}

	@Override
	public void run(ApplicationArguments args) {
		mongo.getCollection(Tracking.COLLECTION)
			.createIndexes(List.of(new IndexModel(Indexes.ascending("hidden", "updatedAt")),
					new IndexModel(Indexes.ascending("hidden", "favorite")),
					new IndexModel(Indexes.ascending("hidden", "status"))));
	}

}
