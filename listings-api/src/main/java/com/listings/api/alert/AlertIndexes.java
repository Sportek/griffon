package com.listings.api.alert;

import com.mongodb.client.model.Indexes;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Component;

@Component
class AlertIndexes implements ApplicationRunner {

	private final MongoTemplate mongo;

	AlertIndexes(MongoTemplate mongo) {
		this.mongo = mongo;
	}

	@Override
	public void run(ApplicationArguments args) {
		mongo.getCollection(Alert.COLLECTION)
			.createIndex(Indexes.compoundIndex(Indexes.ascending("savedSearchId"), Indexes.descending("createdAt")));
		mongo.getCollection(Alert.COLLECTION).createIndex(Indexes.descending("createdAt"));
	}

}
