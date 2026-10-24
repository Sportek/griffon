import type { Map as MapLibreMap } from "maplibre-gl";

/**
 * Price pins are drawn by MapLibre itself (a symbol layer over a stretchable image), not
 * as DOM markers: thousands of them stay smooth when panning on a phone.
 */
const RATIO = 2;
const WIDTH = 40 * RATIO;
const HEIGHT = 24 * RATIO;
const RADIUS = HEIGHT / 2;

export interface PinStyle {
  fill: string;
  stroke: string;
}

function pinImage(style: PinStyle): ImageData {
  const canvas = document.createElement("canvas");
  canvas.width = WIDTH;
  canvas.height = HEIGHT;
  const ctx = canvas.getContext("2d") as CanvasRenderingContext2D;
  const inset = RATIO;
  ctx.beginPath();
  ctx.roundRect(inset, inset, WIDTH - inset * 2, HEIGHT - inset * 2, RADIUS - inset);
  ctx.fillStyle = style.fill;
  ctx.fill();
  ctx.lineWidth = RATIO;
  ctx.strokeStyle = style.stroke;
  ctx.stroke();
  return ctx.getImageData(0, 0, WIDTH, HEIGHT);
}

export function addPinImages(map: MapLibreMap, styles: Record<string, PinStyle>) {
  for (const [name, style] of Object.entries(styles)) {
    if (map.hasImage(name)) map.removeImage(name);
    map.addImage(name, pinImage(style), {
      pixelRatio: RATIO,
      stretchX: [[RADIUS, WIDTH - RADIUS]],
      stretchY: [[RADIUS - 2, RADIUS + 2]],
      content: [RADIUS - 6 * RATIO, 3 * RATIO, WIDTH - RADIUS + 6 * RATIO, HEIGHT - 3 * RATIO],
    });
  }
}
