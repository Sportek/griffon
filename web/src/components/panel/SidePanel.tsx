"use client";

import { useCallback, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { Icon, IconButton } from "@vibe/core";
import { CloseSmall, ExternalPage } from "@vibe/icons";

import { setPanelListing } from "@/lib/panel";
import styles from "./SidePanel.module.css";

/**
 * True while a modal (the photo viewer, a Vibe modal) is open: Escape is theirs then. Not
 * [role=dialog] alone: Vibe keeps a hidden one in the page for each dropdown's menu.
 */
function modalOpen(): boolean {
  return !!document.querySelector("dialog[open], [aria-modal='true']");
}

/**
 * The listing beside the search: opened by a listing link (an intercepted route), it sits
 * over the right of the page, which stays mounted under it: the list keeps its scroll and
 * the map its view. Closing goes back in history, to the page as it was.
 */
export function SidePanel({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const panel = useRef<HTMLElement>(null);
  const body = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setPanelListing(id);
    body.current?.scrollTo({ top: 0 });
  }, [id]);
  useEffect(() => {
    panel.current?.focus({ preventScroll: true });
    return () => setPanelListing(null);
  }, []);

  const close = useCallback(() => router.back(), [router]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented || modalOpen()) return;
      close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [close]);

  return (
    <aside ref={panel} className={styles.panel} aria-label="Annonce" tabIndex={-1}>
      <div className={styles.bar}>
        {/* A plain link: the full page loads as itself, not in the panel again. */}
        <a href={`/annonces/${id}`} className={styles.full}>
          <Icon icon={ExternalPage} size={16} />
          Page complète
        </a>
        <IconButton icon={CloseSmall} kind="tertiary" size="small" aria-label="Fermer l'annonce" onClick={close} />
      </div>
      <div ref={body} className={styles.body}>
        {children}
      </div>
    </aside>
  );
}

export function PanelMessage({ children }: { children: React.ReactNode }) {
  return <p className={styles.message}>{children}</p>;
}

/** While the listing loads: the shape of the gallery and the headline. */
export function PanelSkeleton() {
  return (
    <div className={styles.skeleton} aria-busy="true" aria-label="Chargement de l'annonce">
      <div className={styles.skeletonPhoto} />
      <div className={styles.skeletonLine} style={{ width: "40%", height: 28 }} />
      <div className={styles.skeletonLine} style={{ width: "65%" }} />
      <div className={styles.skeletonLine} style={{ width: "80%" }} />
      <div className={styles.skeletonBlock} />
    </div>
  );
}
