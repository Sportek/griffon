import type { ListingSummary } from "@/lib/types";
import { UnitList } from "../UnitList";
import styles from "./SameBuilding.module.css";

export function SameBuilding({ listings }: { listings: ListingSummary[] }) {
  return (
    <div className={styles.box}>
      <UnitList listings={listings} />
    </div>
  );
}
