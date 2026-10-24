import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { ApiError, getListing } from "@/lib/api";
import {
  ago,
  formatArea,
  formatAvailability,
  formatBedrooms,
  formatDate,
  formatPrice,
  formatRent,
  formatSize,
  NEARBY_NAMES,
  propertyTypeName,
  sourceName,
} from "@/lib/format";
import type { ListingDetail, NearbyStation, PriceBenchmark } from "@/lib/types";
import { Description } from "@/components/listing/Description";
import { Gallery } from "@/components/listing/Gallery";
import { PriceHistory } from "@/components/listing/PriceHistory";
import { TrackingPanel } from "@/components/listing/TrackingPanel";
import { ListingActions } from "@/components/listing/ListingActions";
import { Signals } from "@/components/Signals";
import styles from "./page.module.css";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string }> };

async function load(id: string): Promise<ListingDetail | null> {
  if (!/^[a-f0-9]{24}$/.test(id)) return null;
  return getListing(id);
}

export async function generateMetadata({ params }: Params): Promise<Metadata> {
  const listing = await load((await params).id).catch(() => null);
  if (!listing) return { title: "Annonce" };
  const size = formatSize(listing);
  return { title: [size, formatRent(listing), listing.neighborhood ?? listing.city].filter(Boolean).join(" · ") };
}

function yesNo(value: boolean | null, yes: string, no: string) {
  return value == null ? null : value ? yes : no;
}

const LINE_NAMES: Record<string, string> = { green: "verte", orange: "orange", yellow: "jaune", blue: "bleue" };

function stationLine(station: NearbyStation) {
  if (station.network === "rem") return "REM";
  const lines = station.lines.map((l) => LINE_NAMES[l] ?? l);
  return lines.length ? `ligne ${lines.join(", ")}` : "métro";
}

function benchmarkText(b: PriceBenchmark, sizeLabel: string | null) {
  const where = b.scope === "NEIGHBORHOOD" ? `de ${b.area}` : `à ${b.area}`;
  const what = sizeLabel ? `des ${sizeLabel.replace("≈ ", "")}` : "des logements comparables";
  const delta = Math.abs(b.deltaPercent);
  if (delta < 2) return `Dans la médiane ${what} ${where}`;
  return `${delta.toLocaleString("fr-CA", { maximumFractionDigits: 0 })} % ${b.deltaPercent < 0 ? "sous" : "au-dessus de"} la médiane ${what} ${where}`;
}

