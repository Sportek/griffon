package com.listings.api.run;

import java.time.Duration;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.Executor;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import tools.jackson.databind.json.JsonMapper;

/**
 * Tells the operator when a scrape fails (blocked source, crashed worker, no worker), via
 * an optional webhook ({@code listings.ops.webhook-url}). Without one, failures are only
 * logged and visible through the ingestionRuns query.
 */
@Component
class OpsNotifier {

	private static final Logger log = LoggerFactory.getLogger(OpsNotifier.class);

	private final String webhookUrl;

	private final String format;

	private final Executor executor;

	private final JsonMapper json;

	private final RestClient http;

	OpsNotifier(@Value("${listings.ops.webhook-url:}") String webhookUrl,
			@Value("${listings.ops.webhook-format:JSON}") String format,
			@Qualifier("applicationTaskExecutor") Executor executor, JsonMapper json) {
		this.webhookUrl = webhookUrl.isBlank() ? null : webhookUrl;
		this.format = format.toUpperCase(Locale.ROOT);
		this.executor = executor;
		this.json = json;
		SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
		requestFactory.setConnectTimeout(Duration.ofSeconds(5));
		requestFactory.setReadTimeout(Duration.ofSeconds(10));
		this.http = RestClient.builder().requestFactory(requestFactory).build();
	}

	void runFailed(IngestionRun run) {
		if (webhookUrl == null) {
			return;
		}
		String text = "Scrape %s en échec (run %s, worker %s) : %s".formatted(run.source(), run.id(),
				(run.worker() != null) ? run.worker() : "-", run.error());
		Object payload = switch (format) {
			case "SLACK" -> Map.of("text", text);
			case "DISCORD" -> Map.of("content", text.length() > 2000 ? text.substring(0, 2000) : text);
			default -> Map.of("event", "ingestion_run_failed", "message", text, "source", run.source(), "runId",
					run.id(), "error", String.valueOf(run.error()));
		};
		executor.execute(() -> {
			try {
				http.post()
					.uri(webhookUrl)
					.contentType(MediaType.APPLICATION_JSON)
					.body(json.writeValueAsBytes(payload))
					.retrieve()
					.toBodilessEntity();
			}
			catch (RuntimeException ex) {
				log.warn("Ops webhook failed: {}", ex.getMessage());
			}
		});
	}

}
