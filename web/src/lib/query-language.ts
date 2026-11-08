/**
 * Griffon's filter language, for the query editor: tokens to colour, the same errors as the
 * API (listings-api ListingQuery.java, which runs the query), and completions. Both parsers
 * run the cases of listings-api/src/test/resources/query-cases.json.
 *
 *   (quartier = "Plateau Mont-Royal" ET prix <= 1800) OU (quartier = Rosemont ET prix <= 1600)
 *   taille >= 4½ animaux NON meublé métro <= 10 age < 3j
 *
 * No imports: node --test runs this file as it is.
 */

export type FieldKind = "number" | "duration" | "boolean" | "key" | "raw" | "text";

export interface FieldInfo {
  name: string;
  kind: FieldKind;
  aliases: string[];
  /** What it filters on, for the help and the completions. */
  label: string;
  example: string;
  /** The completions offer the values of this list of the filter options. */
  values?: "neighborhoods" | "cities" | "sources" | "propertyTypes" | "amenities" | "utilitiesIncluded" | "categories";
  /** Only means something for rentals, or for properties for sale. */
  offer?: "rent" | "sale";
}

export const FIELDS: FieldInfo[] = [
  { name: "prix", kind: "number", aliases: ["loyer"], label: "Loyer, ou prix demandé", example: "prix <= 1800" },
  { name: "taille", kind: "number", aliases: [], label: "Taille québécoise (3½, 4½…)", example: "taille >= 4½", offer: "rent" },
  { name: "chambres", kind: "number", aliases: ["ch"], label: "Chambres à coucher", example: "chambres >= 2" },
  { name: "sdb", kind: "number", aliases: ["salles"], label: "Salles de bain", example: "sdb >= 2" },
  { name: "superficie", kind: "number", aliases: ["pi2"], label: "Superficie habitable (pi²)", example: "superficie >= 800" },
  { name: "metro", kind: "number", aliases: [], label: "Minutes à pied du métro", example: "metro <= 10" },
  { name: "rem", kind: "number", aliases: [], label: "Minutes à pied du REM", example: "rem <= 15" },
  { name: "transport", kind: "number", aliases: [], label: "Minutes à pied du métro ou du REM", example: "transport <= 10" },
  { name: "stationnement", kind: "number", aliases: ["parking"], label: "Places de stationnement (seul : au moins une)", example: "stationnement" },
  { name: "annee", kind: "number", aliases: [], label: "Année de construction", example: "annee >= 2000" },
  { name: "terrain", kind: "number", aliases: [], label: "Terrain (pi²)", example: "terrain >= 4000", offer: "sale" },
  { name: "frais", kind: "number", aliases: [], label: "Frais de copropriété par mois", example: "frais <= 300", offer: "sale" },
  { name: "logements", kind: "number", aliases: [], label: "Nombre de logements (plex)", example: "logements >= 2", offer: "sale" },
  { name: "age", kind: "duration", aliases: [], label: "Depuis quand Griffon la connaît", example: "age < 3j" },
  { name: "animaux", kind: "boolean", aliases: [], label: "Animaux acceptés", example: "animaux", offer: "rent" },
  { name: "meuble", kind: "boolean", aliases: [], label: "Meublé", example: "NON meuble", offer: "rent" },
  { name: "fumeur", kind: "boolean", aliases: [], label: "Fumeur permis", example: "NON fumeur", offer: "rent" },
  { name: "photos", kind: "boolean", aliases: [], label: "A des photos", example: "photos" },
  { name: "chauffe", kind: "boolean", aliases: [], label: "Chauffage inclus", example: "chauffe", offer: "rent" },
  { name: "quartier", kind: "key", aliases: [], label: "Quartier", example: 'quartier DANS (Rosemont, "Mile End")', values: "neighborhoods" },
  { name: "ville", kind: "key", aliases: [], label: "Ville", example: "ville != Laval", values: "cities" },
  { name: "inclus", kind: "key", aliases: [], label: "Service inclus dans le loyer", example: 'inclus = "eau chaude"', values: "utilitiesIncluded", offer: "rent" },
  { name: "commodite", kind: "key", aliases: [], label: "Commodité", example: "commodite = balcon", values: "amenities" },
  { name: "source", kind: "raw", aliases: [], label: "Site d'origine", example: "source != kijiji", values: "sources" },
  { name: "type", kind: "raw", aliases: [], label: "Type de propriété", example: "type = condo", values: "propertyTypes" },
  { name: "commerce", kind: "raw", aliases: [], label: "Commerce à distance de marche", example: "commerce = grocery", values: "categories" },
  { name: "texte", kind: "text", aliases: [], label: "Titre ou description contient", example: "texte ~ terrasse" },
  { name: "adresse", kind: "text", aliases: [], label: "Adresse contient", example: 'adresse ~ "Saint-Denis"' },
];

