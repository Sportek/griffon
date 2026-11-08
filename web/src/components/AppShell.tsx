"use client";

import Link from "next/link";
import { useState } from "react";
import { usePathname } from "next/navigation";
import { Icon } from "@vibe/core";
import { Notifications, Search, Status } from "@vibe/icons";

import { usePanelListing } from "@/lib/panel";
import styles from "./AppShell.module.css";
import { ThemeClass } from "./ClientOnly";
import { ToastProvider } from "./ToastProvider";

const NAV = [
  { href: "/", label: "Recherche", icon: Search, match: (p: string) => p === "/" || p.startsWith("/annonces") },
  { href: "/suivi", label: "Suivi", icon: Status, match: (p: string) => p.startsWith("/suivi") },
  { href: "/alertes", label: "Alertes", icon: Notifications, match: (p: string) => p.startsWith("/alertes") },
];

export function AppShell({ children, panel }: { children: React.ReactNode; panel?: React.ReactNode }) {
  const pathname = usePathname();
  // With a listing in the side panel the URL is the listing's, but the page under it is
  // still the one the owner was on: the nav keeps showing that one.
  const panelOpen = usePanelListing() != null;
  const [pagePath, setPagePath] = useState(pathname);
  if (!pathname.startsWith("/annonces/") && pagePath !== pathname) setPagePath(pathname);
  const navPath = panelOpen ? pagePath : pathname;
  return (
    <div className={styles.shell}>
      <ThemeClass />
      <header className={styles.header}>
        <Link href="/" className={styles.brand} aria-label="Griffon, accueil">
          <span className={styles.mark} aria-hidden>
            G
          </span>
          <span className={styles.name}>Griffon</span>
        </Link>
        <nav className={styles.nav} aria-label="Navigation principale">
          {NAV.map((item) => {
            const active = item.match(navPath);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={styles.link}
                data-active={active || undefined}
                aria-current={active ? "page" : undefined}
              >
                <Icon icon={item.icon} size={18} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </header>
      <ToastProvider>
        <main className={styles.main}>{children}</main>
        {panel}
      </ToastProvider>
    </div>
  );
}
