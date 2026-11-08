package com.listings.api.listing;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.regex.Pattern;

import org.bson.Document;

/**
 * Griffon's filter language, a small JQL in French:
 *
 * <pre>
 * (quartier = "Plateau Mont-Royal" ET prix &lt;= 1800) OU (quartier = Rosemont ET prix &lt;= 1600)
 * taille &gt;= 4½ animaux NON meublé métro &lt;= 10 age &lt; 3j
 * commodité DANS (balcon, "lave vaisselle") texte ~ terrasse
 * </pre>
 *
 * Terms side by side are joined with AND; NOT binds tightest, then AND, then OR. Keywords
 * and field names ignore case and accents, and have French and English spellings
 * (ET/AND, OU/OR, NON/NOT, DANS/IN). The web app (web/src/lib/query-language.ts) has a
 * mirror of this parser for instant feedback; both run the cases in
 * src/test/resources/query-cases.json.
 */
public final class ListingQuery {

	static final int MAX_LENGTH = 2000;

	private static final int MAX_DEPTH = 32;

	/** A query that cannot be read, with the span of the text at fault. */
	public static final class QueryException extends IllegalArgumentException {

		private final int start;

		private final int end;

		QueryException(String message, int start, int end) {
			super(message);
			this.start = start;
			this.end = end;
		}

		public int start() {
			return start;
		}

		public int end() {
			return end;
		}

	}

	enum Kind {
		NUMBER, DURATION, BOOLEAN, KEY, RAW, TEXT
	}

	/** A field of the language: its kind and where it lives in a listing document. */
	record Field(String name, Kind kind, String path) {
	}

	static final Map<String, Field> FIELDS = new LinkedHashMap<>();

	private static final Map<String, Field> ALIASES = new LinkedHashMap<>();

	static {
		field("prix", Kind.NUMBER, "price", "loyer");
		field("taille", Kind.NUMBER, "roomsQc");
		field("chambres", Kind.NUMBER, "bedrooms", "ch");
		field("sdb", Kind.NUMBER, "bathrooms", "salles");
		field("superficie", Kind.NUMBER, "areaSqft", "pi2");
		field("metro", Kind.NUMBER, "metroWalkMinutes");
		field("rem", Kind.NUMBER, "remWalkMinutes");
		field("transport", Kind.NUMBER, ProximityFacts.TRANSIT);
		field("stationnement", Kind.NUMBER, "parkingSpots", "parking");
		field("annee", Kind.NUMBER, "yearBuilt");
		field("terrain", Kind.NUMBER, "lotAreaSqft");
		field("frais", Kind.NUMBER, "condoFeesMonthly");
		field("logements", Kind.NUMBER, "units");
		field("age", Kind.DURATION, "firstSeenAt");
		field("animaux", Kind.BOOLEAN, "petsAllowed");
		field("meuble", Kind.BOOLEAN, "furnished");
		field("fumeur", Kind.BOOLEAN, "smokingAllowed");
		field("photos", Kind.BOOLEAN, "photos.0");
		field("chauffe", Kind.BOOLEAN, Keys.UTILITIES);
		field("quartier", Kind.KEY, Keys.NEIGHBORHOOD);
		field("ville", Kind.KEY, Keys.CITY);
		field("inclus", Kind.KEY, Keys.UTILITIES);
		field("commodite", Kind.KEY, Keys.AMENITIES);
		field("source", Kind.RAW, "source");
		field("type", Kind.RAW, "propertyType");
		field("commerce", Kind.RAW, ProximityFacts.CATEGORIES);
		field("texte", Kind.TEXT, "description");
		field("adresse", Kind.TEXT, "address");
	}

	private static void field(String name, Kind kind, String path, String... aliases) {
		Field field = new Field(name, kind, path);
		FIELDS.put(name, field);
		ALIASES.put(name, field);
		for (String alias : aliases) {
			ALIASES.put(alias, field);
		}
	}

	private ListingQuery() {
	}

	/** The MongoDB query document for this text; an empty text matches everything. */
	public static Document toMongo(String text, Instant now) {
		if (text == null || text.isBlank()) {
			return new Document();
		}
		if (text.length() > MAX_LENGTH) {
			throw new QueryException("La requête est trop longue (" + MAX_LENGTH + " caractères au plus).", 0,
					text.length());
		}
		return new Parser(lex(text), text.length(), now).parse();
	}

