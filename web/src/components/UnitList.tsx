"use client";

import Link from "next/link";

import type { ListingSummary } from "@/lib/types";
import { formatArea, formatBedrooms, formatPrice, formatRent, formatSize, isForSale, sourceName } from "@/lib/format";
import { FavoriteButton } from "./FavoriteButton";
import { Signals } from "./Signals";
import { StatusPill } from "./StatusPill";
import styles from "./UnitList.module.css";

/** The size label of a row: the Québec "X ½" for a rent, bedrooms for a property for sale. */
function sizeLabel(listing: ListingSummary): string {
  if (isForSale(listing)) return formatBedrooms(listing.bedrooms) ?? "Chambres non précisées";
  return formatSize(listing) ?? formatBedrooms(listing.bedrooms) ?? "Taille non précisée";
}

function details(listing: ListingSummary): (string | null)[] {
  const unit = listing.unit ? `app. ${listing.unit}` : null;
  if (isForSale(listing)) {
    const fees = listing.condoFeesMonthly != null ? `copropriété ${formatPrice(listing.condoFeesMonthly)}/mois` : null;
    return [unit, formatArea(listing.areaSqft), fees];
  }
  return [unit, formatBedrooms(listing.bedrooms), formatArea(listing.areaSqft)];
}

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
            <span className={styles.size}>{sizeLabel(listing)}</span>
            <span className={styles.details}>
              {details(listing).filter(Boolean).join(" · ") || sourceName(listing.source)}
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
