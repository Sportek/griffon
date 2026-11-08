// Runs with `npm test` (node --test, which strips the types itself).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { complete, highlight, validate } from "./query-language.ts";

type Case = { q: string; error?: string; start?: number; end?: number };

// The cases the API runs too (ListingQueryTests): both parsers accept and refuse the same.
const cases: Case[] = JSON.parse(
  readFileSync(new URL("../../../listings-api/src/test/resources/query-cases.json", import.meta.url), "utf8"),
);

for (const c of cases) {
  test(`« ${c.q} »`, () => {
    const result = validate(c.q);
    if (c.error) {
      assert.equal(result.ok, false, "expected an error");
      if (!result.ok) {
        assert.ok(result.message.includes(c.error), `"${result.message}" should contain "${c.error}"`);
        assert.deepEqual([result.start, result.end], [c.start, c.end], "span of the error");
      }
    } else {
      assert.equal(result.ok, true, result.ok ? "" : result.message);
    }
  });
}

test("colours fields, keywords, operators and values", () => {
  const roles = highlight('quartier DANS (Rosemont, "Mile End") ET NON meublé zzz').map((s) => s.role);
  assert.deepEqual(roles, ["field", "keyword", "paren", "value", "comma", "string", "paren", "keyword", "keyword", "field", "unknown"]);
});

test("completes fields, operators and values", () => {
  const lists = { neighborhoods: [{ value: "Rosemont" }, { value: "Le Plateau-Mont-Royal" }] };
  assert.ok(complete("qua", 3).items.some((i) => i.label === "quartier"));
  const ops = complete("prix ", 5).items.map((i) => i.label);
  assert.ok(ops.includes("<=") && !ops.includes("~"));
  const values = complete("quartier = pla", 14, lists);
  assert.deepEqual(values.items.map((i) => i.insert), ['"Le Plateau-Mont-Royal" ']);
  assert.equal(values.from, 11);
  assert.ok(complete("quartier DANS (Rosemont, ", 25, lists).items.some((i) => i.label === "Le Plateau-Mont-Royal"));
  assert.ok(complete("prix <= 1800 ", 13).items.some((i) => i.label === "OU"));
  assert.ok(complete("animaux = ", 10).items.some((i) => i.label === "non"));
});
