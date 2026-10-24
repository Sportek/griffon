"use client";

import { useRef, useState } from "react";
import { IconButton } from "@vibe/core";
import { NavigationChevronLeft, NavigationChevronRight } from "@vibe/icons";

import styles from "./Gallery.module.css";

export function Gallery({ photos, inactive }: { photos: string[]; inactive: boolean }) {
  const track = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);

  if (!photos.length) {
    return <div className={styles.empty}>La source ne fournit pas de photo.</div>;
  }

  function go(delta: number) {
    const el = track.current;
    if (!el) return;
    const next = Math.max(0, Math.min(photos.length - 1, index + delta));
    el.scrollTo({ left: next * el.clientWidth, behavior: "smooth" });
  }

  return (
    <div className={styles.gallery} data-inactive={inactive || undefined}>
      <div
        ref={track}
        className={styles.track}
        onScroll={(e) => setIndex(Math.round(e.currentTarget.scrollLeft / e.currentTarget.clientWidth))}
        tabIndex={0}
        aria-label={`Photos, ${photos.length} au total`}
      >
        {photos.map((src, i) => (
          // eslint-disable-next-line @next/next/no-img-element -- photos come from the source sites' CDNs
          <img
            key={src}
            src={src}
            alt={`Photo ${i + 1} sur ${photos.length}`}
            loading={i < 2 ? "eager" : "lazy"}
            referrerPolicy="no-referrer"
            className={styles.photo}
          />
        ))}
      </div>
      {photos.length > 1 && (
        <>
          <div className={styles.prev}>
            <IconButton
              icon={NavigationChevronLeft}
              kind="secondary"
              size="small"
              aria-label="Photo précédente"
              disabled={index === 0}
              onClick={() => go(-1)}
            />
          </div>
          <div className={styles.next}>
            <IconButton
              icon={NavigationChevronRight}
              kind="secondary"
              size="small"
              aria-label="Photo suivante"
              disabled={index === photos.length - 1}
              onClick={() => go(1)}
            />
          </div>
          <span className={styles.counter} aria-live="polite">
            {index + 1} / {photos.length}
          </span>
        </>
      )}
    </div>
  );
}
