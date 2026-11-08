"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { IconButton } from "@vibe/core";
import { CloseSmall, NavigationChevronLeft, NavigationChevronRight } from "@vibe/icons";

import { thumbnail } from "@/lib/photos";
import styles from "./PhotoViewer.module.css";

/** How much a click on a photo enlarges it, from its fitted size. */
const ZOOM = 2.5;

/**
 * The photos of a listing on the whole screen: one at a time, fitted to the screen, with the
 * strip of all of them below. Swipe or arrows to move, a click on a photo to zoom where it
 * was clicked (then drag or scroll around), Escape to close.
 */
export function PhotoViewer({
  photos,
  start,
  onClose,
}: {
  photos: string[];
  start: number;
  /** Called with the photo shown last, so the gallery can show the same one. */
  onClose: (index: number) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const strip = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(start);
  const [zoom, setZoom] = useState<{ index: number; x: number; y: number } | null>(null);
  const zoomed = zoom?.index === index;

  useLayoutEffect(() => {
    dialog.current?.showModal();
    const el = track.current;
    if (el) {
      el.scrollLeft = start * el.clientWidth;
      // showModal() focuses the first button (Close); the photos are what the keys act on.
      el.focus({ preventScroll: true });
    }
    // The page under the viewer does not scroll with the wheel meant for a zoomed photo.
    const root = document.documentElement;
    const overflow = root.style.overflow;
    root.style.overflow = "hidden";
    return () => {
      root.style.overflow = overflow;
    };
  }, [start]);

  // The strip follows the photo shown.
  useEffect(() => {
    strip.current
      ?.querySelector<HTMLElement>(`[data-index="${index}"]`)
      ?.scrollIntoView({ inline: "nearest", block: "nearest", behavior: "smooth" });
  }, [index]);

  // Centres the zoomed photo on the point that was clicked.
  useLayoutEffect(() => {
    if (!zoom) return;
    const slide = track.current?.querySelector<HTMLElement>(`[data-slide="${zoom.index}"]`);
    const img = slide?.querySelector("img");
    if (!slide || !img) return;
    const w = slide.scrollWidth;
    const h = slide.scrollHeight;
    const scale = Math.min(w / img.naturalWidth, h / img.naturalHeight) || 1;
    const shownW = img.naturalWidth * scale;
    const shownH = img.naturalHeight * scale;
    slide.scrollLeft = (w - shownW) / 2 + zoom.x * shownW - slide.clientWidth / 2;
    slide.scrollTop = (h - shownH) / 2 + zoom.y * shownH - slide.clientHeight / 2;
  }, [zoom]);

  // Dragging a zoomed photo moves around it; a drag is not a click (no zoom out).
  const drag = useRef<{ x: number; y: number; left: number; top: number; moved: boolean } | null>(null);

  function onPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (!zoomed || event.pointerType !== "mouse") return;
    const slide = event.currentTarget;
    drag.current = { x: event.clientX, y: event.clientY, left: slide.scrollLeft, top: slide.scrollTop, moved: false };
    slide.setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const d = drag.current;
    if (!d) return;
    const dx = event.clientX - d.x;
    const dy = event.clientY - d.y;
    if (Math.abs(dx) + Math.abs(dy) > 4) d.moved = true;
    event.currentTarget.scrollLeft = d.left - dx;
    event.currentTarget.scrollTop = d.top - dy;
  }

  function go(next: number) {
    const el = track.current;
    if (!el) return;
    const target = Math.max(0, Math.min(photos.length - 1, next));
    setZoom(null);
    el.scrollTo({ left: target * el.clientWidth, behavior: "smooth" });
  }

  function onKeyDown(event: React.KeyboardEvent) {
    const moves: Record<string, number> = {
      ArrowLeft: index - 1,
      ArrowRight: index + 1,
      Home: 0,
      End: photos.length - 1,
    };
    if (event.key in moves) {
      event.preventDefault();
      go(moves[event.key]);
    }
  }

  function toggleZoom(event: React.MouseEvent<HTMLDivElement>, i: number) {
    const dragged = drag.current?.moved;
    drag.current = null;
    if (dragged) return;
    if (zoomed) {
      setZoom(null);
      return;
    }
    const img = event.currentTarget.querySelector("img");
    if (!img) return;
    const box = img.getBoundingClientRect();
    // The photo is fitted (object-fit: contain): the click as a share of the picture itself.
    const scale = Math.min(box.width / img.naturalWidth, box.height / img.naturalHeight) || 1;
    const shownW = img.naturalWidth * scale;
    const shownH = img.naturalHeight * scale;
    const x = (event.clientX - box.left - (box.width - shownW) / 2) / shownW;
    const y = (event.clientY - box.top - (box.height - shownH) / 2) / shownH;
    setZoom({ index: i, x: Math.min(1, Math.max(0, x)), y: Math.min(1, Math.max(0, y)) });
  }

  return (
    <dialog
      ref={dialog}
      className={styles.viewer}
      aria-label={`Photos, ${index + 1} sur ${photos.length}`}
      onKeyDown={onKeyDown}
      onClose={() => onClose(index)}
    >
      <div className={styles.top}>
        <span className={styles.counter} aria-live="polite">
          {index + 1} / {photos.length}
        </span>
        <span className={styles.hint}>{zoomed ? "Cliquez pour revenir" : "Cliquez sur la photo pour zoomer"}</span>
        <div className={styles.button}>
          <IconButton
            icon={CloseSmall}
            kind="secondary"
            size="small"
            aria-label="Fermer les photos"
            onClick={() => dialog.current?.close()}
          />
        </div>
      </div>

      <div className={styles.stage}>
        <div
          ref={track}
          className={styles.track}
          tabIndex={-1}
          data-zoomed={zoomed || undefined}
          onScroll={(e) => {
            const next = Math.round(e.currentTarget.scrollLeft / e.currentTarget.clientWidth);
            if (next !== index) {
              setIndex(next);
              setZoom(null);
            }
          }}
        >
          {photos.map((src, i) => (
            <div
              key={src}
              className={styles.slide}
              data-slide={i}
              data-zoomed={zoom?.index === i || undefined}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onClick={(e) => toggleZoom(e, i)}
              onPointerUp={() => {
                if (drag.current && !drag.current.moved) drag.current = null;
              }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- photos come from the source sites' CDNs */}
              <img
                src={src}
                alt={`Photo ${i + 1} sur ${photos.length}`}
                loading={Math.abs(i - start) <= 1 ? "eager" : "lazy"}
                referrerPolicy="no-referrer"
                draggable={false}
                className={styles.photo}
                style={zoom?.index === i ? { width: `${ZOOM * 100}%`, height: `${ZOOM * 100}%` } : undefined}
              />
            </div>
          ))}
        </div>

        {photos.length > 1 && (
          <>
            <div className={`${styles.button} ${styles.prev}`}>
              <IconButton
                icon={NavigationChevronLeft}
                kind="secondary"
                aria-label="Photo précédente"
                disabled={index === 0}
                onClick={() => go(index - 1)}
              />
            </div>
            <div className={`${styles.button} ${styles.next}`}>
              <IconButton
                icon={NavigationChevronRight}
                kind="secondary"
                aria-label="Photo suivante"
                disabled={index === photos.length - 1}
                onClick={() => go(index + 1)}
              />
            </div>
          </>
        )}
      </div>

      {photos.length > 1 && (
        <div ref={strip} className={styles.strip} aria-label="Toutes les photos">
          {photos.map((src, i) => (
            <button
              key={src}
              type="button"
              data-index={i}
              className={styles.thumb}
              aria-current={i === index || undefined}
              aria-label={`Photo ${i + 1}`}
              onClick={() => go(i)}
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- photos come from the source sites' CDNs */}
              <img src={thumbnail(src)} alt="" loading="lazy" referrerPolicy="no-referrer" />
            </button>
          ))}
        </div>
      )}
    </dialog>
  );
}
