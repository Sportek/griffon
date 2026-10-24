package com.listings.api.run;

import java.time.Duration;
import java.util.List;

import com.listings.api.IntegrationTest;
import org.junit.jupiter.api.Test;

import org.springframework.graphql.execution.ErrorType;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;

class IngestionRunGraphQlTests extends IntegrationTest {

	@Test
	void sweepDeactivatesStaleListingsAndReseeingReactivates() {
		upsert(duproprio("old", "Laval", 900.0));
		clock.advance(Duration.ofDays(4));
		upsert(duproprio("fresh", "Laval", 900.0));

		graphQl.document("mutation { sweepInactiveListings }")
			.execute()
			.path("sweepInactiveListings")
			.entity(Integer.class)
			.isEqualTo(1);
		graphQl.document("{ listings(filter: { active: true }) { content { externalId } } }")
			.execute()
			.path("listings.content[*].externalId")
			.entityList(String.class)
			.containsExactly("fresh");
		GraphQlTester.Response old = activeState("old");
		old.path("listingByKey.active").entity(Boolean.class).isEqualTo(false);
		old.path("listingByKey.inactiveSince").hasValue();

		upsert(duproprio("old", "Laval", 900.0));
		GraphQlTester.Response back = activeState("old");
		back.path("listingByKey.active").entity(Boolean.class).isEqualTo(true);
		back.path("listingByKey.inactiveSince").valueIsNull();
	}

	@Test
	void runCountsBatchesAndDeactivatesWhatItDidNotSee() {
		upsert(duproprio("gone", "Laval", 900.0), duproprio("stays", "Laval", 900.0));
		clock.advance(Duration.ofHours(1));

		String runId = graphQl.document("mutation { startIngestionRun(source: \"duproprio\") { id status } }")
			.execute()
			.path("startIngestionRun.id")
			.entity(String.class)
			.get();

		GraphQlTester.Response batch = graphQl.document(UPSERT)
			.variable("listings", List.of(duproprio("stays", "Laval", 900.0), duproprio("new", "Laval", 900.0),
					listing("kijiji", "k1", "Laval", 900.0)))
			.variable("runId", runId)
			.execute();
		batch.path("upsertListings.created").entity(Integer.class).isEqualTo(1);
		batch.path("upsertListings.unchanged").entity(Integer.class).isEqualTo(1);
		batch.path("upsertListings.rejected").entity(Integer.class).isEqualTo(1);
		assertThat(batch.path("upsertListings.results[2].error").entity(String.class).get()).contains("kijiji");

		GraphQlTester.Response finished = graphQl.document("""
				mutation($id: ID!) {
				  finishIngestionRun(id: $id, status: SUCCEEDED, markUnseenInactive: true) {
				    status batches received created unchanged rejected deactivated finishedAt } }""")
			.variable("id", runId)
			.execute();
		finished.path("finishIngestionRun.status").entity(String.class).isEqualTo("SUCCEEDED");
		finished.path("finishIngestionRun.batches").entity(Integer.class).isEqualTo(1);
		finished.path("finishIngestionRun.received").entity(Integer.class).isEqualTo(3);
		finished.path("finishIngestionRun.deactivated").entity(Integer.class).isEqualTo(1);
		activeState("gone").path("listingByKey.active").entity(Boolean.class).isEqualTo(false);
		activeState("stays").path("listingByKey.active").entity(Boolean.class).isEqualTo(true);

		// A finished run accepts neither batches nor a second finish.
		graphQl.document(UPSERT)
			.variable("listings", List.of(duproprio("late", "Laval", 900.0)))
			.variable("runId", runId)
			.execute()
			.errors()
			.satisfy(errors -> assertThat(errors).singleElement()
				.satisfies(e -> assertThat(e.getErrorType()).isEqualTo(ErrorType.BAD_REQUEST)));
		graphQl.document("mutation($id: ID!) { finishIngestionRun(id: $id, status: FAILED) { id } }")
			.variable("id", runId)
			.execute()
			.errors()
			.satisfy(errors -> assertThat(errors).singleElement()
				.satisfies(e -> assertThat(e.getErrorType()).isEqualTo(ErrorType.BAD_REQUEST)));

		graphQl.document("{ ingestionRuns(source: \"duproprio\") { id } }")
			.execute()
			.path("ingestionRuns[*].id")
			.entityList(String.class)
			.containsExactly(runId);
	}

	@Test
	void failedRunDoesNotDeactivateAnything() {
		upsert(duproprio("gone", "Laval", 900.0));
		clock.advance(Duration.ofHours(1));
		String runId = graphQl.document("mutation { startIngestionRun(source: \"duproprio\") { id } }")
			.execute()
			.path("startIngestionRun.id")
			.entity(String.class)
			.get();

		graphQl.document("""
				mutation($id: ID!) {
				  finishIngestionRun(id: $id, status: FAILED, error: "blocked by Cloudflare", markUnseenInactive: true) {
				    deactivated error } }""")
			.variable("id", runId)
			.execute()
			.path("finishIngestionRun.deactivated")
			.entity(Integer.class)
			.isEqualTo(0);
		activeState("gone").path("listingByKey.active").entity(Boolean.class).isEqualTo(true);
	}

	private GraphQlTester.Response activeState(String externalId) {
		return graphQl.document("query($id: String!) { listingByKey(source: \"duproprio\", externalId: $id) { active inactiveSince } }")
			.variable("id", externalId)
			.execute();
	}

}
