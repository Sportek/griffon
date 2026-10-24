package com.listings.api.security;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

import graphql.ExecutionResult;
import graphql.GraphqlErrorBuilder;
import graphql.language.OperationDefinition;
import graphql.parser.InvalidSyntaxException;
import graphql.parser.Parser;
import reactor.core.publisher.Mono;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.graphql.support.DefaultExecutionGraphQlResponse;
import org.springframework.stereotype.Component;

/**
 * Optional shared-secret protection. When {@code listings.security.api-key} is set,
 * mutations (and queries too with {@code protect-queries}) require a matching
 * {@code X-API-Key} header. Without a key configured, the API stays open.
 */
@Component
class ApiKeyInterceptor implements WebGraphQlInterceptor {

	static final String HEADER = "X-API-Key";

	private final byte[] apiKey;

	private final boolean protectQueries;

	ApiKeyInterceptor(@Value("${listings.security.api-key:}") String apiKey,
			@Value("${listings.security.protect-queries:false}") boolean protectQueries) {
		this.apiKey = apiKey.isBlank() ? null : apiKey.getBytes(StandardCharsets.UTF_8);
		this.protectQueries = protectQueries;
	}

	@Override
	public Mono<WebGraphQlResponse> intercept(WebGraphQlRequest request, Chain chain) {
		if (apiKey == null || hasValidKey(request) || (!protectQueries && !containsMutation(request.getDocument()))) {
			return chain.next(request);
		}
		ExecutionResult result = ExecutionResult.newExecutionResult()
			.addError(GraphqlErrorBuilder.newError()
				.errorType(ErrorType.UNAUTHORIZED)
				.message("Missing or invalid " + HEADER + " header")
				.build())
			.build();
		return Mono.just(new WebGraphQlResponse(new DefaultExecutionGraphQlResponse(request.toExecutionInput(), result)));
	}

	private boolean hasValidKey(WebGraphQlRequest request) {
		String provided = request.getHeaders().getFirst(HEADER);
		return provided != null && MessageDigest.isEqual(apiKey, provided.getBytes(StandardCharsets.UTF_8));
	}

	/** True if any operation in the document is a mutation (whichever one ends up selected). */
	private static boolean containsMutation(String document) {
		try {
			return Parser.parse(document)
				.getDefinitionsOfType(OperationDefinition.class)
				.stream()
				.anyMatch(op -> op.getOperation() == OperationDefinition.Operation.MUTATION);
		}
		catch (InvalidSyntaxException ex) {
			// Let execution report the syntax error.
			return false;
		}
	}

}
