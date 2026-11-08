import "server-only";

import { getListing } from "./api";
import type { ListingDetail } from "./types";

/** One listing by its id, or null for an id that cannot be one (or a listing that is gone). */
export async function loadListing(id: string): Promise<ListingDetail | null> {
  if (!/^[a-f0-9]{24}$/.test(id)) return null;
  return getListing(id);
}
