"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore, useTransition } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { Button, EmptyState, Loader } from "@vibe/core";
import { Gallery, Location } from "@vibe/icons";

import { loadListingSummary, loadPage } from "@/app/actions";
import { toQueryString, type SearchState } from "@/lib/search-params";
import type { Suggestion } from "@/lib/suggest";
import type { BoundingBox, FilterOptions, ListingPage, ListingSummary, MapPoint } from "@/lib/types";
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
  page: ListingPage;
  points: MapPoint[];
  options: FilterOptions;
  suggestion: Suggestion | null;
  error: string | null;
}) {
  const router = useRouter();
  const toast = useToast();
  const [pending, startTransition] = useTransition();
  const [loadingMore, startLoadingMore] = useTransition();
  const [listings, setListings] = useState(page.content);
  const [currentPage, setCurrentPage] = useState(page);
  const [lastPage, setLastPage] = useState(page);
  const [view, setView] = useState<"list" | "map">("list");
  const [hovered, setHovered] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [preview, setPreview] = useState<ListingSummary | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [alertOpen, setAlertOpen] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const lastVisit = useLastVisit();

  // A new search from the server replaces the list (and the extra pages loaded so far).
  if (page !== lastPage) {
    setLastPage(page);
    setListings(page.content);
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
      setListings((current) => {
        const known = new Set(current.map((l) => l.id));
        return [...current, ...result.value.content.filter((l) => !known.has(l.id))];
      });
    });
  }

  async function select(id: string | null) {
    setSelected(id);
    if (!id) {
      setPreview(null);
      return;
    }
    const inList = listings.find((l) => l.id === id);
    const card = listRef.current?.querySelector(`[data-listing="${id}"]`);
    if (card && window.matchMedia("(min-width: 1024px)").matches) {
      card.scrollIntoView({ block: "nearest", behavior: "smooth" });
      setPreview(null);
      return;
    }
    if (inList) {
      setPreview(inList);
      return;
    }
    const result = await loadListingSummary(id);
    if (result.ok && result.value) setPreview(result.value);
  }

  function searchArea(zone: BoundingBox) {
    navigate({ ...state, zone });
  }

  const favoriteChanged = (id: string, favorite: boolean) =>
    setListings((current) =>
      current.map((l) =>
        l.id === id
          ? {
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
            }
          : l,
      ),
    );

  const located = points.length;
  const total = currentPage.totalElements;

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
                  toutes sources, sans doublons · {located.toLocaleString("fr-CA")} sur la carte
                </>
              )}
            </span>
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
          ) : listings.length === 0 ? (
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
              {listings.map((listing) => (
                <li key={listing.id} data-listing={listing.id}>
                  <ListingCard
                    listing={listing}
                    highlighted={selected === listing.id || hovered === listing.id}
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
                Afficher plus d&apos;annonces
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
              <ListingCard listing={preview} seenBefore={lastVisit} onFavoriteChange={favoriteChanged} />
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
