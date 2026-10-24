"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { EmptyState, Tab, TabList } from "@vibe/core";

import { saveTracking } from "@/app/actions";
import { STATUSES } from "@/lib/format";
import type { TrackedListing, TrackingStatus } from "@/lib/types";
import { ClientOnly } from "../ClientOnly";
import { useToast } from "../ToastProvider";
import { TrackedCard } from "./TrackedCard";
import styles from "./TrackingBoard.module.css";

const TABS = ["Tableau", "Liste", "Masquées"] as const;

export function TrackingBoard({
  tracked,
  hidden,
  error,
}: {
  tracked: TrackedListing[];
  hidden: TrackedListing[];
  error: string | null;
}) {
  const router = useRouter();
  const toast = useToast();
  const [tab, setTab] = useState(0);
  const [items, setItems] = useState(tracked);
  const [source, setSource] = useState(tracked);
  if (tracked !== source) {
    setSource(tracked);
    setItems(tracked);
  }

  async function move(listingId: string, status: TrackingStatus | null) {
    const previous = items;
    setItems((current) =>
      current.map((i) => (i.tracking.listingId === listingId ? { ...i, tracking: { ...i.tracking, status } } : i)),
    );
    const result = await saveTracking(listingId, status ? { status } : { clearStatus: true });
    if (!result.ok) {
      setItems(previous);
      toast.show(result.error, "negative");
    }
  }

  async function unhide(listingId: string) {
    const result = await saveTracking(listingId, { hidden: false });
    if (result.ok) {
      toast.show("Annonce de nouveau visible dans les résultats", "positive");
      router.refresh();
    } else {
      toast.show(result.error, "negative");
    }
  }

  const unsorted = items.filter((i) => !i.tracking.status);
  const columns = [
    { key: "NONE", label: "Sans statut", color: null as string | null, items: unsorted },
    ...STATUSES.map((s) => ({
      key: s.value,
      label: s.label,
      color: s.color,
      items: items.filter((i) => i.tracking.status === s.value),
    })),
  ];

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Suivi</h1>
        <p className={styles.summary}>
          {items.length} annonce{items.length > 1 ? "s" : ""} suivie{items.length > 1 ? "s" : ""}
          {" · "}
          {items.filter((i) => i.tracking.favorite).length} favori
          {items.filter((i) => i.tracking.favorite).length > 1 ? "s" : ""}
        </p>
        <ClientOnly fallback={<div className={styles.tabsPlaceholder} />}>
          <TabList activeTabId={tab} onTabChange={setTab} size="sm" className={styles.tabs}>
            {TABS.map((label, i) => (
              <Tab key={label} value={i}>
                {label === "Masquées" && hidden.length ? `${label} (${hidden.length})` : label}
              </Tab>
            ))}
          </TabList>
        </ClientOnly>
      </header>

      {error ? (
        <EmptyState title="Le suivi est injoignable" description={error} className={styles.empty} />
      ) : tab === 2 ? (
        hidden.length === 0 ? (
          <EmptyState
            className={styles.empty}
            title="Aucune annonce masquée"
            description="« Masquer » sur une fiche la retire des résultats, avec ses doublons des autres sites."
          />
        ) : (
          <ul className={styles.list}>
            {hidden.map((item) => (
              <li key={item.tracking.listingId}>
                <TrackedCard item={item} onUnhide={() => unhide(item.tracking.listingId)} />
              </li>
            ))}
          </ul>
        )
      ) : items.length === 0 ? (
        <EmptyState
          className={styles.empty}
          title="Rien à suivre pour l'instant"
          description="Ajoutez une annonce aux favoris ou donnez-lui un statut depuis sa fiche : elle apparaîtra ici."
          mainAction={{ text: "Chercher un logement", onClick: () => router.push("/") }}
        />
      ) : tab === 0 ? (
        <div className={styles.board} role="list" aria-label="Annonces par statut">
          {columns.map((column) => (
            <section key={column.key} className={styles.column} role="listitem" aria-label={column.label}>
              <header
                className={styles.columnHeader}
                style={column.color ? { background: column.color } : undefined}
                data-status={column.key}
              >
                <span>{column.label}</span>
                <span className={styles.columnCount}>{column.items.length}</span>
              </header>
              <ul className={styles.columnItems}>
                {column.items.map((item) => (
                  <li key={item.tracking.listingId}>
                    <TrackedCard item={item} compact onMove={(status) => move(item.tracking.listingId, status)} />
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      ) : (
        <ul className={styles.list}>
          {items.map((item) => (
            <li key={item.tracking.listingId}>
              <TrackedCard item={item} onMove={(status) => move(item.tracking.listingId, status)} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
