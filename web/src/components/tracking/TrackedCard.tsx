"use client";

import Link from "next/link";
import { Button } from "@vibe/core";
import { Show } from "@vibe/icons";

import { formatDateTime, formatPrice, formatRent, formatSize, sourceName } from "@/lib/format";
import type { TrackedListing, TrackingStatus } from "@/lib/types";
import { FavoriteButton } from "../FavoriteButton";
import { StatusSelect } from "../StatusSelect";
import styles from "./TrackedCard.module.css";

/** What changed on a followed listing since it was saved: removed, or a new price. */
function changes(item: TrackedListing): string[] {
  const { listing, tracking } = item;
  if (!listing) return ["Annonce supprimée de Griffon"];
  const out: string[] = [];
  if (!listing.active) out.push("Retirée du site");
  if (tracking.priceWhenTracked != null && listing.price != null && listing.price !== tracking.priceWhenTracked) {
    out.push(`Prix : ${formatPrice(tracking.priceWhenTracked)} → ${formatPrice(listing.price)}`);
  }
  return out;
}

export function TrackedCard({
  item,
  compact,
  onMove,
  onUnhide,
}: {
  item: TrackedListing;
  compact?: boolean;
  onMove?: (status: TrackingStatus | null) => void;
  onUnhide?: () => void;
}) {
  const { listing, tracking } = item;
  const alerts = changes(item);
  const place = listing ? [listing.neighborhood, listing.city].filter(Boolean).join(", ") : null;

  return (
    <article className={styles.card} data-compact={compact || undefined}>
      {listing?.photos[0] && !compact && (
        // eslint-disable-next-line @next/next/no-img-element -- photos come from the source sites' CDNs
        <img src={listing.photos[0]} alt="" className={styles.photo} loading="lazy" referrerPolicy="no-referrer" />
      )}
      <div className={styles.body}>
        <div className={styles.top}>
          {listing ? (
            <Link href={`/annonces/${listing.id}`} className={styles.title}>
              {formatRent(listing)}
              {formatSize(listing) ? ` · ${formatSize(listing)}` : ""}
            </Link>
          ) : (
            <span className={styles.title}>Annonce introuvable</span>
          )}
          {listing && !onUnhide && <FavoriteButton listingId={listing.id} favorite={tracking.favorite} size="xs" />}
        </div>
        {listing && (
          <p className={styles.place}>
            {place || listing.address || "Lieu non précisé"} · {sourceName(listing.source)}
          </p>
        )}
        {alerts.map((a) => (
          <p key={a} className={styles.change}>
            {a}
          </p>
        ))}
        {tracking.visitAt && <p className={styles.visit}>Visite {formatDateTime(tracking.visitAt)}</p>}
        {tracking.notes && <p className={styles.notes}>{tracking.notes}</p>}

        {onMove && (
          <div className={styles.status}>
            <StatusSelect value={tracking.status} onChange={onMove} size="small" />
          </div>
        )}
        {onUnhide && (
          <div className={styles.status}>
            <Button size="small" kind="secondary" leftIcon={Show} onClick={onUnhide}>
              Ne plus masquer
            </Button>
          </div>
        )}
      </div>
    </article>
  );
}
