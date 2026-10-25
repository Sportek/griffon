"use client";

import { useState } from "react";
import {
  Checkbox,
  Dropdown,
  Modal,
  ModalBasicLayout,
  ModalContent,
  ModalFooter,
  ModalHeader,
  NumberField,
  TextField,
} from "@vibe/core";

import { AMENITIES, NEARBY, propertyTypeName, SERVICES, sourceName } from "@/lib/format";
import type { SearchState } from "@/lib/search-params";
import type { FilterOptions } from "@/lib/types";
import styles from "./AdvancedFilters.module.css";

type Option<V> = { value: V; label: string };

const MAX_SIZES: Option<number>[] = [1, 2, 3, 4, 5, 6, 7].map((v) => ({ value: v, label: `${v} ½ au plus` }));
const BEDROOMS: Option<number>[] = [
  { value: 1, label: "1 chambre et +" },
  { value: 2, label: "2 chambres et +" },
  { value: 3, label: "3 chambres et +" },
  { value: 4, label: "4 chambres et +" },
];
const BATHROOMS: Option<number>[] = [
  { value: 1, label: "1 salle de bain et +" },
  { value: 2, label: "2 salles de bain et +" },
];

function toggle(list: string[] | undefined, value: string, on: boolean): string[] | undefined {
  const next = on ? [...(list ?? []), value] : (list ?? []).filter((v) => v !== value);
  return next.length ? Array.from(new Set(next)) : undefined;
}

const RESET: Partial<SearchState> = {
  q: undefined,
  prixMin: undefined,
  tailleMax: undefined,
  chambres: undefined,
  sdb: undefined,
  superficie: undefined,
  types: undefined,
  villes: undefined,
  services: undefined,
  commodites: undefined,
  animaux: undefined,
  meuble: undefined,
  stationnement: undefined,
  commerces: undefined,
  sources: undefined,
  photos: undefined,
  retirees: undefined,
};