	// ---------------------------------------------------------------- lexer

	enum TokenType {
		WORD, STRING, OPERATOR, LPAREN, RPAREN, COMMA
	}

	record Token(TokenType type, String text, int start, int end) {

		/** The keyword this word stands for (AND, OR, NOT, IN), or null. */
		String keyword() {
			if (type != TokenType.WORD) {
				return null;
			}
			return switch (fold(text)) {
				case "and", "et" -> "AND";
				case "or", "ou" -> "OR";
				case "not", "non" -> "NOT";
				case "in", "dans" -> "IN";
				default -> null;
			};
		}

	}

	private static final String OPERATOR_CHARS = "=<>!~";

	private static final String STOP_CHARS = "()\",'" + OPERATOR_CHARS;

	static List<Token> lex(String text) {
		List<Token> tokens = new ArrayList<>();
		int i = 0;
		while (i < text.length()) {
			char c = text.charAt(i);
			if (Character.isWhitespace(c)) {
				i++;
			}
			else if (c == '(') {
				tokens.add(new Token(TokenType.LPAREN, "(", i, ++i));
			}
			else if (c == ')') {
				tokens.add(new Token(TokenType.RPAREN, ")", i, ++i));
			}
			else if (c == ',') {
				tokens.add(new Token(TokenType.COMMA, ",", i, ++i));
			}
			else if (c == '"' || c == '\'') {
				int close = text.indexOf(c, i + 1);
				if (close < 0) {
					throw new QueryException("Guillemet " + c + " jamais refermé.", i, text.length());
				}
				tokens.add(new Token(TokenType.STRING, text.substring(i + 1, close), i, close + 1));
				i = close + 1;
			}
			else if (OPERATOR_CHARS.indexOf(c) >= 0) {
				String two = i + 1 < text.length() ? text.substring(i, i + 2) : "";
				if (two.equals("<=") || two.equals(">=") || two.equals("!=") || two.equals("!~")) {
					tokens.add(new Token(TokenType.OPERATOR, two, i, i + 2));
					i += 2;
				}
				else if (c == '!') {
					throw new QueryException("« ! » s'écrit != (différent) ou !~ (ne contient pas).", i, i + 1);
				}
				else {
					tokens.add(new Token(TokenType.OPERATOR, String.valueOf(c), i, ++i));
				}
			}
			else {
				int start = i;
				while (i < text.length() && !Character.isWhitespace(text.charAt(i))
						&& STOP_CHARS.indexOf(text.charAt(i)) < 0) {
					i++;
				}
				tokens.add(new Token(TokenType.WORD, text.substring(start, i), start, i));
			}
		}
		return tokens;
	}

	// ---------------------------------------------------------------- parser

	private static final class Parser {

		private final List<Token> tokens;

		private final int length;

		private final Instant now;

		private int pos;

		private int depth;

		Parser(List<Token> tokens, int length, Instant now) {
			this.tokens = tokens;
			this.length = length;
			this.now = now;
		}

		Document parse() {
			Document query = parseOr();
			if (pos < tokens.size()) {
				Token t = tokens.get(pos);
				throw new QueryException(t.type() == TokenType.RPAREN ? "Parenthèse fermante en trop."
						: "« " + t.text() + " » inattendu.", t.start(), t.end());
			}
			return query;
		}

		private Token peek() {
			return pos < tokens.size() ? tokens.get(pos) : null;
		}

		private boolean peekKeyword(String keyword) {
			Token t = peek();
			return t != null && keyword.equals(t.keyword());
		}

		private QueryException atEnd(String message) {
			return new QueryException(message, length, length);
		}

		private Document parseOr() {
			List<Document> terms = new ArrayList<>();
			terms.add(parseAnd());
			while (peekKeyword("OR")) {
				Token or = tokens.get(pos++);
				if (peek() == null) {
					throw new QueryException("Un critère est attendu après « " + or.text() + " ».", or.start(), or.end());
				}
				terms.add(parseAnd());
			}
			return terms.size() == 1 ? terms.get(0) : new Document("$or", terms);
		}

		private Document parseAnd() {
			List<Document> terms = new ArrayList<>();
			terms.add(parseUnary());
			while (true) {
				Token t = peek();
				if (t == null || t.type() == TokenType.RPAREN || "OR".equals(t.keyword())) {
					break;
				}
				if ("AND".equals(t.keyword())) {
					pos++;
					if (peek() == null) {
						throw new QueryException("Un critère est attendu après « " + t.text() + " ».", t.start(), t.end());
					}
				}
				terms.add(parseUnary());
			}
			return terms.size() == 1 ? terms.get(0) : new Document("$and", terms);
		}

