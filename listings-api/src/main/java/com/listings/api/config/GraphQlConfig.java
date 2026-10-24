package com.listings.api.config;

import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import graphql.GraphQLContext;
import graphql.GraphqlErrorBuilder;
import graphql.execution.CoercedVariables;
import graphql.language.ArrayValue;
import graphql.language.BooleanValue;
import graphql.language.FloatValue;
import graphql.language.IntValue;
import graphql.language.NullValue;
import graphql.language.ObjectValue;
import graphql.language.StringValue;
import graphql.language.Value;
import graphql.language.VariableReference;
import graphql.schema.Coercing;
import graphql.schema.CoercingParseLiteralException;
import graphql.schema.CoercingParseValueException;
import graphql.schema.CoercingSerializeException;
import graphql.schema.GraphQLScalarType;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.DataFetcherExceptionResolver;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.graphql.execution.RuntimeWiringConfigurer;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration(proxyBeanMethods = false)
@EnableScheduling
class GraphQlConfig {

	@Bean
	Clock clock() {
		return Clock.systemUTC();
	}

	@Bean
	RuntimeWiringConfigurer scalars() {
		GraphQLScalarType dateTime = GraphQLScalarType.newScalar()
			.name("DateTime")
			.description("ISO-8601 instant")
			.coercing(new InstantCoercing())
			.build();
		GraphQLScalarType json = GraphQLScalarType.newScalar()
			.name("JSON")
			.description("Arbitrary JSON value")
			.coercing(new JsonCoercing())
			.build();
		return (wiring) -> wiring.scalar(dateTime).scalar(json);
	}

	/** Surfaces validation errors (bad page size, oversized batch...) as BAD_REQUEST with their message. */
	@Bean
	DataFetcherExceptionResolver illegalArgumentResolver() {
		return DataFetcherExceptionResolver.forSingleError((ex, env) -> {
			if (ex instanceof IllegalArgumentException) {
				return GraphqlErrorBuilder.newError(env)
					.errorType(ErrorType.BAD_REQUEST)
					.message(ex.getMessage())
					.build();
			}
			return null;
		});
	}

	static final class InstantCoercing implements Coercing<Instant, String> {

		@Override
		public String serialize(Object value, GraphQLContext context, Locale locale) {
			if (value instanceof Instant instant) {
				return instant.toString();
			}
			throw new CoercingSerializeException("Expected an Instant but got " + value.getClass().getName());
		}

		@Override
		public Instant parseValue(Object input, GraphQLContext context, Locale locale) {
			if (input instanceof String s) {
				try {
					return parse(s);
				}
				catch (DateTimeParseException ex) {
					throw new CoercingParseValueException("Invalid DateTime: " + s, ex);
				}
			}
			throw new CoercingParseValueException("DateTime must be a string");
		}

		@Override
		public Instant parseLiteral(Value<?> input, CoercedVariables variables, GraphQLContext context,
				Locale locale) {
			if (input instanceof StringValue s) {
				try {
					return parse(s.getValue());
				}
				catch (DateTimeParseException ex) {
					throw new CoercingParseLiteralException("Invalid DateTime: " + s.getValue(), ex);
				}
			}
			throw new CoercingParseLiteralException("DateTime must be a string");
		}

		private static Instant parse(String s) {
			// Accepts both "...Z" and offsets such as Python isoformat() "+00:00".
			return OffsetDateTime.parse(s).toInstant();
		}

	}

	/** Passes JSON values through untouched (variables arrive already decoded as maps/lists). */
	static final class JsonCoercing implements Coercing<Object, Object> {

		@Override
		public Object serialize(Object value, GraphQLContext context, Locale locale) {
			return value;
		}

		@Override
		public Object parseValue(Object input, GraphQLContext context, Locale locale) {
			return input;
		}

		@Override
		public Object parseLiteral(Value<?> input, CoercedVariables variables, GraphQLContext context,
				Locale locale) {
			return literal(input, variables);
		}

		private static Object literal(Value<?> value, CoercedVariables variables) {
			if (value instanceof ObjectValue object) {
				Map<String, Object> map = new LinkedHashMap<>();
				object.getObjectFields().forEach(f -> map.put(f.getName(), literal(f.getValue(), variables)));
				return map;
			}
			if (value instanceof ArrayValue array) {
				return array.getValues().stream().map(v -> literal(v, variables)).toList();
			}
			if (value instanceof StringValue s) {
				return s.getValue();
			}
			if (value instanceof IntValue i) {
				return i.getValue().longValueExact();
			}
			if (value instanceof FloatValue f) {
				return f.getValue().doubleValue();
			}
			if (value instanceof BooleanValue b) {
				return b.isValue();
			}
			if (value instanceof VariableReference ref) {
				return variables.get(ref.getName());
			}
			if (value instanceof NullValue) {
				return null;
			}
			throw new CoercingParseLiteralException("Unsupported JSON literal: " + value);
		}

	}

}
