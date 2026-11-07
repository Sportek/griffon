import { gzipSync } from "node:zlib";

import { ApiError, mapListings } from "@/lib/api";
import { parseSearch, toFilter } from "@/lib/search-params";

export const dynamic = "force-dynamic";

/**
 * The map's pins for a search, with the page's query string. Fetched by the map once the
 * list is on screen: thousands of points weigh megabytes, and inlined in the page they
 * held back its first paint.
 */
export async function GET(request: Request) {
  const params: Record<string, string> = {};
  new URL(request.url).searchParams.forEach((value, key) => (params[key] = value));
  let body: string;
  try {
    body = JSON.stringify(await mapListings(toFilter(parseSearch(params)), 10_000));
  } catch (e) {
    const message = e instanceof ApiError ? e.message : "Une erreur inattendue est survenue.";
    return Response.json({ error: message }, { status: 502 });
  }
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "Cache-Control": "private, max-age=60",
    Vary: "Accept-Encoding",
  };
  // Next compresses its pages but not a route's response: 10 000 points are 2 MB of JSON,
  // a tenth of that gzipped.
  if (/\bgzip\b/.test(request.headers.get("accept-encoding") ?? "")) {
    return new Response(gzipSync(body), { headers: { ...headers, "Content-Encoding": "gzip" } });
  }
  return new Response(body, { headers });
}