		private Document parseUnary() {
			if (peekKeyword("NOT")) {
				Token not = tokens.get(pos++);
				if (peek() == null) {
					throw new QueryException("Un critère est attendu après « " + not.text() + " ».", not.start(),
							not.end());
				}
				return new Document("$nor", List.of(parseUnary()));
			}
			return parseAtom();
		}

		private Document parseAtom() {
			Token t = peek();
			if (t == null) {
				throw atEnd("Un critère est attendu.");
			}
			if (t.type() == TokenType.LPAREN) {
				if (++depth > MAX_DEPTH) {
					throw new QueryException("Trop de parenthèses imbriquées.", t.start(), t.end());
				}
				pos++;
				Document inner = parseOr();
				Token close = peek();
				if (close == null || close.type() != TokenType.RPAREN) {
					throw new QueryException("Parenthèse jamais refermée.", t.start(), t.end());
				}
				pos++;
				depth--;
				return inner;
			}
			if (t.type() != TokenType.WORD || t.keyword() != null) {
				throw new QueryException("Un nom de champ est attendu ici, pas « " + t.text() + " ».", t.start(), t.end());
			}
			return parseComparison();
		}

		private Document parseComparison() {
			Token name = tokens.get(pos++);
			Field field = ALIASES.get(fold(name.text()));
			if (field == null) {
				throw unknownField(name);
			}
			Token next = peek();
			if (next != null && next.type() == TokenType.OPERATOR) {
				pos++;
				Token value = peek();
				// A keyword is a value here: "animaux = non".
				if (value == null || (value.type() != TokenType.WORD && value.type() != TokenType.STRING)) {
					throw new QueryException("Une valeur est attendue après « " + next.text() + " ».", next.start(),
							value == null ? next.end() : value.end());
				}
				pos++;
				return compare(field, name, next, value);
			}
			boolean notIn = next != null && "NOT".equals(next.keyword()) && pos + 1 < tokens.size()
					&& "IN".equals(tokens.get(pos + 1).keyword());
			if (next != null && ("IN".equals(next.keyword()) || notIn)) {
				pos += notIn ? 2 : 1;
				return in(field, name, readList(notIn ? tokens.get(pos - 1) : next), notIn);
			}
			return bare(field, name);
		}

		private List<Token> readList(Token in) {
			Token open = peek();
			if (open == null || open.type() != TokenType.LPAREN) {
				throw new QueryException("Une liste entre parenthèses est attendue après « " + in.text()
						+ " », ex. (Plateau, Rosemont).", in.start(), in.end());
			}
			pos++;
			List<Token> values = new ArrayList<>();
			while (true) {
				Token v = peek();
				if (v == null || (v.type() != TokenType.WORD && v.type() != TokenType.STRING)) {
					throw new QueryException("Une valeur est attendue dans la liste.", v == null ? open.start() : v.start(),
							v == null ? length : v.end());
				}
				values.add(v);
				pos++;
				Token sep = peek();
				if (sep != null && sep.type() == TokenType.COMMA) {
					pos++;
					continue;
				}
				if (sep != null && sep.type() == TokenType.RPAREN) {
					pos++;
					return values;
				}
				throw new QueryException("Liste jamais refermée : séparez les valeurs par des virgules et fermez avec ).",
						open.start(), sep == null ? length : sep.end());
			}
		}

		// ------------------------------------------------------------ meaning

		private Document bare(Field field, Token name) {
			return switch (field.name()) {
				case "stationnement" -> new Document(field.path(), new Document("$gte", 1));
				default -> {
					if (field.kind() != Kind.BOOLEAN) {
						throw new QueryException("« " + name.text() + " » attend une comparaison, ex. " + example(field) + ".",
								name.start(), name.end());
					}
					yield bool(field, true);
				}
			};
		}

		private Document bool(Field field, boolean value) {
			return switch (field.name()) {
				case "photos" -> new Document(field.path(), new Document("$exists", value));
				case "chauffe" -> new Document(field.path(), value ? "chauffage" : new Document("$ne", "chauffage"));
				default -> new Document(field.path(), value);
			};
		}

