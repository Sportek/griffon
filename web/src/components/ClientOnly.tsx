"use client";

import { useEffect, useSyncExternalStore } from "react";

const noSubscription = () => () => {};

/** False during the server render and hydration, true once mounted in the browser. */
export function useMounted(): boolean {
  return useSyncExternalStore(
    noSubscription,
    () => true,
    () => false,
  );
}

/**
 * Vibe's dropdowns render their popup layer differently on the server and in the
 * browser, which breaks hydration. They are rendered once mounted, behind a fallback
 * of the same size.
 */
export function ClientOnly({ children, fallback }: { children: React.ReactNode; fallback: React.ReactNode }) {
  return useMounted() ? children : fallback;
}

/**
 * Sets Vibe's theme class from the system preference once hydrated. The colours never
 * wait for it (the stylesheet carries them in a media query); the class only reaches
 * the few component rules written against it, such as tooltip arrows.
 */
export function ThemeClass() {
  useEffect(() => {
    const root = document.documentElement;
    const scheme = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      root.classList.toggle("dark-app-theme", scheme.matches);
      root.classList.toggle("light-app-theme", !scheme.matches);
    };
    apply();
    scheme.addEventListener("change", apply);
    return () => scheme.removeEventListener("change", apply);
  }, []);
  return null;
}
