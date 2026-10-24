"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import {
  Checkbox,
  Modal,
  ModalBasicLayout,
  ModalContent,
  ModalFooter,
  ModalHeader,
  TextField,
} from "@vibe/core";

import { createAlert } from "@/app/actions";
import { formatPrice } from "@/lib/format";
import type { SearchState } from "@/lib/search-params";
import { useToast } from "../ToastProvider";
import styles from "./SaveAlertModal.module.css";

/** "4 ½ et + · 1 750 $ max · Rosemont" from the criteria, as a default name. */
function defaultName(state: SearchState): string {
  const parts = [
    state.tailleMin ? `${state.tailleMin} ½ et +` : null,
    state.prixMax ? `${formatPrice(state.prixMax)} max` : null,
    state.quartiers?.length ? state.quartiers.slice(0, 2).join(", ") + (state.quartiers.length > 2 ? "…" : "") : null,
    state.metro ? `métro ≤ ${state.metro} min` : null,
    state.animaux ? "animaux" : null,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "Toutes les annonces";
}

const DISCORD_WEBHOOK = /^https:\/\/(discord\.com|discordapp\.com)\/api\/webhooks\//;

export function SaveAlertModal({ open, state, onClose }: { open: boolean; state: SearchState; onClose: () => void }) {
  const [name, setName] = useState(defaultName(state));
  const [webhook, setWebhook] = useState("");
  const [priceDrops, setPriceDrops] = useState(true);
  const [pending, startTransition] = useTransition();
  const toast = useToast();

  const webhookInvalid = webhook !== "" && !DISCORD_WEBHOOK.test(webhook);

  function save() {
    if (!name.trim() || webhookInvalid) return;
    startTransition(async () => {
      const result = await createAlert(state, { name: name.trim(), webhookUrl: webhook || null, notifyOnPriceDrop: priceDrops });
      if (result.ok) {
        toast.show(`Alerte « ${result.value.name} » créée`, "positive");
        onClose();
      } else {
        toast.show(result.error, "negative");
      }
    });
  }

  return (
    <Modal id="save-alert" show={open} onClose={onClose} size="small" closeButtonAriaLabel="Fermer">
      <ModalBasicLayout>
        <ModalHeader title="M'alerter des nouvelles annonces" />
        <ModalContent>
          <div className={styles.form}>
            <p className={styles.text}>
              Griffon vérifie cette recherche à chaque nouvelle collecte et garde les annonces trouvées dans{" "}
              <Link href="/alertes">Alertes</Link>.
            </p>
            <TextField
              title="Nom de l'alerte"
              value={name}
              onChange={setName}
              size="medium"
              validation={name.trim() ? undefined : { status: "error", text: "Donnez un nom à l'alerte" }}
            />
            <TextField
              title="Webhook Discord (facultatif)"
              placeholder="https://discord.com/api/webhooks/…"
              value={webhook}
              onChange={(v) => setWebhook(v.trim())}
              size="medium"
              type="url"
              validation={
                webhookInvalid
                  ? { status: "error", text: "Collez l'URL d'un webhook Discord (Paramètres du salon › Intégrations)" }
                  : { text: "Pour recevoir chaque annonce sur Discord dès qu'elle est trouvée." }
              }
            />
            <Checkbox
              label="M'alerter aussi des baisses de prix"
              checked={priceDrops}
              onChange={(e) => setPriceDrops(e.target.checked)}
            />
          </div>
        </ModalContent>
      </ModalBasicLayout>
      <ModalFooter
        primaryButton={{
          text: "Créer l'alerte",
          onClick: save,
          loading: pending,
          disabled: !name.trim() || webhookInvalid,
        }}
        secondaryButton={{ text: "Annuler", onClick: onClose }}
      />
    </Modal>
  );
}
