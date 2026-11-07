"use client";

import { useState } from "react";
import { Button } from "@vibe/core";
import { NavigationChevronDown, NavigationChevronUp } from "@vibe/icons";

import type { ListingGroup, ListingSummary } from "@/lib/types";
import { formatBedrooms, formatPrice, formatSize, isForSale, isNew, periodSuffix, priceDrop, sourceName } from "@/lib/format";
import { thumbnail } from "@/lib/photos";
import { UnitList } from "./UnitList";
import styles from "./BuildingCard.module.css";

/** Rows shown before "Voir les N autres": enough to compare, short enough to scan past. */
const PREVIEW_ROWS = 4;

/** "3 ½ ×2 · 4 ½ ×5" (or "2 ch. ×3" for sale): what the building offers, by size. */
function sizeMix(listings: ListingSummary[]): string {
  const counts = new Map<string, number>();
  for (const l of listings) {
    const label = (isForSale(l) ? formatBedrooms(l.bedrooms) : formatSize(l)?.replace("≈ ", "")) ?? "?";
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort(([a], [b]) => a.localeCompare(b, "fr", { numeric: true }))
    .map(([label, n]) => (n > 1 ? `${label} ×${n}` : label))
    .join(" · ");
}

function priceRange(group: ListingGroup): string {
  if (group.minPrice == null) return "Prix non précisés";
  // A search is of one kind (rent or sale), so a group's members share their price period.
  const suffix = periodSuffix(group.listings[0]?.pricePeriod);
  if (group.maxPrice == null || group.maxPrice === group.minPrice) return `${formatPrice(group.minPrice)}${suffix}`;
  return `${formatPrice(group.minPrice)} – ${formatPrice(group.maxPrice)}${suffix}`;
}

export function BuildingCard({
  group,
  highlighted,
  priority,
  seenBefore,
  onHover,
  onFavoriteChange,
}: {
  group: ListingGroup;
  highlighted?: boolean;
  /** At the top of the first screen: the photo loads first instead of lazily. */
  priority?: boolean;
  seenBefore?: string | null;
  onHover?: (key: string | null) => void;
  onFavoriteChange?: (id: string, favorite: boolean) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const first = group.listings[0];
  const photo = group.listings.find((l) => l.photos.length)?.photos[0];
  const place = [first.neighborhood, first.city].filter(Boolean).join(", ");
  const freshCount = group.listings.filter((l) => l.active && isNew(l.firstSeenAt)).length;
  const dropCount = group.listings.filter((l) => l.active && priceDrop(l) != null).length;
  const sources = [...new Set(group.listings.map((l) => sourceName(l.source)))].join(", ");
  const rows = expanded ? group.listings : group.listings.slice(0, PREVIEW_ROWS);
  const hidden = group.listings.length - rows.length;
  const filtered = group.count < group.totalInBuilding;

  return (
    <article
      className={styles.card}
      data-highlighted={highlighted || undefined}
      onMouseEnter={() => onHover?.(group.key)}
      onMouseLeave={() => onHover?.(null)}
      aria-label={`${group.count} logements au ${group.address ?? "même immeuble"}`}
    >
      <header className={styles.header}>
        <div className={styles.photo}>
          {photo ? (
            // eslint-disable-next-line @next/next/no-img-element -- photos come from the source sites' CDNs
            <img
              src={thumbnail(photo)}
              alt=""
              loading={priority ? "eager" : "lazy"}
              fetchPriority={priority ? "high" : undefined}
              referrerPolicy="no-referrer"
            />
          ) : (
            <span className={styles.noPhoto}>Pas de photo</span>
          )}
          <span className={styles.badge}>{group.count} logements</span>
        </div>
        <div className={styles.summary}>
          <span className={styles.range}>{priceRange(group)}</span>
          <h2 className={styles.address}>{group.address ?? "Même immeuble"}</h2>
          {place && <p className={styles.place}>{place}</p>}
          <p className={styles.mix}>{sizeMix(group.listings)}</p>
          <p className={styles.meta}>
            {filtered
              ? `${group.count} sur ${group.totalInBuilding} logements de l'immeuble correspondent`
              : `${group.totalInBuilding} logements ${isForSale(first) ? "à vendre" : "à louer"} dans l'immeuble`}
            {" · "}
            {sources}
          </p>
          {(freshCount > 0 || dropCount > 0) && (
            <p className={styles.signals}>
              {freshCount > 0 && (
                <span className={styles.signal} data-kind="new">
                  {freshCount} nouveau{freshCount > 1 ? "x" : ""}
                </span>
              )}
              {dropCount > 0 && (
                <span className={styles.signal} data-kind="drop">
                  {dropCount} baisse{dropCount > 1 ? "s" : ""} de prix
                </span>
              )}
            </p>
          )}
        </div>
      </header>

      <div className={styles.units}>
        <UnitList listings={rows} seenBefore={seenBefore} onFavoriteChange={onFavoriteChange} />
      </div>

      {group.listings.length > PREVIEW_ROWS && (
        <div className={styles.more}>
          <Button
            kind="tertiary"
            size="small"
            rightIcon={expanded ? NavigationChevronUp : NavigationChevronDown}
            onClick={() => setExpanded((e) => !e)}
            aria-expanded={expanded}
          >
            {expanded ? "Voir moins" : `Voir les ${hidden} autres`}
          </Button>
        </div>
      )}
    </article>
  );
}
