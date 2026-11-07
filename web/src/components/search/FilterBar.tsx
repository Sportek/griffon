"use client";

import { Button, ButtonGroup, Dropdown } from "@vibe/core";
import { Filter, Notifications } from "@vibe/icons";

import { formatPrice } from "@/lib/format";
import { countAdvanced, isSale, SORTS, switchOffer, type SearchState } from "@/lib/search-params";
import type { FilterOptions, ListingSort } from "@/lib/types";
import { ClientOnly } from "../ClientOnly";
import styles from "./FilterBar.module.css";

type Option<V> = { value: V; label: string };

const budgets = (values: number[]): Option<number>[] => values.map((v) => ({ value: v, label: `${formatPrice(v)} max` }));
const RENT_BUDGETS = budgets([1000, 1250, 1500, 1750, 2000, 2250, 2500, 3000, 3500, 4000]);
const SALE_BUDGETS = budgets([300_000, 400_000, 500_000, 600_000, 750_000, 900_000, 1_000_000, 1_250_000, 1_500_000, 2_000_000]);
const SIZES: Option<number>[] = [1, 2, 3, 4, 5, 6].map((v) => ({ value: v, label: `${v} ½ et +` }));
const BEDROOMS: Option<number>[] = [1, 2, 3, 4, 5].map((v) => ({ value: v, label: `${v} ch. et +` }));
const OFFERS = [
  { value: "rent", text: "À louer" },
  { value: "sale", text: "À vendre" },
];
const TRANSIT: Option<number>[] = [5, 10, 15, 20].map((v) => ({ value: v, label: `≤ ${v} min à pied` }));
const SINCE: Option<"24h" | "3j" | "7j">[] = [
  { value: "24h", label: "Dernières 24 h" },
  { value: "3j", label: "3 derniers jours" },
  { value: "7j", label: "7 derniers jours" },
];
const SORT_OPTIONS: Option<ListingSort>[] = SORTS;

function pick<V>(options: Option<V>[], value: V | undefined) {
  return options.find((o) => o.value === value);
}

export function FilterBar({
  state,
  options,
  onChange,
  onOpenAdvanced,
  onSaveAlert,
}: {
  state: SearchState;
  options: FilterOptions;
  onChange: (changes: Partial<SearchState>) => void;
  onOpenAdvanced: () => void;
  onSaveAlert: () => void;
}) {
  const areas: Option<string>[] = options.neighborhoods.map((n) => ({ value: n, label: n }));
  const selectedAreas = areas.filter((a) => state.quartiers?.includes(a.value));
  const advanced = countAdvanced(state);
  const sale = isSale(state);
  const budgetOptions = sale ? SALE_BUDGETS : RENT_BUDGETS;

  return (
    <div className={styles.bar} role="search" aria-label="Critères de recherche">
      <div className={styles.offer}>
        <ButtonGroup
          size="small"
          groupAriaLabel="Type d'offre"
          options={OFFERS}
          value={sale ? "sale" : "rent"}
          onSelect={(value) => {
            const next = switchOffer(state, value === "sale");
            if (next !== state) onChange(next);
          }}
        />
      </div>
      <div className={styles.field} data-size="m">
        <ClientOnly fallback={<span className={styles.placeholder} />}>
          <Dropdown
            // A rent budget and a sale budget are different lists: remount on switch.
            key={sale ? "sale" : "rent"}
            size="small"
            placeholder={sale ? "Prix" : "Budget"}
            aria-label={sale ? "Prix maximum" : "Loyer maximum"}
            options={budgetOptions}
            value={pick(budgetOptions, state.prixMax)}
            clearable
            onChange={(o: Option<number> | null) => onChange({ prixMax: o?.value })}
            onClear={() => onChange({ prixMax: undefined })}
          />
        </ClientOnly>
      </div>
      <div className={styles.field} data-size="s">
        <ClientOnly fallback={<span className={styles.placeholder} />}>
          {sale ? (
            <Dropdown
              key="bedrooms"
              size="small"
              placeholder="Chambres"
              aria-label="Chambres minimum"
              options={BEDROOMS}
              value={pick(BEDROOMS, state.chambres)}
              clearable
              onChange={(o: Option<number> | null) => onChange({ chambres: o?.value })}
              onClear={() => onChange({ chambres: undefined })}
            />
          ) : (
            <Dropdown
              key="size"
              size="small"
              placeholder="Taille"
              aria-label="Taille minimale"
              options={SIZES}
              value={pick(SIZES, state.tailleMin)}
              clearable
              onChange={(o: Option<number> | null) => onChange({ tailleMin: o?.value })}
              onClear={() => onChange({ tailleMin: undefined })}
            />
          )}
        </ClientOnly>
      </div>
      <div className={styles.field} data-size="l">
        <ClientOnly fallback={<span className={styles.placeholder} />}>
          <Dropdown
            size="small"
            multi
            searchable
            placeholder="Quartiers"
            aria-label="Quartiers"
            noOptionsMessage="Aucun quartier connu"
            options={areas}
            value={selectedAreas}
            minVisibleCount={1}
            onChange={(selected: Option<string>[]) =>
              onChange({ quartiers: selected.length ? selected.map((s) => s.value) : undefined })
            }
            onClear={() => onChange({ quartiers: undefined })}
            clearable
          />
        </ClientOnly>
      </div>
      <div className={styles.field} data-size="m">
        <ClientOnly fallback={<span className={styles.placeholder} />}>
          <Dropdown
            size="small"
            placeholder="Métro ou REM"
            aria-label="Métro ou REM à distance de marche"
            options={TRANSIT}
            value={pick(TRANSIT, state.metro)}
            clearable
            onChange={(o: Option<number> | null) => onChange({ metro: o?.value })}
            onClear={() => onChange({ metro: undefined })}
          />
        </ClientOnly>
      </div>
      <div className={styles.field} data-size="m">
        <ClientOnly fallback={<span className={styles.placeholder} />}>
          <Dropdown
            size="small"
            placeholder="Publiée"
            aria-label="Date de publication"
            options={SINCE}
            value={pick(SINCE, state.depuis)}
            clearable
            onChange={(o: Option<"24h" | "3j" | "7j"> | null) => onChange({ depuis: o?.value })}
            onClear={() => onChange({ depuis: undefined })}
          />
        </ClientOnly>
      </div>
      <Button size="small" kind="secondary" leftIcon={Filter} onClick={onOpenAdvanced} className={styles.button}>
        {advanced ? `Filtres (${advanced})` : "Filtres"}
      </Button>
      <div className={styles.spacer} />
      <div className={styles.field} data-size="m">
        <ClientOnly fallback={<span className={styles.placeholder} />}>
          <Dropdown
            size="small"
            aria-label="Trier par"
            clearable={false}
            options={SORT_OPTIONS}
            value={pick(SORT_OPTIONS, state.tri ?? "NEWEST")}
            onChange={(o: Option<ListingSort>) => onChange({ tri: o.value === "NEWEST" ? undefined : o.value })}
          />
        </ClientOnly>
      </div>
      <Button size="small" leftIcon={Notifications} onClick={onSaveAlert} className={styles.button}>
        M&apos;alerter
      </Button>
    </div>
  );
}
