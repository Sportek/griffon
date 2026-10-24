// MapLibre starts its worker from a URL next to its own module, which the bundler does
// not emit. Serve the worker, a standalone file, from public/.
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

const dist = dirname(createRequire(import.meta.url).resolve("maplibre-gl/dist/maplibre-gl.mjs"));
const out = new URL("../public/maplibre/", import.meta.url);
mkdirSync(out, { recursive: true });
for (const file of ["maplibre-gl-worker.mjs"]) {
  copyFileSync(join(dist, file), new URL(file, out));
}
console.log("maplibre worker copied to public/maplibre/");
