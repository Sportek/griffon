"use client";

import Link from "next/link";

import type { ListingSummary } from "@/lib/types";
import {
  ago,
  formatArea,
  formatAvailability,
  formatBedrooms,
  formatPrice,
  formatRent,
  formatSize,
  isForSale,
  propertyTypeName,
  saleFacts,
  sourceName,
} from "@/lib/format";
import { thumbnail } from "@/lib/photos";
import { FavoriteButton } from "./FavoriteButton";
import { Signals } from "./Signals";
import { StatusPill } from "./StatusPill";
import styles from "./ListingCard.module.css";

function isHeated(listing: ListingSummary) {
  return listing.utilitiesIncluded.some((u) => /heat|chauff/i.test(u));
}

function nearestTransit(listing: ListingSummary): string | null {
  const metro = listing.metroWalkMinutes;
  const rem = listing.remWalkMinutes;
  if (metro == null && rem == null) return null;
  if (rem != null && (metro == null || rem < metro)) return `REM à ${Math.round(rem)} min`;
  return `Métro à ${Math.round(metro as number)} min`;
}

/** For sale: what a buyer pays besides the price, and the age of the building. */
function saleDetails(listing: ListingSummary): string[] {
  return [
    listing.condoFeesMonthly != null ? `Copropriété ${formatPrice(listing.condoFeesMonthly)}/mois` : null,
    listing.yearBuilt != null ? `Construit en ${listing.yearBuilt}` : null,
    listing.lotAreaSqft != null ? `Terrain ${formatArea(listing.lotAreaSqft)}` : null,
  ].filter((d): d is string => !!d);
}

export function ListingCard({
  listing,
  highlighted,
  priority,
  seenBefore,
  onHover,
  onFavoriteChange,
}: {
  listing: ListingSummary;
  highlighted?: boolean;
  /** At the top of the first screen: the photo loads first instead of lazily. */
  priority?: boolean;
  seenBefore?: string | null;
  onHover?: (id: string | null) => void;
  onFavoriteChange?: (id: string, favorite: boolean) => void;
}) {
  const sale = isForSale(listing);
  const facts = sale
    ? saleFacts(listing)
    : [formatSize(listing), formatBedrooms(listing.bedrooms), formatArea(listing.areaSqft)].filter(Boolean);
  const place = [listing.neighborhood, listing.city].filter(Boolean).join(", ") || listing.address || "Lieu non précisé";
  const transit = nearestTransit(listing);
  const photoCount = listing.photoCount ?? listing.photos.length;
  const availability = formatAvailability(listing.availableDate);
  const cheaperElsewhere = listing.duplicates
    .filter((d) => d.price != null && listing.price != null && d.price < listing.price)
    .sort((a, b) => (a.price as number) - (b.price as number))[0];

  return (
    <article
      className={styles.card}
      data-highlighted={highlighted || undefined}
      data-inactive={!listing.active || undefined}
      onMouseEnter={() => onHover?.(listing.id)}
      onMouseLeave={() => onHover?.(null)}
    >
      <div className={styles.photo}>
        {listing.photos[0] ? (
          // eslint-disable-next-line @next/next/no-img-element -- photos come from the source sites' CDNs
          <img
            src={thumbnail(listing.photos[0])}
            alt=""
            loading={priority ? "eager" : "lazy"}
            fetchPriority={priority ? "high" : undefined}
            referrerPolicy="no-referrer"
          />
        ) : (
          <span className={styles.noPhoto}>Pas de photo</span>
        )}
        {photoCount > 1 && <span className={styles.photoCount}>{photoCount} photos</span>}
      </div>

      <div className={styles.body}>
        <div className={styles.top}>
          <span className={styles.price}>{formatRent(listing)}</span>
          <Signals listing={listing} seenBefore={seenBefore} />
        </div>
        <Link href={`/annonces/${listing.id}`} className={styles.title}>
          {facts.length ? facts.join(" · ") : propertyTypeName(listing.propertyType) ?? "Logement"}
          <span className="visually-hidden">
            , {listing.address ?? place}, {formatRent(listing)}
          </span>
          <span className={styles.stretch} aria-hidden />
        </Link>
        <p className={styles.place}>{place}</p>
        <p className={styles.details}>
          {sale
            ? [transit, ...saleDetails(listing)].filter(Boolean).join(" · ") || "Frais et année de construction non précisés"
            : [transit, isHeated(listing) ? "Chauffé" : null, availability].filter(Boolean).join(" · ") ||
              "Proximité et disponibilité non précisées"}
        </p>
        <div className={styles.meta}>
          <span>
            {sourceName(listing.source)}
            {listing.duplicates.length > 0 && (
              <>
                {" "}
                + {listing.duplicates.length} autre{listing.duplicates.length > 1 ? "s" : ""}
              </>
            )}
            {" · "}
            {listing.active ? `vue ${ago(listing.firstSeenAt)}` : `retirée ${ago(listing.inactiveSince ?? listing.lastSeenAt)}`}
          </span>
          {cheaperElsewhere && (
            <span className={styles.cheaper}>
              Moins cher sur {sourceName(cheaperElsewhere.source)}
            </span>
          )}
        </div>
        {listing.tracking?.status && (
          <div className={styles.status}>
            <StatusPill status={listing.tracking.status} size="small" />
          </div>
        )}
      </div>

      <div className={styles.favorite}>
        <FavoriteButton
          listingId={listing.id}
          favorite={listing.tracking?.favorite ?? false}
          onChange={(favorite) => onFavoriteChange?.(listing.id, favorite)}
        />
      </div>
    </article>
  );
}