const ALIASES = new Map<string, FieldInfo>();
for (const f of FIELDS) {
  ALIASES.set(f.name, f);
  for (const a of f.aliases) ALIASES.set(a, f);
}

export const OPERATORS: { op: string; label: string; kinds: FieldKind[] }[] = [
  { op: "=", label: "égal", kinds: ["number", "boolean", "key", "raw"] },
  { op: "!=", label: "différent", kinds: ["number", "boolean", "key", "raw"] },
  { op: "<", label: "moins que", kinds: ["number", "duration"] },
  { op: "<=", label: "au plus", kinds: ["number", "duration"] },
  { op: ">", label: "plus que", kinds: ["number", "duration"] },
  { op: ">=", label: "au moins", kinds: ["number", "duration"] },
  { op: "~", label: "contient", kinds: ["key", "raw", "text"] },
  { op: "!~", label: "ne contient pas", kinds: ["key", "raw", "text"] },
];

export const MAX_LENGTH = 2000;
const MAX_DEPTH = 32;

/** Lower case, without accents: how field names and keywords are compared. */
export function fold(s: string): string {
  return s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

export function fieldOf(word: string): FieldInfo | undefined {
  return ALIASES.get(fold(word));
}

// ------------------------------------------------------------------ lexer

export type TokenType = "word" | "string" | "operator" | "lparen" | "rparen" | "comma";

export interface Token {
  type: TokenType;
  text: string;
  start: number;
  end: number;
  /** A string token whose closing quote is missing. */
  unclosed?: boolean;
}

export type Keyword = "AND" | "OR" | "NOT" | "IN";

export function keyword(t: Token | undefined): Keyword | null {
  if (!t || t.type !== "word") return null;
  switch (fold(t.text)) {
    case "and":
    case "et":
      return "AND";
    case "or":
    case "ou":
      return "OR";
    case "not":
    case "non":
      return "NOT";
    case "in":
    case "dans":
      return "IN";
    default:
      return null;
  }
}

const OPERATOR_CHARS = "=<>!~";
const STOP_CHARS = "()\",'" + OPERATOR_CHARS;

export class QueryError extends Error {
  // Plain fields: node --test strips types but does not compile parameter properties.
  readonly start: number;
  readonly end: number;

  constructor(message: string, start: number, end: number) {
    super(message);
    this.start = start;
    this.end = end;
  }
}

/** The tokens of a text. Lenient (for colouring as one types): never throws. */
export function lex(text: string): Token[] {
  const tokens: Token[] = [];
  let i = 0;
  while (i < text.length) {
    const c = text[i];
    if (/\s/.test(c)) {
      i++;
    } else if (c === "(") {
      tokens.push({ type: "lparen", text: c, start: i, end: ++i });
    } else if (c === ")") {
      tokens.push({ type: "rparen", text: c, start: i, end: ++i });
    } else if (c === ",") {
      tokens.push({ type: "comma", text: c, start: i, end: ++i });
    } else if (c === '"' || c === "'") {
      const close = text.indexOf(c, i + 1);
      if (close < 0) {
        tokens.push({ type: "string", text: text.slice(i + 1), start: i, end: text.length, unclosed: true });
        i = text.length;
      } else {
        tokens.push({ type: "string", text: text.slice(i + 1, close), start: i, end: close + 1 });
        i = close + 1;
      }
    } else if (OPERATOR_CHARS.includes(c)) {
      const two = text.slice(i, i + 2);
      if (two === "<=" || two === ">=" || two === "!=" || two === "!~") {
        tokens.push({ type: "operator", text: two, start: i, end: i + 2 });
        i += 2;
      } else {
        tokens.push({ type: "operator", text: c, start: i, end: ++i });
      }
    } else {
      const start = i;
      while (i < text.length && !/\s/.test(text[i]) && !STOP_CHARS.includes(text[i])) i++;
      tokens.push({ type: "word", text: text.slice(start, i), start, end: i });
    }
  }
  return tokens;
}

// ------------------------------------------------------------------ values

export function number(raw: string): number | null {
  let s = raw.trim().toLowerCase().replace(/ /g, "");
  s = s.replace(/(\$|pi2|pi²|min|ans?)$/, "");
  let factor = 1;
  if (s.endsWith("k")) {
    factor = 1000;
    s = s.slice(0, -1);
  }
  let half = 0;
  if (s.endsWith("½")) {
    half = 0.5;
    s = s.slice(0, -1);
  }
  if (s === "" && half > 0) return half;
  if (!/^-?\d+(\.\d+)?$/.test(s)) return null;
  return (Number(s) + half) * factor;
}

/** Hours, from "3j", "24h", "2sem" or a bare number of days. */
export function durationHours(raw: string): number | null {
  const m = /^(\d+(?:\.\d+)?)\s*(h|j|d|sem|s|w)?$/.exec(raw.trim().toLowerCase());
  if (!m) return null;
  const n = Number(m[1]);
  const unit = m[2] ?? "j";
  return unit === "h" ? n : unit === "sem" || unit === "s" || unit === "w" ? n * 24 * 7 : n * 24;
}

export function yesNo(raw: string): boolean | null {
  switch (fold(raw)) {
    case "oui":
    case "vrai":
    case "true":
    case "yes":
    case "1":
      return true;
    case "non":
    case "faux":
    case "false":
    case "no":
    case "0":
      return false;
    default:
      return null;
  }
}

/** The API's normalized key: "Plateau-Mont-Royal" and "plateau mont royal" are one. */
export function normalizeKey(value: string): string {
  return fold(value).replace(/[^a-z0-9]+/g, " ").trim();
}

function example(field: FieldInfo): string {
  switch (field.name) {
    case "prix":
      return "prix <= 1800";
    case "taille":
      return "taille >= 4½";
    case "metro":
    case "rem":
    case "transport":
      return `${field.name} <= 10`;
    case "age":
      return "age < 3j";
    case "annee":
      return "annee >= 2000";
    case "texte":
      return "texte ~ terrasse";
    case "adresse":
      return 'adresse ~ "Saint-Denis"';
    default:
      return `${field.name} >= 1`;
  }
}

function distance(a: string, b: string): number {
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    prev = cur;
  }
  return prev[b.length];
}

