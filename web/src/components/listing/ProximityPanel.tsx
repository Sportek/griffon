"use client";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";

import {
  categories,
  categoryLabel,
  formatDistance,
  formatWalk,
  kindLabel,
  kindsOf,
  placeName,
} from "@/lib/proximity";
import type { NearbyStation, Proximity } from "@/lib/types";
import styles from "./ProximityPanel.module.css";

const ProximityMap = dynamic(() => import("./ProximityMap").then((m) => m.ProximityMap), {
  ssr: false,
  loading: () => <div className={styles.mapLoading} />,
});

const TRANSIT = "transit";
const LINE_NAMES: Record<string, string> = { green: "verte", orange: "orange", yellow: "jaune", blue: "bleue" };

function stationLine(station: NearbyStation) {
  if (station.network === "rem") return "REM";
  const lines = station.lines.map((l) => LINE_NAMES[l] ?? l);
  return lines.length ? `Ligne ${lines.join(", ")}` : "Métro";
}

/** Every station in reach, nearest first, the nearest metro and REM kept even beyond the walk limit. */
function stationsOf(proximity: Proximity): NearbyStation[] {
  const all = [...(proximity.stations_within_walk ?? [])];
  for (const s of [proximity.nearest_metro, proximity.nearest_rem]) {
    if (s && !all.some((a) => a.name === s.name && a.network === s.network)) all.push(s);
  }
  return all.sort((a, b) => a.walk_minutes - b.walk_minutes);
}

export function ProximityPanel({
  proximity,
  latitude,
  longitude,
}: {
  proximity: Proximity;
  latitude: number | null;
  longitude: number | null;
}) {
  const entries = useMemo(() => categories(proximity), [proximity]);
  const stations = useMemo(() => stationsOf(proximity), [proximity]);
  const [selected, setSelected] = useState<string>(stations.length ? TRANSIT : (entries[0]?.key ?? TRANSIT));
  const [kind, setKind] = useState<string | null>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const limit = proximity.max_walk_minutes ?? 15;

  const entry = entries.find((e) => e.key === selected);
  const kinds = entry ? kindsOf(entry.places) : [];
  const places = entry ? entry.places.filter((p) => !kind || p.kind === kind) : [];

  function choose(key: string) {
    setSelected(key);
    setKind(null);
    setHovered(null);
  }

  const tabs = [
    ...(stations.length ? [{ key: TRANSIT, label: "Métro et REM", count: stations.length }] : []),
    ...entries.map((e) => ({ key: e.key, label: categoryLabel(e.key, 2), count: e.summary.count })),
  ];

  return (
    <div className={styles.panel}>
      <div className={styles.tabs} role="tablist" aria-label="Catégories de lieux">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={tab.key === selected}
            className={styles.tab}
            onClick={() => choose(tab.key)}
          >
            {tab.label}
            <span className={styles.tabCount}>{tab.count}</span>
          </button>
        ))}
      </div>

      <div className={styles.body} role="tabpanel">
        <div className={styles.listColumn}>
          {selected === TRANSIT ? (
            <>
              <p className={styles.summary}>
                {stations.filter((s) => s.walk_minutes <= limit).length} station
                {stations.filter((s) => s.walk_minutes <= limit).length > 1 ? "s" : ""} à moins de {limit} min à pied
              </p>
              <ol className={styles.list}>
                {stations.map((s) => (
                  <li key={`${s.network}-${s.name}`} className={styles.row}>
                    <span
                      className={styles.lineDot}
                      data-line={s.network === "rem" ? "rem" : s.lines[0]}
                      aria-hidden
                    />
                    <span className={styles.name}>
                      <strong>{s.name}</strong>
                      <span className={styles.kind}>{stationLine(s)}</span>
                    </span>
                    <span className={styles.walk}>
                      <strong>{formatWalk(s.walk_minutes)}</strong>
                      <span>{formatDistance(s.walk_distance_m)}</span>
                    </span>
                  </li>
                ))}
              </ol>
            </>
          ) : entry ? (
            <>
              <p className={styles.summary}>
                {entry.summary.count} {categoryLabel(entry.key, entry.summary.count).toLowerCase()} à moins de {limit} min
                à pied
                {entry.summary.count > entry.places.length && ` · les ${entry.places.length} plus proches`}
              </p>
              {kinds.length > 1 && (
                <div className={styles.kinds} role="group" aria-label="Type de lieu">
                  <button
                    type="button"
                    className={styles.kindChip}
                    aria-pressed={kind === null}
                    onClick={() => setKind(null)}
                  >
                    Tous
                  </button>
                  {kinds.map((k) => (
                    <button
                      key={k.kind}
                      type="button"
                      className={styles.kindChip}
                      aria-pressed={kind === k.kind}
                      onClick={() => setKind(kind === k.kind ? null : k.kind)}
                    >
                      {kindLabel(k.kind)} ({k.count})
                    </button>
                  ))}
                </div>
              )}
              <ol className={styles.list}>
                {places.map((p) => {
                  const index = entry.places.indexOf(p);
                  const brand = p.brand && !placeName(p).toLowerCase().includes(p.brand.toLowerCase()) ? p.brand : null;
                  return (
                    <li
                      key={`${p.name}-${p.latitude}-${p.longitude}`}
                      className={styles.row}
                      data-active={hovered === index || undefined}
                      onMouseEnter={() => setHovered(index)}
                      onMouseLeave={() => setHovered(null)}
                    >
                      <span className={styles.number}>{index + 1}</span>
                      <span className={styles.name}>
                        <strong>{placeName(p)}</strong>
                        <span className={styles.kind}>{[kindLabel(p.kind), brand].filter(Boolean).join(" · ")}</span>
                      </span>
                      <span className={styles.walk}>
                        <strong>{formatWalk(p.walk_minutes)}</strong>
                        <span>{formatDistance(p.walk_distance_m)}</span>
                      </span>
                    </li>
                  );
                })}
              </ol>
            </>
          ) : null}
        </div>

        {latitude != null && longitude != null && (
          <div className={styles.mapColumn}>
            <ProximityMap
              latitude={latitude}
              longitude={longitude}
              places={selected === TRANSIT ? [] : places}
              stations={stations}
              activeIndex={hovered}
              onHover={setHovered}
            />
          </div>
        )}
      </div>
      <p className={styles.note}>
        Temps de marche estimés depuis la position de l&apos;annonce, à partir des lieux d&apos;OpenStreetMap.
      </p>
    </div>
  );
}
