import type { TrackingStatus } from "@/lib/types";
import { statusMeta } from "@/lib/format";

import styles from "./StatusPill.module.css";

/** monday's status cell: a full-colour block with the label centred in it. */
export function StatusPill({ status, size = "medium" }: { status: TrackingStatus | null; size?: "small" | "medium" }) {
  if (!status) {
    return (
      <span className={styles.pill} data-size={size} data-empty>
        Sans statut
      </span>
    );
  }
  const meta = statusMeta(status);
  return (
    <span className={styles.pill} data-size={size} data-status={status} style={{ background: meta.color }}>
      {meta.label}
    </span>
  );
}