/** The field this unknown name was probably meant to be. */
export function closestField(word: string): string | null {
  const folded = fold(word);
  let best: string | null = null;
  let bestDistance = 3;
  for (const alias of ALIASES.keys()) {
    const d = distance(alias, folded);
    if (d < bestDistance) {
      bestDistance = d;
      best = ALIASES.get(alias)!.name;
    }
  }
  return best;
}

// ------------------------------------------------------------------ parser

/** The fields a query uses, with the offer each one implies (for the "rent only" warning). */
export interface Checked {
  fields: FieldInfo[];
}

/** Reads a query as the API does: throws a QueryError with the same message and span. */
export function check(text: string): Checked {
  const fields: FieldInfo[] = [];
  if (!text.trim()) return { fields };
  if (text.length > MAX_LENGTH) {
    throw new QueryError(`La requête est trop longue (${MAX_LENGTH} caractères au plus).`, 0, text.length);
  }
  const tokens = lex(text);
  for (const t of tokens) {
    if (t.unclosed) throw new QueryError(`Guillemet ${text[t.start]} jamais refermé.`, t.start, text.length);
    if (t.type === "operator" && t.text === "!") {
      throw new QueryError("« ! » s'écrit != (différent) ou !~ (ne contient pas).", t.start, t.end);
    }
  }
  const length = text.length;
  let pos = 0;
  let depth = 0;
  const peek = () => tokens[pos];
  const peekKeyword = (k: Keyword) => keyword(peek()) === k;

  function parseOr(): void {
    parseAnd();
    while (peekKeyword("OR")) {
      const or = tokens[pos++];
      if (!peek()) throw new QueryError(`Un critère est attendu après « ${or.text} ».`, or.start, or.end);
      parseAnd();
    }
  }

  function parseAnd(): void {
    parseUnary();
    for (;;) {
      const t = peek();
      if (!t || t.type === "rparen" || keyword(t) === "OR") break;
      if (keyword(t) === "AND") {
        pos++;
        if (!peek()) throw new QueryError(`Un critère est attendu après « ${t.text} ».`, t.start, t.end);
      }
      parseUnary();
    }
  }

  function parseUnary(): void {
    if (peekKeyword("NOT")) {
      const not = tokens[pos++];
      if (!peek()) throw new QueryError(`Un critère est attendu après « ${not.text} ».`, not.start, not.end);
      parseUnary();
      return;
    }
    parseAtom();
  }

  function parseAtom(): void {
    const t = peek();
    if (!t) throw new QueryError("Un critère est attendu.", length, length);
    if (t.type === "lparen") {
      if (++depth > MAX_DEPTH) throw new QueryError("Trop de parenthèses imbriquées.", t.start, t.end);
      pos++;
      parseOr();
      const close = peek();
      if (!close || close.type !== "rparen") throw new QueryError("Parenthèse jamais refermée.", t.start, t.end);
      pos++;
      depth--;
      return;
    }
    if (t.type !== "word" || keyword(t) !== null) {
      throw new QueryError(`Un nom de champ est attendu ici, pas « ${t.text} ».`, t.start, t.end);
    }
    parseComparison();
  }

  function parseComparison(): void {
    const name = tokens[pos++];
    const field = fieldOf(name.text);
    if (!field) {
      const closest = closestField(name.text);
      const hint = closest ? ` Vouliez-vous dire « ${closest} » ?` : "";
      throw new QueryError(`Champ inconnu « ${name.text} ».${hint}`, name.start, name.end);
    }
    fields.push(field);
    const next = peek();
    if (next?.type === "operator") {
      pos++;
      const value = peek();
      if (!value || (value.type !== "word" && value.type !== "string")) {
        throw new QueryError(
          `Une valeur est attendue après « ${next.text} ».`,
          next.start,
          value ? value.end : next.end,
        );
      }
      pos++;
      compare(field, name, next, value);
      return;
    }
    const notIn = keyword(next) === "NOT" && keyword(tokens[pos + 1]) === "IN";
    if (next && (keyword(next) === "IN" || notIn)) {
      pos += notIn ? 2 : 1;
      const values = readList(tokens[pos - 1]);
      if (field.kind !== "key" && field.kind !== "raw") {
        throw new QueryError(
          `DANS (...) sert aux listes de quartiers, villes, sources... pas à « ${name.text} ».`,
          name.start,
          name.end,
        );
      }
      for (const v of values) {
        const key = field.kind === "key" ? normalizeKey(v.text) : v.text.trim().toLowerCase();
        if (!key) throw new QueryError("Valeur vide.", v.start, v.end);
      }
      return;
    }
    if (field.name !== "stationnement" && field.kind !== "boolean") {
      throw new QueryError(`« ${name.text} » attend une comparaison, ex. ${example(field)}.`, name.start, name.end);
    }
  }

  function readList(inToken: Token): Token[] {
    const open = peek();
    if (!open || open.type !== "lparen") {
      throw new QueryError(
        `Une liste entre parenthèses est attendue après « ${inToken.text} », ex. (Plateau, Rosemont).`,
        inToken.start,
        inToken.end,
      );
    }
    pos++;
    const values: Token[] = [];
    for (;;) {
      const v = peek();
      if (!v || (v.type !== "word" && v.type !== "string")) {
        throw new QueryError("Une valeur est attendue dans la liste.", v ? v.start : open.start, v ? v.end : length);
      }
      values.push(v);
      pos++;
      const sep = peek();
      if (sep?.type === "comma") {
        pos++;
        continue;
      }
      if (sep?.type === "rparen") {
        pos++;
        return values;
      }
      throw new QueryError(
        "Liste jamais refermée : séparez les valeurs par des virgules et fermez avec ).",
        open.start,
        sep ? sep.end : length,
      );
    }
  }

  function compare(field: FieldInfo, name: Token, op: Token, value: Token): void {
    const o = op.text;
    switch (field.kind) {
      case "number":
        if (value.type === "string" || number(value.text) === null) {
          throw new QueryError(`Un nombre est attendu après « ${o} », ex. ${example(field)}.`, value.start, value.end);
        }
        if (o === "~" || o === "!~") {
          throw new QueryError("« ~ » sert au texte : pour un nombre, utilisez =, <, <=, > ou >=.", op.start, op.end);
        }
        return;
      case "duration":
        if (durationHours(value.text) === null) {
          throw new QueryError("Une durée est attendue, ex. age < 3j ou age < 24h.", value.start, value.end);
        }
        if (!["<", "<=", ">", ">="].includes(o)) {
          throw new QueryError("« age » se compare avec <, <=, > ou >=, ex. age < 3j.", op.start, op.end);
        }
        return;
      case "boolean":
        if (yesNo(value.text) === null || !(o === "=" || o === "!=")) {
          throw new QueryError(
            `« ${name.text} » est oui ou non : écrivez « ${name.text} » ou « NON ${name.text} ».`,
            op.start,
            value.end,
          );
        }
        return;
      case "key":
      case "raw": {
        const v = field.kind === "key" ? normalizeKey(value.text) : value.text.trim().toLowerCase();
        if (!v) throw new QueryError("Valeur vide.", value.start, value.end);
        if (!["=", "!=", "~", "!~"].includes(o)) {
          throw new QueryError(`« ${name.text} » se compare avec =, !=, ~ ou DANS (...).`, op.start, op.end);
        }
        return;
      }
      case "text":
        if (!(o === "~" || o === "!~")) {
          throw new QueryError(
            `« ${name.text} » se cherche avec ~ (contient), ex. ${example(field)}.`,
            op.start,
            op.end,
          );
        }
        return;
    }
  }

  parseOr();
  if (pos < tokens.length) {
    const t = tokens[pos];
    throw new QueryError(t.type === "rparen" ? "Parenthèse fermante en trop." : `« ${t.text} » inattendu.`, t.start, t.end);
  }
  return { fields };
}

