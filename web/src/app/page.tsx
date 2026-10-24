import { ApiError, getFilterOptions, mapListings, searchListings } from "@/lib/api";
import { parseSearch, toFilter } from "@/lib/search-params";
import { suggestRelaxation, type Suggestion } from "@/lib/suggest";
import type { FilterOptions, ListingPage, MapPoint } from "@/lib/types";
import { SearchView } from "@/components/search/SearchView";

export const dynamic = "force-dynamic";

const EMPTY_PAGE: ListingPage = { content: [], totalElements: 0, page: 0, totalPages: 0, hasNext: false };
const NO_OPTIONS: FilterOptions = {
  sources: [],
  cities: [],
  neighborhoods: [],
  propertyTypes: [],
  amenities: [],
  utilitiesIncluded: [],
};

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const state = parseSearch(await searchParams);
  const filter = toFilter(state);

  let page = EMPTY_PAGE;
  let points: MapPoint[] = [];
  let options = NO_OPTIONS;
  let suggestion: Suggestion | null = null;
  let error: string | null = null;
  try {
    [page, points, options] = await Promise.all([
      searchListings(filter, state.tri ?? "NEWEST", 0),
      mapListings(filter, 10_000),
      getFilterOptions(),
    ]);
    if (page.totalElements === 0) suggestion = await suggestRelaxation(state);
  } catch (e) {
    error = e instanceof ApiError ? e.message : "Une erreur inattendue est survenue.";
  }

  return (
    <SearchView state={state} page={page} points={points} options={options} suggestion={suggestion} error={error} />
  );
}
