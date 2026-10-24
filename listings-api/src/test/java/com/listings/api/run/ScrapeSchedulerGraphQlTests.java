package com.listings.api.run;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import com.listings.api.IntegrationTest;
import org.junit.jupiter.api.Test;

import org.springframework.graphql.execution.ErrorType;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;

class ScrapeSchedulerGraphQlTests extends IntegrationTest {

	private static final String SAVE = """
			mutation($input: ScrapeScheduleInput!) {
			  saveScrapeSchedule(input: $input) { id source cron timeZone enabled nextRunAt params { maxPages enrich markUnseenInactive } } }""";

	private static final String CLAIM = """
			mutation($worker: String!, $sources: [String!]) {
			  claimIngestionRun(worker: $worker, sources: $sources) { id source status worker trigger startedAt params { maxPages areas enrich } } }""";

	@Test
	void scheduleComputesNextRunInItsTimeZone() {
		// The test clock starts at 2026-10-01T12:00Z, i.e. 08:00 in Montréal (EDT).
		GraphQlTester.Response saved = save(Map.of("source", "kijiji", "cron", "0 0 3 * * *"));
		saved.path("saveScrapeSchedule.timeZone").entity(String.class).isEqualTo("America/Toronto");
		saved.path("saveScrapeSchedule.nextRunAt").entity(String.class).isEqualTo("2026-10-02T07:00:00Z");

		// Saving again replaces the schedule of that source.
		save(Map.of("source", "kijiji", "cron", "0 30 4 * * *", "enabled", false));
		graphQl.document("{ scrapeSchedules { source cron enabled } }")
			.execute()
			.path("scrapeSchedules[*].cron")
			.entityList(String.class)
			.containsExactly("0 30 4 * * *");
	}

	@Test
	void invalidSchedulesAreRejected() {
		assertBadRequest(save(Map.of("source", "kijiji", "cron", "every day")));
		assertBadRequest(save(Map.of("source", "kijiji", "cron", "0 0 3 * * *", "timeZone", "Mars/Olympus")));
		assertBadRequest(save(Map.of("source", "kijiji", "cron", "0 0 3 * * *", "params",
				Map.of("limit", 10, "markUnseenInactive", true))));
	}

	@Test
	void dueSchedulesQueueOneRunPerSourceAndAWorkerClaimsIt() {
		save(Map.of("source", "duproprio", "cron", "0 0 * * * *", "params", Map.of("maxPages", 5, "enrich", true)));
		assertThat(tick()).isZero();

		clock.advance(Duration.ofHours(1)); // past the next full hour
		assertThat(tick()).isEqualTo(1);
		graphQl.document("{ ingestionRuns { status trigger params { maxPages enrich } } }")
			.execute()
			.path("ingestionRuns[0].status")
			.entity(String.class)
			.isEqualTo("QUEUED");

		// The next slot comes while the run is still queued: skipped, not stacked.
		clock.advance(Duration.ofHours(1));
		assertThat(tick()).isZero();
		graphQl.document("{ ingestionRuns { id } }").execute().path("ingestionRuns").entityList(Object.class).hasSize(1);

		// A worker limited to other sources gets nothing; the right one gets the run.
		claim("wyvern", List.of("kijiji")).path("claimIngestionRun").valueIsNull();
		GraphQlTester.Response claimed = claim("gremlin", null);
		claimed.path("claimIngestionRun.status").entity(String.class).isEqualTo("RUNNING");
		claimed.path("claimIngestionRun.worker").entity(String.class).isEqualTo("gremlin");
		claimed.path("claimIngestionRun.trigger").entity(String.class).isEqualTo("schedule");
		claimed.path("claimIngestionRun.params.maxPages").entity(Integer.class).isEqualTo(5);
		claimed.path("claimIngestionRun.params.enrich").entity(Boolean.class).isEqualTo(true);
		claim("gremlin", null).path("claimIngestionRun").valueIsNull();

		String runId = claimed.path("claimIngestionRun.id").entity(String.class).get();
		graphQl.document(UPSERT)
			.variable("listings", List.of(duproprio("1", "Laval", 900.0)))
			.variable("runId", runId)
			.execute()
			.path("upsertListings.created")
			.entity(Integer.class)
			.isEqualTo(1);
		graphQl.document("mutation($id: ID!) { heartbeatIngestionRun(id: $id) }")
			.variable("id", runId)
			.execute()
			.path("heartbeatIngestionRun")
			.entity(Boolean.class)
			.isEqualTo(true);
		graphQl.document("mutation($id: ID!) { finishIngestionRun(id: $id, status: SUCCEEDED) { status received } }")
			.variable("id", runId)
			.execute()
			.path("finishIngestionRun.received")
			.entity(Integer.class)
			.isEqualTo(1);
	}

