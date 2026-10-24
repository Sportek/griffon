"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Button, TextArea, TextField } from "@vibe/core";
import { Hide, Show } from "@vibe/icons";

import { saveTracking } from "@/app/actions";
import type { TrackingInput } from "@/lib/api";
import type { Tracking, TrackingStatus } from "@/lib/types";
import { FavoriteButton } from "../FavoriteButton";
import { StatusSelect } from "../StatusSelect";
import { useToast } from "../ToastProvider";
import styles from "./TrackingPanel.module.css";

/** "2026-10-24T18:30" for a datetime-local input, in the browser's time zone. */
function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function TrackingPanel({ listingId, tracking }: { listingId: string; tracking: Tracking | null }) {
  const router = useRouter();
  const toast = useToast();
  const [pending, startTransition] = useTransition();
  const [status, setStatus] = useState<TrackingStatus | null>(tracking?.status ?? null);
  const [notes, setNotes] = useState(tracking?.notes ?? "");
  const [visit, setVisit] = useState(toLocalInput(tracking?.visitAt ?? null));
  const [hidden, setHidden] = useState(tracking?.hidden ?? false);

  function save(input: TrackingInput, success?: string) {
    startTransition(async () => {
      const result = await saveTracking(listingId, input);
      if (!result.ok) {
        toast.show(result.error, "negative");
        return;
      }
      if (success) toast.show(success, "positive");
      router.refresh();
    });
  }

  return (
    <section className={styles.panel} aria-labelledby="tracking-heading">
      <div className={styles.header}>
        <h2 id="tracking-heading" className={styles.title}>
          Mon suivi
        </h2>
        <FavoriteButton listingId={listingId} favorite={tracking?.favorite ?? false} size="medium" />
      </div>

      <div className={styles.field}>
        <span className={styles.label}>
          Statut
        </span>
        <StatusSelect
          value={status}
          onChange={(next) => {
            setStatus(next);
            save(next ? { status: next } : { clearStatus: true });
          }}
        />
      </div>

      <TextField
        title="Date et heure de la visite"
        type="datetime-local"
        value={visit}
        size="medium"
        onChange={(v) => {
          setVisit(v);
          if (v) save({ visitAt: new Date(v).toISOString(), status: status ?? "VISIT_PLANNED" });
          else save({ clearVisitAt: true });
          if (v && !status) setStatus("VISIT_PLANNED");
        }}
      />

      <TextArea
        label="Notes"
        placeholder="Proprio sympa, bruit de rue, à rappeler lundi…"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        onBlur={() => {
          if (notes !== (tracking?.notes ?? "")) save({ notes }, "Note enregistrée");
        }}
        resize
      />

      <Button
        kind="tertiary"
        size="small"
        leftIcon={hidden ? Show : Hide}
        loading={pending}
        onClick={() => {
          const next = !hidden;
          setHidden(next);
          save(
            { hidden: next },
            next ? "Annonce masquée, avec ses doublons" : "Annonce de nouveau visible dans les résultats",
          );
        }}
      >
        {hidden ? "Ne plus masquer" : "Masquer (pas intéressé)"}
      </Button>
    </section>
  );
}
