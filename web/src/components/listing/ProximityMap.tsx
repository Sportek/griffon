"use client";

import { useEffect, useRef, useState } from "react";
import { LngLatBounds, Map as MapLibreMap, NavigationControl, setWorkerUrl, type GeoJSONSource } from "maplibre-gl";

import type { NearbyPlace, NearbyStation } from "@/lib/types";
import styles from "./ProximityMap.module.css";

setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

const LIGHT_STYLE = "https://tiles.openfreemap.org/styles/positron";
const DARK_STYLE = "https://tiles.openfreemap.org/styles/dark";
const LINE_COLORS: Record<string, string> = { green: "#00a650", orange: "#f08123", yellow: "#ffd100", blue: "#0083ca" };

function collection(features: GeoJSON.Feature[]): GeoJSON.FeatureCollection {
  return { type: "FeatureCollection", features };
}

function placesData(places: NearbyPlace[]) {
  return collection(
    places.map((p, i) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [p.longitude, p.latitude] },
      properties: { n: String(i + 1), index: i },
    })),
  );
}

function stationsData(stations: NearbyStation[]) {
  return collection(
    stations.map((s) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [s.longitude, s.latitude] },
      properties: { name: s.name, color: s.network === "rem" ? "#7ac143" : LINE_COLORS[s.lines[0]] ?? "#676879" },
    })),
  );
}

/**
 * The listing and the places of one category, numbered like the list beside it, with the
 * metro and REM stations within walking distance.
 */
export function ProximityMap({
  latitude,
  longitude,
  places,
  stations,
  activeIndex,
  onHover,
}: {
  latitude: number;
  longitude: number;
  places: NearbyPlace[];
  stations: NearbyStation[];
  activeIndex: number | null;
  onHover: (index: number | null) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const latest = useRef({ places, stations, onHover });
  const [ready, setReady] = useState(false);

  useEffect(() => {
    latest.current = { places, stations, onHover };
  }, [places, stations, onHover]);

  useEffect(() => {
    if (!container.current) return;
    const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const map = new MapLibreMap({
      container: container.current,
      style: dark ? DARK_STYLE : LIGHT_STYLE,
      center: [longitude, latitude],
      zoom: 14.5,
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      cooperativeGestures: true,
    });
    map.touchZoomRotate.disableRotation();
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;
    const resize = new ResizeObserver(() => map.resize());
    resize.observe(container.current);

    map.on("load", () => {
      const surface = dark ? "#181b34" : "#ffffff";
      map.addSource("stations", { type: "geojson", data: stationsData(latest.current.stations) });
      map.addLayer({
        id: "stations",
        type: "circle",
        source: "stations",
        paint: {
          "circle-color": ["get", "color"],
          "circle-radius": 7,
          "circle-stroke-color": surface,
          "circle-stroke-width": 2,
        },
      });
      map.addLayer({
        id: "station-labels",
        type: "symbol",
        source: "stations",
        layout: {
          "text-field": ["get", "name"],
          "text-font": ["Noto Sans Regular"],
          "text-size": 11,
          "text-offset": [0, 1.2],
          "text-anchor": "top",
        },
        paint: { "text-color": dark ? "#d5d8df" : "#323338", "text-halo-color": surface, "text-halo-width": 1.5 },
      });

      map.addSource("places", { type: "geojson", data: placesData(latest.current.places), promoteId: "index" });
      map.addLayer({
        id: "places",
        type: "circle",
        source: "places",
        paint: {
          "circle-color": ["case", ["boolean", ["feature-state", "active"], false], "#0073ea", dark ? "#30324e" : "#ffffff"],
          "circle-radius": ["case", ["boolean", ["feature-state", "active"], false], 12, 10],
          "circle-stroke-color": "#0073ea",
          "circle-stroke-width": 2,
        },
      });
      map.addLayer({
        id: "place-numbers",
        type: "symbol",
        source: "places",
        layout: {
          "text-field": ["get", "n"],
          "text-font": ["Noto Sans Bold"],
          "text-size": 11,
          "text-allow-overlap": true,
          "icon-allow-overlap": true,
        },
        paint: {
          "text-color": ["case", ["boolean", ["feature-state", "active"], false], "#ffffff", dark ? "#eeeeee" : "#0073ea"],
        },
      });

      map.addSource("home", {
        type: "geojson",
        data: collection([{ type: "Feature", geometry: { type: "Point", coordinates: [longitude, latitude] }, properties: {} }]),
      });
      // Ink rather than blue: the blue line's stations are blue dots too.
      map.addLayer({
        id: "home",
        type: "circle",
        source: "home",
        paint: {
          "circle-color": dark ? "#ffffff" : "#1f2029",
          "circle-radius": 9,
          "circle-stroke-color": dark ? "#1f2029" : "#ffffff",
          "circle-stroke-width": 3,
        },
      });
      map.addLayer({
        id: "home-label",
        type: "symbol",
        source: "home",
        layout: {
          "text-field": "L'annonce",
          "text-font": ["Noto Sans Bold"],
          "text-size": 12,
          "text-offset": [0, -1.4],
          "text-anchor": "bottom",
          "text-allow-overlap": true,
        },
        paint: { "text-color": dark ? "#ffffff" : "#1f2029", "text-halo-color": surface, "text-halo-width": 2 },
      });

      map.on("mousemove", "places", (event) => {
        map.getCanvas().style.cursor = "pointer";
        const index = event.features?.[0]?.properties?.index;
        latest.current.onHover(typeof index === "number" ? index : null);
      });
      map.on("mouseleave", "places", () => {
        map.getCanvas().style.cursor = "";
        latest.current.onHover(null);
      });
      setReady(true);
    });

    return () => {
      resize.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, [latitude, longitude]);

  // New category: new markers, and a frame that takes them all in.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    (map.getSource("places") as GeoJSONSource).setData(placesData(places));
    (map.getSource("stations") as GeoJSONSource).setData(stationsData(stations));
    const bounds = new LngLatBounds([longitude, latitude], [longitude, latitude]);
    for (const p of places) bounds.extend([p.longitude, p.latitude]);
    map.fitBounds(bounds, { padding: 40, maxZoom: 16, duration: 400 });
  }, [places, stations, ready, latitude, longitude]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.removeFeatureState({ source: "places" });
    if (activeIndex != null) map.setFeatureState({ source: "places", id: activeIndex }, { active: true });
  }, [activeIndex, ready]);

  return <div ref={container} className={styles.map} role="region" aria-label="Carte des lieux à proximité" />;
}
