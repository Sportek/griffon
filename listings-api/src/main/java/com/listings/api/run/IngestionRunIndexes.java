package com.listings.api.run;

import com.mongodb.client.model.IndexOptions;
import com.mongodb.client.model.Indexes;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Component;

@Component
class IngestionRunIndexes implements ApplicationRunner {

	private final MongoTemplate mongo;

	IngestionRunIndexes(MongoTemplate mongo) {
		this.mongo = mongo;
	}

	@Override
	public void run(ApplicationArguments args) {
		mongo.getCollection(IngestionRun.COLLECTION)
			.createIndex(Indexes.compoundIndex(Indexes.ascending("source"), Indexes.descending("startedAt")));
		mongo.getCollection(IngestionRun.COLLECTION).createIndex(Indexes.ascending("status", "queuedAt"));
		mongo.getCollection(ScrapeSchedule.COLLECTION)
			.createIndex(Indexes.ascending("source"), new IndexOptions().unique(true));
	}

}
