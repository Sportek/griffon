import type { Metadata } from "next";

import { ApiError, recentAlerts, savedSearches } from "@/lib/api";
import type { Alert, SavedSearch } from "@/lib/types";
import { AlertsView } from "@/components/alerts/AlertsView";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "Alertes" };

export default async function AlertesPage() {
  let searches: SavedSearch[] = [];
  let alerts: Alert[] = [];
  let error: string | null = null;
  try {
    [searches, alerts] = await Promise.all([savedSearches(), recentAlerts(80)]);
  } catch (e) {
    error = e instanceof ApiError ? e.message : "Une erreur inattendue est survenue.";
  }
  return <AlertsView searches={searches} alerts={alerts} error={error} />;
}
