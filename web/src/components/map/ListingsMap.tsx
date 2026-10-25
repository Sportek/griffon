"use client";

import { useEffect, useRef, useState } from "react";
import { Map as MapLibreMap, NavigationControl, setWorkerUrl, type GeoJSONSource } from "maplibre-gl";
import { Button, IconButton } from "@vibe/core";
import { Location, Search } from "@vibe/icons";

import stationsData from "@/data/transit_stations.json";
import { isNew, shortPrice } from "@/lib/format";
import type { BoundingBox, MapPoint } from "@/lib/types";
import { addPinImages } from "./pins";
import styles from "./ListingsMap.module.css";

// Copied there by scripts/copy-maplibre-worker.mjs.
setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

const LIGHT_STYLE = "https://tiles.openfreemap.org/styles/positron";
const DARK_STYLE = "https://tiles.openfreemap.org/styles/dark";
const ISLAND_CENTER: [number, number] = [-73.62, 45.53];

const LINE_COLORS: Record<string, string> = {
  green: "#00a650",
  orange: "#f08123",
  yellow: "#ffd100",
  blue: "#0083ca",
};
const REM_COLOR = "#7ac143";

interface Station {
  name: string;
  network: "metro" | "rem";
  lines: string[];
  latitude: number;
  longitude: number;
}

function stationsGeoJson(): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: (stationsData as Station[]).map((s) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [s.longitude, s.latitude] },
      properties: {
        name: s.name,
        color: s.network === "rem" ? REM_COLOR : LINE_COLORS[s.lines[0]] ?? "#676879",
        interchange: s.lines.length > 1,
      },
    })),
  };
}

/**
 * One pin per building, like the list: the units of a building share an entrance, and
 * stacked pins at one point could not be told apart or clicked. The pin's key is the
 * building key, or the listing id for a listing alone.
 */
function pointsGeoJson(points: MapPoint[]): GeoJSON.FeatureCollection {
  const now = Date.now();
  const byKey = new Map<string, MapPoint[]>();
  for (const p of points) {
    const key = p.buildingKey ?? p.id;
    byKey.set(key, [...(byKey.get(key) ?? []), p]);
  }
  return {
    type: "FeatureCollection",
    features: [...byKey.entries()].map(([key, members]) => {
      const first = members[0];
      const prices = members.map((m) => m.price).filter((v): v is number => v != null);
      const fresh = members.some((m) => isNew(m.firstSeenAt, now));
      const building = members.length > 1;
      const cheapest = prices.length ? Math.min(...prices) : null;
      return {
        type: "Feature" as const,
        id: key,
        geometry: { type: "Point" as const, coordinates: [first.longitude, first.latitude] },
        properties: {
          id: key,
          label: building ? `${members.length} log. · ${shortPrice(cheapest)}+` : shortPrice(first.price),
          pin: fresh ? "pin-new" : building ? "pin-building" : "pin",
          approximate: members.every((m) => m.locationPrecision != null && m.locationPrecision !== "exact"),
        },
      };
    }),
  };
}

