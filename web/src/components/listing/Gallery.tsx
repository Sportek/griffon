"use client";

import { useRef, useState } from "react";
import { IconButton } from "@vibe/core";
import { Fullscreen, NavigationChevronLeft, NavigationChevronRight } from "@vibe/icons";

import { PhotoViewer } from "./PhotoViewer";
import styles from "./Gallery.module.css";

export function Gallery({ photos, inactive }: { photos: string[]; inactive: boolean }) {
  const track = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);
  const [viewing, setViewing] = useState<number | null>(null);

  if (!photos.length) {
    return <div className={styles.empty}>La source ne fournit pas de photo.</div>;
  }

  function show(target: number, behavior: ScrollBehavior = "smooth") {
    const el = track.current;
    if (!el) return;
    const next = Math.max(0, Math.min(photos.length - 1, target));
    el.scrollTo({ left: next * el.clientWidth, behavior });
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
          <button
            key={src}
            type="button"
            className={styles.slide}
            aria-label={`Agrandir la photo ${i + 1} sur ${photos.length}`}
            onClick={() => setViewing(i)}
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- photos come from the source sites' CDNs */}
            <img
              src={src}
              alt=""
              loading={i < 2 ? "eager" : "lazy"}
              referrerPolicy="no-referrer"
              className={styles.photo}
            />
          </button>
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
              onClick={() => show(index - 1)}
            />
          </div>
          <div className={styles.next}>
            <IconButton
              icon={NavigationChevronRight}
              kind="secondary"
              size="small"
              aria-label="Photo suivante"
              disabled={index === photos.length - 1}
              onClick={() => show(index + 1)}
            />
          </div>
        </>
      )}
      <div className={styles.expand}>
        <IconButton
          icon={Fullscreen}
          kind="secondary"
          size="small"
          aria-label="Voir les photos en grand"
          onClick={() => setViewing(index)}
        />
      </div>
      {photos.length > 1 && (
        <span className={styles.counter} aria-live="polite">
          {index + 1} / {photos.length}
        </span>
      )}
      {viewing != null && (
        <PhotoViewer
          photos={photos}
          start={viewing}
          onClose={(last) => {
            setViewing(null);
            show(last, "instant");
          }}
        />
      )}
    </div>
  );
}