	@Test
	void manualTriggerQueuesARunButNeverTwice() {
		graphQl.document("mutation { triggerScrape(source: \"centris\", params: { areas: [\"montreal\"] }) { status trigger } }")
			.execute()
			.path("triggerScrape.trigger")
			.entity(String.class)
			.isEqualTo("manual");
		assertBadRequest(graphQl.document("mutation { triggerScrape(source: \"centris\") { id } }").execute());
		claim("gremlin", List.of("centris")).path("claimIngestionRun.params.areas[0]")
			.entity(String.class)
			.isEqualTo("montreal");
	}

	@Test
	void silentWorkersAndUnclaimedRunsAreFailed() {
		graphQl.document("mutation { triggerScrape(source: \"kijiji\") { id } }").execute();
		graphQl.document("mutation { triggerScrape(source: \"centris\") { id } }").execute();
		claim("gremlin", List.of("kijiji"));

		clock.advance(Duration.ofMinutes(31));
		tick();
		GraphQlTester.Response kijiji = graphQl.document("{ ingestionRuns(source: \"kijiji\") { status error finishedAt } }")
			.execute();
		kijiji.path("ingestionRuns[0].status").entity(String.class).isEqualTo("FAILED");
		assertThat(kijiji.path("ingestionRuns[0].error").entity(String.class).get()).contains("gremlin");
		graphQl.document("{ ingestionRuns(source: \"centris\") { status } }")
			.execute()
			.path("ingestionRuns[0].status")
			.entity(String.class)
			.isEqualTo("QUEUED");

		clock.advance(Duration.ofHours(6));
		tick();
		GraphQlTester.Response centris = graphQl.document("{ ingestionRuns(source: \"centris\") { status error } }")
			.execute();
		centris.path("ingestionRuns[0].status").entity(String.class).isEqualTo("FAILED");
		assertThat(centris.path("ingestionRuns[0].error").entity(String.class).get()).contains("worker");

		// A failed slot frees the source: it can be queued again.
		graphQl.document("mutation { triggerScrape(source: \"kijiji\") { status } }")
			.execute()
			.path("triggerScrape.status")
			.entity(String.class)
			.isEqualTo("QUEUED");
	}

	@Test
	void heartbeatKeepsALongRunAlive() {
		graphQl.document("mutation { triggerScrape(source: \"kijiji\") { id } }").execute();
		String id = claim("gremlin", null).path("claimIngestionRun.id").entity(String.class).get();
		for (int i = 0; i < 4; i++) {
			clock.advance(Duration.ofMinutes(20));
			graphQl.document("mutation($id: ID!) { heartbeatIngestionRun(id: $id) }").variable("id", id).execute();
			tick();
		}
		graphQl.document("{ ingestionRuns { status } }")
			.execute()
			.path("ingestionRuns[0].status")
			.entity(String.class)
			.isEqualTo("RUNNING");
	}

	private GraphQlTester.Response save(Map<String, Object> input) {
		return graphQl.document(SAVE).variable("input", input).execute();
	}

	private GraphQlTester.Response claim(String worker, List<String> sources) {
		return graphQl.document(CLAIM).variable("worker", worker).variable("sources", sources).execute();
	}

	private int tick() {
		return graphQl.document("mutation { runSchedulerTick }")
			.execute()
			.path("runSchedulerTick")
			.entity(Integer.class)
			.get();
	}

	private static void assertBadRequest(GraphQlTester.Response response) {
		response.errors()
			.satisfy(errors -> assertThat(errors).singleElement()
				.satisfies(e -> assertThat(e.getErrorType()).isEqualTo(ErrorType.BAD_REQUEST)));
	}

}