		private Document compare(Field field, Token name, Token op, Token value) {
			String o = op.text();
			switch (field.kind()) {
				case NUMBER -> {
					Double n = number(value.text());
					if (n == null || value.type() == TokenType.STRING) {
						throw new QueryException("Un nombre est attendu après « " + o + " », ex. " + example(field) + ".",
								value.start(), value.end());
					}
					return numeric(field, op, n);
				}
				case DURATION -> {
					Duration d = duration(value.text());
					if (d == null) {
						throw new QueryException("Une durée est attendue, ex. age < 3j ou age < 24h.", value.start(),
								value.end());
					}
					Date limit = Date.from(now.minus(d));
					// A younger listing was first seen later: the comparison flips.
					String mongo = switch (o) {
						case "<" -> "$gt";
						case "<=" -> "$gte";
						case ">" -> "$lt";
						case ">=" -> "$lte";
						default -> throw new QueryException("« age » se compare avec <, <=, > ou >=, ex. age < 3j.",
								op.start(), op.end());
					};
					return new Document(field.path(), new Document(mongo, limit));
				}
				case BOOLEAN -> {
					Boolean b = yesNo(value.text());
					if (b == null || !(o.equals("=") || o.equals("!="))) {
						throw new QueryException("« " + name.text() + " » est oui ou non : écrivez « " + name.text()
								+ " » ou « NON " + name.text() + " ».", op.start(), value.end());
					}
					return bool(field, o.equals("=") == b);
				}
				case KEY, RAW -> {
					String v = field.kind() == Kind.KEY ? Keys.normalize(value.text())
							: value.text().trim().toLowerCase(Locale.ROOT);
					if (v == null || v.isEmpty()) {
						throw new QueryException("Valeur vide.", value.start(), value.end());
					}
					return switch (o) {
						case "=" -> new Document(field.path(), v);
						case "!=" -> new Document(field.path(), new Document("$ne", v));
						case "~" -> new Document(field.path(), Pattern.compile(Pattern.quote(v)));
						case "!~" -> new Document(field.path(), new Document("$not", Pattern.compile(Pattern.quote(v))));
						default -> throw new QueryException("« " + name.text() + " » se compare avec =, !=, ~ ou DANS (...).",
								op.start(), op.end());
					};
				}
				case TEXT -> {
					if (!(o.equals("~") || o.equals("!~"))) {
						throw new QueryException("« " + name.text() + " » se cherche avec ~ (contient), ex. " + example(field)
								+ ".", op.start(), op.end());
					}
					Pattern pattern = Pattern.compile(foldingRegex(value.text()), Pattern.CASE_INSENSITIVE);
					List<Document> places = field.name().equals("texte")
							? List.of(new Document("title", pattern), new Document("description", pattern))
							: List.of(new Document(field.path(), pattern));
					return new Document(o.equals("~") ? "$or" : "$nor", places);
				}
				default -> throw new IllegalStateException(field.kind().name());
			}
		}

		private Document numeric(Field field, Token op, double n) {
			Double v = n;
			return switch (op.text()) {
				case "=" -> new Document(field.path(), v);
				case "!=" -> new Document(field.path(), new Document("$ne", v));
				case "<" -> new Document(field.path(), new Document("$lt", v));
				case "<=" -> new Document(field.path(), new Document("$lte", v));
				case ">" -> new Document(field.path(), new Document("$gt", v));
				case ">=" -> new Document(field.path(), new Document("$gte", v));
				default -> throw new QueryException("« ~ » sert au texte : pour un nombre, utilisez =, <, <=, > ou >=.",
						op.start(), op.end());
			};
		}

		private Document in(Field field, Token name, List<Token> values, boolean not) {
			if (field.kind() != Kind.KEY && field.kind() != Kind.RAW) {
				throw new QueryException("DANS (...) sert aux listes de quartiers, villes, sources... pas à « "
						+ name.text() + " ».", name.start(), name.end());
			}
			List<String> keys = new ArrayList<>();
			for (Token v : values) {
				String key = field.kind() == Kind.KEY ? Keys.normalize(v.text()) : v.text().trim().toLowerCase(Locale.ROOT);
				if (key == null || key.isEmpty()) {
					throw new QueryException("Valeur vide.", v.start(), v.end());
				}
				keys.add(key);
			}
			return new Document(field.path(), new Document(not ? "$nin" : "$in", keys));
		}

