"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore, useTransition } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { Button, EmptyState, Loader } from "@vibe/core";
import { Gallery, Location } from "@vibe/icons";

import { loadGroup, loadListingSummary, loadPage } from "@/app/actions";
import { single } from "@/lib/groups";
import { toQueryString, type SearchState } from "@/lib/search-params";
import type { Suggestion } from "@/lib/suggest";
import type { BoundingBox, FilterOptions, ListingGroup, ListingGroupPage, ListingSummary, MapPoint } from "@/lib/types";
import { BuildingCard } from "../BuildingCard";
import { ListingCard } from "../ListingCard";
import { useToast } from "../ToastProvider";
import { AdvancedFilters } from "./AdvancedFilters";
import { FilterBar } from "./FilterBar";
import { SaveAlertModal } from "./SaveAlertModal";
import styles from "./SearchView.module.css";

const ListingsMap = dynamic(() => import("../map/ListingsMap").then((m) => m.ListingsMap), {
  ssr: false,
  loading: () => <div className={styles.mapLoading} />,
});

const LAST_VISIT_KEY = "griffon:last-visit";

let previousVisit: string | null | undefined;

/** Read once per page load, before this visit overwrites it. */
function readPreviousVisit(): string | null {
  if (previousVisit === undefined) {
    try {
      previousVisit = localStorage.getItem(LAST_VISIT_KEY);
    } catch {
      // Private mode or blocked storage: "new" falls back to the last 48 hours.
      previousVisit = null;
    }
  }
  return previousVisit;
}

const noSubscription = () => () => {};

/** When the owner last opened the search, so listings found since read as new. */
function useLastVisit(): string | null {
  const lastVisit = useSyncExternalStore(noSubscription, readPreviousVisit, () => null);
  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        localStorage.setItem(LAST_VISIT_KEY, new Date().toISOString());
      } catch {}
    }, 10_000);
    return () => clearTimeout(timer);
  }, []);
  return lastVisit;
}

