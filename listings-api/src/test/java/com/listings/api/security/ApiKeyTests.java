package com.listings.api.security;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.listings.api.TestcontainersConfiguration;
import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

/** Goes through real HTTP: the API key check is a web interceptor. */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
		properties = { "listings.security.api-key=s3cret", "listings.inactivity.enabled=false",
				"listings.scheduler.enabled=false" })
@Import(TestcontainersConfiguration.class)
class ApiKeyTests {

	private static final String MUTATION = """
			{"query": "mutation { startIngestionRun(source: \\"duproprio\\") { id } }"}""";

	private static final String QUERY = """
			{"query": "{ filterOptions { sources } }"}""";

	@LocalServerPort
	int port;

	private final HttpClient http = HttpClient.newHttpClient();

	@Test
	void mutationsNeedTheKey() throws Exception {
		assertThat(post(MUTATION, null)).contains("UNAUTHORIZED").doesNotContain("startIngestionRun\":{");
		assertThat(post(MUTATION, "wrong")).contains("UNAUTHORIZED");
		assertThat(post(MUTATION, "s3cret")).contains("\"startIngestionRun\":{\"id\"").doesNotContain("errors");
	}

	@Test
	void queriesStayOpenByDefault() throws Exception {
		assertThat(post(QUERY, null)).contains("\"filterOptions\"").doesNotContain("errors");
	}

	private String post(String body, String apiKey) throws IOException, InterruptedException {
		HttpRequest.Builder request = HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/graphql"))
			.header("Content-Type", "application/json")
			.POST(HttpRequest.BodyPublishers.ofString(body));
		if (apiKey != null) {
			request.header(ApiKeyInterceptor.HEADER, apiKey);
		}
		return http.send(request.build(), HttpResponse.BodyHandlers.ofString()).body();
	}

}
