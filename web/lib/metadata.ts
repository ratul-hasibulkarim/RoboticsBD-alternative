import type { Metadata } from "next";

import type { TComponent } from "./api";
import { componentDescription } from "./seo";

export function componentMetadata(c: TComponent, sub: "" | "/prices" | "/datasheet" | "/use-cases" | "/alternatives"): Metadata {
  const label: Record<typeof sub, string> = {
    "": `${c.mpn}${c.manufacturer ? ` ${c.manufacturer}` : ""} — price, datasheet & pinout`,
    "/prices": `${c.mpn} price comparison (${c.offer_count} offers)`,
    "/datasheet": `${c.mpn} datasheet PDF`,
    "/use-cases": `${c.mpn} tutorials, wiring & example code`,
    "/alternatives": `${c.mpn} alternatives & equivalents`,
  };
  const path = `/component/${c.slug}${sub}`;
  return {
    title: label[sub],
    description: componentDescription(c),
    // Every page canonicalises to itself; no two pages share a canonical (W6).
    alternates: { canonical: path },
    openGraph: { title: label[sub], url: path, type: "website", images: c.images[0] ? [{ url: c.images[0].url }] : [] },
  };
}
