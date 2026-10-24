import type { ListingSummary } from "@/lib/types";
import { formatPrice, isNew, priceDrop } from "@/lib/format";

import styles from "./Signals.module.css";

/** Freshness and price movement, in the status column's colour language. */
export function Signals({ listing, seenBefore }: { listing: ListingSummary; seenBefore?: string | null }) {
  const drop = priceDrop(listing);
  const fresh = listing.active && isNew(listing.firstSeenAt);
  const unseen = seenBefore != null && listing.firstSeenAt > seenBefore;
  return (
    <span className={styles.signals}>
      {!listing.active && <span className={styles.signal} data-kind="gone">Retirée</span>}
      {listing.active && (fresh || unseen) && <span className={styles.signal} data-kind="new">Nouveau</span>}
      {listing.active && drop != null && (
        <span className={styles.signal} data-kind="drop">
          −{formatPrice(drop)}
        </span>
      )}
    </span>
  );
}