function isDark() {
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function boundsOf(map: MapLibreMap): BoundingBox {
  const b = map.getBounds();
  return { south: b.getSouth(), west: b.getWest(), north: b.getNorth(), east: b.getEast() };
}

function addLayers(map: MapLibreMap, dark: boolean) {
  addPinImages(map, {
    pin: { fill: dark ? "#30324e" : "#ffffff", stroke: dark ? "#797e93" : "#c3c6d4" },
    "pin-new": { fill: "#00854d", stroke: "#00854d" },
    "pin-building": { fill: dark ? "#30324e" : "#ffffff", stroke: "#0073ea" },
    "pin-active": { fill: "#0073ea", stroke: "#0073ea" },
  });

  map.addSource("stations", { type: "geojson", data: stationsGeoJson() });
  map.addLayer({
    id: "stations",
    type: "circle",
    source: "stations",
    minzoom: 10,
    paint: {
      "circle-color": ["get", "color"],
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 3, 14, 6],
      "circle-stroke-color": dark ? "#181b34" : "#ffffff",
      "circle-stroke-width": ["case", ["get", "interchange"], 3, 1.5],
    },
  });
  map.addLayer({
    id: "station-labels",
    type: "symbol",
    source: "stations",
    minzoom: 13,
    layout: {
      "text-field": ["get", "name"],
      "text-font": ["Noto Sans Regular"],
      "text-size": 11,
      "text-offset": [0, 1.1],
      "text-anchor": "top",
    },
    paint: {
      "text-color": dark ? "#d5d8df" : "#323338",
      "text-halo-color": dark ? "#181b34" : "#ffffff",
      "text-halo-width": 1.5,
    },
  });

  map.addSource("listings", {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
    cluster: true,
    clusterRadius: 44,
    clusterMaxZoom: 14,
    promoteId: "id",
  });
  map.addLayer({
    id: "approximate",
    type: "circle",
    source: "listings",
    filter: ["all", ["!", ["has", "point_count"]], ["get", "approximate"]],
    paint: {
      "circle-color": "#0073ea",
      "circle-opacity": 0.08,
      "circle-stroke-color": "#0073ea",
      "circle-stroke-opacity": 0.35,
      "circle-stroke-width": 1,
      "circle-radius": ["interpolate", ["exponential", 2], ["zoom"], 11, 6, 16, 120],
    },
  });
  map.addLayer({
    id: "clusters",
    type: "circle",
    source: "listings",
    filter: ["has", "point_count"],
    paint: {
      "circle-color": "#0073ea",
      "circle-opacity": 0.92,
      "circle-stroke-color": dark ? "#181b34" : "#ffffff",
      "circle-stroke-width": 2,
      "circle-radius": ["step", ["get", "point_count"], 16, 20, 20, 100, 26, 500, 32],
    },
  });
  map.addLayer({
    id: "cluster-count",
    type: "symbol",
    source: "listings",
    filter: ["has", "point_count"],
    layout: {
      "text-field": ["get", "point_count_abbreviated"],
      "text-font": ["Noto Sans Bold"],
      "text-size": 13,
      "text-allow-overlap": true,
    },
    paint: { "text-color": "#ffffff" },
  });
  map.addLayer({
    id: "pins",
    type: "symbol",
    source: "listings",
    filter: ["!", ["has", "point_count"]],
    layout: {
      "icon-image": ["get", "pin"],
      "icon-text-fit": "both",
      "icon-allow-overlap": true,
      "text-allow-overlap": true,
      "text-field": ["get", "label"],
      "text-font": ["Noto Sans Bold"],
      "text-size": 12,
      "symbol-sort-key": ["case", ["==", ["get", "pin"], "pin-new"], 1, 0],
    },
    paint: {
      "text-color": ["case", ["==", ["get", "pin"], "pin-new"], "#ffffff", dark ? "#eeeeee" : "#323338"],
    },
  });
  map.addLayer({
    id: "pins-active",
    type: "symbol",
    source: "listings",
    filter: ["==", ["get", "id"], ""],
    layout: {
      "icon-image": "pin-active",
      "icon-text-fit": "both",
      "icon-allow-overlap": true,
      "text-allow-overlap": true,
      "text-field": ["get", "label"],
      "text-font": ["Noto Sans Bold"],
      "text-size": 13,
    },
    paint: { "text-color": "#ffffff" },
  });
}

