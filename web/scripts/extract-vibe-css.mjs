// Vibe injects its component styles from JavaScript, in the browser only, so a server
// render arrives unstyled until hydration. On the server it collects them into
// globalThis.injectedStyles instead: load the library once here and write that out as a
// static stylesheet the layout imports.
//
// Vibe also switches theme through a class (.dark-app-theme). Setting it from a script
// before paint fights React's hydration, so the dark variables are repeated under a
// prefers-color-scheme query: the page follows the system theme with no script and no flash.
import { writeFileSync } from "node:fs";

globalThis.injectedStyles = {};
await import("@vibe/core");
await import("@vibe/core/next");

let css = Object.values(globalThis.injectedStyles).join("\n");
const dark = css.match(/\.dark-app-theme\{([^}]*)\}/);
if (!dark) throw new Error("Vibe's .dark-app-theme block was not found: the theme extraction needs updating");
css += `\n@media (prefers-color-scheme: dark){:root:not(.light-app-theme){${dark[1]}}}\n`;

writeFileSync(new URL("../src/app/vibe.generated.css", import.meta.url), css);
console.log(`vibe.generated.css: ${Object.keys(globalThis.injectedStyles).length} style blocks, ${(css.length / 1024).toFixed(0)} KiB`);