export type CheckResult = { ok: true; fields: FieldInfo[] } | { ok: false; message: string; start: number; end: number };

export function validate(text: string): CheckResult {
  try {
    return { ok: true, ...check(text) };
  } catch (e) {
    if (e instanceof QueryError) return { ok: false, message: e.message, start: e.start, end: e.end };
    throw e;
  }
}

// ------------------------------------------------------------------ colouring

export type Role = "field" | "unknown" | "keyword" | "operator" | "value" | "string" | "paren" | "comma";

export interface Span {
  start: number;
  end: number;
  role: Role;
}

/** What each token is, for the editor's colours: a field, a value, a keyword... */
export function highlight(text: string): Span[] {
  const tokens = lex(text);
  return tokens.map((t, i) => {
    const prev = tokens[i - 1];
    let role: Role;
    if (t.type === "string") role = "string";
    else if (t.type === "operator") role = "operator";
    else if (t.type === "lparen" || t.type === "rparen") role = "paren";
    else if (t.type === "comma") role = "comma";
    else if (prev?.type === "operator" || insideList(tokens, i)) role = "value";
    else if (keyword(t)) role = "keyword";
    else role = fieldOf(t.text) ? "field" : "unknown";
    return { start: t.start, end: t.end, role };
  });
}

/** Whether token i sits in the (a, b) list of an IN. */
function insideList(tokens: Token[], i: number): boolean {
  for (let j = i - 1; j >= 0; j--) {
    const t = tokens[j];
    if (t.type === "comma" || t.type === "word" || t.type === "string") continue;
    if (t.type === "lparen") return keyword(tokens[j - 1]) === "IN";
    return false;
  }
  return false;
}

