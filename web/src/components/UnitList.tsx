"use client";

import Link from "next/link";

import type { ListingSummary } from "@/lib/types";
import { formatArea, formatBedrooms, formatRent, formatSize, sourceName } from "@/lib/format";
import { FavoriteButton } from "./FavoriteButton";
import { Signals } from "./Signals";
import { StatusPill } from "./StatusPill";
import styles from "./UnitList.module.css";

/** The units of one building, one compact row each: size, unit, price, then what to do with it. */
export function UnitList({
  listings,
  seenBefore,
  onFavoriteChange,
}: {
  listings: ListingSummary[];
  seenBefore?: string | null;
  onFavoriteChange?: (id: string, favorite: boolean) => void;
}) {
  return (
    <ul className={styles.units}>
      {listings.map((listing) => (
        <li key={listing.id} className={styles.unit} data-inactive={!listing.active || undefined}>
          <Link href={`/annonces/${listing.id}`} className={styles.link}>
            <span className={styles.size}>
              {formatSize(listing) ?? formatBedrooms(listing.bedrooms) ?? "Taille non précisée"}
            </span>
            <span className={styles.details}>
              {[listing.unit ? `app. ${listing.unit}` : null, formatBedrooms(listing.bedrooms), formatArea(listing.areaSqft)]
                .filter(Boolean)
                .join(" · ") || sourceName(listing.source)}
            </span>
            <span className={styles.price}>{formatRent(listing)}</span>
          </Link>
          <span className={styles.aside}>
            <Signals listing={listing} seenBefore={seenBefore} />
            {listing.tracking?.status && <StatusPill status={listing.tracking.status} size="small" />}
            <FavoriteButton
              listingId={listing.id}
              favorite={listing.tracking?.favorite ?? false}
              size="xs"
              onChange={(favorite) => onFavoriteChange?.(listing.id, favorite)}
            />
          </span>
        </li>
      ))}
    </ul>
  );
}
