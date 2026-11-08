"use client";

import { useSyncExternalStore } from "react";

/**
 * The listing shown in the side panel, if any. The panel sets it while it is open: the
 * search highlights that card and its pin, and listing links swap the panel's listing
 * instead of stacking one history entry per listing looked at.
 */
let openId: string | null = null;
const listeners = new Set<() => void>();

export function setPanelListing(id: string | null): void {
  if (id === openId) return;
  openId = id;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function usePanelListing(): string | null {
  return useSyncExternalStore(subscribe, () => openId, () => null);
}
