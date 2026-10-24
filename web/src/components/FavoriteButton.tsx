"use client";

import { useState, useTransition } from "react";
import { IconButton } from "@vibe/core";
import { Heart } from "@vibe/icons";

import { saveTracking } from "@/app/actions";
import { useToast } from "./ToastProvider";
import styles from "./FavoriteButton.module.css";

export function FavoriteButton({
  listingId,
  favorite,
  onChange,
  size = "small",
}: {
  listingId: string;
  favorite: boolean;
  onChange?: (favorite: boolean) => void;
  size?: "xs" | "small" | "medium";
}) {
  const [value, setValue] = useState(favorite);
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  function toggle(event: React.MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    const next = !value;
    setValue(next);
    onChange?.(next);
    startTransition(async () => {
      const result = await saveTracking(listingId, { favorite: next });
      if (!result.ok) {
        setValue(!next);
        onChange?.(!next);
        toast.show(result.error, "negative");
      }
    });
  }

  return (
    <span className={styles.wrapper} data-active={value || undefined}>
      <IconButton
        icon={Heart}
        size={size}
        kind="tertiary"
        active={value}
        disabled={pending}
        onClick={toggle}
        aria-label={value ? "Retirer des favoris" : "Ajouter aux favoris"}
        aria-pressed={value}
        tooltipContent={value ? "Retirer des favoris" : "Ajouter aux favoris"}
      />
    </span>
  );
}