export default async function ListingPage({ params }: Params) {
  const { id } = await params;
  let listing: ListingDetail | null;
  try {
    listing = await load(id);
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

  const size = formatSize(listing);
  const place = [listing.neighborhood, listing.city].filter(Boolean).join(", ");
  const proximity = listing.proximity;
  const stations = [proximity?.nearest_metro, proximity?.nearest_rem].filter((s): s is NearbyStation => !!s);
  const essentials = Object.entries(proximity?.essentials ?? {})
    .filter(([, summary]) => summary.count > 0)
    .sort(([, a], [, b]) => (a.nearest?.walk_minutes ?? 99) - (b.nearest?.walk_minutes ?? 99));

  const facts: [string, string | null][] = [
    ["Taille", size],
    ["Chambres", formatBedrooms(listing.bedrooms)],
    ["Salles de bain", listing.bathrooms != null ? String(listing.bathrooms) : null],
    ["Superficie", formatArea(listing.areaSqft)],
    ["Type", propertyTypeName(listing.propertyType)],
    ["Disponibilité", formatAvailability(listing.availableDate)],
    ["Bail", listing.leaseTerm],
    ["Animaux", yesNo(listing.petsAllowed, "Acceptés", "Refusés")],
    ["Meublé", yesNo(listing.furnished, "Oui", "Non")],
    ["Fumeur", yesNo(listing.smokingAllowed, "Permis", "Non-fumeur")],
    ["Stationnement", listing.parkingSpots != null ? (listing.parkingSpots > 0 ? `${listing.parkingSpots} place${listing.parkingSpots > 1 ? "s" : ""}` : "Aucun") : null],
    ["Construction", listing.yearBuilt != null ? String(listing.yearBuilt) : null],
  ];

  const sources = [
    { id: listing.id, source: listing.source, url: listing.url, price: listing.price, active: listing.active, current: true },
    ...listing.duplicates.map((d) => ({ ...d, current: false })),
  ].sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity));

  return (
    <div className={styles.page}>
      <nav className={styles.crumbs} aria-label="Fil d'Ariane">
        <Link href="/">Recherche</Link>
        <span aria-hidden>›</span>
        <span>{place || "Annonce"}</span>
      </nav>

      <Gallery photos={listing.photos} inactive={!listing.active} />

      <header className={styles.header}>
        <div className={styles.headline}>
          <div className={styles.priceRow}>
            <h1 className={styles.price}>{formatRent(listing)}</h1>
            <Signals listing={{ ...listing, duplicates: [] }} />
          </div>
          <p className={styles.facts}>
            {[size, formatBedrooms(listing.bedrooms), formatArea(listing.areaSqft), propertyTypeName(listing.propertyType)]
              .filter(Boolean)
              .join(" · ")}
          </p>
          <p className={styles.address}>
            {[listing.address, place, listing.postalCode].filter(Boolean).join(", ") || "Adresse non précisée"}
            {listing.locationPrecision && listing.locationPrecision !== "exact" && (
              <span className={styles.approx}> · position approximative</span>
            )}
          </p>
        </div>
        <ListingActions url={listing.url} source={sourceName(listing.source)} active={listing.active} title={listing.title} />
      </header>

      {!listing.active && (
        <p className={styles.removed} role="status">
          Retirée de {sourceName(listing.source)} {ago(listing.inactiveSince ?? listing.lastSeenAt)} : elle n&apos;est
          probablement plus disponible.
        </p>
      )}

      <div className={styles.layout}>
        <div className={styles.main}>
          <section className={styles.section} aria-labelledby="facts-heading">
            <h2 id="facts-heading" className={styles.sectionTitle}>
              L&apos;essentiel
            </h2>
            <dl className={styles.factGrid}>
              {facts.map(([label, value]) => (
                <div key={label} className={styles.fact}>
                  <dt>{label}</dt>
                  <dd data-unknown={value == null || undefined}>{value ?? "Non précisé"}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section className={styles.section} aria-labelledby="included-heading">
            <h2 id="included-heading" className={styles.sectionTitle}>
              Inclus et commodités
            </h2>
            <p className={styles.subtle}>
              <strong>Inclus dans le loyer : </strong>
              {listing.utilitiesIncluded.length ? listing.utilitiesIncluded.join(", ") : "non précisé"}
            </p>
            {listing.amenities.length > 0 ? (
              <ul className={styles.tags}>
                {listing.amenities.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            ) : (
              <p className={styles.subtle}>Aucune commodité précisée.</p>
            )}
          </section>

          <section className={styles.section} aria-labelledby="proximity-heading">
            <h2 id="proximity-heading" className={styles.sectionTitle}>
              À proximité
            </h2>
            {!proximity ? (
              <p className={styles.subtle}>La proximité n&apos;a pas encore été calculée pour cette annonce.</p>
            ) : (
              <>
                {stations.length > 0 ? (
                  <ul className={styles.stations}>
                    {stations.map((s) => (
                      <li key={s.name + s.network}>
                        <span className={styles.stationDot} data-line={s.network === "rem" ? "rem" : s.lines[0]} aria-hidden />
                        <span>
                          <strong>{s.name}</strong> ({stationLine(s)})
                        </span>
                        <span className={styles.walk}>{Math.round(s.walk_minutes)} min à pied</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className={styles.subtle}>Aucune station de métro ou de REM à distance de marche.</p>
                )}
                {essentials.length > 0 && (
                  <ul className={styles.essentials}>
                    {essentials.map(([category, summary]) => (
                      <li key={category}>
                        <span>{NEARBY_NAMES[category] ?? category}</span>
                        <span className={styles.walk}>
                          {summary.nearest
                            ? `${summary.nearest.name ?? "la plus proche"} · ${Math.round(summary.nearest.walk_minutes)} min`
                            : `${summary.count} à pied`}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </section>

          <section className={styles.section} aria-labelledby="history-heading">
            <h2 id="history-heading" className={styles.sectionTitle}>
              Historique du prix
            </h2>
            <PriceHistory history={listing.priceHistory} lastSeenAt={listing.lastSeenAt} />
          </section>

          {listing.description && (
            <section className={styles.section} aria-labelledby="description-heading">
              <h2 id="description-heading" className={styles.sectionTitle}>
                Description
              </h2>
              <Description text={listing.description} />
            </section>
          )}
        </div>

        <div className={styles.tracking}>
          <TrackingPanel listingId={listing.id} tracking={listing.tracking} />
        </div>

        <aside className={styles.aside}>
          {listing.priceBenchmark && (
            <section className={styles.card} aria-labelledby="benchmark-heading">
              <h2 id="benchmark-heading" className={styles.cardTitle}>
                Repère de prix
              </h2>
              <p className={styles.benchmark} data-direction={listing.priceBenchmark.deltaPercent < 0 ? "down" : "up"}>
                {benchmarkText(listing.priceBenchmark, size)}
              </p>
              <p className={styles.subtle}>
                Médiane {formatPrice(listing.priceBenchmark.median)}, sur {listing.priceBenchmark.sampleSize} annonces
                actives.
              </p>
            </section>
          )}

          <section className={styles.card} aria-labelledby="sources-heading">
            <h2 id="sources-heading" className={styles.cardTitle}>
              {sources.length > 1 ? `Publiée sur ${sources.length} sites` : "Source"}
            </h2>
            <ul className={styles.sources}>
              {sources.map((s) => (
                <li key={s.id}>
                  <a href={s.url} target="_blank" rel="noopener noreferrer">
                    {sourceName(s.source)}
                  </a>
                  {!s.active && <span className={styles.subtle}> (retirée)</span>}
                  <span className={styles.sourcePrice}>{formatPrice(s.price)}</span>
                </li>
              ))}
            </ul>
          </section>

          <section className={styles.card} aria-labelledby="freshness-heading">
            <h2 id="freshness-heading" className={styles.cardTitle}>
              Fraîcheur
            </h2>
            <dl className={styles.freshness}>
              {listing.publishedAt && (
                <div>
                  <dt>Publiée</dt>
                  <dd>{/^\d{4}-\d{2}-\d{2}/.test(listing.publishedAt) ? formatDate(listing.publishedAt) : listing.publishedAt}</dd>
                </div>
              )}
              <div>
                <dt>Trouvée par Griffon</dt>
                <dd>{ago(listing.firstSeenAt)}</dd>
              </div>
              <div>
                <dt>{listing.active ? "Revue en ligne" : "Vue en ligne pour la dernière fois"}</dt>
                <dd>{ago(listing.lastSeenAt)}</dd>
              </div>
            </dl>
          </section>
        </aside>
      </div>
    </div>
  );
}