// ------------------------------------------------------------------ completions

export interface Completion {
  /** Shown in the menu. */
  label: string;
  /** Replaces the word under the cursor. */
  insert: string;
  detail?: string;
  kind: "field" | "operator" | "value" | "keyword";
}

export interface CompletionContext {
  /** The span of the text the chosen completion replaces. */
  from: number;
  to: number;
  items: Completion[];
}

export type ValueLists = Partial<Record<NonNullable<FieldInfo["values"]>, { value: string; label?: string }[]>>;

function quote(value: string): string {
  return /^[^\s()",'=<>!~]+$/.test(value) && !keyword({ type: "word", text: value, start: 0, end: 0 })
    ? value
    : `"${value.replace(/"/g, "")}"`;
}

const BOOLEAN_VALUES = ["oui", "non"];

/**
 * What can come at the cursor: a field at the start of a term, an operator after a field,
 * a value after an operator (the known quartiers, villes, sources...), a keyword after a
 * complete term.
 */
export function complete(text: string, cursor: number, lists: ValueLists = {}, offer?: "rent" | "sale"): CompletionContext {
  const before = text.slice(0, cursor);
  const tokens = lex(before);
  let last = tokens[tokens.length - 1];
  // The word being typed (none right after a space or a bracket).
  const typing =
    last && last.end === cursor && (last.type === "word" || (last.type === "string" && last.unclosed)) ? last : undefined;
  const from = typing ? typing.start : cursor;
  const prefix = typing ? fold(typing.type === "string" ? typing.text : typing.text) : "";
  const context = typing ? tokens.slice(0, -1) : tokens;
  last = context[context.length - 1];
  const prev = context[context.length - 2];

  const startsWith = (s: string) => fold(s).startsWith(prefix) || (prefix.length > 1 && fold(s).includes(prefix));

  const fieldItems = (): Completion[] =>
    FIELDS.filter((f) => !f.offer || !offer || f.offer === offer)
      .filter((f) => startsWith(f.name) || f.aliases.some(startsWith))
      .map((f) => ({ label: f.name, insert: f.kind === "boolean" ? f.name : `${f.name} `, detail: f.label, kind: "field" }));

  const keywordItems = (words: string[]): Completion[] =>
    words.filter(startsWith).map((w) => ({ label: w, insert: `${w} `, kind: "keyword" }));

  const valueItems = (field: FieldInfo): Completion[] => {
    if (field.kind === "boolean") return BOOLEAN_VALUES.filter(startsWith).map((v) => ({ label: v, insert: `${v} `, kind: "value" }));
    const list = field.values ? (lists[field.values] ?? []) : [];
    return list
      .filter((v) => startsWith(v.value) || (v.label ? startsWith(v.label) : false))
      .slice(0, 50)
      .map((v) => ({ label: v.label ?? v.value, insert: `${quote(v.value)} `, detail: v.label ? v.value : undefined, kind: "value" }));
  };

  // After an operator: a value of that field.
  if (last?.type === "operator" && prev?.type === "word") {
    const field = fieldOf(prev.text);
    return { from, to: cursor, items: field ? valueItems(field) : [] };
  }
  // Inside an IN list: a value.
  if (last && (last.type === "lparen" || last.type === "comma")) {
    let j = context.length - 1;
    while (j >= 0 && context[j].type !== "lparen") j--;
    if (j > 0 && keyword(context[j - 1]) === "IN") {
      let k = j - 2;
      if (keyword(context[k]) === "NOT") k--;
      const field = context[k] ? fieldOf(context[k].text) : undefined;
      return { from, to: cursor, items: field ? valueItems(field) : [] };
    }
  }
  // After a field name: its operators (or, for a yes/no field, the next term).
  if (last?.type === "word" && !keyword(last) && prev?.type !== "operator" && fieldOf(last.text)) {
    const field = fieldOf(last.text)!;
    if (!typing) {
      const ops: Completion[] = OPERATORS.filter((o) => o.kinds.includes(field.kind)).map((o) => ({
        label: o.op,
        insert: `${o.op} `,
        detail: o.label,
        kind: "operator",
      }));
      if (field.kind === "key" || field.kind === "raw") ops.push({ label: "DANS", insert: "DANS (", detail: "parmi une liste", kind: "keyword" });
      if (field.kind === "boolean" || field.name === "stationnement") {
        return { from, to: cursor, items: [...keywordItems(["ET", "OU"]), ...ops] };
      }
      return { from, to: cursor, items: ops };
    }
  }
  // After a complete term: a keyword, or the next field (ET is implied).
  const afterTerm =
    last &&
    (last.type === "rparen" || last.type === "string" || (last.type === "word" && !keyword(last)));
  if (afterTerm) {
    return { from, to: cursor, items: [...keywordItems(["ET", "OU", "NON"]), ...fieldItems()] };
  }
  return { from, to: cursor, items: [...fieldItems(), ...keywordItems(["NON"])] };
}