export function AdvancedFilters({
  open,
  state,
  options,
  onClose,
  onApply,
}: {
  open: boolean;
  state: SearchState;
  options: FilterOptions;
  onClose: () => void;
  onApply: (changes: Partial<SearchState>) => void;
}) {
  // Mounted on opening, so each opening starts from the current search.
  const [draft, setDraft] = useState<SearchState>(state);
  const set = (changes: Partial<SearchState>) => setDraft((d) => ({ ...d, ...changes }));

  const types: Option<string>[] = options.propertyTypes.map((t) => ({ value: t, label: propertyTypeName(t) ?? t }));
  const cities: Option<string>[] = options.cities.map((c) => ({ value: c, label: c }));

  return (
    <Modal id="advanced-filters" show={open} onClose={onClose} size="medium" closeButtonAriaLabel="Fermer">
      <ModalBasicLayout>
        <ModalHeader title="Filtres" />
        <ModalContent>
          <div className={styles.form}>
            <section className={styles.section}>
              <TextField
                title="Mot-clé"
                placeholder="piscine, terrasse, rénové…"
                value={draft.q ?? ""}
                onChange={(v) => set({ q: v || undefined })}
                size="medium"
              />
              <div className={styles.row}>
                <NumberField
                  id="filter-price-min"
                  label="Prix minimum ($)"
                  value={draft.prixMin ?? null}
                  min={0}
                  step={50}
                  onChange={(v) => set({ prixMin: v ?? undefined })}
                />
                <NumberField
                  id="filter-price-max"
                  label="Prix maximum ($)"
                  value={draft.prixMax ?? null}
                  min={0}
                  step={50}
                  onChange={(v) => set({ prixMax: v ?? undefined })}
                />
              </div>
            </section>

            <section className={styles.section}>
              <h3 className={styles.heading}>Logement</h3>
              <div className={styles.row}>
                <Dropdown
                  label="Taille maximale"
                  placeholder="Peu importe"
                  options={MAX_SIZES}
                  value={MAX_SIZES.find((o) => o.value === draft.tailleMax)}
                  clearable
                  onChange={(o: Option<number> | null) => set({ tailleMax: o?.value })}
                  onClear={() => set({ tailleMax: undefined })}
                />
                <Dropdown
                  label="Chambres"
                  placeholder="Peu importe"
                  options={BEDROOMS}
                  value={BEDROOMS.find((o) => o.value === draft.chambres)}
                  clearable
                  onChange={(o: Option<number> | null) => set({ chambres: o?.value })}
                  onClear={() => set({ chambres: undefined })}
                />
              </div>
              <div className={styles.row}>
                <Dropdown
                  label="Salles de bain"
                  placeholder="Peu importe"
                  options={BATHROOMS}
                  value={BATHROOMS.find((o) => o.value === draft.sdb)}
                  clearable
                  onChange={(o: Option<number> | null) => set({ sdb: o?.value })}
                  onClear={() => set({ sdb: undefined })}
                />
                <NumberField
                  id="filter-area-min"
                  label="Superficie minimale (pi²)"
                  value={draft.superficie ?? null}
                  min={0}
                  step={50}
                  onChange={(v) => set({ superficie: v ?? undefined })}
                />
              </div>
              <Dropdown
                label="Type de logement"
                placeholder="Tous les types"
                multi
                options={types}
                value={types.filter((t) => draft.types?.includes(t.value))}
                onChange={(selected: Option<string>[]) =>
                  set({ types: selected.length ? selected.map((s) => s.value) : undefined })
                }
                clearable
                onClear={() => set({ types: undefined })}
              />
              <Dropdown
                label="Villes"
                placeholder="Toutes les villes"
                multi
                searchable
                options={cities}
                value={cities.filter((c) => draft.villes?.includes(c.value))}
                onChange={(selected: Option<string>[]) =>
                  set({ villes: selected.length ? selected.map((s) => s.value) : undefined })
                }
                clearable
                onClear={() => set({ villes: undefined })}
              />
            </section>

            <section className={styles.section}>
              <h3 className={styles.heading}>Conditions</h3>
              <div className={styles.checks}>
                <Checkbox
                  label="Animaux acceptés"
                  checked={!!draft.animaux}
                  onChange={(e) => set({ animaux: e.target.checked || undefined })}
                />
                <Checkbox
                  label="Meublé ou semi-meublé"
                  checked={!!draft.meuble}
                  onChange={(e) => set({ meuble: e.target.checked || undefined })}
                />
                <Checkbox
                  label="Stationnement"
                  checked={!!draft.stationnement}
                  onChange={(e) => set({ stationnement: e.target.checked || undefined })}
                />
              </div>
              <p className={styles.hint}>
                Une annonce qui ne précise pas ces conditions n&apos;apparaît pas quand le filtre est coché.
              </p>
            </section>

            <section className={styles.section}>
              <h3 className={styles.heading}>Services inclus</h3>
              <div className={styles.checks}>
                {SERVICES.map((s) => (
                  <Checkbox
                    key={s.key}
                    label={s.label}
                    checked={!!draft.services?.includes(s.key)}
                    onChange={(e) => set({ services: toggle(draft.services, s.key, e.target.checked) })}
                  />
                ))}
              </div>
            </section>

            <section className={styles.section}>
              <h3 className={styles.heading}>Commodités</h3>
              <div className={styles.checks}>
                {AMENITIES.map((a) => (
                  <Checkbox
                    key={a.key}
                    label={a.label}
                    checked={!!draft.commodites?.includes(a.key)}
                    onChange={(e) => set({ commodites: toggle(draft.commodites, a.key, e.target.checked) })}
                  />
                ))}
              </div>
            </section>

            <section className={styles.section}>
              <h3 className={styles.heading}>À distance de marche</h3>
              <div className={styles.checks}>
                {NEARBY.map((n) => (
                  <Checkbox
                    key={n.key}
                    label={n.label}
                    checked={!!draft.commerces?.includes(n.key)}
                    onChange={(e) => set({ commerces: toggle(draft.commerces, n.key, e.target.checked) })}
                  />
                ))}
              </div>
              <p className={styles.hint}>Au moins un à 15 min à pied ou moins. Seulement pour les annonces dont la proximité a été calculée.</p>
            </section>

            <section className={styles.section}>
              <h3 className={styles.heading}>Sources et affichage</h3>
              <div className={styles.checks}>
                {options.sources.map((s) => (
                  <Checkbox
                    key={s}
                    label={sourceName(s)}
                    checked={!draft.sources || draft.sources.includes(s)}
                    onChange={(e) => {
                      const current = draft.sources ?? options.sources;
                      const next = e.target.checked ? [...current, s] : current.filter((v) => v !== s);
                      set({ sources: next.length === options.sources.length ? undefined : next });
                    }}
                  />
                ))}
              </div>
              <div className={styles.checks}>
                <Checkbox
                  label="Avec photos seulement"
                  checked={!!draft.photos}
                  onChange={(e) => set({ photos: e.target.checked || undefined })}
                />
                <Checkbox
                  label="Inclure les annonces retirées"
                  checked={!!draft.retirees}
                  onChange={(e) => set({ retirees: e.target.checked || undefined })}
                />
              </div>
            </section>
          </div>
        </ModalContent>
      </ModalBasicLayout>
      <ModalFooter
        primaryButton={{ text: "Afficher les résultats", onClick: () => onApply(draft) }}
        secondaryButton={{ text: "Tout effacer", onClick: () => setDraft((d) => ({ ...d, ...RESET })) }}
      />
    </Modal>
  );
}
