"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button, EmptyState, Toggle } from "@vibe/core";
import { Delete, Search } from "@vibe/icons";

import { changeAlert, removeAlert } from "@/app/actions";
import { ago, formatPrice } from "@/lib/format";
import { fromFilter, toQueryString } from "@/lib/search-params";
import type { Alert, ListingFilter, SavedSearch } from "@/lib/types";
import { ListingCard } from "../ListingCard";
import { useToast } from "../ToastProvider";
import styles from "./AlertsView.module.css";

/** The saved criteria as one readable line. */
function describe(filter: ListingFilter): string {
  const parts = [
    filter.minRoomsQc ? `${filter.minRoomsQc} ½ et +` : null,
    filter.maxPrice ? `${formatPrice(filter.maxPrice)} max` : null,
    filter.neighborhoods?.length ? filter.neighborhoods.join(", ") : null,
    filter.cities?.length ? filter.cities.join(", ") : null,
    filter.maxTransitWalkMinutes ? `métro ou REM ≤ ${filter.maxTransitWalkMinutes} min` : null,
    filter.petsAllowed ? "animaux acceptés" : null,
    filter.utilitiesIncluded?.includes("chauffage") ? "chauffé" : null,
    filter.text ? `« ${filter.text} »` : null,
    filter.within ? "zone de carte" : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "Toutes les annonces en ligne";
}

function dayLabel(iso: string) {
  const date = new Date(iso);
  const today = new Date();
  const yesterday = new Date(Date.now() - 86_400_000);
  if (date.toDateString() === today.toDateString()) return "Aujourd'hui";
  if (date.toDateString() === yesterday.toDateString()) return "Hier";
  return date.toLocaleDateString("fr-CA", { weekday: "long", day: "numeric", month: "long" });
}

function SavedSearchRow({ search }: { search: SavedSearch }) {
  const router = useRouter();
  const toast = useToast();
  const [pending, startTransition] = useTransition();
  const [confirming, setConfirming] = useState(false);

  function update(changes: Parameters<typeof changeAlert>[1], message: string) {
    startTransition(async () => {
      const result = await changeAlert(search, changes);
      if (result.ok) {
        toast.show(message, "positive");
        router.refresh();
      } else toast.show(result.error, "negative");
    });
  }

  function remove() {
    if (!confirming) {
      setConfirming(true);
      return;
    }
    startTransition(async () => {
      const result = await removeAlert(search.id);
      if (result.ok) {
        toast.show(`Alerte « ${search.name} » supprimée`);
        router.refresh();
      } else toast.show(result.error, "negative");
    });
  }

  return (
    <li className={styles.search} data-paused={!search.enabled || undefined}>
      <div className={styles.searchMain}>
        <h3 className={styles.searchName}>{search.name}</h3>
        <p className={styles.searchCriteria}>{describe(search.filter)}</p>
        <p className={styles.searchMeta}>
          {search.matches.totalElements.toLocaleString("fr-CA")} annonce{search.matches.totalElements > 1 ? "s" : ""} en ligne
          {" · "}
          {search.lastAlertAt ? `dernière trouvée ${ago(search.lastAlertAt)}` : "rien de nouveau encore"}
          {" · "}
          {search.webhookUrl ? "envoyée sur Discord" : "dans Griffon seulement"}
          {search.notifyOnPriceDrop ? " · baisses de prix incluses" : ""}
        </p>
      </div>
      <div className={styles.searchActions}>
        <Toggle
          isSelected={search.enabled}
          onChange={(enabled) => update({ enabled }, enabled ? "Alerte réactivée" : "Alerte en pause")}
          disabled={pending}
          aria-label={search.enabled ? "Mettre en pause" : "Réactiver"}
          onOverrideText="Active"
          offOverrideText="En pause"
        />
        <Button
          size="small"
          kind="tertiary"
          leftIcon={Search}
          onClick={() => router.push(`/${toQueryString(fromFilter(search.filter))}`)}
        >
          Voir
        </Button>
        <Button
          size="small"
          kind="tertiary"
          color={confirming ? "negative" : "primary"}
          leftIcon={Delete}
          loading={pending && confirming}
          onClick={remove}
          onBlur={() => setConfirming(false)}
        >
          {confirming ? "Confirmer" : "Supprimer"}
        </Button>
      </div>
    </li>
  );
}

export function AlertsView({ searches, alerts, error }: { searches: SavedSearch[]; alerts: Alert[]; error: string | null }) {
  const router = useRouter();
  const groups = new Map<string, Alert[]>();
  for (const alert of alerts) {
    if (!alert.listing) continue;
    const day = dayLabel(alert.createdAt);
    groups.set(day, [...(groups.get(day) ?? []), alert]);
  }

  if (error) {
    return <EmptyState className={styles.empty} title="Les alertes sont injoignables" description={error} />;
  }

  return (
    <div className={styles.page}>
      <section className={styles.searches} aria-labelledby="searches-heading">
        <div className={styles.sectionHeader}>
          <h1 id="searches-heading" className={styles.title}>
            Alertes
          </h1>
          <Button size="small" onClick={() => router.push("/")}>
            Nouvelle alerte
          </Button>
        </div>
        {searches.length === 0 ? (
          <EmptyState
            className={styles.emptyInline}
            layout="compact"
            title="Aucune alerte"
            description="Faites une recherche, puis « M'alerter » : chaque nouvelle annonce correspondante arrivera ici, et sur Discord si vous le voulez."
          />
        ) : (
          <ul className={styles.searchList}>
            {searches.map((s) => (
              <SavedSearchRow key={s.id} search={s} />
            ))}
          </ul>
        )}
      </section>

      <section className={styles.feed} aria-labelledby="feed-heading">
        <h2 id="feed-heading" className={styles.feedTitle}>
          Dernières annonces trouvées
        </h2>
        {groups.size === 0 ? (
          <p className={styles.muted}>
            Les annonces trouvées par vos alertes s&apos;affichent ici après chaque collecte.{" "}
            <Link href="/?depuis=24h">Voir les nouveautés des dernières 24 h</Link>
          </p>
        ) : (
          [...groups.entries()].map(([day, items]) => (
            <div key={day} className={styles.day}>
              <h3 className={styles.dayTitle}>{day}</h3>
              <ul className={styles.feedList}>
                {items.map((alert) => (
                  <li key={alert.id}>
                    <p className={styles.reason}>
                      {alert.reason === "PRICE_DROP"
                        ? `Baisse de prix : ${formatPrice(alert.previousPrice)} → ${formatPrice(alert.price)}`
                        : "Nouvelle annonce"}
                      {alert.savedSearch && searches.length > 1 && <> · {alert.savedSearch.name}</>}
                    </p>
                    <ListingCard listing={alert.listing!} />
                  </li>
                ))}
              </ul>
            </div>
          ))
        )}
      </section>
    </div>
  );
}