export function ListingsMap({
  points,
  activeId,
  onSelect,
  onSearchArea,
  loading,
  className,
}: {
  points: MapPoint[];
  activeId: string | null;
  onSelect: (id: string | null) => void;
  onSearchArea: (bounds: BoundingBox) => void;
  loading?: boolean;
  className?: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const pointsRef = useRef(points);
  const activeRef = useRef(activeId);
  const onSelectRef = useRef(onSelect);
  const [ready, setReady] = useState(false);
  const [moved, setMoved] = useState(false);
  const [showStations, setShowStations] = useState(true);

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    if (!container.current) return;
    let dark = isDark();
    const map = new MapLibreMap({
      container: container.current,
      style: dark ? DARK_STYLE : LIGHT_STYLE,
      center: ISLAND_CENTER,
      zoom: 10.6,
      minZoom: 8,
      maxZoom: 18,
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
    });
    map.touchZoomRotate.disableRotation();
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;

    map.on("style.load", () => {
      addLayers(map, dark);
      (map.getSource("listings") as GeoJSONSource).setData(pointsGeoJson(pointsRef.current));
      map.setFilter("pins-active", ["==", ["get", "id"], activeRef.current ?? ""]);
      setReady(true);
    });

    map.on("click", "pins", (event) => {
      const id = event.features?.[0]?.properties?.id as string | undefined;
      if (id) onSelectRef.current(id);
    });
    map.on("click", "clusters", async (event) => {
      const feature = event.features?.[0];
      if (!feature) return;
      const source = map.getSource("listings") as GeoJSONSource;
      const zoom = await source.getClusterExpansionZoom(feature.properties.cluster_id as number);
      map.easeTo({ center: (feature.geometry as GeoJSON.Point).coordinates as [number, number], zoom });
    });
    map.on("click", (event) => {
      const hits = map.queryRenderedFeatures(event.point, { layers: ["pins", "clusters", "pins-active"] });
      if (!hits.length) onSelectRef.current(null);
    });
    for (const layer of ["pins", "clusters"]) {
      map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
    }
    map.on("dragend", () => setMoved(true));
    map.on("zoomend", (event) => {
      if ((event as { originalEvent?: unknown }).originalEvent) setMoved(true);
    });

    // The map pane is hidden behind the list on a phone: resize when it is shown again.
    const resize = new ResizeObserver(() => map.resize());
    resize.observe(container.current);

    const scheme = window.matchMedia("(prefers-color-scheme: dark)");
    const onScheme = () => {
      dark = scheme.matches;
      setReady(false);
      map.setStyle(dark ? DARK_STYLE : LIGHT_STYLE);
    };
    scheme.addEventListener("change", onScheme);

    return () => {
      scheme.removeEventListener("change", onScheme);
      resize.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    pointsRef.current = points;
    const source = mapRef.current?.getSource("listings") as GeoJSONSource | undefined;
    if (ready && source) source.setData(pointsGeoJson(points));
  }, [points, ready]);

  useEffect(() => {
    activeRef.current = activeId;
    if (ready) mapRef.current?.setFilter("pins-active", ["==", ["get", "id"], activeId ?? ""]);
  }, [activeId, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    for (const layer of ["stations", "station-labels"]) {
      map.setLayoutProperty(layer, "visibility", showStations ? "visible" : "none");
    }
  }, [showStations, ready]);

  function locate() {
    navigator.geolocation?.getCurrentPosition(
      (position) =>
        mapRef.current?.flyTo({ center: [position.coords.longitude, position.coords.latitude], zoom: 14 }),
      () => undefined,
      { enableHighAccuracy: false, timeout: 8000 },
    );
  }

  return (
    <div className={[styles.wrapper, className].filter(Boolean).join(" ")}>
      <div ref={container} className={styles.map} role="region" aria-label="Carte des annonces" />
      {moved && (
        <div className={styles.searchArea}>
          <Button
            size="small"
            leftIcon={Search}
            loading={loading}
            onClick={() => {
              if (!mapRef.current) return;
              onSearchArea(boundsOf(mapRef.current));
              setMoved(false);
            }}
          >
            Rechercher dans cette zone
          </Button>
        </div>
      )}
      <div className={styles.tools}>
        <Button
          size="small"
          kind="secondary"
          active={showStations}
          aria-pressed={showStations}
          onClick={() => setShowStations((v) => !v)}
          className={styles.toolButton}
        >
          Métro et REM
        </Button>
        <IconButton
          icon={Location}
          size="small"
          kind="secondary"
          aria-label="Me localiser"
          tooltipContent="Me localiser"
          onClick={locate}
          className={styles.toolButton}
        />
      </div>
      <div className={styles.legend} aria-hidden>
        <span className={styles.legendItem}>
          <span className={styles.swatch} data-kind="new" /> Nouveau (48 h)
        </span>
        <span className={styles.legendItem}>
          <span className={styles.swatch} data-kind="building" /> Plusieurs logements
        </span>
        <span className={styles.legendItem}>
          <span className={styles.swatch} data-kind="approx" /> Position approximative
        </span>
      </div>
    </div>
  );
}
