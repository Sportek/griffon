"use client";

import { Button } from "@vibe/core";
import { ExternalPage, Share } from "@vibe/icons";

import { useToast } from "../ToastProvider";
import styles from "./ListingActions.module.css";

export function ListingActions({
  url,
  source,
  active,
  title,
}: {
  url: string;
  source: string;
  active: boolean;
  title: string | null;
}) {
  const toast = useToast();

  async function share() {
    const link = window.location.href;
    try {
      if (navigator.share) {
        await navigator.share({ title: title ?? "Annonce Griffon", url: link });
        return;
      }
      await navigator.clipboard.writeText(link);
      toast.show("Lien copié", "positive");
    } catch {
      // The share sheet was dismissed.
    }
  }

  return (
    <div className={styles.actions}>
      <Button
        rightIcon={ExternalPage}
        kind={active ? "primary" : "secondary"}
        onClick={() => window.open(url, "_blank", "noopener,noreferrer")}
      >
        {active ? `Voir l'annonce sur ${source}` : `Ouvrir sur ${source}`}
      </Button>
      <Button kind="secondary" leftIcon={Share} onClick={share}>
        Partager
      </Button>
    </div>
  );
}
