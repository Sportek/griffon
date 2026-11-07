// Vibe injects its component styles from JavaScript, in the browser only, so a server
// render arrives unstyled until hydration. On the server it collects them into
// globalThis.injectedStyles instead: load the components the app uses here and write
// their styles out as a static stylesheet the layout imports.
//
// Only the components imported from @vibe/core in src/ are loaded (with what they import
// in turn), not the whole library: the stylesheet blocks the first paint, and most of
// Vibe's 160-odd components are never shown. A component missed here still works, Vibe's
// own injection styles it once its JavaScript runs.
//
// Vibe also switches theme through a class (.dark-app-theme). Setting it from a script
// before paint fights React's hydration, so the dark variables are repeated under a
// prefers-color-scheme query: the page follows the system theme with no script and no flash.
import { readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const src = fileURLToPath(new URL("../src/", import.meta.url));

function sources(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.(tsx?|jsx?)$/.test(name) ? [path] : [];
  });
}

/** The names imported from "@vibe/core", across the app's sources. */
const used = new Set();
for (const file of sources(src)) {
  for (const [, names] of readFileSync(file, "utf8").matchAll(/import\s*(?:type\s*)?\{([^}]*)\}\s*from\s*["']@vibe\/core["']/g)) {
    for (const name of names.split(",")) {
      const clean = name.trim().replace(/^type\s+/, "").split(/\s+as\s+/)[0];
      if (clean && !/^type\s/.test(name.trim())) used.add(clean);
    }
  }
}

// @vibe/core's entry point is a list of re-exports: find the module behind each name.
const entry = createRequire(import.meta.url).resolve("@vibe/core");
const index = readFileSync(entry, "utf8");
const modules = new Map();
for (const [, names, from] of index.matchAll(/export\{([^}]*)\}from"([^"]+)"/g)) {
  for (const binding of names.split(",")) {
    const exported = binding.split(/\s+as\s+/).pop().trim();
    if (used.has(exported)) modules.set(exported, from);
  }
}
const missing = [...used].filter((name) => !modules.has(name));
if (missing.length) throw new Error(`Not found in @vibe/core's entry point: ${missing.join(", ")}`);

globalThis.injectedStyles = {};
// The entry point's own first import: the tokens, theme variables and base styles.
for (const [, side] of index.matchAll(/import"([^"]+)";/g)) {
  await import(pathToFileURL(join(dirname(entry), side)).href);
}
for (const from of new Set(modules.values())) {
  await import(pathToFileURL(join(dirname(entry), from)).href);
}

let css = Object.values(globalThis.injectedStyles).join("\n");
const dark = css.match(/\.dark-app-theme\{([^}]*)\}/);
if (!dark) throw new Error("Vibe's .dark-app-theme block was not found: the theme extraction needs updating");
css += `\n@media (prefers-color-scheme: dark){:root:not(.light-app-theme){${dark[1]}}}\n`;

writeFileSync(new URL("../src/app/vibe.generated.css", import.meta.url), css);
console.log(
  `vibe.generated.css: ${used.size} components, ${Object.keys(globalThis.injectedStyles).length} style blocks, ${(css.length / 1024).toFixed(0)} KiB`,
);
