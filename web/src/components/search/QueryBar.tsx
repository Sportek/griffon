"use client";

import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Button, Icon, IconButton } from "@vibe/core";
import { Check, CloseSmall, Info, Warning } from "@vibe/icons";

import { AMENITIES, NEARBY, NEARBY_NAMES, SERVICES, propertyTypeName, sourceName } from "@/lib/format";
import {
  complete,
  FIELDS,
  highlight,
  OPERATORS,
  validate,
  type Completion,
  type Role,
  type ValueLists,
} from "@/lib/query-language";
import type { FilterOptions } from "@/lib/types";
import styles from "./QueryBar.module.css";

const EXAMPLES = [
  { query: "(quartier ~ rosemont OU quartier ~ villeray) ET taille >= 4½ ET prix <= 1900", label: "Deux quartiers, 4 ½ et plus" },
  {
    query: '(quartier ~ plateau ET prix <= 2000) OU (quartier = Rosemont ET prix <= 1700)',
    label: "Un budget par quartier",
  },
  { query: "animaux chauffe NON meuble metro <= 10", label: "Animaux, chauffé, non meublé, près du métro" },
  { query: "age < 24h ET source != kijiji", label: "Nouvelles du jour, sauf Kijiji" },
  { query: "texte ~ terrasse OU commodite = balcon", label: "Une terrasse ou un balcon" },
];

/** The values the completions offer for each list field. */
function valueLists(options: FilterOptions): ValueLists {
  const known = (keys: { key: string; label: string }[], raw: string[]) => [
    ...keys.map((k) => ({ value: k.key, label: k.label })),
    ...raw.filter((r) => !keys.some((k) => k.key === r.toLowerCase())).map((r) => ({ value: r })),
  ];
  return {
    neighborhoods: options.neighborhoods.map((value) => ({ value })),
    cities: options.cities.map((value) => ({ value })),
    sources: options.sources.map((value) => ({ value, label: sourceName(value) })),
    propertyTypes: options.propertyTypes.map((value) => ({ value, label: propertyTypeName(value) ?? value })),
    amenities: known(AMENITIES, options.amenities),
    utilitiesIncluded: known(SERVICES, options.utilitiesIncluded),
    categories: Object.entries({ ...Object.fromEntries(NEARBY.map((n) => [n.key, n.label])), ...NEARBY_NAMES }).map(
      ([value, label]) => ({ value, label }),
    ),
  };
}

/** The text cut into coloured runs, the error underlined, and a marker where the caret is. */
function Mirror({
  text,
  cursor,
  error,
  caretRef,
}: {
  text: string;
  cursor: number;
  error: { start: number; end: number } | null;
  caretRef: React.RefObject<HTMLSpanElement | null>;
}) {
  const roles: (Role | null)[] = new Array(text.length).fill(null);
  for (const span of highlight(text)) roles.fill(span.role, span.start, span.end);
  const runs: React.ReactNode[] = [];
  let i = 0;
  while (i <= text.length) {
    if (i === cursor) runs.push(<span key="caret" ref={caretRef} />);
    if (i === text.length) break;
    const role = roles[i];
    const bad = !!error && i >= error.start && i < error.end;
    let j = i + 1;
    while (j < text.length && j !== cursor && roles[j] === role && (!!error && j >= error.start && j < error.end) === bad) j++;
    runs.push(
      <span key={i} data-role={role ?? undefined} data-error={bad || undefined}>
        {text.slice(i, j)}
      </span>,
    );
    i = j;
  }
  // A trailing newline would collapse: keep the last line's height.
  runs.push(<span key="end">{"​"}</span>);
  return <>{runs}</>;
}

/**
 * The query editor under the filter bar: Griffon's filter language, coloured as one types,
 * checked on every key (the same errors as the API), with completions of the fields, the
 * operators and the known values (quartiers, villes, sources...). Enter applies the query.
 */
