"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { usePanelListing } from "@/lib/panel";

/**
 * A link to a listing. From the search (or the follow-up board) it opens in the side panel,
 * over the page that stays as it is; with the panel open it replaces the listing shown, so
 * closing the panel goes straight back to the search. From a full listing page it loads the
 * other listing as a full page too.
 */
export function ListingLink({
  id,
  className,
  children,
}: {
  id: string;
  className?: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const panelOpen = usePanelListing() != null;
  const href = `/annonces/${id}`;
  if (!panelOpen && pathname.startsWith("/annonces/")) {
    return (
      <a href={href} className={className}>
        {children}
      </a>
    );
  }
  return (
    <Link href={href} className={className} replace={panelOpen} scroll={false}>
      {children}
    </Link>
  );
}
