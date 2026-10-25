"use server";

import { revalidatePath } from "next/cache";

import {
  ApiError,
  createSavedSearch,
  deleteSavedSearch,
  getListing,
  mapListings,
  searchGroups,
  searchListings,
  updateSavedSearch,
  updateTracking,
  type SavedSearchInput,
  type TrackingInput,
} from "@/lib/api";
import { toAlertFilter, toFilter, type SearchState } from "@/lib/search-params";
import { asGroups } from "@/lib/groups";
import type {
  BoundingBox,
  ListingGroup,
  ListingGroupPage,
  ListingSummary,
  MapPoint,
  SavedSearch,
  Tracking,
} from "@/lib/types";

/** Server actions return errors as values: a thrown error loses its message in production. */
export type Result<T> = { ok: true; value: T } | { ok: false; error: string };

async function attempt<T>(run: () => Promise<T>): Promise<Result<T>> {
  try {
    return { ok: true, value: await run() };
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "Une erreur inattendue est survenue.";
    return { ok: false, error: message };
  }
}

/** One page of the search: one item per building, or per listing with `unites`. */
export async function loadPage(state: SearchState, page: number): Promise<Result<ListingGroupPage>> {
  return attempt(async () =>
    state.unites
      ? asGroups(await searchListings(toFilter(state), state.tri ?? "NEWEST", page))
      : searchGroups(toFilter(state), state.tri ?? "NEWEST", page),
  );
}

/** A building pin's group, when it is not in the loaded pages of the list. */
export async function loadGroup(state: SearchState, buildingKey: string): Promise<Result<ListingGroup | null>> {
  return attempt(async () => {
    const page = await searchGroups({ ...toFilter(state), buildingKeys: [buildingKey] }, "PRICE_ASC", 0, 1);
    return page.content[0] ?? null;
  });
}

export async function loadMapPoints(state: SearchState, within?: BoundingBox): Promise<Result<MapPoint[]>> {
  return attempt(() => mapListings({ ...toFilter(state), within }, 10_000));
}

/** A pin's listing, when it is not in the loaded page of the list. */
export async function loadListingSummary(id: string): Promise<Result<ListingSummary | null>> {
  return attempt(async () => (await getListing(id)) as ListingSummary | null);
}

export async function saveTracking(listingId: string, input: TrackingInput): Promise<Result<Tracking>> {
  const result = await attempt(() => updateTracking(listingId, input));
  if (result.ok) {
    revalidatePath("/suivi");
    revalidatePath(`/annonces/${listingId}`);
  }
  return result;
}

export interface AlertSettings {
  name: string;
  webhookUrl?: string | null;
  notifyOnPriceDrop?: boolean;
}

export async function createAlert(state: SearchState, settings: AlertSettings): Promise<Result<SavedSearch>> {
  const result = await attempt(() =>
    createSavedSearch({
      name: settings.name,
      filter: toAlertFilter(state),
      webhookUrl: settings.webhookUrl || null,
      webhookFormat: "DISCORD",
      notifyOnPriceDrop: settings.notifyOnPriceDrop ?? false,
      enabled: true,
    }),
  );
  if (result.ok) revalidatePath("/alertes");
  return result;
}

export async function changeAlert(
  search: SavedSearch,
  changes: Partial<Pick<SavedSearchInput, "name" | "webhookUrl" | "notifyOnPriceDrop" | "enabled">>,
): Promise<Result<SavedSearch>> {
  const filter = Object.fromEntries(Object.entries(search.filter).filter(([, v]) => v != null));
  const result = await attempt(() =>
    updateSavedSearch(search.id, {
      name: changes.name ?? search.name,
      filter,
      webhookUrl: changes.webhookUrl !== undefined ? changes.webhookUrl || null : search.webhookUrl,
      webhookFormat: search.webhookFormat,
      notifyOnPriceDrop: changes.notifyOnPriceDrop ?? search.notifyOnPriceDrop,
      enabled: changes.enabled ?? search.enabled,
    }),
  );
  if (result.ok) revalidatePath("/alertes");
  return result;
}

export async function removeAlert(id: string): Promise<Result<boolean>> {
  const result = await attempt(() => deleteSavedSearch(id));
  if (result.ok) revalidatePath("/alertes");
  return result;
}
