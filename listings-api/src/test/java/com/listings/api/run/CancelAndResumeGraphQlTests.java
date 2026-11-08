package com.listings.api.run;

import java.time.Duration;
import java.util.List;

import com.listings.api.IntegrationTest;
import org.junit.jupiter.api.Test;

import org.springframework.graphql.execution.ErrorType;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;

class CancelAndResumeGraphQlTests extends IntegrationTest {

	private static final String CLAIM = """
			mutation { claimIngestionRun(worker: "gremlin") { id } }""";

	private static final String HEARTBEAT = "mutation($id: ID!) { heartbeatIngestionRun(id: $id) }";

	private static final String CANCEL = """
			mutation($id: ID!) { cancelIngestionRun(id: $id) { status cancelRequested error finishedAt } }""";

	private static final String RESUME = """
			mutation($id: ID!) { resumeIngestionRun(id: $id) { id status trigger resumeOf coverageSince
			  params { areas enrich markUnseenInactive } } }""";

	private static final String FINISH = """
			mutation($id: ID!, $status: IngestionRunStatus!) {
			  finishIngestionRun(id: $id, status: $status, markUnseenInactive: true) { status deactivated } }""";

	@Test
	void cancellingAQueuedRunStopsItAtOnce() {
		String id = trigger("kijiji");
		GraphQlTester.Response cancelled = graphQl.document(CANCEL).variable("id", id).execute();
		cancelled.path("cancelIngestionRun.status").entity(String.class).isEqualTo("CANCELLED");
		cancelled.path("cancelIngestionRun.finishedAt").hasValue();
		graphQl.document(CLAIM).execute().path("claimIngestionRun").valueIsNull();
		// Already over: a second cancel is refused.
		assertBadRequest(graphQl.document(CANCEL).variable("id", id).execute());
	}

	@Test
	void cancellingARunningRunTellsTheWorkerThroughItsHeartbeat() {
		trigger("kijiji");
		String id = claim();
		assertThat(heartbeat(id)).isTrue();

		GraphQlTester.Response flagged = graphQl.document(CANCEL).variable("id", id).execute();
		flagged.path("cancelIngestionRun.status").entity(String.class).isEqualTo("RUNNING");
		flagged.path("cancelIngestionRun.cancelRequested").entity(Boolean.class).isEqualTo(true);
		assertThat(heartbeat(id)).isFalse();

		graphQl.document(FINISH)
			.variable("id", id)
			.variable("status", "CANCELLED")
			.execute()
			.path("finishIngestionRun.status")
			.entity(String.class)
			.isEqualTo("CANCELLED");
	}

	@Test
	void resumedRunSkipsWhatTheInterruptedOneSentAndStillDeactivatesTheRest() {
		upsert(duproprio("sent", "Laval", 900.0), duproprio("later", "Laval", 900.0),
				duproprio("gone", "Laval", 900.0));
		clock.advance(Duration.ofHours(1));
		graphQl.document("""
				mutation { triggerScrape(source: "duproprio", params: { areas: ["laval"], markUnseenInactive: true }) { id } }""")
			.execute();
		String first = claim();
		send(first, duproprio("sent", "Laval", 900.0));
		clock.advance(Duration.ofMinutes(10));
		graphQl.document(FINISH).variable("id", first).variable("status", "FAILED").execute();

		GraphQlTester.Response resumed = graphQl.document(RESUME).variable("id", first).execute();
		resumed.path("resumeIngestionRun.status").entity(String.class).isEqualTo("QUEUED");
		resumed.path("resumeIngestionRun.trigger").entity(String.class).isEqualTo("resume");
		resumed.path("resumeIngestionRun.resumeOf").entity(String.class).isEqualTo(first);
		resumed.path("resumeIngestionRun.params.areas[0]").entity(String.class).isEqualTo("laval");
		resumed.path("resumeIngestionRun.params.markUnseenInactive").entity(Boolean.class).isEqualTo(true);
		// Only one pending run per source.
		assertBadRequest(graphQl.document(RESUME).variable("id", first).execute());

		String second = claim();
		graphQl.document("query($id: ID!) { ingestionRunAlreadySeen(id: $id) }")
			.variable("id", second)
			.execute()
			.path("ingestionRunAlreadySeen")
			.entityList(String.class)
			.containsExactly("sent");

		clock.advance(Duration.ofMinutes(10));
		send(second, duproprio("later", "Laval", 900.0));
		// "sent" was not re-sent, yet only "gone" is deactivated: coverage starts with the first run.
		graphQl.document(FINISH)
			.variable("id", second)
			.variable("status", "SUCCEEDED")
			.execute()
			.path("finishIngestionRun.deactivated")
			.entity(Integer.class)
			.isEqualTo(1);
		graphQl.document("{ listings(filter: { active: false }) { content { externalId } } }")
			.execute()
			.path("listings.content[*].externalId")
			.entityList(String.class)
			.containsExactly("gone");
	}

	@Test
	void onlyInterruptedWorkerRunsCanBeResumed() {
		String queued = trigger("kijiji");
		assertBadRequest(graphQl.document(RESUME).variable("id", queued).execute());

		String cli = graphQl.document("mutation { startIngestionRun(source: \"centris\") { id } }")
			.execute()
			.path("startIngestionRun.id")
			.entity(String.class)
			.get();
		graphQl.document(FINISH).variable("id", cli).variable("status", "FAILED").execute();
		assertBadRequest(graphQl.document(RESUME).variable("id", cli).execute());

		graphQl.document("query($id: ID!) { ingestionRunAlreadySeen(id: $id) }")
			.variable("id", queued)
			.execute()
			.path("ingestionRunAlreadySeen")
			.entityList(String.class)
			.hasSize(0);
	}

	@Test
	void runsSavedBeforeCancelAndResumeStillLoad() {
		mongo.getCollection(IngestionRun.COLLECTION)
			.insertOne(new org.bson.Document("source", "kijiji").append("status", "SUCCEEDED")
				.append("trigger", "schedule")
				.append("queuedAt", java.util.Date.from(clock.instant()))
				.append("batches", 0)
				.append("received", 0)
				.append("created", 0)
				.append("updated", 0)
				.append("unchanged", 0)
				.append("rejected", 0)
				.append("deactivated", 0));
		GraphQlTester.Response runs = graphQl.document("{ ingestionRuns { source cancelRequested resumeOf } }").execute();
		runs.path("ingestionRuns[0].cancelRequested").entity(Boolean.class).isEqualTo(false);
		runs.path("ingestionRuns[0].resumeOf").valueIsNull();
	}

	private String trigger(String source) {
		return graphQl.document("mutation($s: String!) { triggerScrape(source: $s) { id } }")
			.variable("s", source)
			.execute()
			.path("triggerScrape.id")
			.entity(String.class)
			.get();
	}

	private String claim() {
		return graphQl.document(CLAIM).execute().path("claimIngestionRun.id").entity(String.class).get();
	}

	private boolean heartbeat(String id) {
		return graphQl.document(HEARTBEAT)
			.variable("id", id)
			.execute()
			.path("heartbeatIngestionRun")
			.entity(Boolean.class)
			.get();
	}

	private void send(String runId, java.util.Map<String, Object> listing) {
		graphQl.document(UPSERT).variable("listings", List.of(listing)).variable("runId", runId).execute();
	}

	private static void assertBadRequest(GraphQlTester.Response response) {
		response.errors().expect(e -> e.getErrorType() == ErrorType.BAD_REQUEST).verify();
	}

}
