import { ApiError, getFilterOptions, searchGroups, searchListings } from "@/lib/api";
import { asGroups } from "@/lib/groups";
import { parseSearch, toFilter } from "@/lib/search-params";
import { suggestRelaxation, type Suggestion } from "@/lib/suggest";
import type { FilterOptions, ListingGroupPage } from "@/lib/types";
import { SearchView } from "@/components/search/SearchView";

export const dynamic = "force-dynamic";

const EMPTY_PAGE: ListingGroupPage = { content: [], totalGroups: 0, totalListings: 0, page: 0, hasNext: false };
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
  let options = NO_OPTIONS;
  let suggestion: Suggestion | null = null;
  let error: string | null = null;
  try {
    const sort = state.tri ?? "NEWEST";
    // The map's pins are not awaited here: the map fetches them itself (/api/carte).
    [page, options] = await Promise.all([
      state.unites ? searchListings(filter, sort, 0).then(asGroups) : searchGroups(filter, sort, 0),
      getFilterOptions(),
    ]);
    if (page.totalListings === 0) suggestion = await suggestRelaxation(state);
  } catch (e) {
    error = e instanceof ApiError ? e.message : "Une erreur inattendue est survenue.";
  }

  return (
    <SearchView state={state} page={page} options={options} suggestion={suggestion} error={error} />
  );
}
