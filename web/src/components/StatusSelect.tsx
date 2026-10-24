"use client";

import { useEffect, useId, useRef, useState } from "react";

import { STATUSES, statusMeta } from "@/lib/format";
import type { TrackingStatus } from "@/lib/types";
import styles from "./StatusSelect.module.css";

/**
 * monday's status cell: the whole cell is the colour, and clicking it opens the column's
 * labels to pick from. Used wherever a listing's step in the search can change.
 */
export function StatusSelect({
  value,
  onChange,
  size = "medium",
}: {
  value: TrackingStatus | null;
  onChange: (status: TrackingStatus | null) => void;
  size?: "small" | "medium";
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !root.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  function pick(status: TrackingStatus | null) {
    setOpen(false);
    if (status !== value) onChange(status);
  }

  const meta = value ? statusMeta(value) : null;

  return (
    <div className={styles.root} ref={root} data-size={size}>
      <button
        type="button"
        className={styles.cell}
        data-status={value ?? undefined}
        style={meta ? { background: meta.color } : undefined}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((o) => !o)}
      >
        {meta ? meta.label : "Choisir un statut"}
      </button>
      {open && (
        <div className={styles.menu} id={menuId} role="menu" aria-label="Statut de la démarche">
          {STATUSES.map((s) => (
            <button
              key={s.value}
              type="button"
              role="menuitemradio"
              aria-checked={s.value === value}
              className={styles.option}
              data-status={s.value}
              style={{ background: s.color }}
              onClick={() => pick(s.value)}
            >
              {s.label}
            </button>
          ))}
          {value && (
            <button type="button" role="menuitem" className={styles.clear} onClick={() => pick(null)}>
              Retirer le statut
            </button>
          )}
        </div>
      )}
    </div>
  );
}
