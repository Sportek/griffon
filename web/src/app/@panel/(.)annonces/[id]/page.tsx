import { ApiError } from "@/lib/api";
import { loadListing } from "@/lib/listing";
import type { ListingDetail } from "@/lib/types";
import { ListingDetailView } from "@/components/listing/ListingDetailView";
import { PanelMessage } from "@/components/panel/SidePanel";

export const dynamic = "force-dynamic";

export default async function PanelListing({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let listing: ListingDetail | null;
  try {
    listing = await loadListing(id);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "Une erreur inattendue est survenue.";
    return <PanelMessage>{message}</PanelMessage>;
  }
  if (!listing) return <PanelMessage>Cette annonce n&apos;existe pas ou n&apos;existe plus.</PanelMessage>;
  return <ListingDetailView listing={listing} />;
}
