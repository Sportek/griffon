/**
 * A card's photo at the size it is shown (128 px square, twice that on a dense screen), from
 * the source sites that serve smaller versions. The full photo weighs 200 to 300 KB; the
 * thumbnail a tenth of that. Other URLs are left as they are.
 */
export function thumbnail(url: string): string {
  try {
    const parsed = new URL(url);
    // Centris resizes on request, to a few set sizes only (400x300 answers empty):
    // media.ashx?id=...&t=pi&w=1260&h=1024&sm=c
    if (parsed.hostname === "mspublic.centris.ca" && parsed.searchParams.has("w")) {
      parsed.searchParams.set("w", "480");
      parsed.searchParams.set("h", "360");
      return parsed.toString();
    }
    // rentals.ca keeps several sizes side by side: /property-pictures/{large,medium,small}/...
    if (parsed.hostname === "images.rentals.ca") {
      parsed.pathname = parsed.pathname.replace(/^\/property-pictures\/(?:large|medium)\//, "/property-pictures/small/");
      return parsed.toString();
    }
  } catch {
    // Not a URL: shown as given.
  }
  return url;
}