		private QueryException unknownField(Token name) {
			String folded = fold(name.text());
			String closest = ALIASES.keySet()
				.stream()
				.min(Comparator.comparingInt(a -> distance(a, folded)))
				.filter(a -> distance(a, folded) <= 2)
				.map(a -> ALIASES.get(a).name())
				.orElse(null);
			String hint = closest != null ? " Vouliez-vous dire « " + closest + " » ?" : "";
			return new QueryException("Champ inconnu « " + name.text() + " »." + hint, name.start(), name.end());
		}

	}

	// ---------------------------------------------------------------- values

	static String example(Field field) {
		return switch (field.name()) {
			case "prix" -> "prix <= 1800";
			case "taille" -> "taille >= 4½";
			case "metro", "rem", "transport" -> field.name() + " <= 10";
			case "age" -> "age < 3j";
			case "annee" -> "annee >= 2000";
			case "texte" -> "texte ~ terrasse";
			case "adresse" -> "adresse ~ \"Saint-Denis\"";
			default -> field.name() + " >= 1";
		};
	}

	/** "1800", "1800$", "1.5k", "4½", "4.5", "800pi2" as a number; null if it is not one. */
	static Double number(String raw) {
		String s = raw.trim().toLowerCase(Locale.ROOT).replace(" ", "");
		s = s.replaceAll("(\\$|pi2|pi²|min|ans?)$", "");
		double factor = 1;
		if (s.endsWith("k")) {
			factor = 1000;
			s = s.substring(0, s.length() - 1);
		}
		double half = 0;
		if (s.endsWith("½")) {
			half = 0.5;
			s = s.substring(0, s.length() - 1);
		}
		if (s.isEmpty() && half > 0) {
			return half;
		}
		if (!s.matches("-?\\d+(\\.\\d+)?")) {
			return null;
		}
		return (Double.parseDouble(s) + half) * factor;
	}

	/** "3j", "24h", "2sem", or a bare number of days. */
	static Duration duration(String raw) {
		var m = Pattern.compile("^(\\d+(?:\\.\\d+)?)\\s*(h|j|d|sem|s|w)?$").matcher(raw.trim().toLowerCase(Locale.ROOT));
		if (!m.matches()) {
			return null;
		}
		double n = Double.parseDouble(m.group(1));
		String unit = m.group(2) == null ? "j" : m.group(2);
		double hours = switch (unit) {
			case "h" -> n;
			case "sem", "s", "w" -> n * 24 * 7;
			default -> n * 24;
		};
		return Duration.ofMinutes(Math.round(hours * 60));
	}

	static Boolean yesNo(String raw) {
		return switch (fold(raw)) {
			case "oui", "vrai", "true", "yes", "1" -> true;
			case "non", "faux", "false", "no", "0" -> false;
			default -> null;
		};
	}

	/** Lower case, without accents: how field names and keywords are compared. */
	static String fold(String s) {
		return java.text.Normalizer.normalize(s, java.text.Normalizer.Form.NFD)
			.replaceAll("\\p{M}", "")
			.toLowerCase(Locale.ROOT);
	}

	/** A regex for this text that also matches it with or without accents. */
	static String foldingRegex(String text) {
		StringBuilder out = new StringBuilder();
		for (char c : fold(text).toCharArray()) {
			out.append(switch (c) {
				case 'a' -> "[aàâä]";
				case 'c' -> "[cç]";
				case 'e' -> "[eéèêë]";
				case 'i' -> "[iîï]";
				case 'o' -> "[oôö]";
				case 'u' -> "[uùûü]";
				default -> Pattern.quote(String.valueOf(c));
			});
		}
		return out.toString();
	}

	private static int distance(String a, String b) {
		int[] prev = new int[b.length() + 1];
		int[] cur = new int[b.length() + 1];
		for (int j = 0; j <= b.length(); j++) {
			prev[j] = j;
		}
		for (int i = 1; i <= a.length(); i++) {
			cur[0] = i;
			for (int j = 1; j <= b.length(); j++) {
				int cost = a.charAt(i - 1) == b.charAt(j - 1) ? 0 : 1;
				cur[j] = Math.min(Math.min(cur[j - 1] + 1, prev[j] + 1), prev[j - 1] + cost);
			}
			int[] swap = prev;
			prev = cur;
			cur = swap;
		}
		return prev[b.length()];
	}

}
