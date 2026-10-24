import "server-only";

import { countListings } from "./api";
import { formatPrice } from "./format";
import { toFilter, toQueryString, type SearchState } from "./search-params";

export interface Suggestion {
  /** "0 résultat à moins de 1 500 $ · 14 à moins de 1 750 $" */
  message: string;
  action: string;
  href: string;
  count: number;
}

interface Relaxation {
  applies: (s: SearchState) => boolean;
  relax: (s: SearchState) => SearchState;
  describe: (s: SearchState, relaxed: SearchState, count: number) => { message: string; action: string };
}

const ADVANCED: (keyof SearchState)[] = [
  "q",
  "prixMin",
  "tailleMax",
  "chambres",
  "sdb",
  "superficie",
  "types",
  "villes",
  "services",
  "commodites",
  "animaux",
  "meuble",
  "stationnement",
  "commerces",
  "sources",
  "photos",
];

const roundUp50 = (n: number) => Math.ceil(n / 50) * 50;

const RELAXATIONS: Relaxation[] = [
  {
    applies: (s) => s.prixMax != null,
    relax: (s) => ({ ...s, prixMax: roundUp50((s.prixMax as number) * 1.15) }),
    describe: (s, r, count) => ({
      message: `0 résultat à moins de ${formatPrice(s.prixMax)}, ${count} à moins de ${formatPrice(r.prixMax)}`,
      action: `Monter le budget à ${formatPrice(r.prixMax)}`,
    }),
  },
  {
    applies: (s) => s.metro != null,
    relax: (s) => ({ ...s, metro: undefined }),
    describe: (s, _r, count) => ({
      message: `0 résultat à ${s.metro} min du métro, ${count} sans ce critère`,
      action: "Retirer le critère métro",
    }),
  },
  {
    applies: (s) => s.tailleMin != null && s.tailleMin > 1,
    relax: (s) => ({ ...s, tailleMin: (s.tailleMin as number) - 1 }),
    describe: (s, r, count) => ({
      message: `0 résultat en ${s.tailleMin} ½ et plus, ${count} en ${r.tailleMin} ½ et plus`,
      action: `Accepter les ${r.tailleMin} ½`,
    }),
  },
  {
    applies: (s) => !!s.quartiers?.length,
    relax: (s) => ({ ...s, quartiers: undefined }),
    describe: (_s, _r, count) => ({
      message: `0 résultat dans ces quartiers, ${count} ailleurs`,
      action: "Chercher dans tous les quartiers",
    }),
  },
  {
    applies: (s) => s.depuis != null,
    relax: (s) => ({ ...s, depuis: undefined }),
    describe: (_s, _r, count) => ({
      message: `0 nouvelle annonce sur cette période, ${count} au total`,
      action: "Voir toutes les dates",
    }),
  },
  {
    applies: (s) => ADVANCED.some((key) => s[key] !== undefined),
    relax: (s) => ({ ...s, ...Object.fromEntries(ADVANCED.map((key) => [key, undefined])) }),
    describe: (_s, _r, count) => ({
      message: `0 résultat avec les filtres avancés, ${count} sans eux`,
      action: "Retirer les filtres avancés",
    }),
  },
  {
    applies: (s) => s.zone != null,
    relax: (s) => ({ ...s, zone: undefined }),
    describe: (_s, _r, count) => ({
      message: `0 résultat dans cette zone de la carte, ${count} ailleurs`,
      action: "Chercher partout",
    }),
  },
];

/** For an empty result: the single relaxed criterion that brings back the most listings. */
export async function suggestRelaxation(state: SearchState): Promise<Suggestion | null> {
  const candidates = RELAXATIONS.filter((r) => r.applies(state));
  const counts = await Promise.all(
    candidates.map(async (r) => {
      const relaxed = r.relax(state);
      return { r, relaxed, count: await countListings(toFilter(relaxed)).catch(() => 0) };
    }),
  );
  const best = counts.filter((c) => c.count > 0).sort((a, b) => b.count - a.count)[0];
  if (!best) return null;
  const { message, action } = best.r.describe(state, best.relaxed, best.count);
  return { message, action, href: `/${toQueryString(best.relaxed)}`, count: best.count };
}
