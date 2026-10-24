import type { Metadata } from "next";

import { ApiError, trackedListings } from "@/lib/api";
import type { TrackedListing } from "@/lib/types";
import { TrackingBoard } from "@/components/tracking/TrackingBoard";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Suivi" };

export default async function SuiviPage() {
  let tracked: TrackedListing[] = [];
  let hidden: TrackedListing[] = [];
  let error: string | null = null;
  try {
    [tracked, hidden] = await Promise.all([trackedListings(false), trackedListings(true)]);
  } catch (e) {
    error = e instanceof ApiError ? e.message : "Une erreur inattendue est survenue.";
  }
  return <TrackingBoard tracked={tracked} hidden={hidden} error={error} />;
}