export function SearchView({
  state,
  page,
  points,
  options,
  suggestion,
  error,
}: {
  state: SearchState;
  page: ListingGroupPage;
  points: MapPoint[];
  options: FilterOptions;
  suggestion: Suggestion | null;
  error: string | null;
}) {
  const router = useRouter();
  const toast = useToast();
  const [pending, startTransition] = useTransition();
  const [loadingMore, startLoadingMore] = useTransition();
  const [groups, setGroups] = useState(page.content);
  const [currentPage, setCurrentPage] = useState(page);
  const [lastPage, setLastPage] = useState(page);
  const [view, setView] = useState<"list" | "map">("list");
  const [hovered, setHovered] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [preview, setPreview] = useState<ListingGroup | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [alertOpen, setAlertOpen] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const lastVisit = useLastVisit();

  // A new search from the server replaces the list (and the extra pages loaded so far).
  if (page !== lastPage) {
    setLastPage(page);
    setGroups(page.content);
    setCurrentPage(page);
    setSelected(null);
    setPreview(null);
  }

  const navigate = useCallback(
    (next: SearchState) => {
      startTransition(() => router.push(`/${toQueryString(next)}`, { scroll: false }));
      listRef.current?.scrollTo({ top: 0 });
    },
    [router],
  );

  const change = (changes: Partial<SearchState>) => navigate({ ...state, ...changes });

  function loadMore() {
    startLoadingMore(async () => {
      const result = await loadPage(state, currentPage.page + 1);
      if (!result.ok) {
        toast.show(result.error, "negative");
        return;
      }
      setCurrentPage(result.value);
      setGroups((current) => {
        const known = new Set(current.map((g) => g.key));
        return [...current, ...result.value.content.filter((g) => !known.has(g.key))];
      });
    });
  }

  /** A pin is a building (its key) or a listing alone (its id), like the list's items. */
  async function select(key: string | null) {
    setSelected(key);
    if (!key) {
      setPreview(null);
      return;
    }
    const inList = groups.find((g) => g.key === key);
    const card = listRef.current?.querySelector(`[data-group="${CSS.escape(key)}"]`);
    if (card && window.matchMedia("(min-width: 1024px)").matches) {
      card.scrollIntoView({ block: "nearest", behavior: "smooth" });
      setPreview(null);
      return;
    }
    if (inList) {
      setPreview(inList);
      return;
    }
    if (/^[a-f0-9]{24}$/.test(key)) {
      const result = await loadListingSummary(key);
      if (result.ok && result.value) setPreview(single(result.value));
    } else {
      const result = await loadGroup(state, key);
      if (result.ok && result.value) setPreview(result.value);
    }
  }

  function searchArea(zone: BoundingBox) {
    navigate({ ...state, zone });
  }

  const withFavorite = (l: ListingSummary, id: string, favorite: boolean): ListingSummary =>
    l.id !== id
      ? l
      : {
              ...l,
              tracking: l.tracking
                ? { ...l.tracking, favorite }
                : {
                    listingId: id,
                    favorite,
                    status: null,
                    notes: null,
                    visitAt: null,
                    hidden: false,
                    priceWhenTracked: l.price,
                    createdAt: new Date().toISOString(),
                    updatedAt: new Date().toISOString(),
                  },
        };

  const favoriteChanged = (id: string, favorite: boolean) =>
    setGroups((current) =>
      current.map((g) => ({ ...g, listings: g.listings.map((l) => withFavorite(l, id, favorite)) })),
    );

  const located = points.length;
  const total = currentPage.totalListings;
  const buildings = groups.filter((g) => g.count > 1).length;

  return (
    <div className={styles.view} data-view={view}>
      <FilterBar
        state={state}
        options={options}
        onChange={change}
        onOpenAdvanced={() => setAdvancedOpen(true)}
        onSaveAlert={() => setAlertOpen(true)}
      />

      <div className={styles.split}>
        <section className={styles.listPane} ref={listRef} aria-labelledby="results-heading" aria-busy={pending}>
          <header className={styles.resultsHeader}>
            <h1 id="results-heading" className={styles.count}>
              {total.toLocaleString("fr-CA")} annonce{total > 1 ? "s" : ""}
            </h1>
            <span className={styles.scope}>
              {pending ? (
                <Loader size={16} />
              ) : (
                <>
                  {!state.unites && currentPage.totalGroups < total
                    ? `${currentPage.totalGroups.toLocaleString("fr-CA")} adresses · `
                    : ""}
                  toutes sources, sans doublons · {located.toLocaleString("fr-CA")} sur la carte
                </>
              )}
            </span>
            {(state.unites || buildings > 0) && (
              <Button size="xs" kind="tertiary" onClick={() => change({ unites: state.unites ? undefined : true })}>
                {state.unites ? "Regrouper par immeuble" : "Voir chaque logement"}
              </Button>
            )}
            {state.zone && (
              <Button size="xs" kind="tertiary" onClick={() => change({ zone: undefined })}>
                Retirer la zone de carte
              </Button>
            )}
          </header>

          {error ? (
            <EmptyState
              className={styles.empty}
              title="Les annonces sont injoignables"
              description={error}
              mainAction={{ text: "Réessayer", onClick: () => router.refresh() }}
            />
          ) : groups.length === 0 ? (
            <EmptyState
              className={styles.empty}
              title="Aucune annonce ne correspond"
              description={suggestion ? suggestion.message : "Essayez d'élargir le budget ou la taille."}
              mainAction={
                suggestion
                  ? { text: suggestion.action, onClick: () => startTransition(() => router.push(suggestion.href)) }
                  : { text: "Effacer les critères", onClick: () => navigate({}) }
              }
            />
          ) : (
            <ol className={styles.list}>
              {groups.map((group) => (
                <li key={group.key} data-group={group.key}>
                  <SearchItem
                    group={group}
                    highlighted={selected === group.key || hovered === group.key}
                    seenBefore={lastVisit}
                    onHover={setHovered}
                    onFavoriteChange={favoriteChanged}
                  />
                </li>
              ))}
            </ol>
          )}

          {currentPage.hasNext && (
            <div className={styles.more}>
              <Button kind="secondary" onClick={loadMore} loading={loadingMore}>
                {state.unites ? "Afficher plus d'annonces" : "Afficher plus d'adresses"}
              </Button>
            </div>
          )}
        </section>

        <section className={styles.mapPane} aria-label="Carte">
          <ListingsMap
            points={points}
            activeId={hovered ?? selected}
            onSelect={select}
            onSearchArea={searchArea}
            loading={pending}
            className={styles.map}
          />
          {preview && (
            <div className={styles.preview}>
              <SearchItem group={preview} seenBefore={lastVisit} onFavoriteChange={favoriteChanged} />
            </div>
          )}
        </section>
      </div>

      <div className={styles.viewToggle}>
        {view === "list" ? (
          <Button leftIcon={Location} onClick={() => setView("map")}>
            Carte
          </Button>
        ) : (
          <Button leftIcon={Gallery} onClick={() => setView("list")}>
            Liste
          </Button>
        )}
      </div>

      {advancedOpen && (
        <AdvancedFilters
          open
          state={state}
          options={options}
          onClose={() => setAdvancedOpen(false)}
          onApply={(next) => {
            setAdvancedOpen(false);
            navigate(next);
          }}
        />
      )}
      {alertOpen && <SaveAlertModal open state={state} onClose={() => setAlertOpen(false)} />}
    </div>
  );
}

/** A building with several matching units, or a listing on its own. */
function SearchItem({
  group,
  ...props
}: {
  group: ListingGroup;
  highlighted?: boolean;
  seenBefore?: string | null;
  onHover?: (key: string | null) => void;
  onFavoriteChange?: (id: string, favorite: boolean) => void;
}) {
  return group.count > 1 ? <BuildingCard group={group} {...props} /> : <ListingCard listing={group.listings[0]} {...props} />;
}