export function QueryBar({
  value,
  sale,
  options,
  onApply,
  onClose,
}: {
  value: string | undefined;
  sale: boolean;
  options: FilterOptions;
  onApply: (query: string | undefined) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState(value ?? "");
  const [cursor, setCursor] = useState(draft.length);
  const [menuOpen, setMenuOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [helpOpen, setHelpOpen] = useState(!value);
  const [lastValue, setLastValue] = useState(value);
  const input = useRef<HTMLTextAreaElement>(null);
  const caret = useRef<HTMLSpanElement>(null);
  const menu = useRef<HTMLUListElement>(null);
  const pendingCursor = useRef<number | null>(null);
  const listId = useId();
  const lists = useMemo(() => valueLists(options), [options]);

  // A query changed elsewhere (back in history, an alert opened as a search) replaces the draft.
  if (value !== lastValue) {
    setLastValue(value);
    setDraft(value ?? "");
  }

  const result = useMemo(() => validate(draft), [draft]);
  const completion = useMemo(
    () => (menuOpen ? complete(draft, cursor, lists, sale ? "sale" : "rent") : null),
    [menuOpen, draft, cursor, lists, sale],
  );
  const items = completion?.items ?? [];
  const showMenu = menuOpen && items.length > 0;
  const applied = (value ?? "") === draft.trim();
  // The word being typed at the end is not an error yet: no red while the owner types it.
  const typing = !result.ok && menuOpen && cursor === draft.length && result.end === draft.length && /\S$/.test(draft);
  const state = !draft.trim() ? "empty" : result.ok ? "ok" : typing ? "typing" : "error";
  const offWarning = result.ok
    ? result.fields.find((f) => f.offer && f.offer !== (sale ? "sale" : "rent"))
    : undefined;

  useLayoutEffect(() => {
    if (pendingCursor.current != null && input.current) {
      input.current.setSelectionRange(pendingCursor.current, pendingCursor.current);
      pendingCursor.current = null;
    }
    // The menu opens under the caret, measured on the mirror's marker.
    const c = caret.current;
    const m = menu.current;
    if (c && m) {
      const room = (m.parentElement?.clientWidth ?? 0) - m.offsetWidth;
      m.style.left = `${Math.max(0, Math.min(c.offsetLeft - 8, room))}px`;
      m.style.top = `${c.offsetTop + c.offsetHeight + 6}px`;
    }
  });

  useEffect(() => {
    if (!value) input.current?.focus();
    // Only when the bar opens empty: the owner opened it to write a query.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function edit(text: string, at: number) {
    setDraft(text.replace(/\r?\n/g, " "));
    setCursor(at);
    setActive(0);
  }

  function accept(item: Completion) {
    if (!completion) return;
    const next = draft.slice(0, completion.from) + item.insert + draft.slice(completion.to);
    const at = completion.from + item.insert.length;
    pendingCursor.current = at;
    edit(next, at);
    setMenuOpen(true);
    input.current?.focus();
  }

  function apply() {
    if (!result.ok) return;
    setMenuOpen(false);
    setHelpOpen(false);
    onApply(draft.trim() || undefined);
  }

  function insertExample(text: string, replace: boolean) {
    const next = replace ? text : `${draft.trimEnd()}${draft.trim() ? " " : ""}${text}`;
    pendingCursor.current = next.length;
    edit(next, next.length);
    setMenuOpen(false);
    input.current?.focus();
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (showMenu) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        setActive((a) => (a + (event.key === "ArrowDown" ? 1 : items.length - 1)) % items.length);
        return;
      }
      if (event.key === "Tab" || (event.key === "Enter" && !event.ctrlKey && !event.metaKey)) {
        event.preventDefault();
        accept(items[Math.min(active, items.length - 1)]);
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        setMenuOpen(false);
        return;
      }
    }
    if (event.key === " " && event.ctrlKey) {
      event.preventDefault();
      setMenuOpen(true);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      apply();
    }
  }

  const syncCursor = (el: HTMLTextAreaElement) => setCursor(el.selectionStart ?? el.value.length);

  return (
    <div className={styles.bar} role="group" aria-label="Requête de filtre">
      <div className={styles.row}>
        <span className={styles.label} aria-hidden>
          Requête
        </span>
        <div className={styles.editor} data-invalid={state === "error" || undefined}>
          <div className={styles.mirror} aria-hidden>
            <Mirror text={draft} cursor={cursor} error={result.ok || typing ? null : result} caretRef={caret} />
          </div>
          <textarea
            ref={input}
            className={styles.input}
            value={draft}
            rows={1}
            spellCheck={false}
            autoCapitalize="off"
            autoComplete="off"
            autoCorrect="off"
            placeholder='Ex. quartier DANS (Rosemont, Villeray) ET prix <= 1800 OU age < 3j'
            aria-label="Requête de filtre"
            aria-invalid={!result.ok || undefined}
            aria-describedby={`${listId}-status`}
            role="combobox"
            aria-expanded={showMenu}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={showMenu ? `${listId}-${active}` : undefined}
            onChange={(e) => {
              edit(e.target.value, e.target.selectionStart ?? e.target.value.length);
              setMenuOpen(true);
            }}
            onKeyDown={onKeyDown}
            onSelect={(e) => syncCursor(e.currentTarget)}
            onBlur={() => setMenuOpen(false)}
          />
          {showMenu && (
            <ul
              ref={menu}
              id={listId}
              role="listbox"
              className={styles.menu}
              aria-label="Suggestions"
            >
              {items.map((item, i) => (
                <li
                  key={`${item.kind}-${item.label}-${i}`}
                  id={`${listId}-${i}`}
                  role="option"
                  aria-selected={i === active}
                  className={styles.option}
                  data-kind={item.kind}
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => accept(item)}
                >
                  <span className={styles.optionLabel}>{item.label}</span>
                  {item.detail && <span className={styles.optionDetail}>{item.detail}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className={styles.actions}>
          <Button size="small" onClick={apply} disabled={!result.ok || applied}>
            Appliquer
          </Button>
          <IconButton
            icon={Info}
            size="small"
            kind="tertiary"
            aria-label={helpOpen ? "Masquer l'aide" : "Afficher l'aide"}
            aria-expanded={helpOpen}
            active={helpOpen}
            onClick={() => setHelpOpen((o) => !o)}
          />
          <IconButton
            icon={CloseSmall}
            size="small"
            kind="tertiary"
            aria-label="Retirer la requête et fermer"
            onClick={() => {
              if (value) onApply(undefined);
              onClose();
            }}
          />
        </div>
      </div>

      <p id={`${listId}-status`} className={styles.status} data-state={state} aria-live="polite">
        {state === "ok" && <Icon icon={Check} size={14} />}
        {state === "error" && <Icon icon={Warning} size={14} />}
        <span>
          {state === "empty" &&
            "Tapez un champ (prix, quartier, taille…) : les suggestions s'ouvrent. Ctrl + Espace pour les rouvrir."}
          {state === "typing" && "Continuez, ou choisissez une suggestion (Entrée ou Tab)."}
          {state === "error" && !result.ok && result.message}
          {state === "ok" && (applied ? "Requête appliquée." : "Requête valide : Entrée pour l'appliquer.")}
          {state === "ok" && offWarning && (
            <span className={styles.warning}>
              « {offWarning.name} » ne vaut que pour les {offWarning.offer === "rent" ? "locations" : "propriétés à vendre"} :
              aucune annonce ici ne l&apos;a.
            </span>
          )}
        </span>
      </p>

      {helpOpen && (
        <div className={styles.help}>
          <section>
            <h3>Exemples</h3>
            <ul className={styles.examples}>
              {EXAMPLES.map((e) => (
                <li key={e.query}>
                  <button type="button" onClick={() => insertExample(e.query, true)}>
                    <code>{e.query}</code>
                    <span>{e.label}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
          <section>
            <h3>Combiner</h3>
            <dl className={styles.grammar}>
              <dt>
                <code>ET</code> <code>OU</code> <code>NON</code>
              </dt>
              <dd>Deux critères côte à côte valent ET. NON passe avant ET, qui passe avant OU.</dd>
              <dt>
                <code>( … )</code>
              </dt>
              <dd>Groupe des critères : (A OU B) ET C.</dd>
              <dt>
                <code>DANS (a, b)</code>
              </dt>
              <dd>Une valeur parmi une liste ; NON DANS pour l&apos;exclure.</dd>
              <dt>
                <code>&quot;…&quot;</code>
              </dt>
              <dd>Entre guillemets, une valeur avec des espaces.</dd>
            </dl>
            <h3>Comparer</h3>
            <ul className={styles.operators}>
              {OPERATORS.map((o) => (
                <li key={o.op}>
                  <code>{o.op}</code> {o.label}
                </li>
              ))}
            </ul>
            <p className={styles.note}>
              Nombres : 1800, 1800$, 1.5k, 4½. Durées : 24h, 3j, 2sem. Oui/non : <code>animaux</code>,{" "}
              <code>NON meuble</code>, <code>animaux = non</code>. Majuscules et accents sont ignorés.
            </p>
          </section>
          <section className={styles.fieldsSection}>
            <h3>Champs</h3>
            <ul className={styles.fields}>
              {FIELDS.map((f) => (
                <li key={f.name} data-off={(f.offer && f.offer !== (sale ? "sale" : "rent")) || undefined}>
                  <button type="button" onClick={() => insertExample(f.example, false)} title={`Ajouter ${f.example}`}>
                    <code>{f.name}</code>
                    <span>{f.label}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </div>
  );
}
