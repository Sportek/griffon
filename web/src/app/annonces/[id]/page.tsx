import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ApiError } from "@/lib/api";
import { formatRent, formatSize, isForSale, saleFacts } from "@/lib/format";
import { loadListing } from "@/lib/listing";
import type { ListingDetail } from "@/lib/types";
import { ListingDetailView } from "@/components/listing/ListingDetailView";
import styles from "./page.module.css";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string }> };

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const listing = await loadListing((await params).id).catch(() => null);
  if (!listing) return { title: "Annonce" };
  const size = isForSale(listing) ? saleFacts(listing)[0] : formatSize(listing);
  return { title: [size, formatRent(listing), listing.neighborhood ?? listing.city].filter(Boolean).join(" · ") };
}

export default async function ListingPage({ params }: Params) {
  const { id } = await params;
  let listing: ListingDetail | null;
  try {
    listing = await loadListing(id);
  } catch (error) {
    return (
      <div className={styles.page}>
        <p className={styles.error}>
          {error instanceof ApiError ? error.message : "Une erreur inattendue est survenue."}
        </p>
      </div>
    );
  }
  if (!listing) notFound();

  const place = [listing.neighborhood, listing.city].filter(Boolean).join(", ");
  return (
    <div className={styles.page}>
      <nav className={styles.crumbs} aria-label="Fil d'Ariane">
        <Link href="/">Recherche</Link>
        <span aria-hidden>›</span>
        <span>{place || "Annonce"}</span>
      </nav>
      <ListingDetailView listing={listing} />
    </div>
  );
}
